"""Matriz de oferta: situação de cada turma×UC no cenário (cargas horárias,
encontros necessários, instrutores elegíveis e ambientes compatíveis)."""
from __future__ import annotations

import math
from collections import defaultdict
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    Alocacao,
    Ambiente,
    Curso,
    CompetenciaInstrutor,
    HabilitacaoInstrutor,
    Instrutor,
    InstrutorUnidade,
    PeriodoHorario,
    Recurso,
    RecursoAmbiente,
    TipoAmbiente,
    Turma,
    TurmaUC,
    UCPrerequisito,
    UCRecurso,
    UnidadeCurricular,
)
from app.services.areas import recurso_atende
from app.services.calendario import minutos


def minutos_por_periodo(db: Session, unidade_id: int, turno_id: int | None = None) -> float:
    """Carga horária (minutos) que uma aula/período vale: 60 em hora-aula; senão, a duração média das aulas do turno
    (55 min de dia, 50 à noite) ou, sem turno, da unidade."""
    from app.services.regras_aula import hora_aula, regras_aula
    if hora_aula(regras_aula(db)):
        return 60.0
    q = select(PeriodoHorario).where(PeriodoHorario.unidade_id == unidade_id, PeriodoHorario.ativo.is_(True), PeriodoHorario.excepcional.is_(False))
    ps = db.scalars(q.where(PeriodoHorario.turno_id == turno_id)).all() if turno_id else []
    ps = ps or db.scalars(q).all()
    if not ps:
        return 50.0
    return sum(minutos(p.hora_fim) - minutos(p.hora_inicio) for p in ps) / len(ps)


def periodos_por_encontro(db: Session, turma: Turma, uc: UnidadeCurricular) -> int:
    """Aulas por encontro: o turno inteiro quando a regra está ativa; senão, a duração do bloco da UC."""
    from app.services.regras_aula import blocos, periodos_do_turno, regras_aula
    if regras_aula(db).get("turno_inteiro") and turma.turno_id:
        # o turno inteiro é o bloco contínuo de aulas (na PFP, a manhã 08–12 ou a tarde 13–17)
        n = max((len(b) for d in (turma.dias_possiveis or [0]) for b in blocos(periodos_do_turno(db, turma.turno_id, d))), default=0)
        if n:
            return n
    return uc.duracao_bloco_periodos


def area_da_turma(db: Session, turma) -> int | None:
    """Área da turma (ou, se não informada, a do curso)."""
    if getattr(turma, "area_id", None):
        return turma.area_id
    curso = db.get(Curso, turma.curso_id) if getattr(turma, "curso_id", None) else None
    return curso.area_id if curso else None


# Nível do instrutor: o BÁSICO só dá aula em aprendizagem industrial básica (AIB) e qualificações;
# o TÉCNICO, em todas as modalidades. O tipo de oferta vem do prefixo do código da turma (HTC-ELT-12);
# sem prefixo conhecido, vale o tipo do curso.
OFERTAS_BASICAS = {"AIB", "QUA"}
OFERTAS_TECNICAS = {"HTC", "AIT", "ESP"}
NIVEIS_INSTRUTOR = {"basico": "Básico (AIB e qualificações)", "tecnico": "Técnico (todas as modalidades)"}


def _sem_acento(s: str) -> str:
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFD", s or "") if unicodedata.category(c) != "Mn").lower()


def nivel_da_turma(db: Session, turma) -> str:
    """Nível de instrutor que a turma exige: "basico" (aceita básico e técnico) ou "tecnico" (só técnico)."""
    if turma is None:
        return "basico"
    pref = (getattr(turma, "codigo", "") or "").split("-")[0].strip().upper()
    if pref in OFERTAS_BASICAS:
        return "basico"
    if pref in OFERTAS_TECNICAS:
        return "tecnico"
    curso = db.get(Curso, turma.curso_id) if getattr(turma, "curso_id", None) else None
    tipo = _sem_acento(curso.tipo if curso else "")
    return "basico" if ("qualifica" in tipo or "basic" in tipo) else "tecnico"


def dias_com_ead(dias_possiveis, dias_ead, ead_antes=None) -> list[int]:
    """Dias de aula presencial: os dias EAD (turma 80-20) saem dos dias de aula; um dia que deixa de ser EAD volta a ser de aula."""
    ead = set(dias_ead or [])
    dias = set(dias_possiveis or []) | (set(ead_antes or []) - ead)
    return sorted(dias - ead)


def nivel_atende(nivel_instrutor: str | None, nivel_turma: str | None) -> bool:
    return not (nivel_turma == "tecnico" and (nivel_instrutor or "tecnico") == "basico")


def _tem_certificacao(db: Session, instrutor_id: int, uc: UnidadeCurricular, na_data: date) -> bool:
    if not uc.certificacao_exigida:
        return True
    return bool(db.scalar(select(func.count()).select_from(HabilitacaoInstrutor).where(
        HabilitacaoInstrutor.instrutor_id == instrutor_id, HabilitacaoInstrutor.ativo.is_(True),
        func.lower(HabilitacaoInstrutor.nome) == uc.certificacao_exigida.strip().lower(),
        (HabilitacaoInstrutor.valido_ate.is_(None)) | (HabilitacaoInstrutor.valido_ate >= na_data))))


def instrutores_elegiveis(db: Session, uc: UnidadeCurricular, unidade_id: int, na_data: date | None = None, area_id: int | None = None,
                          nivel: str | None = None) -> list[dict]:
    """Elegibilidade pela matriz de competências (nunca por seleção manual), pelo nível exigido pela turma
    (instrutor básico não entra em turma técnica) e, se informada, pela área da turma (instrutor sem área definida é aceito).
    UC TRANSVERSAL: qualquer instrutor ativo da unidade pode dar (sem competência, área ou nível); só a certificação exigida vale."""
    na_data = na_data or date.today()
    if getattr(uc, "categoria", "tecnica") == "transversal":
        res = []
        for inst in db.scalars(select(Instrutor).where(Instrutor.ativo.is_(True), Instrutor.situacao == "ativo").order_by(Instrutor.nome)):
            unidades = {inst.unidade_id, *db.scalars(select(InstrutorUnidade.unidade_id).where(InstrutorUnidade.instrutor_id == inst.id))}
            if unidade_id not in unidades or not _tem_certificacao(db, inst.id, uc, na_data):
                continue
            res.append({"id": inst.id, "nome": inst.nome, "matricula": inst.matricula, "nivel": "pleno", "area_id": inst.area_id,
                        "nivel_instrutor": inst.nivel, "transversal": True})
        return res
    q = (
        select(Instrutor, CompetenciaInstrutor)
        .join(CompetenciaInstrutor, CompetenciaInstrutor.instrutor_id == Instrutor.id)
        .where(CompetenciaInstrutor.uc_id == uc.id, CompetenciaInstrutor.ativo.is_(True),
               CompetenciaInstrutor.nivel.in_(["pleno", "parcial"]),
               Instrutor.ativo.is_(True), Instrutor.situacao == "ativo")
    )
    res = []
    for inst, comp in db.execute(q):
        if comp.valido_ate and comp.valido_ate < na_data:
            continue
        if area_id and not recurso_atende(db, inst, area_id):
            continue
        if not nivel_atende(inst.nivel, nivel):
            continue
        unidades = {inst.unidade_id, *db.scalars(select(InstrutorUnidade.unidade_id).where(InstrutorUnidade.instrutor_id == inst.id))}
        if unidade_id not in unidades:
            continue
        if not _tem_certificacao(db, inst.id, uc, na_data):
            continue
        res.append({"id": inst.id, "nome": inst.nome, "matricula": inst.matricula, "nivel": comp.nivel, "area_id": inst.area_id,
                    "nivel_instrutor": inst.nivel})
    return res


def ambientes_compativeis(db: Session, uc: UnidadeCurricular, turma: Turma, grupo_dividido: bool = False) -> list[dict]:
    """Compatibilidade técnica (tipo + equipamentos fixos ou acervo móvel),
    capacidade física e acessibilidade. Não basta ter vagas."""
    tipos = {t.id for t in uc.tipos_ambiente}
    tamanho = turma.qtd_alunos if not grupo_dividido else math.ceil(turma.qtd_alunos / max(turma.num_grupos, 1))
    reqs = db.scalars(select(UCRecurso).where(UCRecurso.uc_id == uc.id)).all()
    moveis = defaultdict(int)
    for r in db.scalars(select(Recurso).where(Recurso.unidade_id == turma.unidade_id, Recurso.movel.is_(True),
                                              Recurso.ativo.is_(True), Recurso.situacao == "disponivel")):
        moveis[r.tipo] += r.quantidade_total
    res = []
    area_turma = area_da_turma(db, turma)
    especializados = {t.id for t in db.scalars(select(TipoAmbiente).where(TipoAmbiente.especializado.is_(True)))}
    for amb in db.scalars(select(Ambiente).where(Ambiente.unidade_id == turma.unidade_id, Ambiente.ativo.is_(True),
                                                 Ambiente.situacao == "operacional")):
        if amb.tipo_ambiente_id in especializados and not recurso_atende(db, amb, area_turma):
            continue  # laboratório especializado que não atende a área da turma
        if tipos and amb.tipo_ambiente_id not in tipos:
            continue
        if tamanho > amb.capacidade_fisica:
            continue
        if turma.necessidades_acessibilidade and not amb.acessivel:
            continue
        fixos = defaultdict(int)
        for tipo, q in db.execute(select(Recurso.tipo, RecursoAmbiente.quantidade).join(RecursoAmbiente, RecursoAmbiente.recurso_id == Recurso.id)
                                  .where(RecursoAmbiente.ambiente_id == amb.id, Recurso.ativo.is_(True))):
            fixos[tipo] += q
        faltantes = {r.recurso_tipo: r.quantidade - fixos.get(r.recurso_tipo, 0) for r in reqs if fixos.get(r.recurso_tipo, 0) < r.quantidade}
        if any(moveis.get(t, 0) < q for t, q in faltantes.items()):
            continue
        res.append({
            "id": amb.id, "codigo": amb.codigo, "nome": amb.nome, "capacidade_fisica": amb.capacidade_fisica,
            "capacidade_operacional": amb.capacidade_operacional, "requer_recursos_moveis": faltantes,
            "acima_operacional": tamanho > amb.capacidade_operacional,
        })
    return res


def situacao_carga_horaria(db: Session, cenario_id: int | None, tuc: TurmaUC) -> dict:
    turma = db.get(Turma, tuc.turma_id)
    uc = db.get(UnidadeCurricular, tuc.uc_id)
    realizada_min = float(tuc.ch_realizada or 0) * 60
    programada_min = 0.0
    grupos_div = uc.divide_grupos and turma.num_grupos > 1
    if cenario_id:
        linhas = db.execute(select(Alocacao.status, Alocacao.minutos_aula, Alocacao.grupo).where(
            Alocacao.cenario_id == cenario_id, Alocacao.turma_uc_id == tuc.id, Alocacao.status != "cancelada")).all()
        # Com divisão em grupos, a carga é controlada por grupo; reporta o grupo menos atendido.
        if grupos_div:
            por_grupo = {g: [0.0, 0.0] for g in range(1, turma.num_grupos + 1)}
            for st, m, g in linhas:
                alvo = por_grupo.keys() if g is None else [g]
                for gg in alvo:
                    if gg in por_grupo:
                        por_grupo[gg][0 if st == "realizada" else 1] += m
            pior = min(por_grupo.values(), key=lambda v: v[0] + v[1])
            realizada_min += pior[0]
            programada_min = pior[1]
        else:
            for st, m, _g in linhas:
                if st == "realizada":
                    realizada_min += m
                else:
                    programada_min += m
    total_h = uc.carga_horaria_total
    restante_h = max(total_h - (realizada_min + programada_min) / 60, 0)
    mpp = minutos_por_periodo(db, turma.unidade_id, turma.turno_id)
    horas_encontro = periodos_por_encontro(db, turma, uc) * mpp / 60
    encontros_necessarios = math.ceil(restante_h / horas_encontro - 1e-9) if horas_encontro else 0
    prereqs = db.scalars(select(UnidadeCurricular.codigo).join(UCPrerequisito, UCPrerequisito.prerequisito_id == UnidadeCurricular.id)
                         .where(UCPrerequisito.uc_id == uc.id)).all()
    if tuc.situacao in ("concluida", "cancelada"):
        estado = tuc.situacao
    elif restante_h <= 0.01:
        estado = "programada_integralmente"
    elif programada_min > 0 or realizada_min > 0:
        estado = "em_execucao" if realizada_min > 0 else "parcialmente_programada"
    else:
        estado = "pendente_alocacao"
    return {
        "turma_uc_id": tuc.id, "turma_id": turma.id, "turma_codigo": turma.codigo, "uc_id": uc.id,
        "uc_codigo": uc.codigo, "uc_nome": uc.nome, "situacao_cadastro": tuc.situacao, "estado_planejamento": estado,
        "total_h": total_h, "realizada_h": round(realizada_min / 60, 2), "programada_h": round(programada_min / 60, 2),
        "restante_h": round(restante_h, 2), "horas_por_encontro": round(horas_encontro, 2),
        "periodos_por_encontro": periodos_por_encontro(db, turma, uc),
        "periodos_sugeridos": min(periodos_por_encontro(db, turma, uc), max(1, math.ceil(restante_h * 60 / mpp - 1e-9))) if restante_h > 0 else periodos_por_encontro(db, turma, uc),
        "encontros_necessarios": encontros_necessarios, "encontros_semanais": uc.encontros_semanais, "duracao_bloco_periodos": uc.duracao_bloco_periodos,
        "data_inicio": (tuc.data_inicio or turma.data_inicio).isoformat(),
        "data_limite": (tuc.data_limite or turma.data_fim).isoformat(),
        "prerequisitos": prereqs, "divide_grupos": grupos_div, "num_grupos": turma.num_grupos,
        "recursos_necessarios": [{"tipo": r.recurso_tipo, "quantidade": r.quantidade} for r in db.scalars(select(UCRecurso).where(UCRecurso.uc_id == uc.id))],
    }


def matriz_oferta(db: Session, cenario_id: int | None, turma_ids: list[int] | None = None, detalhar: bool = True) -> list[dict]:
    q = select(TurmaUC).join(Turma).where(TurmaUC.ativo.is_(True), Turma.ativo.is_(True))
    if turma_ids is not None:
        q = q.where(TurmaUC.turma_id.in_(turma_ids))
    res = []
    for tuc in db.scalars(q.order_by(TurmaUC.turma_id, TurmaUC.id)):
        info = situacao_carga_horaria(db, cenario_id, tuc)
        if detalhar:
            uc = db.get(UnidadeCurricular, tuc.uc_id)
            turma = db.get(Turma, tuc.turma_id)
            info["instrutores_elegiveis"] = instrutores_elegiveis(db, uc, turma.unidade_id, area_id=area_da_turma(db, turma), nivel=nivel_da_turma(db, turma))
            info["ambientes_compativeis"] = ambientes_compativeis(db, uc, turma, info["divide_grupos"])
        res.append(info)
    return res
