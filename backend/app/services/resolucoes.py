"""Resolver os riscos do semestre: para cada caso, o sistema calcula uma correção concreta e pronta para aceitar.

Usa os mesmos motores de sempre (candidatos à substituição, salas compatíveis, validação central, gerador) e devolve
cada sugestão com uma `acao` que `sugestoes.aplicar` executa. Nada é gravado aqui: aceitar é uma decisão do usuário.

- Aula sem instrutor ou com o instrutor ausente → o substituto mais indicado (livre, da área e com a UC).
- Aula sem sala ou em sala indisponível → a sala compatível livre mais adequada ao tamanho da turma.
- Aula em feriado/dia não letivo → o horário livre mais próximo da turma (mesma semana ou a seguinte).
- UC que depende de um só instrutor → habilitar um segundo instrutor da área, com folga na jornada.
- UC que pode não terminar no prazo → gerar de novo os horários da turma (semestre em edição).
Os demais riscos (pedidos, EPIs, sobrecarga, capacidade, padrão de dias) não têm correção automática: vão para a página certa.

Trocar sala e remarcar valem também com o horário aprovado ou publicado (como a substituição): são ajustes
operacionais, sempre pela validação central, com auditoria e aviso ao instrutor.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import ConflitoValidacao, EntradaInvalida, NaoEncontrado
from app.models import (Alocacao, Ambiente, Bloqueio, CenarioPlanejamento, CompetenciaInstrutor, Instrutor, InstrutorArea, PeriodoHorario,
                        RegistroDecisao, Turma, TurmaUC, UnidadeCurricular)
from app.services import auditoria
from app.services.validacao import AulaProposta, BaseDados, possui_bloqueio, validar_aula

RESOLVIVEIS = {"sem_recurso", "instrutor_ausente", "sala_indisponivel", "nao_letivo", "dependencia", "prazo", "capacidade"}
LINKS = {"solicitacoes": "/solicitacoes", "epis": "/epis", "sobrecarga": "/consultas", "padrao_dias": "/cadastros/turmas",
         "capacidade": "/simulador"}
ESTADOS_AJUSTE = ("em_elaboracao", "em_validacao", "aguardando_aprovacao", "aprovado", "publicado")
LIMITE = 15


def _rot(db: Session, a: Alocacao) -> dict:
    t, uc = db.get(Turma, a.turma_id), db.get(UnidadeCurricular, a.uc_id)
    inst = db.get(Instrutor, a.instrutor_id) if a.instrutor_id else None
    amb = db.get(Ambiente, a.ambiente_id) if a.ambiente_id else None
    return {"caso": f"{t.codigo if t else '?'} · {uc.codigo if uc else '?'} · {a.data:%d/%m} {a.inicio:%H:%M}–{a.fim:%H:%M}",
            "detalhe": f"instrutor: {inst.nome if inst else 'sem instrutor'} · sala: {amb.codigo if amb else 'sem sala'}"}


def _futuras(db: Session, cenario_id: int, unidades, hoje: date) -> list[Alocacao]:
    fim = (db.get(CenarioPlanejamento, cenario_id).periodo_fim or hoje + timedelta(days=120))
    turmas = {t.id for t in db.scalars(select(Turma).where(Turma.simulacao_id.is_(None))) if unidades is None or t.unidade_id in unidades}
    return [a for a in db.scalars(select(Alocacao).where(Alocacao.cenario_id == cenario_id, Alocacao.status == "programada",
                                                         Alocacao.data >= hoje, Alocacao.data <= fim).order_by(Alocacao.inicio)) if a.turma_id in turmas]


def _proposta(a: Alocacao, **kw) -> AulaProposta:
    base = dict(turma_uc_id=a.turma_uc_id, inicio=a.inicio, fim=a.fim, minutos_aula=a.minutos_aula, grupo=a.grupo, instrutor_id=a.instrutor_id,
                ambiente_id=a.ambiente_id, excecao_id=a.excecao_id, alocacao_id=a.id, origem="ajuste")
    base.update(kw)
    return AulaProposta(**base)


# ----------------------------------------------------------------------------- busca de correções
def _substituto(db: Session, cenario_id: int, a: Alocacao, motivo: str) -> dict:
    from app.services import substituicao
    try:
        cand = substituicao.candidatos(db, cenario_id, [a], max_dias=1)["instrutores"]
    except ConflitoValidacao as e:
        return {"motivo_sem": str(e)}
    c = next((x for x in cand if x["grupo"] == "recomendado"), None) or next((x for x in cand if x["grupo"] == "excecao"), None)
    if c is None:
        return {"motivo_sem": "Nenhum instrutor livre neste horário (nem de outra área)."}
    return {"sugestao": f"{c['nome']} assume a aula" + ("" if c["grupo"] == "recomendado" else " (de outra área ou sem a UC: exceção justificada)"),
            "acao": {"tipo": "substituir", "alocacao_ids": [a.id], "substituto_id": c["id"], "motivo": motivo},
            "alternativas": [x["nome"] for x in cand if x["grupo"] in ("recomendado", "excecao") and x["id"] != c["id"]][:4]}


def _sala(db: Session, b: BaseDados, a: Alocacao, evitar: int | None = None) -> dict:
    from app.services.planejamento import ambientes_compativeis
    turma, uc = db.get(Turma, a.turma_id), db.get(UnidadeCurricular, a.uc_id)
    livres = []
    for amb in ambientes_compativeis(db, uc, turma, a.grupo is not None):
        if amb["id"] in (a.ambiente_id, evitar):
            continue
        oc = validar_aula(b, _proposta(a, ambiente_id=amb["id"]), {a.id})
        if not [o for o in oc if o.severidade == "bloqueio" and o.recurso_tipo == "ambiente"]:
            livres.append(amb)
    if not livres:
        return {"motivo_sem": "Nenhuma sala compatível (tipo, capacidade e área) livre neste horário."}
    livres.sort(key=lambda x: abs((x.get("capacidade") or x.get("capacidade_operacional") or 0) - (turma.qtd_alunos or 0)))
    s = livres[0]
    return {"sugestao": f"Passar a aula para {s['codigo']}" + (f" ({s.get('nome')})" if s.get("nome") else ""),
            "acao": {"tipo": "trocar_sala", "alocacao_ids": [a.id], "ambiente_id": s["id"]},
            "alternativas": [x["codigo"] for x in livres[1:5]]}


def _remarcacao(db: Session, b: BaseDados, a: Alocacao, hoje: date, reservados: list | None = None) -> dict:
    """Primeiro horário livre da turma (mesmo instrutor e sala). `reservados` guarda os horários já sugeridos nesta
    leva, para duas sugestões não disputarem o mesmo horário."""
    reservados = reservados if reservados is not None else []
    from app.services.calendario import Calendarios, combinar
    turma = db.get(Turma, a.turma_id)
    cal = Calendarios(db)
    periodos = [p for p in db.scalars(select(PeriodoHorario).where(PeriodoHorario.turno_id == turma.turno_id, PeriodoHorario.ativo.is_(True),
                                                                  PeriodoHorario.excepcional.is_(False)).order_by(PeriodoHorario.ordem))]
    dur = (a.fim - a.inicio)
    seg = a.data - timedelta(days=a.data.weekday())
    fim_sem = turma.data_fim or (hoje + timedelta(days=120))
    for k in range(max(14, (fim_sem - seg).days + 1)):  # da semana da aula até o fim da turma
        d = seg + timedelta(days=k)
        if d < hoje or d == a.data or d.weekday() not in (turma.dias_possiveis or []) or d.weekday() in (turma.dias_ead or []):
            continue
        if not cal.dia_letivo(turma, d)[0]:
            continue
        for i, p in enumerate(periodos):
            if d.weekday() not in (p.dias_semana or []):
                continue
            ini = combinar(d, p.hora_inicio)
            fim = ini + dur
            n = len([q for q in periodos[i:] if d.weekday() in (q.dias_semana or []) and combinar(d, q.hora_fim) <= fim])
            if not n or combinar(d, periodos[i + n - 1].hora_fim) != fim:
                continue
            if any(r[0] < fim and r[1] > ini and (r[2] == a.turma_id or (a.instrutor_id and r[3] == a.instrutor_id)
                                                     or (a.ambiente_id and r[4] == a.ambiente_id)) for r in reservados):
                continue
            if not possui_bloqueio(validar_aula(b, _proposta(a, inicio=ini, fim=fim), {a.id})):
                reservados.append((ini, fim, a.turma_id, a.instrutor_id, a.ambiente_id))
                return {"sugestao": f"Remarcar para {d:%d/%m} ({['seg', 'ter', 'qua', 'qui', 'sex', 'sáb', 'dom'][d.weekday()]}) {ini:%H:%M}–{fim:%H:%M}, mesmo instrutor e sala",
                        "acao": {"tipo": "remarcar", "alocacao_ids": [a.id], "data": d.isoformat(), "periodo_inicio_id": p.id, "num_periodos": n}}
    return {"motivo_sem": "Nenhum horário livre da turma até o fim do período com o mesmo instrutor e sala."}


def _segundo_instrutor(db: Session, cenario_id: int, turma: Turma, uc: UnidadeCurricular, hoje: date) -> dict:
    from app.services.planejamento import _tem_certificacao, area_da_turma, nivel_atende, nivel_da_turma
    area, nivel = area_da_turma(db, turma), nivel_da_turma(db, turma)
    habil = set(db.scalars(select(CompetenciaInstrutor.instrutor_id).where(CompetenciaInstrutor.uc_id == uc.id, CompetenciaInstrutor.ativo.is_(True),
                                                                           CompetenciaInstrutor.nivel != "em_formacao")))
    outras = set(db.scalars(select(InstrutorArea.instrutor_id).where(InstrutorArea.area_id == area))) if area else set()
    seg = hoje - timedelta(days=hoje.weekday())
    cand = []
    for i in db.scalars(select(Instrutor).where(Instrutor.ativo.is_(True), Instrutor.situacao == "ativo", Instrutor.unidade_id == turma.unidade_id)):
        if i.id in habil or not nivel_atende(i.nivel, nivel) or not (i.area_id == area or i.id in outras or getattr(i, "todas_areas", False)):
            continue
        if not _tem_certificacao(db, i.id, uc, hoje):  # UC com certificação obrigatória (ex.: NR-10)
            continue
        horas = (db.scalar(select(func.coalesce(func.sum(Alocacao.minutos_aula), 0)).where(
            Alocacao.cenario_id == cenario_id, Alocacao.instrutor_id == i.id, Alocacao.status != "cancelada",
            Alocacao.data >= seg, Alocacao.data < seg + timedelta(days=28))) or 0) / 60 / 4
        cand.append((horas / float(i.carga_horaria_contratual or 40), i))
    if not cand:
        cert = f" e a certificação {uc.certificacao_exigida}" if uc.certificacao_exigida else ""
        return {"motivo_sem": f"Nenhum outro instrutor da área com o nível exigido{cert} para habilitar. Considere capacitar ou contratar."}
    cand.sort(key=lambda x: x[0])
    pct, i = cand[0]
    return {"sugestao": f"Habilitar {i.nome} na UC (da área, {round(100 * pct)}% da jornada ocupada nas próximas semanas)",
            "acao": {"tipo": "habilitar_instrutor", "instrutor_id": i.id, "uc_id": uc.id, "turma_id": turma.id},
            "alternativas": [x[1].nome for x in cand[1:4]]}


def sugerir(db: Session, cenario_id: int, codigo: str, unidades=None, hoje: date | None = None) -> dict:
    """Uma sugestão por caso do risco (até LIMITE casos), com a ação pronta para aceitar."""
    from app.services import riscos
    hoje = hoje or date.today()
    cen = db.get(CenarioPlanejamento, cenario_id)
    if cen is None:
        raise NaoEncontrado("Semestre não encontrado.")
    if codigo not in RESOLVIVEIS:
        return {"codigo": codigo, "automatico": False, "link": LINKS.get(codigo), "itens": [], "total": 0}
    itens, total = [], 0
    b = BaseDados(db, cenario_id)
    futuras = _futuras(db, cenario_id, unidades, hoje)
    reservados: list = []
    if codigo == "sem_recurso":
        casos = [a for a in futuras if not a.instrutor_id or not a.ambiente_id]
        total = len(casos)
        for a in casos[:LIMITE]:
            it = {"id": f"a{a.id}", **_rot(db, a)}
            it.update(_substituto(db, cenario_id, a, "Aula sem instrutor: sugestão aceita na análise de riscos") if not a.instrutor_id else _sala(db, b, a))
            itens.append(it)
    elif codigo == "instrutor_ausente":
        bloq = {}
        for x in db.scalars(select(Bloqueio).where(Bloqueio.alvo_tipo == "instrutor", Bloqueio.ativo.is_(True), Bloqueio.tipo.notin_(riscos.RESERVAS),
                                                   Bloqueio.fim > datetime.combine(hoje, datetime.min.time()))):
            bloq.setdefault(x.alvo_id, []).append(x)
        casos = [(a, x) for a in futuras if a.instrutor_id for x in bloq.get(a.instrutor_id, []) if x.inicio < a.fim and x.fim > a.inicio]
        total = len(casos)
        for a, x in casos[:LIMITE]:
            it = {"id": f"a{a.id}", **_rot(db, a)}
            it["detalhe"] += f" · ausência: {x.tipo}{(' – ' + x.motivo) if x.motivo else ''}"
            it.update(_substituto(db, cenario_id, a, f"Titular ausente ({x.tipo}): sugestão aceita na análise de riscos"))
            itens.append(it)
    elif codigo == "sala_indisponivel":
        ambs = {x.id: x for x in db.scalars(select(Ambiente))}
        bloq = {}
        for x in db.scalars(select(Bloqueio).where(Bloqueio.alvo_tipo == "ambiente", Bloqueio.ativo.is_(True),
                                                   Bloqueio.fim > datetime.combine(hoje, datetime.min.time()))):
            bloq.setdefault(x.alvo_id, []).append(x)
        casos = [a for a in futuras if a.ambiente_id and (any(x.inicio < a.fim and x.fim > a.inicio for x in bloq.get(a.ambiente_id, []))
                                                         or (a.ambiente_id in ambs and ambs[a.ambiente_id].situacao != "operacional"))]
        total = len(casos)
        for a in casos[:LIMITE]:
            r = _sala(db, b, a, evitar=a.ambiente_id)
            if not r.get("acao"):  # nenhuma outra sala do tipo: remarcar para quando a sala estiver livre
                r2 = _remarcacao(db, b, a, hoje, reservados)
                r = {**r2, "sugestao": r2["sugestao"] + " (sem outra sala do mesmo tipo livre)"} if r2.get("acao") else r
            itens.append({"id": f"a{a.id}", **_rot(db, a), **r})
    elif codigo == "nao_letivo":
        from app.services.calendario import Calendarios
        cal = Calendarios(db)
        turmas = {}
        casos = []
        for a in futuras:
            t = turmas.setdefault(a.turma_id, db.get(Turma, a.turma_id))
            ok, motivo = cal.dia_letivo(t, a.data)
            if not ok:
                casos.append((a, motivo))
        total = len(casos)
        for a, motivo in casos[:LIMITE]:
            it = {"id": f"a{a.id}", **_rot(db, a)}
            it["detalhe"] += f" · {motivo}"
            it.update(_remarcacao(db, b, a, hoje, reservados))
            itens.append(it)
    elif codigo == "dependencia":
        risco = next(r for r in riscos.analisar(db, cenario_id, unidades, hoje)["riscos"] if r["codigo"] == "dependencia")
        vistos = set()
        total = risco["quantidade"]
        for a in futuras:
            if a.turma_uc_id in vistos or len(itens) >= LIMITE:
                continue
            vistos.add(a.turma_uc_id)
            t, uc = db.get(Turma, a.turma_id), db.get(UnidadeCurricular, a.uc_id)
            if not any(i["turma"] == t.codigo and i["uc"] == uc.codigo for i in risco["itens"]):
                continue
            it = {"id": f"u{a.turma_uc_id}", "caso": f"{t.codigo} · {uc.codigo} {uc.nome}",
                  "detalhe": "só um instrutor habilitado: " + next(i["habilitados"] for i in risco["itens"] if i["turma"] == t.codigo and i["uc"] == uc.codigo)}
            it.update(_segundo_instrutor(db, cenario_id, t, uc, hoje))
            itens.append(it)
    elif codigo == "prazo":
        risco = next(r for r in riscos.analisar(db, cenario_id, unidades, hoje)["riscos"] if r["codigo"] == "prazo")
        total = risco["quantidade"]
        editavel = cen.estado in ("em_elaboracao", "em_validacao")
        for i in risco["itens"][:LIMITE]:
            t = db.scalar(select(Turma).where(Turma.codigo == i["turma"], Turma.simulacao_id.is_(None)))
            it = {"id": f"p{t.id if t else i['turma']}{i['uc']}", "caso": f"{i['turma']} · {i['uc']}",
                  "detalhe": f"faltam {i['falta_h']} h; cabem {i['cabe_h']} h até {date.fromisoformat(i['prazo']):%d/%m/%Y}" if i.get("prazo") else f"faltam {i['falta_h']} h"}
            if t is None:
                it["motivo_sem"] = "Turma não encontrada."
            elif not editavel:
                it["motivo_sem"] = ("O semestre está publicado: crie uma proposta de alteração (Semestres e aprovação) e gere os horários "
                                    "da turma nela, ou amplie os dias de aula da UC no cadastro.")
            else:
                it.update({"sugestao": f"Gerar de novo os horários da turma {t.codigo} (o gerador prioriza o prazo)",
                           "acao": {"tipo": "gerar_turma", "turma_id": t.id}})
            itens.append(it)
    elif codigo == "capacidade":
        from app.services import gargalos
        g = gargalos.analisar(db, cenario_id, hoje, cen.periodo_fim or hoje + timedelta(days=120), cen.unidade_id)["gargalos"]
        total = len(g)
        editavel = cen.estado in ("em_elaboracao", "em_validacao")
        for k, x in enumerate(g[:LIMITE]):
            it = {"id": f"g{k}", "caso": x["recurso"] + (f" · {x['turno']}" if x.get("turno") else ""), "detalhe": x["descricao"],
                  "alternativas": x.get("alternativas", [])}
            if x["tipo"] == "deficit_habilitacao":
                cod = x["recurso"].split(" em ", 1)[-1].split(" – ")[0].strip()
                tuc = db.execute(select(TurmaUC, Turma, UnidadeCurricular).join(Turma, Turma.id == TurmaUC.turma_id)
                                 .join(UnidadeCurricular, UnidadeCurricular.id == TurmaUC.uc_id)
                                 .where(UnidadeCurricular.codigo == cod, Turma.simulacao_id.is_(None), TurmaUC.ativo.is_(True))).first()
                if tuc:
                    r = _segundo_instrutor(db, cenario_id, tuc[1], tuc[2], hoje)
                    it.update({k2: v for k2, v in r.items() if k2 != "alternativas"})
                else:
                    it["motivo_sem"] = "UC sem turma ativa."
            elif x["tipo"] == "inviabilidade_calendario" and " – " in x["recurso"]:
                t = db.scalar(select(Turma).where(Turma.codigo == x["recurso"].split(" – ")[0].strip(), Turma.simulacao_id.is_(None)))
                if t is not None and editavel:
                    it.update({"sugestao": f"Gerar de novo os horários da turma {t.codigo} (o gerador prioriza o prazo)",
                               "acao": {"tipo": "gerar_turma", "turma_id": t.id}})
                else:
                    it["motivo_sem"] = ("Semestre publicado: amplie os dias de aula da UC ou o prazo no cadastro da turma, ou gere numa proposta de alteração."
                                        if t is not None else "Turma não encontrada.")
            else:
                it["motivo_sem"] = "Sem correção automática: veja as alternativas (o simulador mostra o impacto)."
            itens.append(it)
    return {"codigo": codigo, "automatico": True, "itens": itens, "total": total, "mostrando": len(itens),
            "com_sugestao": sum(1 for i in itens if i.get("acao")), "estado_semestre": cen.estado}


# ----------------------------------------------------------------------------- ajustes operacionais (aceitar)
def ajustar(db: Session, ctx, cenario_id: int, alocacao_ids: list[int], ambiente_id: int | None = None, data: str | None = None,
            periodo_inicio_id: int | None = None, num_periodos: int | None = None, motivo: str = "") -> dict:
    """Troca a sala ou remarca aulas (também com o horário aprovado/publicado), sempre pela validação central."""
    from app.services.alocacao import DadosAula, resolver_horario, travar_recursos
    from app.services.notificacoes import notificar
    cen = db.get(CenarioPlanejamento, cenario_id)
    if cen is None:
        raise NaoEncontrado("Semestre não encontrado.")
    if cen.estado not in ESTADOS_AJUSTE or cen.tipo == "simulacao":
        raise ConflitoValidacao(f"Não é possível ajustar aulas num semestre '{cen.estado}'.")
    aulas = [a for a in (db.get(Alocacao, int(i)) for i in alocacao_ids or []) if a is not None and a.cenario_id == cenario_id]
    if not aulas:
        raise EntradaInvalida("Nenhuma aula para ajustar.")
    b = BaseDados(db, cenario_id)
    feitas, falhas = 0, []
    for a in aulas:
        if a.status == "realizada":
            falhas.append(f"{a.data:%d/%m}: aula já realizada")
            continue
        kw = {}
        if ambiente_id:
            kw["ambiente_id"] = int(ambiente_id)
        if data:
            turma = db.get(Turma, a.turma_id)
            ini, fim, mins = resolver_horario(db, turma, DadosAula(turma_uc_id=a.turma_uc_id, data=date.fromisoformat(data),
                                                                   periodo_inicio_id=int(periodo_inicio_id), num_periodos=int(num_periodos)))
            kw.update(inicio=ini, fim=fim, minutos_aula=mins)
        travar_recursos(db, cenario_id, [("ambiente", kw.get("ambiente_id", a.ambiente_id)), ("instrutor", a.instrutor_id), ("turma", a.turma_id)])
        oc = validar_aula(b, _proposta(a, **kw), {a.id})
        if possui_bloqueio(oc):
            falhas.append(f"{a.data:%d/%m}: " + "; ".join(o.descricao for o in oc if o.severidade == "bloqueio")[:300])
            continue
        antes = auditoria.snapshot(a)
        if "ambiente_id" in kw:
            a.ambiente_id = kw["ambiente_id"]
        if "inicio" in kw:
            a.inicio, a.fim, a.data, a.minutos_aula = kw["inicio"], kw["fim"], kw["inicio"].date(), kw["minutos_aula"]
            amb = db.get(Ambiente, a.ambiente_id) if a.ambiente_id else None
            a.fim_ambiente = a.fim + timedelta(minutes=(amb.tempo_preparacao_min if amb else 0) or 0)
        a.fixa = True  # o gerador não desfaz o ajuste
        a.observacao = (motivo or "Ajuste aceito na análise de riscos")[:2000]
        a.versao += 1
        db.flush()
        auditoria.registrar(db, ctx, "alocacao.ajuste", "alocacoes", a.id, antes=antes, depois=auditoria.snapshot(a), motivo=motivo)
        db.add(RegistroDecisao(tipo="alteracao_manual", cenario_id=cenario_id, alocacao_id=a.id, usuario_id=getattr(ctx, "id", None), motivo=motivo,
                               dados={"ajuste": "trocar_sala" if ambiente_id and not data else "remarcar", "ambiente_id": a.ambiente_id,
                                      "inicio": a.inicio.isoformat()}))
        if a.instrutor_id:
            amb = db.get(Ambiente, a.ambiente_id) if a.ambiente_id else None
            t = db.get(Turma, a.turma_id)
            notificar(db, a.instrutor_id, "aula", f"Aula da {t.codigo if t else 'turma'} ajustada",
                      f"Agora em {a.data:%d/%m} {a.inicio:%H:%M}–{a.fim:%H:%M}" + (f", sala {amb.codigo}" if amb else "") + ".", "turmas", ctx)
        feitas += 1
    if not feitas:
        raise ConflitoValidacao("O ajuste não passou na validação: " + " | ".join(falhas[:3]))
    return {"ajustadas": feitas, "falhas": falhas}
