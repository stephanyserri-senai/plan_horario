"""Indicadores de ocupação e capacidade, sempre calculados a partir das aulas
gravadas e dos cadastros (sem valores fictícios).

Taxa de ocupação temporal = horas ocupadas / horas efetivamente disponíveis × 100,
onde horas disponíveis = períodos de aula da unidade nos dias letivos do
intervalo, restritos à disponibilidade do ambiente e descontados bloqueios e
manutenções. Utilização da capacidade física é apresentada separadamente.
"""
from __future__ import annotations

import math
from collections import defaultdict
from datetime import date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.services.regras_aula import limite_letivo_efetivo
from app.models import (
    Alocacao,
    Ambiente,
    Bloqueio,
    CenarioPlanejamento,
    Configuracao,
    DisponibilidadeAmbiente,
    DisponibilidadeInstrutor,
    HistoricoAuditoria,
    Instrutor,
    PeriodoHorario,
    TipoAmbiente,
    Turma,
    TurmaUC,
    Turno,
    UnidadeCurricular,
    Validacao,
    VersaoPlanejamento,
)
from app.services.calendario import Calendarios, combinar, minutos
from app.services.planejamento import area_da_turma, instrutores_elegiveis, situacao_carga_horaria

DIAS = ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"]


def limiares(db: Session) -> dict:
    cfg = db.get(Configuracao, "limiares_ocupacao")
    base = {"subutilizado_pct": 30.0, "demanda_excessiva_pct": 85.0, "instrutor_critico_pct": 90.0}
    if cfg:
        base.update(cfg.valor)
    return base


def _overlap(a0, a1, b0, b1) -> float:
    return max(0.0, (min(a1, b1) - max(a0, b0)).total_seconds() / 60)


def periodo_padrao(db: Session, cenario: CenarioPlanejamento) -> tuple[date, date]:
    if cenario.periodo_inicio and cenario.periodo_fim:
        return cenario.periodo_inicio, cenario.periodo_fim
    r = db.execute(select(func.min(Alocacao.data), func.max(Alocacao.data)).where(Alocacao.cenario_id == cenario.id)).first()
    if r and r[0]:
        return r[0], r[1]
    hoje = date.today()
    return hoje, hoje + timedelta(days=27)


def _datas(d0: date, d1: date):
    d = d0
    while d <= d1:
        yield d
        d += timedelta(days=1)


def _semanas(d0: date, d1: date) -> int:
    return max(1, math.ceil(((d1 - d0).days + 1) / 7))


def _rotulo_turno(db, turnos: dict, t, todos) -> str:
    """Nome do turno; com mais de uma unidade no resultado, acrescenta a unidade (ex.: "Manhã – Beira Mar")."""
    if t not in turnos:
        return str(t)
    unidades = {turnos[x].unidade_id for x in todos if x in turnos}
    if len(unidades) <= 1:
        return turnos[t].nome
    from app.models import Unidade
    un = db.get(Unidade, turnos[t].unidade_id)
    return f"{turnos[t].nome} – {un.nome.removeprefix('Unidade ') if un else turnos[t].unidade_id}"


def ocupacao_ambientes(db: Session, cenario_id: int, d0: date, d1: date, unidade_id=None, tipo_ambiente_id=None,
                       ambiente_id=None, turno_id=None, unidades_permitidas=None) -> dict:
    q = select(Ambiente).where(Ambiente.ativo.is_(True))
    if unidade_id:
        q = q.where(Ambiente.unidade_id == unidade_id)
    if unidades_permitidas is not None:
        q = q.where(Ambiente.unidade_id.in_(unidades_permitidas))
    if tipo_ambiente_id:
        q = q.where(Ambiente.tipo_ambiente_id == tipo_ambiente_id)
    if ambiente_id:
        q = q.where(Ambiente.id == ambiente_id)
    ambientes = db.scalars(q.order_by(Ambiente.codigo)).all()
    tipos = {t.id: t for t in db.scalars(select(TipoAmbiente))}
    turnos = {t.id: t for t in db.scalars(select(Turno))}
    cal = Calendarios(db)
    lim = limiares(db)
    periodos_un: dict[int, list[PeriodoHorario]] = defaultdict(list)
    for p in db.scalars(select(PeriodoHorario).where(PeriodoHorario.ativo.is_(True))):
        if turno_id and p.turno_id != turno_id:
            continue
        periodos_un[p.unidade_id].append(p)
    aulas = db.execute(
        select(Alocacao, Turma.qtd_alunos, Turma.num_grupos).join(Turma, Turma.id == Alocacao.turma_id)
        .where(Alocacao.cenario_id == cenario_id, Alocacao.status != "cancelada", Alocacao.data >= d0, Alocacao.data <= d1,
               Alocacao.ambiente_id.isnot(None))).all()
    por_amb = defaultdict(list)
    for a, alunos, ngr in aulas:
        por_amb[a.ambiente_id].append((a, alunos if a.grupo is None else math.ceil(alunos / max(ngr, 1))))

    linhas = []
    tot = defaultdict(float)
    por_turno = defaultdict(lambda: [0.0, 0.0])
    por_dia = defaultdict(lambda: [0.0, 0.0])
    por_unidade = defaultdict(lambda: [0.0, 0.0])
    for amb in ambientes:
        disp_rows = db.scalars(select(DisponibilidadeAmbiente).where(DisponibilidadeAmbiente.ambiente_id == amb.id)).all()
        bloqs = db.scalars(select(Bloqueio).where(Bloqueio.ativo.is_(True), Bloqueio.inicio <= combinar(d1, datetime.max.time()),
                                                  Bloqueio.fim >= combinar(d0, datetime.min.time()),
                                                  ((Bloqueio.alvo_tipo == "ambiente") & (Bloqueio.alvo_id == amb.id))
                                                  | ((Bloqueio.alvo_tipo == "unidade") & (Bloqueio.alvo_id == amb.unidade_id)))).all()
        disp_min = 0.0
        bloq_min = 0.0
        janelas_disp = defaultdict(list)  # data -> [(inicio, fim, turno_id)]
        operacional = amb.situacao == "operacional"
        for d in _datas(d0, d1):
            letivo, _ = cal.dia_letivo_unidade(amb.unidade_id, d)
            if not letivo:
                continue
            for p in periodos_un.get(amb.unidade_id, []):
                if d.weekday() not in (p.dias_semana or []):
                    continue
                ini, fim = combinar(d, p.hora_inicio), combinar(d, p.hora_fim)
                if disp_rows:
                    m = sum(_overlap(ini, fim, combinar(d, j.hora_inicio), combinar(d, j.hora_fim)) for j in disp_rows if j.dia_semana == d.weekday())
                else:
                    m = (fim - ini).total_seconds() / 60
                if m <= 0:
                    continue
                bm = sum(_overlap(ini, fim, b.inicio, b.fim) for b in bloqs)
                bm = min(bm, m)
                if not operacional:
                    bm = m
                bloq_min += bm
                disp_min += m - bm
                if m - bm > 0:
                    janelas_disp[d].append((ini, fim, p.turno_id))
                    por_turno[p.turno_id][1] += m - bm
                    por_dia[d.weekday()][1] += m - bm
                    por_unidade[amb.unidade_id][1] += m - bm
        ocup_min = 0.0
        util_cap = []
        for a, tam in por_amb.get(amb.id, []):
 
            for ini, fim, t in janelas_disp.get(a.data, []):
                o = _overlap(a.inicio, a.fim, ini, fim)
                if o:
                    ocup_min += o
                    por_turno[t][0] += o
                    por_dia[a.data.weekday()][0] += o
                    por_unidade[amb.unidade_id][0] += o
            util_cap.append(100 * tam / amb.capacidade_fisica)
        taxa = 100 * ocup_min / disp_min if disp_min else 0.0
        classif = "sem_disponibilidade" if not disp_min else ("subutilizado" if taxa < lim["subutilizado_pct"] else
                                                               "demanda_excessiva" if taxa > lim["demanda_excessiva_pct"] else "adequado")
        linhas.append({
            "ambiente_id": amb.id, "codigo": amb.codigo, "nome": amb.nome, "unidade_id": amb.unidade_id,
            "tipo": tipos[amb.tipo_ambiente_id].nome if amb.tipo_ambiente_id in tipos else None,
            "especializado": bool(tipos.get(amb.tipo_ambiente_id) and tipos[amb.tipo_ambiente_id].especializado),
            "situacao": amb.situacao, "capacidade_fisica": amb.capacidade_fisica, "capacidade_operacional": amb.capacidade_operacional,
            "horas_disponiveis": round(disp_min / 60, 2), "horas_bloqueadas": round(bloq_min / 60, 2),
            "horas_ocupadas": round(ocup_min / 60, 2), "horas_ociosas": round(max(disp_min - ocup_min, 0) / 60, 2),
            "taxa_ocupacao_pct": round(taxa, 1), "utilizacao_capacidade_fisica_pct": round(sum(util_cap) / len(util_cap), 1) if util_cap else 0.0,
            "aulas": len(por_amb.get(amb.id, [])), "classificacao": classif,
        })
        tot["disp"] += disp_min
        tot["ocup"] += ocup_min
        tot["bloq"] += bloq_min

    def pct(par):
        return round(100 * par[0] / par[1], 1) if par[1] else 0.0
    return {
        "periodo": {"inicio": d0.isoformat(), "fim": d1.isoformat()},
        "resumo": {
            "total_ambientes": len(ambientes),
            "disponiveis": sum(1 for a in ambientes if a.situacao == "operacional"),
            "bloqueados_ou_manutencao": sum(1 for a in ambientes if a.situacao != "operacional"),
            "horas_disponiveis": round(tot["disp"] / 60, 1), "horas_ocupadas": round(tot["ocup"] / 60, 1),
            "horas_ociosas": round(max(tot["disp"] - tot["ocup"], 0) / 60, 1), "horas_bloqueadas": round(tot["bloq"] / 60, 1),
            "taxa_ocupacao_pct": round(100 * tot["ocup"] / tot["disp"], 1) if tot["disp"] else 0.0,
            "subutilizados": sum(1 for l in linhas if l["classificacao"] == "subutilizado"),
            "demanda_excessiva": sum(1 for l in linhas if l["classificacao"] == "demanda_excessiva"),
        },
        "por_turno": [{"turno_id": t, "turno": _rotulo_turno(db, turnos, t, por_turno), "horas_ocupadas": round(v[0] / 60, 1),
                       "horas_disponiveis": round(v[1] / 60, 1), "taxa_ocupacao_pct": pct(v)} for t, v in sorted(por_turno.items())],
        "por_dia_semana": [{"dia": DIAS[d], "horas_ocupadas": round(v[0] / 60, 1), "horas_disponiveis": round(v[1] / 60, 1),
                            "taxa_ocupacao_pct": pct(v)} for d, v in sorted(por_dia.items())],
        "por_unidade": [{"unidade_id": u, "horas_ocupadas": round(v[0] / 60, 1), "horas_disponiveis": round(v[1] / 60, 1),
                         "taxa_ocupacao_pct": pct(v)} for u, v in sorted(por_unidade.items())],
        "ambientes": linhas,
        "limiares": lim,
        "formula": "taxa = horas ocupadas ÷ horas efetivamente disponíveis × 100 (dias letivos, períodos de aula, sem bloqueios)",
    }


def _turno_da_aula(a: Alocacao, turnos_unidade: list[Turno]) -> int | None:
    for t in turnos_unidade:
        if t.hora_inicio <= a.inicio.time() < t.hora_fim:
            return t.id
    return None


def ocupacao_instrutores(db: Session, cenario_id: int, d0: date, d1: date, unidade_id=None, instrutor_id=None,
                         unidades_permitidas=None, mostrar_pessoais=False) -> dict:
    q = select(Instrutor).where(Instrutor.ativo.is_(True))
    if unidade_id:
        q = q.where(Instrutor.unidade_id == unidade_id)
    if unidades_permitidas is not None:
        q = q.where(Instrutor.unidade_id.in_(unidades_permitidas))
    if instrutor_id:
        q = q.where(Instrutor.id == instrutor_id)
    instrutores = db.scalars(q.order_by(Instrutor.nome)).all()
    lim = limiares(db)
    n_sem = _semanas(d0, d1)
    turnos = db.scalars(select(Turno)).all()
    turnos_un = defaultdict(list)
    for t in turnos:
        turnos_un[t.unidade_id].append(t)
    nomes_turno = {t.id: t.nome for t in turnos}
    ambientes = {a.id: a for a in db.scalars(select(Ambiente))}
    cod_turma = dict(db.execute(select(Turma.id, Turma.codigo)).all())
    cod_uc = dict(db.execute(select(UnidadeCurricular.id, UnidadeCurricular.codigo)).all())
    linhas = []
    for inst in instrutores:
        aulas = db.scalars(select(Alocacao).where(Alocacao.cenario_id == cenario_id, Alocacao.instrutor_id == inst.id,
                                                  Alocacao.status != "cancelada", Alocacao.data >= d0, Alocacao.data <= d1)
                           .order_by(Alocacao.inicio)).all()
        disp_sem = sum(minutos(j.hora_fim) - minutos(j.hora_inicio) for j in
                       db.scalars(select(DisponibilidadeInstrutor).where(DisponibilidadeInstrutor.instrutor_id == inst.id))) / 60
        efetiva = min(limite_letivo_efetivo(inst), disp_sem)
        total_h = sum(a.minutos_aula for a in aulas) / 60
        media = total_h / n_sem
        por_semana = defaultdict(float)
        por_turno = defaultdict(float)
        por_unidade = defaultdict(float)
        por_dia = defaultdict(list)
        for a in aulas:
            por_semana[a.data - timedelta(days=a.data.weekday())] += a.minutos_aula / 60
            amb = ambientes.get(a.ambiente_id)
            un = amb.unidade_id if amb else inst.unidade_id
            t = _turno_da_aula(a, turnos_un.get(un, []))
            por_turno[nomes_turno.get(t, "fora de turno")] += a.minutos_aula / 60
            por_unidade[un] += a.minutos_aula / 60
            por_dia[a.data].append((a, un))
        janelas = 0.0
        deslocamentos = 0
        for d, lst in por_dia.items():
            for (a1, _), (a2, _) in zip(lst, lst[1:]):
                gap = (a2.inicio - a1.fim).total_seconds() / 3600
                if 0 < gap < 3:
                    janelas += gap
            deslocamentos += max(0, len({u for _, u in lst}) - 1)
        semanas_excesso = sum(1 for h in por_semana.values() if h > limite_letivo_efetivo(inst) + 1e-6)
        ocup = 100 * media / efetiva if efetiva else 0.0
        linha = {
            "instrutor_id": inst.id, "nome": inst.nome, "matricula": inst.matricula, "unidade_id": inst.unidade_id,
            "carga_contratual_h": float(inst.carga_horaria_contratual), "limite_letivo_h": limite_letivo_efetivo(inst),
            "disponibilidade_declarada_h": round(disp_sem, 2), "capacidade_efetiva_h": round(efetiva, 2),
            "alocada_total_h": round(total_h, 2), "alocada_media_semanal_h": round(media, 2),
            "restante_semanal_h": round(max(efetiva - media, 0), 2), "ocupacao_pct": round(ocup, 1),
            "maior_semana_h": round(max(por_semana.values()), 2) if por_semana else 0.0,
            "por_turno_h": {k: round(v, 2) for k, v in por_turno.items()},
            "por_unidade_h": {str(k): round(v, 2) for k, v in por_unidade.items()},
            "ucs": len({a.uc_id for a in aulas}), "turmas": len({a.turma_id for a in aulas}),
            "turmas_lista": sorted({cod_turma.get(a.turma_id, "?") for a in aulas}), "ucs_lista": sorted({cod_uc.get(a.uc_id, "?") for a in aulas}),
            "por_dia_semana_h": {DIAS[i]: round(sum(a.minutos_aula for a in aulas if a.data.weekday() == i) / 60 / n_sem, 2) for i in range(6)},
            "janelas_h": round(janelas, 2), "deslocamentos": deslocamentos, "semanas_acima_limite": semanas_excesso,
            "critico": ocup >= lim["instrutor_critico_pct"] or semanas_excesso > 0,
        }
        if mostrar_pessoais:
            linha["email"] = inst.email
        linhas.append(linha)
    return {
        "periodo": {"inicio": d0.isoformat(), "fim": d1.isoformat(), "semanas": n_sem},
        "resumo": {
            "instrutores": len(linhas),
            "ocupacao_media_pct": round(sum(l["ocupacao_pct"] for l in linhas) / len(linhas), 1) if linhas else 0.0,
            "criticos": sum(1 for l in linhas if l["critico"]),
            "sem_aulas": sum(1 for l in linhas if l["alocada_total_h"] == 0),
        },
        "instrutores": linhas, "limiares": lim,
        "formula": "ocupação = horas alocadas por semana (média) ÷ capacidade efetiva para ensino (mínimo entre limite letivo e disponibilidade declarada) × 100",
    }


def turmas_ucs(db: Session, cenario_id: int, data_referencia: date | None = None, turma_id=None, curso_id=None, unidade_id=None,
               unidades_permitidas=None) -> dict:
    data_referencia = data_referencia or date.today()
    q = select(TurmaUC).join(Turma).where(TurmaUC.ativo.is_(True), Turma.ativo.is_(True), Turma.simulacao_id.is_(None))
    if turma_id:
        q = q.where(Turma.id == turma_id)
    if curso_id:
        q = q.where(Turma.curso_id == curso_id)
    if unidade_id:
        q = q.where(Turma.unidade_id == unidade_id)
    if unidades_permitidas is not None:
        q = q.where(Turma.unidade_id.in_(unidades_permitidas))
    cal = Calendarios(db)
    linhas = []
    for tuc in db.scalars(q.order_by(TurmaUC.turma_id, TurmaUC.id)):
        info = situacao_carga_horaria(db, cenario_id, tuc)
        turma = db.get(Turma, tuc.turma_id)
        uc = db.get(UnidadeCurricular, tuc.uc_id)
        limite = date.fromisoformat(info["data_limite"])
        aulas = db.scalars(select(Alocacao).where(Alocacao.cenario_id == cenario_id, Alocacao.turma_uc_id == tuc.id,
                                                  Alocacao.status != "cancelada")).all()
        # capacidade restante estimada: dias letivos da turma até o prazo × encontros/semana
        inicio_restante = max(data_referencia, max((a.data for a in aulas), default=data_referencia) + timedelta(days=1),
                              date.fromisoformat(info["data_inicio"]))
        dias_letivos = sum(1 for d in _datas(inicio_restante, limite) if d.weekday() in (turma.dias_possiveis or []) and cal.dia_letivo(turma, d)[0]) if inicio_restante <= limite else 0
        semanas_rest = dias_letivos / max(len(turma.dias_possiveis or [1]), 1)
        capacidade_h = semanas_rest * uc.encontros_semanais * info["horas_por_encontro"]
        if info["restante_h"] <= 0.01:
            risco = "sem_risco"
        elif info["restante_h"] > capacidade_h:
            risco = "alto"
        elif info["restante_h"] > 0.8 * capacidade_h:
            risco = "medio"
        else:
            risco = "baixo"
        dist = defaultdict(float)
        for a in aulas:
            dist[DIAS[a.data.weekday()]] += a.minutos_aula / 60
        elegiveis = instrutores_elegiveis(db, uc, turma.unidade_id, data_referencia, area_da_turma(db, turma))
        nomes_inst = {i.id: i.nome for i in db.scalars(select(Instrutor).where(Instrutor.id.in_({x.instrutor_id for x in aulas if x.instrutor_id})))} if aulas else {}
        info.update({
            "turma_nome": turma.nome, "instrutores": sorted(set(nomes_inst.values())),
            "proxima_aula": (lambda d: d.isoformat() if d else None)(min((a.data for a in aulas if a.data >= data_referencia and a.status == "programada"), default=None)),
            "ultima_aula": (lambda d: d.isoformat() if d else None)(max((a.data for a in aulas), default=None)), "percentual_conclusao": round(100 * info["realizada_h"] / info["total_h"], 1) if info["total_h"] else 0.0,
            "percentual_programado": round(100 * (info["realizada_h"] + info["programada_h"]) / info["total_h"], 1) if info["total_h"] else 0.0,
            "encontros_planejados": len(aulas), "distribuicao_semanal_h": dict(dist),
            "ambientes_utilizados": sorted({a.ambiente_id for a in aulas if a.ambiente_id}),
            "capacidade_restante_estimada_h": round(capacidade_h, 1), "risco_atraso": risco,
            "sem_instrutor_elegivel": not elegiveis, "aulas_sem_instrutor": sum(1 for a in aulas if not a.instrutor_id),
            "aulas_sem_ambiente": sum(1 for a in aulas if not a.ambiente_id),
        })
        linhas.append(info)
    return {"data_referencia": data_referencia.isoformat(), "itens": linhas,
            "resumo": {"turma_ucs": len(linhas), "em_risco_alto": sum(1 for l in linhas if l["risco_atraso"] == "alto"),
                       "em_risco_medio": sum(1 for l in linhas if l["risco_atraso"] == "medio"),
                       "sem_instrutor_elegivel": sum(1 for l in linhas if l["sem_instrutor_elegivel"]),
                       "ch_total_h": round(sum(l["total_h"] for l in linhas), 1),
                       "ch_realizada_h": round(sum(l["realizada_h"] for l in linhas), 1),
                       "ch_programada_h": round(sum(l["programada_h"] for l in linhas), 1),
                       "ch_pendente_h": round(sum(l["restante_h"] for l in linhas), 1)}}


def institucionais(db: Session, cenario_id: int, d0: date, d1: date, unidades_permitidas=None, data_referencia=None) -> dict:
    amb = ocupacao_ambientes(db, cenario_id, d0, d1, unidades_permitidas=unidades_permitidas)
    ins = ocupacao_instrutores(db, cenario_id, d0, d1, unidades_permitidas=unidades_permitidas)
    tu = turmas_ucs(db, cenario_id, data_referencia=data_referencia, unidades_permitidas=unidades_permitidas)
    r = tu["resumo"]
    turmas_incompletas = len({l["turma_id"] for l in tu["itens"] if l["restante_h"] > 0.01 and l["situacao_cadastro"] not in ("concluida", "cancelada")})
    ultima_val = db.scalars(select(Validacao).where(Validacao.cenario_id == cenario_id).order_by(Validacao.id.desc())).first()
    bloqueados = db.scalar(select(func.count()).select_from(HistoricoAuditoria).where(
        HistoricoAuditoria.acao == "alocacao.bloqueada", HistoricoAuditoria.em >= combinar(d0, datetime.min.time()),
        HistoricoAuditoria.em <= combinar(d1, datetime.max.time())))
    salas = sorted([a for a in amb["ambientes"] if a["horas_disponiveis"] > 0], key=lambda a: a["taxa_ocupacao_pct"])
    versoes = db.scalars(select(VersaoPlanejamento).where(VersaoPlanejamento.cenario_id == cenario_id).order_by(VersaoPlanejamento.numero)).all()
    total = r["ch_total_h"] or 1
    return {
        "periodo": amb["periodo"],
        "percentual_aulas_alocadas": round(100 * (r["ch_programada_h"] + r["ch_realizada_h"]) / total, 1) if r["ch_total_h"] else 0.0,
        "percentual_ch_programada": round(100 * r["ch_programada_h"] / total, 1) if r["ch_total_h"] else 0.0,
        "turmas_programacao_incompleta": turmas_incompletas,
        "conflitos_bloqueados": bloqueados,
        "alertas_pendentes": ultima_val.total_alertas if ultima_val else None,
        "bloqueios_ultima_validacao": ultima_val.total_bloqueios if ultima_val else None,
        "ambientes_maior_ocupacao": list(reversed(salas[-5:])),
        "ambientes_maior_ociosidade": salas[:5],
        "instrutores_criticos": [i for i in ins["instrutores"] if i["critico"]],
        "ucs_em_risco": [l for l in tu["itens"] if l["risco_atraso"] in ("alto", "medio")],
        "ambientes": amb["resumo"], "instrutores": ins["resumo"], "turmas_ucs": r,
        "ocupacao_por_turno": amb["por_turno"], "ocupacao_por_dia": amb["por_dia_semana"],
        "evolucao_versoes": [{"versao": v.numero, "estado": v.estado, "criado_em": v.criado_em.isoformat(),
                              "indicadores": v.indicadores} for v in versoes],
    }


def resumo_cenario(db: Session, cenario_id: int) -> dict:
    """Indicadores compactos guardados em versões e usados em comparações."""
    cen = db.get(CenarioPlanejamento, cenario_id)
    d0, d1 = periodo_padrao(db, cen)
    amb = ocupacao_ambientes(db, cenario_id, d0, d1)
    ins = ocupacao_instrutores(db, cenario_id, d0, d1)
    n_aulas = db.scalar(select(func.count()).select_from(Alocacao).where(Alocacao.cenario_id == cenario_id, Alocacao.status != "cancelada"))
    horas = db.scalar(select(func.coalesce(func.sum(Alocacao.minutos_aula), 0)).where(Alocacao.cenario_id == cenario_id, Alocacao.status != "cancelada")) / 60
    return {
        "periodo": amb["periodo"], "aulas": n_aulas, "horas_programadas": round(horas, 1),
        "taxa_ocupacao_ambientes_pct": amb["resumo"]["taxa_ocupacao_pct"], "ocupacao_por_turno": amb["por_turno"],
        "ocupacao_media_instrutores_pct": ins["resumo"]["ocupacao_media_pct"],
        "instrutores_criticos": ins["resumo"]["criticos"],
        "ocupacao_por_instrutor": {str(i["instrutor_id"]): i["ocupacao_pct"] for i in ins["instrutores"]},
        "ocupacao_por_ambiente": {str(a["ambiente_id"]): a["taxa_ocupacao_pct"] for a in amb["ambientes"]},
        "janelas_instrutores_h": round(sum(i["janelas_h"] for i in ins["instrutores"]), 2),
        "deslocamentos": sum(i["deslocamentos"] for i in ins["instrutores"]),
    }
