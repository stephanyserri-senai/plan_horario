"""Aciona o worker do otimizador assim que um job entra na fila.

Na Vercel não há processo persistente: o solver roda no workflow do GitHub
Actions "Worker do otimizador". Sem acionamento, o job esperaria o próximo
agendamento (~15 min). Com PLAN_GITHUB_TOKEN configurado (somente no servidor),
a API dispara o workflow imediatamente (workflow_dispatch), e o planejador não
precisa abrir o GitHub para nada.

Falhas aqui nunca derrubam a requisição: o job continua na fila e o
agendamento periódico o processa.
"""
import json
import logging
import os
import time
import urllib.error
import urllib.request

from app.core.config import get_settings

log = logging.getLogger("acionador")
_ultimo: dict[str, float] = {"t": 0.0}
_INTERVALO_MIN_S = 20  # evita disparos em rajada (o workflow já processa toda a fila)


def configurado() -> bool:
    s = get_settings()
    return bool(s.github_token and repositorio())


def repositorio() -> str:
    s = get_settings()
    if s.github_repo:
        return s.github_repo
    dono, nome = os.environ.get("VERCEL_GIT_REPO_OWNER"), os.environ.get("VERCEL_GIT_REPO_SLUG")
    return f"{dono}/{nome}" if dono and nome else ""


def referencia() -> str:
    s = get_settings()
    return s.github_ref or os.environ.get("VERCEL_GIT_COMMIT_REF") or "main"


def acionar_worker(forcar: bool = False) -> str:
    """Retorna 'acionado', 'recente' (disparado há poucos segundos),
    'nao_configurado' ou 'falhou'."""
    s = get_settings()
    if s.modo_executor != "fila":
        return "nao_aplicavel"
    if not configurado():
        return "nao_configurado"
    agora = time.monotonic()
    if not forcar and agora - _ultimo["t"] < _INTERVALO_MIN_S:
        return "recente"
    url = f"https://api.github.com/repos/{repositorio()}/actions/workflows/{s.github_workflow}/dispatches"
    req = urllib.request.Request(url, data=json.dumps({"ref": referencia()}).encode(), method="POST", headers={
        "Authorization": f"Bearer {s.github_token}", "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "plan-horario"})
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            ok = r.status in (200, 204)
    except urllib.error.HTTPError as e:
        log.error("Falha ao acionar o worker no GitHub (HTTP %s). Verifique PLAN_GITHUB_TOKEN (permissão Actions: Read and write) "
                  "e o repositório %s.", e.code, repositorio())
        return "falhou"
    except Exception as e:  # rede, timeout
        log.error("Falha ao acionar o worker no GitHub: %s", type(e).__name__)
        return "falhou"
    if ok:
        _ultimo["t"] = agora
        log.info("Worker do otimizador acionado (%s@%s)", repositorio(), referencia())
        return "acionado"
    return "falhou"
