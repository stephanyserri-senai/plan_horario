"""Integração banco ↔ solver: montagem da entrada, execução assíncrona,
aplicação do resultado (expansão em aulas datadas + validação central) e
registro completo de cada execução."""
from __future__ import annotations

import logging
import math
import threading
import traceback
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import SessionLocal
from app.models import (
    Alocacao,
    AlocacaoRecurso,
    Ambiente,
    Atividade,
    CenarioPlanejamento,
    DeslocamentoUnidade,
    DisponibilidadeAmbiente,
    DisponibilidadeInstrutor,
    ExecucaoOtimizacao,
    Instrutor,
    InstrutorUnidade,
    ParametrosOtimizacao,
    PeriodoHorario,
    Recurso,
    RegistroDecisao,
    ResultadoOtimizacao,
    SimulacaoCapacidade,
    TipoAmbiente,
    Turma,
    TurmaUC,
    UnidadeCurricular,
)
from app.models.planejamento import TODOS_GRUPOS
from app.services import auditoria
from app.services.calendario import Calendarios, bloco_de_periodos, combinar, minutos
from app.services.planejamento import ambientes_compativeis, area_da_turma, instrutores_elegiveis, periodos_por_encontro
from app.services.regras_aula import credito_bloco, credito_periodo, periodos_do_turno, periodos_para_fechar, regras_aula
from app.services import agenda_instrutor
from app.services.validacao import AulaProposta, BaseDados, SessaoExistente, carga_horaria_minutos, possui_bloqueio, validar_aula
from app.solver.contrato import (
    AmbienteS,
    AtividadeS,
    EntradaSolver,
    InstrutorS,
    Janela,
    OcupacaoFixa,
    OpcaoAnterior,
    SaidaSolver,
    Slot,
)
from app.solver.criterios import normalizar_pesos


def resolver(entrada):
    """Importação tardia do CP-SAT: o OR-Tools só é necessário no processo que
    executa o solver (worker/servidor local). A API serverless não o carrega."""
    try:
        from app.solver.cpsat import resolver as _resolver
    except ImportError as e:  # pragma: no cover - depende do ambiente
        raise RuntimeError("OR-Tools não está instalado neste processo. Em produção serverless (Vercel), a otimização "
                           "é executada pelo worker externo (PLAN_EXECUTOR=fila). Ver DEPLOY.md.") from e
    return _resolver(entrada)

log = logging.getLogger("otimizacao")
_executor: ThreadPoolExecutor | None = None
_lock = threading.Lock()


def executor() -> ThreadPoolExecutor:
    global _executor
    with _lock:
        if _executor is None:
            _executor = ThreadPoolExecutor(max_workers=get_settings().max_jobs_simultaneos, thread_name_prefix="solver")
    return _executor


def recuperar_execucoes_interrompidas(db: Session, somente_expiradas: bool = False) -> int:
    """Execuções em andamento quando o processo caiu são marcadas como falha e o
    cenário volta a 'em_elaboracao' (a aplicação do resultado é transacional:
    nenhuma aula parcial fica gravada).

    - modo thread (servidor único): na inicialização, todas as execuções
      'executando' pertencem a um processo que morreu;
    - modo fila (worker externo): só são recuperadas as execuções cujo
      heartbeat expirou (o worker pode estar vivo em outra máquina)."""
    s = get_settings()
    q = select(ExecucaoOtimizacao).where(ExecucaoOtimizacao.status.in_(["executando"] if somente_expiradas else ["pendente", "executando"]))
    if somente_expiradas:
        limite = datetime.now() - timedelta(seconds=s.worker_heartbeat_expira_s)
        q = q.where(func.coalesce(ExecucaoOtimizacao.heartbeat_em, ExecucaoOtimizacao.iniciado_em) < limite)
    pend = db.scalars(q.with_for_update(skip_locked=True)).all()
    cenarios = set()
    for e in pend:
        e.status = "falha"
        e.motivo_termino = ("Execução interrompida (o processo que a executava parou de responder). "
                            "Nenhuma aula foi gravada; solicite novamente.")
        e.finalizado_em = datetime.now()
        cenarios.add(e.cenario_id)
    if somente_expiradas:
        if cenarios:
            db.execute(update(CenarioPlanejamento).where(CenarioPlanejamento.id.in_(cenarios), CenarioPlanejamento.estado == "em_otimizacao")
                       .values(estado="em_elaboracao"))
    else:
        db.execute(update(CenarioPlanejamento).where(CenarioPlanejamento.estado == "em_otimizacao").values(estado="em_elaboracao"))
    db.commit()
    return len(pend)


def reivindicar_execucao(db: Session, worker: str) -> int | None:
    """Fila no PostgreSQL: o próximo job pendente é reservado com
    FOR UPDATE SKIP LOCKED — dois workers nunca pegam o mesmo job."""
    ex = db.scalars(select(ExecucaoOtimizacao).where(ExecucaoOtimizacao.status == "pendente").order_by(ExecucaoOtimizacao.id)
                    .limit(1).with_for_update(skip_locked=True)).first()
    if ex is None:
        db.rollback()
        return None
    agora = datetime.now()
    ex.status, ex.worker, ex.iniciado_em, ex.heartbeat_em = "executando", worker, agora, agora
    db.commit()
    return ex.id


def heartbeat_execucao(execucao_id: int):
    with SessionLocal() as db:
        db.execute(update(ExecucaoOtimizacao).where(ExecucaoOtimizacao.id == execucao_id, ExecucaoOtimizacao.status == "executando")
                   .values(heartbeat_em=datetime.now()))
        db.commit()


def despachar(execucao_id: int, ctx=None, forcar_sincrono: bool = False) -> str:
    """Encaminha a execução conforme PLAN_EXECUTOR. Retorna o modo usado."""
    modo = "sincrono" if forcar_sincrono else get_settings().modo_executor
    if modo == "sincrono":
        executar(execucao_id, ctx)
    elif modo == "thread":
        submeter(execucao_id)
    else:
        # modo "fila": o job fica 'pendente' até um worker (python -m app.worker) reivindicá-lo;
        # se configurado, o worker do GitHub Actions é acionado na hora.
        from app.services.acionador import acionar_worker
        acionar_worker()
    return modo


# =============================================================================
# Montagem
# =============================================================================
def _simulacao_do_cenario(db: Session, cenario_id: int) -> int | None:
    return db.scalar(select(SimulacaoCapacidade.id).where(SimulacaoCapacidade.cenario_simulado_id == cenario_id))


def turma_ucs_do_escopo(db: Session, cenario: CenarioPlanejamento, escopo: dict) -> list[TurmaUC]:
    sim_id = _simulacao_do_cenario(db, cenario.id)
    q = select(TurmaUC).join(Turma).where(TurmaUC.ativo.is_(True), Turma.ativo.is_(True),
                                          TurmaUC.situacao.notin_(["concluida", "cancelada"]),
                                          Turma.situacao.notin_(["concluida", "cancelada"]))
    q = q.where((Turma.simulacao_id.is_(None)) | (Turma.simulacao_id == sim_id)) if sim_id else q.where(Turma.simulacao_id.is_(None))
    if cenario.unidade_id:
        q = q.where(Turma.unidade_id == cenario.unidade_id)
    tipo, ids = escopo.get("tipo", "instituicao"), escopo.get("ids") or []
    if tipo == "turma":
        q = q.where(Turma.id.in_(ids))
    elif tipo == "curso":
        q = q.where(Turma.curso_id.in_(ids))
    elif tipo == "turno":
        q = q.where(Turma.turno_id.in_(ids))
    elif tipo == "unidade":
        q = q.where(Turma.unidade_id.in_(ids))
    elif tipo == "simulacao":
        q = q.where(Turma.simulacao_id == sim_id)
    if escopo.get("turma_uc_ids"):
        q = q.where(TurmaUC.id.in_(escopo["turma_uc_ids"]))
    return db.scalars(q.order_by(Turma.prioridade, TurmaUC.id)).all()


def _padroes(aulas: list[Alocacao], periodo_por_inicio) -> list[OpcaoAnterior]:
    vistos = {}
    for a in aulas:
        sid = periodo_por_inicio(a)
        if sid is None:
            continue
        k = (a.data.weekday(), sid, a.instrutor_id, a.ambiente_id)
        vistos[k] = OpcaoAnterior(*k)
    return list(vistos.values())


def montar_entrada(db: Session, cenario: CenarioPlanejamento, escopo: dict, pesos: dict, limite_s: float, modo: str) -> tuple[EntradaSolver, dict]:
    tucs = turma_ucs_do_escopo(db, cenario, escopo)
    a_partir = date.fromisoformat(escopo["a_partir_de"]) if escopo.get("a_partir_de") else None
    regenerar = bool(escopo.get("regenerar_flexiveis", False))
    tuc_ids = {t.id for t in tucs}
    # aulas que serão substituídas (flexíveis, programadas, a partir da data)
    substituir = []
    if regenerar and tuc_ids:
        q = select(Alocacao).where(Alocacao.cenario_id == cenario.id, Alocacao.turma_uc_id.in_(tuc_ids),
                                   Alocacao.status == "programada", Alocacao.fixa.is_(False))
        if a_partir:
            q = q.where(Alocacao.data >= a_partir)
        substituir = db.scalars(q).all()
    ids_subst = {a.id for a in substituir}

    periodos = db.scalars(select(PeriodoHorario).where(PeriodoHorario.ativo.is_(True))).all()
    per_por_inicio = {(p.unidade_id, p.hora_inicio): p.id for p in periodos}
    ambientes_all = {a.id: a for a in db.scalars(select(Ambiente))}
    turmas = {}

    def periodo_da_aula(a: Alocacao):
        amb = ambientes_all.get(a.ambiente_id)
        t = turmas.get(a.turma_id) or db.get(Turma, a.turma_id)
        un = amb.unidade_id if amb else t.unidade_id
        return per_por_inicio.get((un, a.inicio.time()))

    publicado = db.scalars(select(CenarioPlanejamento).where(CenarioPlanejamento.estado == "publicado",
                                                             CenarioPlanejamento.id != cenario.id,
                                                             (CenarioPlanejamento.unidade_id == cenario.unidade_id) if cenario.unidade_id
                                                             else CenarioPlanejamento.unidade_id.is_(None))).first()
    b = BaseDados(db, cenario.id).precarregar()
    regras = regras_aula(db)
    atividades: list[AtividadeS] = []
    meta = {"atividades": {}, "substituir": sorted(ids_subst), "publicado_id": publicado.id if publicado else None, "ajustes": []}
    instr_ids, amb_ids, unidades = set(), set(), set()
    for tuc in tucs:
        turma = turmas.setdefault(tuc.turma_id, db.get(Turma, tuc.turma_id))
        uc = db.get(UnidadeCurricular, tuc.uc_id)
        unidades.add(turma.unidade_id)
        dividir = uc.divide_grupos and turma.num_grupos > 1
        grupos = list(range(1, turma.num_grupos + 1)) if dividir else [None]
        di = max(turma.data_inicio, tuc.data_inicio or turma.data_inicio, a_partir or turma.data_inicio)
        df = min(turma.data_fim, tuc.data_limite or turma.data_fim)
        if df < di:
            continue
        insts = instrutores_elegiveis(db, uc, turma.unidade_id, di, area_da_turma(db, turma))
        ambs = ambientes_compativeis(db, uc, turma, dividir)
        ps_unidade = [p for p in periodos if p.unidade_id == turma.unidade_id and (not turma.turno_id or p.turno_id == turma.turno_id)]
        mpp = (sum(credito_periodo(regras, p) for p in ps_unidade) / len(ps_unidade)) if ps_unidade else 50
        num_periodos = periodos_por_encontro(db, turma, uc)
        horas_encontro = num_periodos * mpp / 60
        semanas = max(((df - di).days + 1) / 7, 1 / 7)
        for g in grupos:
            realizados, programados = carga_horaria_minutos(b, tuc, g, ids_subst)
            restante_h = (uc.carga_horaria_total * 60 - realizados - programados) / 60
            if restante_h <= 0.01:
                continue
            enc = min(uc.encontros_semanais, math.ceil(restante_h / horas_encontro - 1e-9))
            necessarias = restante_h / (horas_encontro * enc)
            if necessarias > semanas + 1e-6:
                novo = min(math.ceil(restante_h / (horas_encontro * semanas) - 1e-9), len(turma.dias_possiveis or []) * 2)
                if novo > enc:
                    meta["ajustes"].append(f"{turma.codigo}/{uc.codigo}{f' G{g}' if g else ''}: encontros semanais ampliados de {enc} para {novo} para cumprir o prazo de {df:%d/%m/%Y}.")
                    enc = novo
            urg = min(1.0, (restante_h / (horas_encontro * enc)) / semanas)
            chave = f"{tuc.id}-{g or 0}"
            anteriores_cen = [a for a in substituir if a.turma_uc_id == tuc.id and (g is None or a.grupo == g)]
            anteriores_pub = []
            if publicado:
                anteriores_pub = db.scalars(select(Alocacao).where(Alocacao.cenario_id == publicado.id, Alocacao.turma_uc_id == tuc.id,
                                                                   Alocacao.status == "programada", Alocacao.grupo.is_(g) if g is None else Alocacao.grupo == g)).all()
            recm = {str(a["id"]): a["requer_recursos_moveis"] for a in ambs if a["requer_recursos_moveis"]}
            at = AtividadeS(
                chave=chave, turma_id=turma.id, turma_uc_id=tuc.id, uc_id=uc.id, grupo=g, grupos=list(TODOS_GRUPOS) if g is None else [g],
                unidade_id=turma.unidade_id, turno_id=turma.turno_id, dias_permitidos=list(turma.dias_possiveis or []),
                num_periodos=num_periodos, encontros=enc, instrutores=[i["id"] for i in insts], ambientes=[a["id"] for a in ambs],
                tamanho=turma.qtd_alunos if g is None else math.ceil(turma.qtd_alunos / turma.num_grupos),
                data_ini=di.toordinal(), data_fim=df.toordinal(), prioridade=min(turma.prioridade, uc.prioridade), urgencia=round(urg, 3),
                aceita_convencional=any(not t.especializado for t in uc.tipos_ambiente) or not uc.tipos_ambiente,
                recursos_moveis=recm, anteriores=_padroes(anteriores_pub, periodo_da_aula)[:enc],
                preservar=_padroes(anteriores_cen, periodo_da_aula)[:enc],
                descricao=f"{turma.codigo} – {uc.codigo} {uc.nome}{f' (grupo {g})' if g else ''}",
            )
            atividades.append(at)
            meta["atividades"][chave] = {"turma_uc_id": tuc.id, "grupo": g, "restante_min": round(restante_h * 60), "data_ini": di.isoformat(),
                                         "turno_id": turma.turno_id,
                                         "data_fim": df.isoformat(), "descricao": at.descricao}
            instr_ids.update(at.instrutores)
            amb_ids.update(at.ambientes)

    # ocupações fixas: demais aulas do cenário (padrões recorrentes; aulas avulsas são tratadas na expansão)
    fixas: list[OcupacaoFixa] = []
    grupos_fixos = defaultdict(list)
    recursos_aula = defaultdict(list)
    for ar in db.scalars(select(AlocacaoRecurso).join(Alocacao).where(Alocacao.cenario_id == cenario.id)):
        recursos_aula[ar.alocacao_id].append(ar)
    recursos = {r.id: r for r in db.scalars(select(Recurso))}
    for s in b._sessoes.values():
        if s.id in ids_subst or (a_partir and s.data < a_partir):
            continue
        grupos_fixos[(s.data.weekday(), s.inicio.time(), s.fim.time(), s.turma_id, tuple(s.grupos), s.instrutor_id, s.ambiente_id)].append(s)
    for (dia, hi, hf, turma_id, grupos, inst, amb), lst in grupos_fixos.items():
        if len(lst) < 2:
            continue  # aula avulsa: validada data a data na expansão
        d0, d1 = min(s.data for s in lst).toordinal(), max(s.data for s in lst).toordinal()
        ini, fim = minutos(hi), minutos(hf)
        mins = lst[0].minutos_aula
        fixas.append(OcupacaoFixa("turma", str(turma_id), dia, ini, fim, d0, d1, grupos=list(grupos)))
        if inst:
            fixas.append(OcupacaoFixa("instrutor", str(inst), dia, ini, fim, d0, d1, unidade_id=lst[0].unidade_id, minutos=mins))
            instr_ids.add(inst)
        if amb:
            prep = ambientes_all[amb].tempo_preparacao_min or 0
            fixas.append(OcupacaoFixa("ambiente", str(amb), dia, ini, fim + prep, d0, d1))
        for ar in recursos_aula.get(lst[0].id, []):
            r = recursos.get(ar.recurso_id)
            if r and r.movel:
                fixas.append(OcupacaoFixa("recurso_movel", f"{r.unidade_id}:{r.tipo}", dia, ini, fim, d0, d1, quantidade=ar.quantidade))

    # instrutores e ambientes
    instrutores = []
    for i in db.scalars(select(Instrutor).where(Instrutor.id.in_(instr_ids))):
        disp = [(j.dia_semana, minutos(j.hora_inicio), minutos(j.hora_fim))
                for j in db.scalars(select(DisponibilidadeInstrutor).where(DisponibilidadeInstrutor.instrutor_id == i.id))]
        # turnos de planejamento (PL) / projeto (PJ) marcados toda semana não recebem aula
        reservas = agenda_instrutor.reservas_semanais(db, i.id, cenario.periodo_inicio, cenario.periodo_fim)
        if reservas and disp:
            disp = agenda_instrutor.subtrair(disp, reservas)
        disp = [Janela(*j) for j in disp]
        uns = sorted({i.unidade_id, *db.scalars(select(InstrutorUnidade.unidade_id).where(InstrutorUnidade.instrutor_id == i.id))})
        unidades.update(uns)
        instrutores.append(InstrutorS(i.id, uns, disp, int(float(i.limite_ch_letiva) * 60), int(float(i.max_horas_dia) * 60),
                                      int(float(i.intervalo_minimo_h or 0) * 60), i.turno_preferencial_id))
    tipos = {t.id: t for t in db.scalars(select(TipoAmbiente))}
    ambientes = []
    for a in db.scalars(select(Ambiente).where(Ambiente.id.in_(amb_ids))):
        disp = [Janela(j.dia_semana, minutos(j.hora_inicio), minutos(j.hora_fim))
                for j in db.scalars(select(DisponibilidadeAmbiente).where(DisponibilidadeAmbiente.ambiente_id == a.id))]
        ambientes.append(AmbienteS(a.id, a.unidade_id, a.capacidade_operacional, a.capacidade_fisica,
                                   bool(tipos.get(a.tipo_ambiente_id) and tipos[a.tipo_ambiente_id].especializado), disp, a.tempo_preparacao_min or 0))
    slots = [Slot(p.id, p.unidade_id, p.turno_id, p.ordem, list(p.dias_semana or []), minutos(p.hora_inicio), minutos(p.hora_fim), p.excepcional,
                  credito_periodo(regras, p))
             for p in periodos if p.unidade_id in unidades]
    acervo = defaultdict(int)
    for r in recursos.values():
        if r.movel and r.ativo and r.situacao == "disponivel":
            acervo[f"{r.unidade_id}:{r.tipo}"] += r.quantidade_total
    desl = {f"{min(d.origem_id, d.destino_id)}:{max(d.origem_id, d.destino_id)}": d.minutos
            for d in db.scalars(select(DeslocamentoUnidade).where(DeslocamentoUnidade.ativo.is_(True)))}
    s = get_settings()
    entrada = EntradaSolver(slots=slots, instrutores=instrutores, ambientes=ambientes, atividades=atividades, fixas=fixas,
                            acervo_movel=dict(acervo), deslocamentos=desl, pesos=pesos, modo=modo, limite_tempo_s=limite_s,
                            threads=s.solver_threads)
    return entrada, meta


# =============================================================================
# Aplicação
# =============================================================================
def _reservar_moveis(b: BaseDados, db: Session, unidade_id: int, faltantes: dict, ini: datetime, fim: datetime) -> list[tuple[int, int]] | None:
    reservas = []
    for tipo, q in faltantes.items():
        falta = q
        for r in b.recursos_moveis(unidade_id, tipo):
            em_uso = sum(qq for s, qq in b.uso_recurso(r.id, ini.date()) if s.inicio < fim and ini < s.fim)
            livre = r.quantidade_total - em_uso
            if livre > 0:
                usar = min(livre, falta)
                reservas.append((r.id, usar))
                falta -= usar
            if falta <= 0:
                break
        if falta > 0:
            return None
    return reservas


def aplicar_resultado(db: Session, ctx, cenario: CenarioPlanejamento, saida: SaidaSolver, meta: dict, execucao_id: int | None) -> dict:
    """Expande o padrão semanal em aulas datadas. Cada aula passa pela
    validação central; datas inviáveis (feriado, bloqueio pontual, aula avulsa
    conflitante) são puladas e a aula segue para a semana seguinte."""
    if meta["substituir"]:
        db.execute(delete(Alocacao).where(Alocacao.id.in_(meta["substituir"])))
        db.flush()
    b = BaseDados(db, cenario.id).precarregar()
    cal = Calendarios(db)
    por_ativ = defaultdict(list)
    for a in saida.atribuicoes:
        por_ativ[a.chave].append(a)
    periodos = {p.id: p for p in db.scalars(select(PeriodoHorario))}
    regras = regras_aula(db)
    criadas, puladas, riscos = 0, [], []
    parciais = []  # aulas de fechamento de carga horária (turno incompleto)
    for chave, atribs in por_ativ.items():
        info = meta["atividades"][chave]
        tuc = db.get(TurmaUC, info["turma_uc_id"])
        turma = db.get(Turma, tuc.turma_id)
        g = info["grupo"]
        di, df = date.fromisoformat(info["data_ini"]), date.fromisoformat(info["data_fim"])
        restante = info["restante_min"]
        atividades_db = {}
        for at in sorted(atribs, key=lambda a: (a.dia, a.ini)):
            atv = Atividade(cenario_id=cenario.id, turma_uc_id=tuc.id, grupo=g, instrutor_id=at.instrutor_id, ambiente_id=at.ambiente_id,
                            dia_semana=at.dia, periodo_inicio_id=at.slot_inicio_id, num_periodos=at.num_periodos, data_inicio=di,
                            data_fim=df, origem="solver", execucao_id=execucao_id)
            db.add(atv)
            atividades_db[(at.dia, at.ini)] = atv
        db.flush()
        amb_cache = {}
        seg = di - timedelta(days=di.weekday())
        ultima = None
        while seg <= df and restante > 0:
            for at in sorted(atribs, key=lambda a: (a.dia, a.ini)):
                if restante <= 0:
                    break
                d = seg + timedelta(days=at.dia)
                if d < di or d > df:
                    continue
                ok, motivo = cal.dia_letivo(turma, d)
                if not ok:
                    puladas.append({"atividade": info["descricao"], "data": d.isoformat(), "motivo": motivo})
                    continue
                p0 = periodos[at.slot_inicio_id]
                ini = combinar(d, p0.hora_inicio)
                fim = ini + timedelta(minutes=at.fim - at.ini)
                mins = at.minutos
                parcial = False
                if restante < at.minutos:
                    # fechamento da carga horária: só as aulas necessárias; o resto do turno fica livre
                    bloco = [periodos[i] for i in at.slot_ids]
                    n = periodos_para_fechar(regras, restante, bloco)
                    if credito_bloco(regras, bloco[:n]) > restante and n > 1:
                        n -= 1  # contagem por minutos reais: não exceder a carga
                    bloco = bloco[:n]
                    fim = combinar(d, bloco[-1].hora_fim)
                    mins = credito_bloco(regras, bloco)
                    parcial = n < len(at.slot_ids)
                amb = amb_cache.setdefault(at.ambiente_id, db.get(Ambiente, at.ambiente_id) if at.ambiente_id else None)
                faltantes = {}
                if amb:
                    req = b.recursos_uc(tuc.uc_id)
                    fixos = b.recursos_fixos_ambiente(amb.id)
                    faltantes = {r.recurso_tipo: r.quantidade - fixos.get(r.recurso_tipo, 0) for r in req if fixos.get(r.recurso_tipo, 0) < r.quantidade}
                reservas = []
                if faltantes:
                    reservas = _reservar_moveis(b, db, amb.unidade_id, faltantes, ini, fim)
                    if reservas is None:
                        puladas.append({"atividade": info["descricao"], "data": d.isoformat(), "motivo": "recursos móveis indisponíveis na data"})
                        continue
                prop = AulaProposta(turma_uc_id=tuc.id, inicio=ini, fim=fim, minutos_aula=mins, grupo=g, instrutor_id=at.instrutor_id,
                                    ambiente_id=at.ambiente_id, recursos=reservas, origem="solver")
                oc = validar_aula(b, prop)
                if possui_bloqueio(oc):
                    puladas.append({"atividade": info["descricao"], "data": d.isoformat(),
                                    "motivo": "; ".join(o.descricao for o in oc if o.severidade == "bloqueio")[:400]})
                    continue
                prep = timedelta(minutes=(amb.tempo_preparacao_min if amb else 0) or 0)
                al = Alocacao(cenario_id=cenario.id, atividade_id=atividades_db[(at.dia, at.ini)].id, turma_uc_id=tuc.id, turma_id=turma.id,
                              uc_id=tuc.uc_id, grupo=g, grupos=list(TODOS_GRUPOS) if g is None else [g], instrutor_id=at.instrutor_id,
                              ambiente_id=at.ambiente_id, data=d, inicio=ini, fim=fim, fim_ambiente=fim + prep, minutos_aula=mins,
                              origem="solver", status="programada", criado_por_id=getattr(ctx, "id", None))
                db.add(al)
                db.flush()
                for rid, q in reservas:
                    db.add(AlocacaoRecurso(alocacao_id=al.id, recurso_id=rid, quantidade=q))
                sess = SessaoExistente(al.id, turma.id, tuc.id, tuc.uc_id, al.grupos, al.instrutor_id, al.ambiente_id, d, ini, fim, fim + prep,
                                       mins, "programada", amb.unidade_id if amb else turma.unidade_id, dict(reservas))
                b.adicionar_virtual(sess)
                restante -= mins
                if parcial:
                    parciais.append({"al": al, "limite": df, "turno_id": turma.turno_id})
                criadas += 1
                ultima = d
            seg += timedelta(days=7)
        for atv in atividades_db.values():
            atv.data_fim = ultima or atv.data_inicio
        if restante > 0:
            riscos.append({"atividade": info["descricao"], "turma_uc_id": tuc.id, "grupo": g, "faltam_h": round(restante / 60, 2),
                           "data_limite": df.isoformat(),
                           "motivo": "Datas letivas insuficientes até o prazo com o padrão semanal gerado (feriados/bloqueios pontuais)."})
    db.flush()
    juntadas = _compactar_fechamentos(db, cenario, parciais, regras) if regras.get("turno_inteiro") else 0
    return {"aulas_criadas": criadas, "aulas_substituidas": len(meta["substituir"]), "datas_puladas": puladas, "riscos_conclusao": riscos,
            "fechamentos_parciais": len(parciais), "fechamentos_juntados": juntadas}


def _compactar_fechamentos(db: Session, cenario: CenarioPlanejamento, parciais: list[dict], regras: dict) -> int:
    """Junta, no mesmo turno, aulas de fechamento de carga horária de UCs da mesma turma.

    A aula de fechamento mais tardia é a "anfitriã"; uma de data anterior é
    movida para as aulas livres logo após ela (o que mantém cada fechamento
    depois das demais aulas da sua UC). Cada movimento passa pela validação
    central e pelas restrições do banco; se algo impedir, nada muda."""
    grupos = defaultdict(list)
    for x in parciais:
        grupos[(x["al"].turma_id, tuple(x["al"].grupos))].append(x)
    juntadas = 0
    for lst in grupos.values():
        lst.sort(key=lambda x: (x["al"].data, x["al"].inicio))
        usados: set[int] = set()
        for host in reversed(lst):
            h = host["al"]
            if h.id in usados:
                continue
            livres = [p for p in periodos_do_turno(db, host["turno_id"], h.data.weekday()) if combinar(h.data, p.hora_inicio) >= h.fim]
            for guest in lst:
                gal = guest["al"]
                if gal.id == h.id or gal.id in usados or gal.data >= h.data or h.data > guest["limite"]:
                    continue
                n = len([p for p in periodos_do_turno(db, guest["turno_id"], gal.data.weekday())
                         if combinar(gal.data, p.hora_inicio) >= gal.inicio and combinar(gal.data, p.hora_fim) <= gal.fim])
                if n == 0 or n > len(livres):
                    continue
                bloco = livres[:n]
                ini, fim = combinar(h.data, bloco[0].hora_inicio), combinar(h.data, bloco[-1].hora_fim)
                prop = AulaProposta(turma_uc_id=gal.turma_uc_id, inicio=ini, fim=fim, minutos_aula=gal.minutos_aula,
                                    grupo=None if len(gal.grupos) == len(TODOS_GRUPOS) else gal.grupos[0], instrutor_id=gal.instrutor_id,
                                    ambiente_id=gal.ambiente_id, alocacao_id=gal.id, origem="solver")
                if possui_bloqueio(validar_aula(BaseDados(db, cenario.id), prop)):
                    continue
                antes = (gal.data, gal.inicio, gal.fim, gal.fim_ambiente)
                try:
                    with db.begin_nested():
                        prep = gal.fim_ambiente - gal.fim
                        gal.data, gal.inicio, gal.fim, gal.fim_ambiente = h.data, ini, fim, fim + prep
                        db.flush()
                except Exception:
                    gal.data, gal.inicio, gal.fim, gal.fim_ambiente = antes
                    continue
                usados.update({h.id, gal.id})
                livres = livres[n:]
                juntadas += 1
                if not livres:
                    break
    db.flush()
    return juntadas


# =============================================================================
# Execução
# =============================================================================
def criar_execucao(db: Session, ctx, cenario_id: int, escopo: dict, parametros_id: int | None = None, pesos: dict | None = None,
                   limite_tempo_s: float | None = None, modo: str = "completo", aplicar: bool = True) -> ExecucaoOtimizacao:
    from app.services.alocacao import obter_cenario_editavel
    cen = obter_cenario_editavel(db, cenario_id, bloquear=True)
    em_curso = db.scalar(select(ExecucaoOtimizacao.id).where(ExecucaoOtimizacao.cenario_id == cenario_id,
                                                             ExecucaoOtimizacao.status.in_(["pendente", "executando"])))
    if em_curso:
        from app.core.errors import ConflitoConcorrencia
        raise ConflitoConcorrencia(f"Já existe uma execução em andamento para este cenário (#{em_curso}).")
    conj = db.get(ParametrosOtimizacao, parametros_id) if parametros_id else db.scalars(select(ParametrosOtimizacao).where(ParametrosOtimizacao.padrao.is_(True))).first()
    pesos_final = normalizar_pesos({**((conj.pesos if conj else {}) or {}), **(pesos or {})})
    limite = float(limite_tempo_s or (conj.limite_tempo_s if conj else get_settings().solver_limite_padrao_s))
    limite = max(1.0, min(limite, float(get_settings().solver_limite_max_s)))
    ex = ExecucaoOtimizacao(cenario_id=cenario_id, escopo=escopo, status="pendente", criado_por_id=getattr(ctx, "id", None),
                            parametros={"pesos": pesos_final, "limite_tempo_s": limite, "modo": modo, "aplicar": aplicar,
                                        "conjunto_parametros": {"id": conj.id, "nome": conj.nome, "versao": conj.versao} if conj else None})
    db.add(ex)
    cen.estado = "em_otimizacao"
    db.flush()
    auditoria.registrar(db, ctx, "otimizacao.solicitar", "execucoes_otimizacao", ex.id, depois={"escopo": escopo, **ex.parametros})
    return ex


def executar(execucao_id: int, ctx=None):
    """Executa uma otimização (chamado pela fila assíncrona ou diretamente)."""
    db = SessionLocal()
    try:
        ex = db.get(ExecucaoOtimizacao, execucao_id)
        if ex is None or ex.status in ("concluida", "falha", "cancelada"):
            return
        ex.status, ex.iniciado_em, ex.heartbeat_em = "executando", ex.iniciado_em or datetime.now(), datetime.now()
        db.commit()
        if ctx is None and ex.criado_por_id:
            from app.core.deps import carregar_contexto
            from app.models import Usuario
            u = db.get(Usuario, ex.criado_por_id)
            ctx = carregar_contexto(db, u) if u else None
        cen = db.get(CenarioPlanejamento, ex.cenario_id)
        par = ex.parametros
        entrada, meta = montar_entrada(db, cen, ex.escopo, par["pesos"], par["limite_tempo_s"], par["modo"])
        db.rollback()  # montagem é somente leitura
        saida = resolver(entrada)
        diagnosticos = list(saida.diagnosticos) + meta["ajustes"]
        resultado = {"solver": {k: v for k, v in saida.to_dict().items() if k not in ("atribuicoes",)},
                     "atribuicoes": len(saida.atribuicoes), "atividades": len(entrada.atividades), "ocupacoes_fixas": len(entrada.fixas)}
        if saida.status in ("INVIAVEL",) and par["modo"] == "completo" and entrada.atividades:
            # diagnóstico: busca parcial curta para identificar o que não cabe
            entrada.modo = "parcial"
            entrada.limite_tempo_s = min(15.0, par["limite_tempo_s"])
            parcial = resolver(entrada)
            resultado["diagnostico_parcial"] = {"status": parcial.status, "nao_alocados": parcial.nao_alocados}
            from app.services.recomendacoes import explicar_nao_alocacao
            exp = []
            for n in (parcial.nao_alocados or saida.nao_alocados)[:20]:
                try:
                    exp.append(explicar_nao_alocacao(db, cen.id, n["turma_uc_id"], n.get("grupo")))
                except Exception as e:  # diagnóstico nunca derruba a execução
                    exp.append({"turma_uc_id": n["turma_uc_id"], "erro": str(e)})
            resultado["explicacoes"] = exp
            # gargalos agregados envolvendo as turmas do escopo
            from app.services import gargalos as g_srv
            datas = [date.fromordinal(a.data_ini) for a in entrada.atividades] + [date.fromordinal(a.data_fim) for a in entrada.atividades]
            turmas_escopo = {db.get(Turma, a.turma_id).codigo for a in entrada.atividades}
            analise = g_srv.analisar(db, cen.id, min(datas), max(datas), cen.unidade_id)
            resultado["gargalos"] = [g for g in analise["gargalos"]
                                     if any(i.get("turma") in turmas_escopo for i in g.get("itens", [])) or any(t in g["recurso"] for t in turmas_escopo)]
            for g in resultado["gargalos"]:
                diagnosticos.append(f"Gargalo ({g['tipo']}): {g['descricao']}")
        aplicado = None
        if saida.status in ("OTIMA", "VIAVEL") and par.get("aplicar", True):
            cen = db.scalars(select(CenarioPlanejamento).where(CenarioPlanejamento.id == cen.id).with_for_update()).first()
            aplicado = aplicar_resultado(db, ctx, cen, saida, meta, ex.id)
            resultado["aplicacao"] = aplicado
            if saida.nao_alocados:
                from app.services.recomendacoes import explicar_nao_alocacao
                resultado["explicacoes"] = [explicar_nao_alocacao(db, cen.id, n["turma_uc_id"], n.get("grupo")) for n in saida.nao_alocados[:20]]
            db.add(RegistroDecisao(tipo="resultado_cenario", cenario_id=cen.id, dados={"execucao_id": ex.id, "status": saida.status,
                                                                                         "termos": saida.termos, "aulas": aplicado["aulas_criadas"]}))
        ex = db.get(ExecucaoOtimizacao, execucao_id)
        ex.status = "concluida"
        ex.status_solver = saida.status
        ex.motivo_termino = saida.motivo
        ex.objetivo, ex.limite_inferior, ex.tempo_s = saida.objetivo, saida.limite_inferior, round(saida.tempo_s, 3)
        ex.diagnosticos = diagnosticos
        ex.resultado = resultado
        ex.finalizado_em = datetime.now()
        pesos = par["pesos"]
        for crit, val in saida.termos.items():
            db.add(ResultadoOtimizacao(execucao_id=ex.id, criterio=crit, valor_bruto=val, peso=pesos.get(crit, 0), pontos=val * pesos.get(crit, 0)))
        cen = db.get(CenarioPlanejamento, ex.cenario_id)
        cen.estado = "em_elaboracao"
        cen.lock_version += 1
        auditoria.registrar(db, ctx or "sistema", "otimizacao.concluir", "execucoes_otimizacao", ex.id,
                            depois={"status_solver": saida.status, "aulas": (aplicado or {}).get("aulas_criadas")}, origem="solver")
        db.commit()
    except Exception as e:
        db.rollback()
        log.exception("Falha na otimização %s", execucao_id)
        ex = db.get(ExecucaoOtimizacao, execucao_id)
        if ex:
            ex.status = "falha"
            ex.motivo_termino = f"Erro interno: {e}"
            ex.diagnosticos = [traceback.format_exc()[-2000:]]
            ex.finalizado_em = datetime.now()
            cen = db.get(CenarioPlanejamento, ex.cenario_id)
            if cen and cen.estado == "em_otimizacao":
                cen.estado = "em_elaboracao"
            db.commit()
    finally:
        db.close()


def submeter(execucao_id: int):
    executor().submit(executar, execucao_id)
