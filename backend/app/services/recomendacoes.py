"""Módulo de recomendação explicável.

Responde perguntas de planejamento com cálculos sobre os dados cadastrados.
Nunca inventa disponibilidade, competências ou resultados, e nunca autoriza
violação de restrição obrigatória: toda alternativa proposta é verificada pela
validação central (ou indicada explicitamente como estimativa agregada).

Formato de cada recomendação:
  pergunta, problema, dados_utilizados, alternativas, restricoes_atendidas,
  impacto, limitacoes, antes, depois
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import CenarioPlanejamento, PeriodoHorario, Turma, TurmaUC, Turno, UnidadeCurricular
from app.services import gargalos as g_srv
from app.services import indicadores, objetivo
from app.services.calendario import Calendarios, combinar
from app.services.planejamento import ambientes_compativeis, area_da_turma, instrutores_elegiveis, nivel_da_turma, situacao_carga_horaria
from app.services.validacao import BLOQUEIO, AulaProposta, BaseDados, validar_aula

REGRAS_INSTRUTOR = {"INSTRUTOR_SOBREPOSICAO", "INSTRUTOR_FORA_DISPONIBILIDADE", "INSTRUTOR_SEM_DISPONIBILIDADE", "JORNADA_DIARIA",
                    "LIMITE_SEMANAL", "INTERJORNADA", "DESLOCAMENTO_INSUFICIENTE", "BLOQUEIO_INSTRUTOR", "INSTRUTOR_NAO_HABILITADO"}
REGRAS_AMBIENTE = {"AMBIENTE_SOBREPOSICAO", "AMBIENTE_FORA_DISPONIBILIDADE", "BLOQUEIO_AMBIENTE", "AMBIENTE_INDISPONIVEL",
                   "RECURSO_AUSENTE", "RECURSO_CONFLITO", "CAPACIDADE_FISICA"}
REGRAS_TURMA = {"TURMA_SOBREPOSICAO", "DIA_NAO_LETIVO", "BLOQUEIO_TURMA", "BLOQUEIO_UNIDADE", "FORA_FUNCIONAMENTO"}


def _semana_referencia(db: Session, turma: Turma, tuc: TurmaUC) -> date:
    cal = Calendarios(db)
    d = max(tuc.data_inicio or turma.data_inicio, turma.data_inicio)
    seg = d - timedelta(days=d.weekday())
    # primeira semana com ao menos um dia letivo
    for _ in range(10):
        if any(cal.dia_letivo(turma, seg + timedelta(days=k))[0] for k in turma.dias_possiveis or []):
            return seg
        seg += timedelta(days=7)
    return seg


def explicar_nao_alocacao(db: Session, cenario_id: int, turma_uc_id: int, grupo: int | None = None) -> dict:
    """Por que uma turma não conseguiu horário? Qual recurso está impedindo?"""
    tuc = db.get(TurmaUC, turma_uc_id)
    turma = db.get(Turma, tuc.turma_id)
    uc = db.get(UnidadeCurricular, tuc.uc_id)
    info = situacao_carga_horaria(db, cenario_id, tuc)
    elegiveis = instrutores_elegiveis(db, uc, turma.unidade_id, area_id=area_da_turma(db, turma), nivel=nivel_da_turma(db, turma))
    ambs = ambientes_compativeis(db, uc, turma, grupo is not None)
    seg = _semana_referencia(db, turma, tuc)
    b = BaseDados(db, cenario_id).precarregar()
    ps = db.scalars(select(PeriodoHorario).where(PeriodoHorario.unidade_id == turma.unidade_id, PeriodoHorario.ativo.is_(True),
                                                 *( [PeriodoHorario.turno_id == turma.turno_id] if turma.turno_id else []))
                    .order_by(PeriodoHorario.turno_id, PeriodoHorario.ordem)).all()
    L = uc.duracao_bloco_periodos
    motivos = Counter()
    candidatos = 0
    viaveis = []
    turma_livre = inst_livre = amb_livre = 0
    for k in turma.dias_possiveis or []:
        d = seg + timedelta(days=k)
        seq = [p for p in ps if d.weekday() in (p.dias_semana or [])]
        por_turno = defaultdict(list)
        for p in seq:
            por_turno[p.turno_id].append(p)
        for lst in por_turno.values():
            for i in range(len(lst) - L + 1):
                bloco = lst[i:i + L]
                ini, fim = combinar(d, bloco[0].hora_inicio), combinar(d, bloco[-1].hora_fim)
                mins = sum((p.hora_fim.hour * 60 + p.hora_fim.minute) - (p.hora_inicio.hour * 60 + p.hora_inicio.minute) for p in bloco)
                candidatos += 1
                base = AulaProposta(turma_uc_id=tuc.id, inicio=ini, fim=fim, minutos_aula=mins, grupo=grupo)
                oc_t = [o for o in validar_aula(b, base) if o.severidade == BLOQUEIO and o.regra in REGRAS_TURMA]
                if oc_t:
                    motivos.update(o.regra for o in oc_t)
                    continue
                turma_livre += 1
                insts_ok = []
                for inst in elegiveis:
                    oc = [o for o in validar_aula(b, AulaProposta(**{**base.__dict__, "instrutor_id": inst["id"]}))
                          if o.severidade == BLOQUEIO and o.regra in REGRAS_INSTRUTOR]
                    if oc:
                        motivos.update(o.regra for o in oc)
                    else:
                        insts_ok.append(inst)
                rooms_ok = []
                for amb in ambs:
                    oc = [o for o in validar_aula(b, AulaProposta(**{**base.__dict__, "ambiente_id": amb["id"]}))
                          if o.severidade == BLOQUEIO and o.regra in REGRAS_AMBIENTE]
                    if oc:
                        motivos.update(o.regra for o in oc)
                    else:
                        rooms_ok.append(amb)
                inst_livre += bool(insts_ok)
                amb_livre += bool(rooms_ok)
                if insts_ok and rooms_ok:
                    viaveis.append({"data": d.isoformat(), "inicio": ini.strftime("%H:%M"), "fim": fim.strftime("%H:%M"),
                                    "instrutores": [i["nome"] for i in insts_ok], "ambientes": [a["codigo"] for a in rooms_ok],
                                    # aceitar a sugestão: aula neste bloco com o primeiro instrutor e a primeira sala livres
                                    "acao": {"tipo": "alocar_aula", "turma_uc_id": tuc.id, "data": d.isoformat(), "periodo_inicio_id": bloco[0].id,
                                             "num_periodos": len(bloco), "grupo": grupo, "instrutor_id": insts_ok[0]["id"], "ambiente_id": rooms_ok[0]["id"],
                                             "rotulo": f"{insts_ok[0]['nome']} · {rooms_ok[0]['codigo']}"}})
    if not elegiveis:
        recurso, problema = "instrutor", f"Não há instrutor habilitado na matriz de competências para {uc.codigo} – {uc.nome} na unidade."
    elif not ambs:
        recurso, problema = "ambiente", f"Nenhum ambiente é tecnicamente compatível (tipo, capacidade {turma.qtd_alunos}, acessibilidade, equipamentos) com {uc.codigo}."
    elif turma_livre == 0:
        recurso, problema = "turma", "A turma não possui períodos livres no turno/dias permitidos na semana de referência."
    elif inst_livre == 0:
        recurso, problema = "instrutor", "Nos horários livres da turma, nenhum instrutor habilitado está disponível."
    elif amb_livre == 0:
        recurso, problema = "ambiente", "Nos horários livres da turma, nenhum ambiente compatível está livre."
    elif len(viaveis) < info["encontros_semanais"]:
        recurso, problema = "combinação", f"Há {len(viaveis)} horário(s) com turma, instrutor e ambiente livres simultaneamente, mas a UC precisa de {info['encontros_semanais']} encontro(s) semanal(is)."
    else:
        recurso, problema = "nenhum", "Existem horários viáveis na semana de referência; a não alocação decorreu da competição com outras atividades ou dos limites semanais/datas."
    alternativas = []
    if viaveis:
        alternativas.append({"tipo": "horarios_viaveis", "descricao": "Horários validados pela regra central na semana de referência.", "itens": viaveis[:10]})
    if recurso in ("instrutor", "combinação"):
        alternativas.append({"tipo": "instrutores", "descricao": "Ampliar disponibilidade ou habilitar instrutores; instrutores habilitados atuais:",
                             "itens": [i["nome"] for i in elegiveis]})
    if recurso in ("ambiente", "combinação"):
        alternativas.append({"tipo": "ambientes", "descricao": "Ambientes compatíveis (verifique ampliação de horário ou liberação):",
                             "itens": [a["codigo"] for a in ambs]})
    analise_inst = None
    if recurso in ("instrutor", "combinação"):
        # quem poderia dar a aula, por que não pode (inclusive o teto de 90%) e o que mudar no horário
        from app.services import diagnostico_instrutor
        analise_inst = diagnostico_instrutor.analisar(db, cenario_id, tuc.id)
        problema = f"{problema} {analise_inst['resumo']}"
        alternativas = [{"tipo": s["tipo"], "descricao": s["descricao"], "acao": s.get("acao")} for s in analise_inst["sugestoes"]] + \
                       [a for a in alternativas if a["tipo"] != "instrutores"]
    turnos_alt = [t.nome for t in db.scalars(select(Turno).where(Turno.unidade_id == turma.unidade_id, Turno.id != turma.turno_id))]
    if turnos_alt:
        alternativas.append({"tipo": "turno", "descricao": "Avaliar mudança de turno no simulador (impacto calculado antes de aplicar).", "itens": turnos_alt})
    return {
        "pergunta": f"Por que {turma.codigo} – {uc.codigo}{f' (grupo {grupo})' if grupo else ''} não conseguiu horário?",
        "problema": problema, "recurso_limitante": recurso,
        "dados_utilizados": {"semana_referencia": seg.isoformat(), "blocos_candidatos": candidatos, "blocos_com_turma_livre": turma_livre,
                             "blocos_com_instrutor_livre": inst_livre, "blocos_com_ambiente_livre": amb_livre,
                             "instrutores_habilitados": len(elegiveis), "ambientes_compativeis": len(ambs),
                             "carga_restante_h": info["restante_h"], "motivos_bloqueio_mais_frequentes": dict(motivos.most_common(6))},
        "alternativas": alternativas, "analise_instrutores": analise_inst,
        "restricoes_atendidas": "Os horários listados passaram por todas as restrições obrigatórias da validação central.",
        "impacto": f"{len(viaveis)} bloco(s) viável(is) identificado(s) na semana de referência.",
        "limitacoes": "Análise na semana de referência; semanas com feriados ou bloqueios pontuais podem diferir. Os horários viáveis são independentes entre si: usar um pode inviabilizar outro.",
        "antes": {"restante_h": info["restante_h"]}, "depois": None,
    }


def impacto_mudanca_turno(db: Session, cenario_id: int, turma_id: int, novo_turno_id: int) -> dict:
    """O que acontece se uma turma mudar de turno? (estimativa agregada de capacidade)"""
    turma = db.get(Turma, turma_id)
    cen = db.get(CenarioPlanejamento, cenario_id)
    d0, d1 = indicadores.periodo_padrao(db, cen)
    antes = g_srv.analisar(db, cenario_id, d0, d1)
    original = turma.turno_id
    try:
        turma.turno_id = novo_turno_id
        db.flush()
        depois = g_srv.analisar(db, cenario_id, d0, d1)
    finally:
        turma.turno_id = original
        db.flush()
        db.rollback()  # garante que nada é persistido
    novo = db.get(Turno, novo_turno_id)

    def deficit(r):
        return round(sum(g.get("deficit_h", 0) for g in r["gargalos"]), 1)
    return {
        "pergunta": f"O que acontece se a turma {turma.codigo} mudar para o turno {novo.nome if novo else novo_turno_id}?",
        "problema": "Avaliação de impacto antes de alterar o cadastro.",
        "dados_utilizados": {"periodo": [d0.isoformat(), d1.isoformat()], "demandas": antes["demandas_consideradas"]},
        "alternativas": [], "restricoes_atendidas": "Estimativa agregada; nenhuma aula foi alterada.",
        "impacto": f"Déficit total de capacidade passaria de {deficit(antes)} h para {deficit(depois)} h semanais.",
        "limitacoes": "Simulação agregada de capacidade: a viabilidade final depende da geração completa da grade (use o simulador completo).",
        "antes": {"deficit_total_h": deficit(antes), "gargalos": len(antes["gargalos"])},
        "depois": {"deficit_total_h": deficit(depois), "gargalos": len(depois["gargalos"]), "detalhes": depois["gargalos"][:10]},
    }


def impacto_ampliar_ambiente(db: Session, cenario_id: int, ambiente_id: int, horas_semana: float) -> dict:
    cen = db.get(CenarioPlanejamento, cenario_id)
    d0, d1 = indicadores.periodo_padrao(db, cen)
    antes = g_srv.analisar(db, cenario_id, d0, d1)
    depois = g_srv.analisar(db, cenario_id, d0, d1, horas_extra_ambiente={ambiente_id: horas_semana})

    def deficit_amb(r):
        return round(sum(g["deficit_h"] for g in r["gargalos"] if g["tipo"] in ("deficit_turno", "deficit_capacidade_total")), 1)
    return {
        "pergunta": f"Qual o impacto de ampliar em {horas_semana} h semanais (por turno) a disponibilidade do ambiente #{ambiente_id}?",
        "problema": "Avaliação de ampliação de capacidade.", "dados_utilizados": {"periodo": [d0.isoformat(), d1.isoformat()]},
        "alternativas": [], "restricoes_atendidas": "Estimativa agregada (fluxo máximo); nenhum cadastro foi alterado.",
        "impacto": f"Déficit de ambientes: {deficit_amb(antes)} h → {deficit_amb(depois)} h semanais.",
        "limitacoes": "Considera apenas capacidade semanal agregada; não substitui a geração completa da grade.",
        "antes": {"deficit_ambientes_h": deficit_amb(antes)}, "depois": {"deficit_ambientes_h": deficit_amb(depois)},
    }


def liberar_capacidade(db: Session, cenario_id: int) -> dict:
    """Quais alterações liberariam capacidade? Cruza gargalos com recursos ociosos compatíveis."""
    cen = db.get(CenarioPlanejamento, cenario_id)
    d0, d1 = indicadores.periodo_padrao(db, cen)
    garg = g_srv.analisar(db, cenario_id, d0, d1)
    amb = indicadores.ocupacao_ambientes(db, cenario_id, d0, d1)
    ociosos = {a["codigo"]: a for a in amb["ambientes"] if a["classificacao"] == "subutilizado"}
    sugestoes = []
    for g in garg["gargalos"]:
        compat = [c for c in g.get("ambientes_compativeis", []) if c in ociosos]
        sugestoes.append({"gargalo": g["descricao"], "tipo": g["tipo"], "deficit_h": g.get("deficit_h"),
                          "ambientes_compativeis_ociosos": [{"codigo": c, "horas_ociosas": ociosos[c]["horas_ociosas"],
                                                             "taxa_ocupacao_pct": ociosos[c]["taxa_ocupacao_pct"]} for c in compat],
                          "alternativas": g.get("alternativas", [])})
    return {"pergunta": "Quais alterações liberariam capacidade?", "problema": f"{len(garg['gargalos'])} gargalo(s) identificado(s).",
            "dados_utilizados": {"periodo": [d0.isoformat(), d1.isoformat()], "ambientes_subutilizados": list(ociosos)},
            "alternativas": sugestoes, "restricoes_atendidas": "Somente ambientes tecnicamente compatíveis são indicados.",
            "impacto": None, "limitacoes": garg["observacao"], "antes": garg["resumo"], "depois": None}


def melhor_cenario(db: Session, cenario_ids: list[int], criterio: str, pesos: dict | None = None) -> dict:
    """Qual cenário reduz mais as janelas / causa menos mudanças?"""
    avals = [objetivo.avaliar_cenario(db, c, pesos) for c in cenario_ids]
    linhas = []
    for a in avals:
        v = next(c for c in a["criterios"] if c["criterio"] == criterio)
        linhas.append({"cenario_id": a["cenario_id"], "valor": v["valor_bruto"], "unidade": v["unidade"], "pontuacao_total": a["pontuacao_total"]})
    linhas.sort(key=lambda l: l["valor"])
    return {"pergunta": f"Qual cenário minimiza '{criterio}'?", "problema": None,
            "dados_utilizados": {"cenarios": cenario_ids, "pesos": avals[0]["pesos"] if avals else None},
            "alternativas": linhas, "restricoes_atendidas": "Avaliação sobre as aulas gravadas de cada cenário.",
            "impacto": (f"Cenário #{linhas[0]['cenario_id']} tem o menor valor ({linhas[0]['valor']} {linhas[0]['unidade']})." if linhas else None),
            "limitacoes": "Valores normalizados por semana com aulas.", "antes": None, "depois": None}


def ucs_em_risco(db: Session, cenario_id: int, data_referencia: date | None = None) -> dict:
    tu = indicadores.turmas_ucs(db, cenario_id, data_referencia)
    risco = [i for i in tu["itens"] if i["risco_atraso"] in ("alto", "medio")]
    return {"pergunta": "Quais UCs apresentam risco de não conclusão?", "problema": f"{len(risco)} turma×UC com risco.",
            "dados_utilizados": {"data_referencia": tu["data_referencia"]},
            "alternativas": [{"turma": i["turma_codigo"], "uc": i["uc_codigo"], "restante_h": i["restante_h"],
                              "capacidade_restante_estimada_h": i["capacidade_restante_estimada_h"], "risco": i["risco_atraso"],
                              "data_limite": i["data_limite"]} for i in risco],
            "restricoes_atendidas": None, "impacto": None,
            "limitacoes": "Capacidade restante estimada = dias letivos restantes × encontros semanais × horas por encontro.",
            "antes": tu["resumo"], "depois": None}
