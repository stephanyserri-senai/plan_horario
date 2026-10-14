"""Worker do otimizador (serviço separado da Vercel).

Processa a fila armazenada no PostgreSQL/Supabase:
- execucoes_otimizacao com status 'pendente' (gerador de horários);
- simulacoes_capacidade 'pendente' do tipo 'completa' (simulador).

Garantias:
- cada job é reservado com SELECT ... FOR UPDATE SKIP LOCKED (vários workers
  podem rodar em paralelo sem processar o mesmo job);
- heartbeat periódico; jobs cujo worker parou de responder são marcados como
  falha (nenhuma aula parcial é gravada — a aplicação é transacional);
- SIGTERM/SIGINT: termina o job atual e encerra.

Uso:
    python -m app.worker            # loop contínuo
    python -m app.worker --uma-vez  # processa o que houver e sai (cron/testes)
"""
from __future__ import annotations

import argparse
import logging
import os
import signal
import socket
import threading
import time
from datetime import datetime

from app.core.config import get_settings
from app.core.db import SessionLocal
from app.models import Configuracao, SimulacaoCapacidade
from app.services import otimizacao, simulador

log = logging.getLogger("worker")
_parar = threading.Event()


def _sinal(signum, _frame):
    log.info("Sinal %s recebido: encerrando após o job atual.", signum)
    _parar.set()


class Heartbeat:
    def __init__(self, fn, intervalo: float = 30.0):
        self.fn, self.intervalo, self._fim = fn, intervalo, threading.Event()
        self._t = threading.Thread(target=self._loop, daemon=True)

    def _loop(self):
        while not self._fim.wait(self.intervalo):
            try:
                self.fn()
            except Exception:
                log.exception("Falha ao registrar heartbeat")

    def __enter__(self):
        self._t.start()
        return self

    def __exit__(self, *a):
        self._fim.set()


def _status(worker: str, estado: str, job: str | None = None):
    with SessionLocal() as db:
        db.merge(Configuracao(chave="worker_status", descricao="Último sinal do worker do otimizador (atualizado automaticamente).",
                              valor={"worker": worker, "estado": estado, "job": job, "em": datetime.now().isoformat(timespec="seconds")}))
        db.commit()


def _heartbeat_simulacao(sim_id: int):
    with SessionLocal() as db:
        s = db.get(SimulacaoCapacidade, sim_id)
        if s and s.status == "executando":
            s.heartbeat_em = datetime.now()
            db.commit()


def _recuperar_simulacoes(db) -> int:
    from datetime import timedelta

    from sqlalchemy import func, select
    limite = datetime.now() - timedelta(seconds=get_settings().worker_heartbeat_expira_s)
    sims = db.scalars(select(SimulacaoCapacidade).where(SimulacaoCapacidade.status == "executando",
                                                        func.coalesce(SimulacaoCapacidade.heartbeat_em, SimulacaoCapacidade.iniciado_em) < limite)
                      .with_for_update(skip_locked=True)).all()
    for s in sims:
        s.status, s.finalizado_em = "falha", datetime.now()
        s.resultado = {"erro": "Simulação interrompida (o worker parou de responder). Solicite novamente."}
    db.commit()
    return len(sims)


def processar_um(worker: str) -> bool:
    """Processa no máximo um job. Retorna True se havia trabalho."""
    with SessionLocal() as db:
        n = otimizacao.recuperar_execucoes_interrompidas(db, somente_expiradas=True) + _recuperar_simulacoes(db)
        if n:
            log.warning("%s job(s) órfão(s) marcado(s) como falha.", n)
        eid = otimizacao.reivindicar_execucao(db, worker)
    if eid is not None:
        log.info("Execução de otimização #%s iniciada", eid)
        _status(worker, "executando", f"execucao:{eid}")
        t0 = time.time()
        with Heartbeat(lambda: otimizacao.heartbeat_execucao(eid)):
            otimizacao.executar(eid)
        log.info("Execução #%s finalizada em %.1fs", eid, time.time() - t0)
        return True
    with SessionLocal() as db:
        sid = simulador.reivindicar_simulacao(db, worker)
    if sid is not None:
        log.info("Simulação #%s iniciada", sid)
        _status(worker, "executando", f"simulacao:{sid}")
        with Heartbeat(lambda: _heartbeat_simulacao(sid)), SessionLocal() as db:
            try:
                simulador.processar_simulacao(db, sid)
            except Exception:
                log.exception("Simulação #%s falhou", sid)
        return True
    return False


def main(argv=None):
    p = argparse.ArgumentParser(description="Worker do otimizador de horários")
    p.add_argument("--uma-vez", action="store_true", help="processa os jobs disponíveis e encerra")
    args = p.parse_args(argv)
    s = get_settings()
    logging.basicConfig(level=s.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    try:
        import ortools  # noqa: F401
    except ImportError:
        raise SystemExit("OR-Tools não instalado: instale backend/requirements.txt (não o requirements da Vercel).")
    worker = f"{socket.gethostname()}:{os.getpid()}"
    signal.signal(signal.SIGTERM, _sinal)
    signal.signal(signal.SIGINT, _sinal)
    log.info("Worker %s iniciado (intervalo %.1fs)", worker, s.worker_intervalo_s)
    while not _parar.is_set():
        try:
            trabalhou = processar_um(worker)
        except Exception:
            log.exception("Erro no ciclo do worker")
            trabalhou = False
        if args.uma_vez and not trabalhou:
            break
        if not trabalhou:
            try:
                _status(worker, "ocioso")
            except Exception:
                log.exception("Falha ao registrar status do worker")
            _parar.wait(s.worker_intervalo_s)
    try:
        _status(worker, "encerrado")
    except Exception:
        log.exception("Falha ao registrar status do worker")
    log.info("Worker %s encerrado", worker)


if __name__ == "__main__":
    main()
