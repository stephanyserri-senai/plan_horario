"""Substituição de instrutor em aulas já programadas.

Para imprevistos (falta, afastamento, ninguém da área disponível): o substituto pode ser de
outra área ou não ter a UC cadastrada — isso fica registrado como exceção justificada do
tipo "regra_academica" com o motivo informado. Conflitos reais (o substituto já tem aula no
horário, fora da disponibilidade, jornada, certificação obrigatória) continuam bloqueando.
Vale também para semestres aprovados/publicados, porque só troca o instrutor (horário e sala
não mudam). A aula fica fixa para o gerador de horários não desfazer a troca, e o titular
original fica guardado para desfazer depois.

Presença do substituto no turno da aula:
- em PL (planejamento) ou PJ (projeto): está na escola, então pode assumir até no mesmo dia;
  o PL/PJ daquele turno vira a aula;
- turno vazio (sem aula, PL ou PJ): pode ser acionado, desde que a substituição seja planejada
  com pelo menos 1 dia de antecedência (no próprio dia ele não está na escola).
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import ConflitoValidacao, EntradaInvalida, NaoEncontrado
from app.models import Alocacao, Bloqueio, CenarioPlanejamento, ExcecaoAutorizada, Instrutor, Turma, UnidadeCurricular
from app.services import auditoria
from app.services.alocacao import travar_recursos
from app.services.notificacoes import notificar
from app.services.validacao import AulaProposta, BaseDados, validar_aula

ESTADOS_SUBSTITUICAO = ("em_elaboracao", "em_validacao", "aguardando_aprovacao", "aprovado", "publicado")
RESERVAS = {"planejamento": "PL", "projeto": "PJ"}
ANTECEDENCIA_DIAS = 1  # turno vazio: acionar com pelo menos 1 dia de antecedência


def hoje() -> date:
    return date.today()


def _reserva(b: BaseDados, instrutor_id: int, ini, fim) -> Bloqueio | None:
    """PL/PJ do instrutor que cobre o horário (ele está na escola)."""
    return next((x for x in b.bloqueios("instrutor", instrutor_id, ini, fim) if x.tipo in RESERVAS), None)


def _sem_antecedencia(dia: date) -> str | None:
    limite = hoje() + timedelta(days=ANTECEDENCIA_DIAS)
    if dia < limite:
        return (f"turno vazio em {dia:%d/%m}: só pode ser acionado com pelo menos {ANTECEDENCIA_DIAS} dia de antecedência "
                f"(para esta data, só quem está em PL ou PJ)")
    return None
EXCECIONAVEIS = {"INSTRUTOR_OUTRA_AREA", "INSTRUTOR_NAO_HABILITADO"}


def _cenario(db: Session, cenario_id: int) -> CenarioPlanejamento:
    cen = db.get(CenarioPlanejamento, cenario_id)
    if cen is None:
        raise NaoEncontrado("Semestre/cenário não encontrado.")
    if cen.estado not in ESTADOS_SUBSTITUICAO or cen.tipo == "simulacao":
        raise ConflitoValidacao(f"Não é possível registrar substituição em um cenário '{cen.estado}'.")
    return cen


def aulas_alvo(db: Session, cenario_id: int, alocacao_id: int | None = None, instrutor_id: int | None = None,
               inicio: date | None = None, fim: date | None = None, turma_uc_id: int | None = None) -> list[Alocacao]:
    """Uma aula, ou todas as aulas do instrutor no período (opcionalmente só de uma turma × UC)."""
    if alocacao_id:
        a = db.get(Alocacao, alocacao_id)
        if a is None or a.cenario_id != cenario_id:
            raise NaoEncontrado("Aula não encontrada neste semestre.")
        return [a]
    if not instrutor_id or not inicio:
        raise EntradaInvalida("Escolha a aula, ou o instrutor ausente e o período.")
    q = select(Alocacao).where(Alocacao.cenario_id == cenario_id, Alocacao.instrutor_id == instrutor_id, Alocacao.status != "cancelada",
                               Alocacao.data >= inicio, Alocacao.data <= (fim or inicio))
    if turma_uc_id:
        q = q.where(Alocacao.turma_uc_id == turma_uc_id)
    return list(db.scalars(q.order_by(Alocacao.inicio)))


def _blocos(aulas: list[Alocacao]) -> list[dict]:
    """Agrupa os períodos de um mesmo dia/turma×UC num bloco (uma aula de turno inteiro)."""
    g = defaultdict(list)
    for a in aulas:
        g[(a.data, a.turma_uc_id, a.grupo)].append(a)
    return [{"data": d, "turma_uc_id": tuc, "grupo": gr, "inicio": min(x.inicio for x in xs), "fim": max(x.fim for x in xs),
             "minutos": sum(x.minutos_aula for x in xs), "ids": [x.id for x in xs]} for (d, tuc, gr), xs in sorted(g.items(), key=lambda k: (k[0][0], k[0][1]))]


def candidatos(db: Session, cenario_id: int, aulas: list[Alocacao], max_dias: int = 12) -> dict:
    """Instrutores para assumir as aulas: livres e da área (recomendados), livres mas de outra área ou sem a UC
    (com justificativa), livres só em parte, e indisponíveis. Avaliados pela validação central."""
    from app.models import Area, CompetenciaInstrutor
    from app.services.areas import areas_do_recurso
    if not aulas:
        return {"aulas": 0, "dias": 0, "instrutores": []}
    _cenario(db, cenario_id)
    blocos = _blocos(aulas)
    amostra = blocos[:max_dias]
    b = BaseDados(db, cenario_id).precarregar()
    ignorar = {a.id for a in aulas}
    atuais = {a.instrutor_id for a in aulas}
    turmas = {t.id: t for t in db.scalars(select(Turma).where(Turma.id.in_({a.turma_id for a in aulas})))}
    unidades = {t.unidade_id for t in turmas.values()}
    ucs = {a.uc_id for a in aulas}
    areas = {a.id: a.nome for a in db.scalars(select(Area))}
    comps = defaultdict(set)
    for c in db.scalars(select(CompetenciaInstrutor).where(CompetenciaInstrutor.uc_id.in_(ucs), CompetenciaInstrutor.ativo.is_(True))):
        comps[c.instrutor_id].add(c.uc_id)
    res = []
    for i in db.scalars(select(Instrutor).where(Instrutor.ativo.is_(True), Instrutor.situacao == "ativo")):
        if i.id in atuais:
            continue
        bloqueados, precisa_exc, motivos, presenca = 0, False, [], set()
        for bl in amostra:
            oc = validar_aula(b, AulaProposta(turma_uc_id=bl["turma_uc_id"], inicio=bl["inicio"], fim=bl["fim"], minutos_aula=bl["minutos"],
                                              grupo=bl["grupo"], instrutor_id=i.id, origem="substituicao"), ignorar)
            proprios = [o for o in oc if o.recurso_tipo == "instrutor" and o.severidade == "bloqueio"]
            impeditivos = [o for o in proprios if o.regra not in EXCECIONAVEIS]
            if impeditivos:
                bloqueados += 1
                motivos += [f"{bl['data']:%d/%m}: {o.descricao}" for o in impeditivos]
                continue
            r = _reserva(b, i.id, bl["inicio"], bl["fim"])
            if r is None and (falta := _sem_antecedencia(bl["data"])):
                bloqueados += 1
                motivos.append(falta)
                continue
            presenca.add(RESERVAS[r.tipo] if r else "vazio")
            if proprios:  # só outra área / sem a UC: assume com exceção justificada
                precisa_exc = True
                motivos += [o.descricao for o in proprios]
        grupo = ("indisponivel" if bloqueados == len(amostra) else "parcial" if bloqueados else "excecao" if precisa_exc else "recomendado")
        if grupo == "indisponivel" and i.unidade_id not in unidades:
            continue  # de outra unidade e sem horário: só polui a lista
        todas, ars = areas_do_recurso(db, i)
        res.append({"id": i.id, "nome": i.nome, "grupo": grupo, "dias_livres": len(amostra) - bloqueados, "dias_avaliados": len(amostra),
                    "area": "todas as áreas" if todas else ", ".join(sorted(areas[x] for x in ars if x in areas)) or None,
                    "ministra_uc": bool(comps.get(i.id, set()) & ucs), "outra_unidade": i.unidade_id not in unidades,
                    # PL/PJ = está na escola; vazio = precisa ser acionado com antecedência
                    "presenca": sorted(presenca, key=["PL", "PJ", "vazio"].index), "na_escola": bool(presenca) and "vazio" not in presenca,
                    "motivos": list(dict.fromkeys(motivos))[:4]})
    ordem = {"recomendado": 0, "excecao": 1, "parcial": 2, "indisponivel": 3}
    res.sort(key=lambda x: (ordem[x["grupo"]], not x["na_escola"], x["outra_unidade"], not x["ministra_uc"], -x["dias_livres"], x["nome"]))
    return {"aulas": len(aulas), "dias": len(blocos), "dias_avaliados": len(amostra), "instrutores": res,
            "hoje": hoje().isoformat(), "antecedencia_dias": ANTECEDENCIA_DIAS}


def _descrever(db: Session, aulas: list[Alocacao]) -> str:
    turmas = {t.id: t.codigo for t in db.scalars(select(Turma).where(Turma.id.in_({a.turma_id for a in aulas})))}
    ucs = {u.id: u.codigo for u in db.scalars(select(UnidadeCurricular).where(UnidadeCurricular.id.in_({a.uc_id for a in aulas})))}
    partes = defaultdict(set)
    for a in aulas:
        partes[f"{turmas.get(a.turma_id)} · {ucs.get(a.uc_id)}"].add(a.data)
    return "; ".join(f"{k} em {', '.join(d.strftime('%d/%m') for d in sorted(ds)[:8])}{'…' if len(ds) > 8 else ''}" for k, ds in partes.items())


def substituir(db: Session, ctx, cenario_id: int, aulas: list[Alocacao], substituto_id: int, motivo: str, somente_validar: bool = False) -> dict:
    motivo = (motivo or "").strip()
    if len(motivo) < 10:
        raise EntradaInvalida("Explique o motivo da substituição (mínimo de 10 caracteres). Ex.: falta do titular por motivo de saúde.")
    cen = _cenario(db, cenario_id)
    sub = db.get(Instrutor, int(substituto_id))
    if sub is None or not sub.ativo:
        raise NaoEncontrado("Instrutor substituto não encontrado.")
    if not aulas:
        raise EntradaInvalida("Nenhuma aula encontrada para substituir no período informado.")
    travar_recursos(db, cenario_id, [("instrutor", sub.id)] + [("instrutor", a.instrutor_id) for a in aulas])
    sp = db.begin_nested()
    exc = ExcecaoAutorizada(tipo="regra_academica", justificativa=f"Substituição de instrutor: {motivo}", autorizado_por_id=ctx.id)
    db.add(exc)
    db.flush()
    b = BaseDados(db, cenario_id)
    ok, falhas, usou_exc, feitas, convertidas = [], [], False, [], []
    for a in aulas:
        rot = {"alocacao_id": a.id, "data": a.data.isoformat(), "horario": f"{a.inicio:%H:%M}–{a.fim:%H:%M}"}
        if a.status == "realizada":
            falhas.append({**rot, "motivos": ["aula já realizada"]})
            continue
        if a.instrutor_id == sub.id:
            falhas.append({**rot, "motivos": [f"{sub.nome} já é o instrutor desta aula"]})
            continue
        outra = db.get(ExcecaoAutorizada, a.excecao_id) if a.excecao_id else None
        exc_id = a.excecao_id if outra is not None and outra.tipo != "regra_academica" else exc.id
        p = AulaProposta(turma_uc_id=a.turma_uc_id, inicio=a.inicio, fim=a.fim, minutos_aula=a.minutos_aula, grupo=a.grupo, instrutor_id=sub.id,
                         ambiente_id=a.ambiente_id, excecao_id=exc_id, alocacao_id=a.id, origem="substituicao")
        oc = validar_aula(b, p, {a.id})
        bloq = [o for o in oc if o.severidade == "bloqueio" and o.recurso_tipo == "instrutor"]
        if bloq:
            falhas.append({**rot, "motivos": [o.descricao for o in bloq][:3]})
            continue
        reserva = _reserva(b, sub.id, a.inicio, a.fim)
        if reserva is None and (falta := _sem_antecedencia(a.data)):
            falhas.append({**rot, "motivos": [falta]})
            continue
        if reserva is not None:
            convertidas.append(reserva)
        usou_exc = usou_exc or (exc_id == exc.id and any(o.regra == "EXCECAO_REGRA_ACADEMICA" for o in oc))
        ok.append({**rot, "avisos": [o.descricao for o in oc if o.regra in ("EXCECAO_REGRA_ACADEMICA", "SUBSTITUTO_EM_PL_PJ")][:3]})
        if somente_validar:
            continue
        antes = auditoria.snapshot(a)
        titular = a.instrutor_titular_id or a.instrutor_id
        a.instrutor_titular_id = titular if titular != sub.id else None
        a.instrutor_id = sub.id
        precisa = any(o.regra == "EXCECAO_REGRA_ACADEMICA" for o in oc)
        a.excecao_id = exc_id if exc_id != exc.id else (exc.id if precisa else None)
        a.fixa = True  # o gerador de horários não desfaz a substituição
        a.observacao = f"Substituição: {motivo}"[:2000]
        a.versao += 1
        feitas.append((a, antes, titular))
    if somente_validar or not feitas:
        sp.rollback()
        return {"substituidas": 0, "possiveis": len(ok), "falhas": falhas, "aulas": ok, "previa": True, "cenario_publicado": cen.estado == "publicado"}
    if not usou_exc:
        db.delete(exc)  # ninguém precisou da exceção (substituto da mesma área e com a UC)
    viraram_aula = []
    for r in {x.id: x for x in convertidas}.values():  # o PL/PJ do substituto naquele turno vira a aula
        viraram_aula.append(f"{RESERVAS[r.tipo]} de {r.inicio:%d/%m}")
        auditoria.registrar(db, ctx, "bloqueio.excluir", "bloqueios", r.id, antes=auditoria.snapshot(r), motivo=f"Substituição: {motivo}")
        db.delete(r)
    try:
        db.flush()
        sp.commit()
    except (IntegrityError, DBAPIError):
        sp.rollback()
        raise ConflitoValidacao("Outro usuário alterou a agenda do substituto ao mesmo tempo. Recarregue e tente de novo.")
    for a, antes, _t in feitas:
        auditoria.registrar(db, ctx, "alocacao.substituir", "alocacoes", a.id, antes=antes, depois=auditoria.snapshot(a), motivo=motivo)
    aulas_feitas = [a for a, _, _ in feitas]
    resumo = _descrever(db, aulas_feitas)
    titulares = defaultdict(list)
    for a, _, t in feitas:
        titulares[t].append(a)
    nomes = {i.id: i.nome for i in db.scalars(select(Instrutor).where(Instrutor.id.in_(set(titulares) | {sub.id})))}
    situacao = "" if cen.estado == "publicado" else " (horário ainda em planejamento)"
    for t, xs in titulares.items():
        conv = f" Seu {', '.join(viraram_aula)} vira(m) aula." if viraram_aula else ""
        notificar(db, sub.id, "substituicao", f"Você vai substituir {nomes.get(t, 'outro instrutor')}",
                  f"{len(xs)} aula(s): {_descrever(db, xs)}. Motivo: {motivo}{situacao}.{conv}", "turmas", ctx)
        notificar(db, t, "substituicao", f"{sub.nome} vai substituir você", f"{len(xs)} aula(s): {_descrever(db, xs)}. Motivo: {motivo}{situacao}", "turmas", ctx)
    return {"substituidas": len(feitas), "falhas": falhas, "aulas": ok, "resumo": resumo, "excecao_id": exc.id if usou_exc else None,
            "pl_pj_convertidos": viraram_aula,
            "previa": False, "cenario_publicado": cen.estado == "publicado"}


def desfazer(db: Session, ctx, alocacao_ids: list[int], motivo: str | None = None) -> dict:
    """Devolve as aulas ao instrutor titular (se ele estiver livre)."""
    feitas, falhas = [], []
    for aid in alocacao_ids:
        a = db.get(Alocacao, int(aid))
        if a is None or not a.instrutor_titular_id:
            falhas.append({"alocacao_id": aid, "motivos": ["aula sem substituição registrada"]})
            continue
        _cenario(db, a.cenario_id)
        travar_recursos(db, a.cenario_id, [("instrutor", a.instrutor_titular_id)])
        exc = db.get(ExcecaoAutorizada, a.excecao_id) if a.excecao_id else None
        exc_id = None if exc is not None and exc.justificativa.startswith("Substituição de instrutor") else a.excecao_id
        p = AulaProposta(turma_uc_id=a.turma_uc_id, inicio=a.inicio, fim=a.fim, minutos_aula=a.minutos_aula, grupo=a.grupo,
                         instrutor_id=a.instrutor_titular_id, ambiente_id=a.ambiente_id, excecao_id=exc_id, alocacao_id=a.id)
        oc = validar_aula(BaseDados(db, a.cenario_id), p, {a.id})
        bloq = [o for o in oc if o.severidade == "bloqueio" and o.recurso_tipo == "instrutor"]
        if bloq:
            falhas.append({"alocacao_id": a.id, "data": a.data.isoformat(), "motivos": [o.descricao for o in bloq][:3]})
            continue
        antes = auditoria.snapshot(a)
        sub = a.instrutor_id
        a.instrutor_id, a.instrutor_titular_id, a.excecao_id = a.instrutor_titular_id, None, exc_id
        a.observacao, a.versao = None, a.versao + 1
        db.flush()
        auditoria.registrar(db, ctx, "alocacao.desfazer_substituicao", "alocacoes", a.id, antes=antes, depois=auditoria.snapshot(a), motivo=motivo)
        feitas.append((a, sub))
    por_par = defaultdict(list)
    for a, sub in feitas:
        por_par[(a.instrutor_id, sub)].append(a)
    nomes = {i.id: i.nome for i in db.scalars(select(Instrutor))}
    for (tit, sub), xs in por_par.items():
        notificar(db, tit, "substituicao", "Suas aulas voltaram para você", f"{len(xs)} aula(s): {_descrever(db, xs)} (substituição por {nomes.get(sub)} desfeita).", "turmas", ctx)
        notificar(db, sub, "substituicao", "Substituição cancelada", f"Você não vai mais dar {len(xs)} aula(s): {_descrever(db, xs)}.", "turmas", ctx)
    return {"desfeitas": len(feitas), "falhas": falhas}
