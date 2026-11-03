"""Impacto da divisão EaD/presencial no planejamento já gerado, e a correção.

Depois de corrigir a carga das UCs (reimportação da matriz ou cadastro), as aulas já programadas podem passar da nova
carga PRESENCIAL (ex.: UC de 24 h com 8 h EaD agora tem só 16 h de aula) ou faltar aula. `impacto` mostra, por turma × UC
(e grupo), o que muda; `aplicar` remove do cenário escolhido as aulas programadas que passam da carga presencial — das
últimas para as primeiras — e NUNCA mexe em aula realizada nem em aula fixa. O que faltar é gerado de novo pelo
gerador de horários (só a carga presencial).
"""
from __future__ import annotations

from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Alocacao, Turma, TurmaUC, UnidadeCurricular
from app.services import auditoria
from app.services.carga_uc import ch_ead, ch_presencial


def _linhas(db: Session, cenario_id: int, unidades=None):
    aulas = db.scalars(select(Alocacao).where(Alocacao.cenario_id == cenario_id, Alocacao.status != "cancelada")
                       .order_by(Alocacao.inicio)).all()
    por_tuc = defaultdict(list)
    for a in aulas:
        por_tuc[a.turma_uc_id].append(a)
    if not por_tuc:
        return []
    tucs = {t.id: t for t in db.scalars(select(TurmaUC).where(TurmaUC.id.in_(list(por_tuc))))}
    ucs = {u.id: u for u in db.scalars(select(UnidadeCurricular).where(UnidadeCurricular.id.in_({t.uc_id for t in tucs.values()})))}
    turmas = {t.id: t for t in db.scalars(select(Turma).where(Turma.id.in_({t.turma_id for t in tucs.values()})))}
    res = []
    for tid, lista in por_tuc.items():
        tuc = tucs.get(tid)
        if tuc is None:
            continue
        uc, turma = ucs[tuc.uc_id], turmas[tuc.turma_id]
        if unidades is not None and turma.unidade_id not in unidades:
            continue
        grupos = sorted({a.grupo for a in lista if a.grupo is not None}) or [None]
        for g in grupos:
            doc = [a for a in lista if g is None or a.grupo in (None, g)]
            realizada = sum(a.minutos_aula for a in doc if a.status == "realizada") + int(float(tuc.ch_realizada or 0) * 60)
            programada = [a for a in doc if a.status != "realizada" and (g is None or a.grupo == g)]
            res.append((tuc, uc, turma, g, realizada, programada, doc))
    return res


def impacto(db: Session, cenario_id: int, unidades=None) -> dict:
    itens = []
    for tuc, uc, turma, g, realizada, programada, _doc in _linhas(db, cenario_id, unidades):
        alvo = int(ch_presencial(uc) * 60)
        prog = sum(a.minutos_aula for a in programada)
        excesso = realizada + prog - alvo
        remover, fixas = [], []
        if excesso > 0:
            resta = excesso
            for a in sorted(programada, key=lambda x: x.inicio, reverse=True):
                if resta <= 0:
                    break
                (fixas if a.fixa else remover).append(a)
                if not a.fixa:
                    resta -= a.minutos_aula
        falta = max(0, alvo - realizada - prog)
        if falta < 60:  # sobra menor que uma aula: arredondamento normal do fechamento da carga, não é falta
            falta = 0
        if not remover and not fixas and falta == 0:
            continue
        itens.append({"turma_uc_id": tuc.id, "turma": turma.codigo, "uc": uc.codigo, "uc_nome": uc.nome, "grupo": g,
                      "modalidade": uc.modalidade, "total_h": uc.carga_horaria_total, "ead_h": ch_ead(uc), "presencial_h": ch_presencial(uc),
                      "divisao_confirmada": bool(uc.divisao_confirmada),
                      "realizadas_h": round(realizada / 60, 1), "programadas_h": round(prog / 60, 1),
                      "excesso_h": round(max(0, excesso) / 60, 1), "falta_h": round(falta / 60, 1),
                      "aulas_a_remover": len(remover), "horas_a_remover": round(sum(a.minutos_aula for a in remover) / 60, 1),
                      "aulas_fixas_mantidas": len(fixas), "so_ead": ch_presencial(uc) <= 0,
                      "realizadas_acima": realizada > alvo})
    itens.sort(key=lambda x: (x["turma"], x["uc"], x["grupo"] or 0))
    return {"cenario_id": cenario_id, "itens": itens,
            "resumo": {"turma_ucs": len({i["turma_uc_id"] for i in itens}), "aulas_a_remover": sum(i["aulas_a_remover"] for i in itens),
                       "horas_a_remover": round(sum(i["horas_a_remover"] for i in itens), 1),
                       "horas_faltando": round(sum(i["falta_h"] for i in itens), 1),
                       "realizadas_acima": sum(1 for i in itens if i["realizadas_acima"])}}


def aplicar(db: Session, ctx, cenario_id: int, turma_uc_ids: list[int] | None = None, unidades=None) -> dict:
    """Remove do cenário (editável) as aulas programadas acima da carga presencial. Realizadas e fixas ficam."""
    from app.services.alocacao import obter_cenario_editavel
    obter_cenario_editavel(db, cenario_id, bloquear=True)
    alvo_ids = set(turma_uc_ids or [])
    removidas, horas = 0, 0.0
    for tuc, uc, _turma, _g, realizada, programada, _doc in _linhas(db, cenario_id, unidades):
        if alvo_ids and tuc.id not in alvo_ids:
            continue
        excesso = realizada + sum(a.minutos_aula for a in programada) - int(ch_presencial(uc) * 60)
        for a in sorted(programada, key=lambda x: x.inicio, reverse=True):
            if excesso <= 0:
                break
            if a.fixa or a.status == "realizada":
                continue
            antes = auditoria.snapshot(a)
            excesso -= a.minutos_aula
            horas += a.minutos_aula / 60
            removidas += 1
            db.delete(a)
            auditoria.registrar(db, ctx, "alocacao.remover", "alocacoes", a.id, antes=antes,
                                motivo=f"correção da carga presencial de {uc.codigo} ({ch_presencial(uc):g} h presenciais de {uc.carga_horaria_total} h)")
    db.flush()
    depois = impacto(db, cenario_id, unidades)
    return {"aulas_removidas": removidas, "horas_removidas": round(horas, 1), "horas_faltando": depois["resumo"]["horas_faltando"],
            "pendente": depois["itens"]}
