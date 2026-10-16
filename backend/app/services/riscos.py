"""Riscos ao desenvolvimento do semestre: tudo o que pode atrapalhar as turmas daqui para a frente.

Cada risco traz a gravidade (alta, média, baixa), quantos casos há, o que fazer e onde resolver. Nada é
alterado: é uma análise para apoiar a decisão, a partir dos cadastros e da grade do semestre.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (Alocacao, Ambiente, Bloqueio, CenarioPlanejamento, Instrutor, SolicitacaoInstrutor, Turma, TurmaUC,
                        UnidadeCurricular)

ORDEM = {"alta": 0, "media": 1, "baixa": 2}
RESERVAS = {"planejamento", "projeto"}  # PL/PJ: o instrutor está na escola (não é ausência)


def _risco(codigo, titulo, gravidade, itens, descricao, o_que_fazer, link=None, max_itens=40):
    return {"codigo": codigo, "titulo": titulo, "gravidade": gravidade, "quantidade": len(itens), "descricao": descricao,
            "o_que_fazer": o_que_fazer, "link": link, "itens": itens[:max_itens]}


def analisar(db: Session, cenario_id: int, unidades=None, hoje: date | None = None) -> dict:
    from app.services import analise_ocupacao, gargalos, indicadores
    from app.services.calendario import Calendarios
    from app.services.planejamento import area_da_turma, instrutores_elegiveis, nivel_da_turma
    from app.services.regras_institucionais import conformidade
    cen = db.get(CenarioPlanejamento, cenario_id)
    hoje = hoje or date.today()
    fim = cen.periodo_fim or hoje + timedelta(days=120)
    turmas = {t.id: t for t in db.scalars(select(Turma).where(Turma.simulacao_id.is_(None)))
              if unidades is None or t.unidade_id in unidades}
    ucs = {u.id: u for u in db.scalars(select(UnidadeCurricular))}
    insts = {i.id: i for i in db.scalars(select(Instrutor))}
    ambs = {a.id: a for a in db.scalars(select(Ambiente))}
    futuras = [a for a in db.scalars(select(Alocacao).where(Alocacao.cenario_id == cenario_id, Alocacao.status == "programada",
                                                            Alocacao.data >= hoje, Alocacao.data <= fim).order_by(Alocacao.inicio))
               if a.turma_id in turmas]
    rot = lambda a: {"data": a.data.isoformat(), "horario": f"{a.inicio:%H:%M}–{a.fim:%H:%M}", "turma": turmas[a.turma_id].codigo,  # noqa: E731
                     "uc": ucs[a.uc_id].codigo if a.uc_id in ucs else "", "instrutor": insts[a.instrutor_id].nome if a.instrutor_id in insts else "—",
                     "sala": ambs[a.ambiente_id].codigo if a.ambiente_id in ambs else "—"}
    riscos = []

    # 1) carga que não cabe até o prazo
    tu = indicadores.turmas_ucs(db, cenario_id, hoje, unidades_permitidas=unidades)
    prazo = [{"turma": i["turma_codigo"], "uc": i["uc_codigo"], "falta_h": i["restante_h"], "cabe_h": i["capacidade_restante_estimada_h"],
              "prazo": i["data_limite"], "risco": i["risco_atraso"]} for i in tu["itens"] if i["risco_atraso"] in ("alto", "medio")]
    riscos.append(_risco("prazo", "UCs que podem não terminar no prazo", "alta" if any(p["risco"] == "alto" for p in prazo) else "media", prazo,
                         "A carga horária que falta é maior (ou quase) do que cabe nos dias letivos até o prazo da UC.",
                         "Abra o risco: o sistema sugere gerar de novo os horários da turma (semestre em edição) ou indica o ajuste no cadastro.", "/cronograma"))

    # 2) aulas sem instrutor ou sem sala
    sem = [{**rot(a), "falta": " e ".join(x for x, ok in (("instrutor", a.instrutor_id), ("sala", a.ambiente_id)) if not ok)}
           for a in futuras if not a.instrutor_id or not a.ambiente_id]
    riscos.append(_risco("sem_recurso", "Aulas sem instrutor ou sem sala", "alta", sem,
                         "Aulas já marcadas que ainda não têm instrutor ou sala definidos.",
                         "Abra o risco e aceite a sugestão de cada aula: o sistema indica o instrutor ou a sala livre e compatível.", "/grade"))

    # 3) instrutor ausente (licença, folga, treinamento, indisponibilidade) em dia de aula
    bloq_i = defaultdict(list)
    for b in db.scalars(select(Bloqueio).where(Bloqueio.alvo_tipo == "instrutor", Bloqueio.ativo.is_(True), Bloqueio.tipo.notin_(RESERVAS),
                                               Bloqueio.fim > datetime.combine(hoje, time()))):
        bloq_i[b.alvo_id].append(b)
    ausente = [{**rot(a), "motivo": f"{b.tipo}: {b.motivo or ''}".strip(": ")}
               for a in futuras if a.instrutor_id for b in bloq_i.get(a.instrutor_id, []) if b.inicio < a.fim and b.fim > a.inicio]
    riscos.append(_risco("instrutor_ausente", "Instrutor ausente em dia de aula", "alta", ausente,
                         "O instrutor tem licença, folga, treinamento (TR) ou outra indisponibilidade no horário de uma aula marcada.",
                         "Abra o risco e aceite o substituto sugerido para cada aula (livre, da área e com a UC; senão, com exceção justificada).", "/grade"))

    # 4) sala em manutenção ou bloqueada em dia de aula
    bloq_a = defaultdict(list)
    for b in db.scalars(select(Bloqueio).where(Bloqueio.alvo_tipo == "ambiente", Bloqueio.ativo.is_(True),
                                               Bloqueio.fim > datetime.combine(hoje, time()))):
        bloq_a[b.alvo_id].append(b)
    sala = [{**rot(a), "motivo": f"{b.tipo}: {b.motivo or ''}".strip(": ")}
            for a in futuras if a.ambiente_id for b in bloq_a.get(a.ambiente_id, []) if b.inicio < a.fim and b.fim > a.inicio]
    sala += [{**rot(a), "motivo": f"sala {ambs[a.ambiente_id].situacao}"} for a in futuras
             if a.ambiente_id in ambs and ambs[a.ambiente_id].situacao != "operacional"]
    riscos.append(_risco("sala_indisponivel", "Sala ou laboratório indisponível em dia de aula", "alta", sala,
                         "A sala está em manutenção, interditada ou bloqueada no horário de uma aula marcada.",
                         "Abra o risco e aceite a sala compatível livre sugerida (ou a remarcação para quando a sala estiver livre).", "/grade"))

    # 5) aula em feriado, recesso ou dia não letivo
    cal = Calendarios(db)
    nao_letivo = []
    for a in futuras:
        ok, motivo = cal.dia_letivo(turmas[a.turma_id], a.data)
        if not ok:
            nao_letivo.append({**rot(a), "motivo": motivo})
    riscos.append(_risco("nao_letivo", "Aulas em feriado ou dia não letivo", "media", nao_letivo,
                         "Aulas marcadas em dias que o calendário não considera letivos.", "Abra o risco e aceite a remarcação sugerida: o primeiro horário livre da turma com o mesmo instrutor e sala.", "/grade"))

    # 6) UC que depende de um único instrutor (se ele faltar, ninguém da casa substitui)
    unico, vistos = [], set()
    for a in futuras:
        if a.turma_uc_id in vistos:
            continue
        vistos.add(a.turma_uc_id)
        t, uc = turmas[a.turma_id], ucs.get(a.uc_id)
        if uc is None or uc.categoria == "transversal":
            continue
        eleg = instrutores_elegiveis(db, uc, t.unidade_id, hoje, area_da_turma(db, t), nivel=nivel_da_turma(db, t))
        if len(eleg) <= 1:
            unico.append({"turma": t.codigo, "uc": uc.codigo, "habilitados": eleg[0]["nome"] if eleg else "nenhum"})
    riscos.append(_risco("dependencia", "UCs que dependem de um só instrutor", "media", unico,
                         "Só um instrutor está habilitado para a UC: uma falta, licença ou treinamento dele deixa a turma sem aula.",
                         "Abra o risco e aceite habilitar o segundo instrutor sugerido (da área, com o nível e a certificação exigidos e com folga).", "/cadastros/instrutores"))

    # 7) instrutores acima do teto de 90% em alguma semana
    rk = analise_ocupacao.ranking(db, cenario_id, hoje, fim, unidades, limite=500)
    sobre = [{"instrutor": i["nome"], "media_pct": i["ocupacao_pct"], "pico_pct": i["pico_pct"], "maior_semana_h": i["maior_semana_h"]}
             for i in rk["instrutores_mais"] if i["pico_pct"] > 90 + 1e-6]
    riscos.append(_risco("sobrecarga", "Instrutores acima do teto de 90% em alguma semana", "media", sobre,
                         "Na semana mais cheia o instrutor passa de 90% da jornada com aula (sem turno de planejamento): risco de desgaste e de não ter quem substitua.",
                         "Redistribua aulas para quem tem folga (ranking de ocupação em Consultas).", "/consultas"))

    # 8) falta de capacidade (salas, laboratórios ou instrutores compatíveis)
    g = gargalos.analisar(db, cenario_id, hoje, fim, cen.unidade_id)
    cap = [{"tipo": x["tipo"].replace("_", " "), "recurso": x["recurso"], "falta_h_semana": x.get("deficit_h"), "descricao": x["descricao"]}
           for x in g["gargalos"]]
    riscos.append(_risco("capacidade", "Falta de sala, laboratório ou instrutor compatível", "alta" if cap else "baixa", cap,
                         "A demanda semanal das turmas passa da capacidade dos recursos compatíveis (salas do tipo exigido, instrutores habilitados).",
                         "Abra o risco: cada caso traz a sugestão do sistema (quando há correção automática) ou as alternativas.", None))

    # 9) solicitações de folga/substituição aguardando decisão
    pend = []
    for s in db.scalars(select(SolicitacaoInstrutor).where(SolicitacaoInstrutor.status == "pendente", SolicitacaoInstrutor.data_fim >= hoje)):
        i = insts.get(s.instrutor_id)
        if i is None or (unidades is not None and i.unidade_id not in unidades):
            continue
        pend.append({"instrutor": i.nome, "pedido": s.tipo, "de": s.data_inicio.isoformat(), "ate": s.data_fim.isoformat(), "justificativa": s.justificativa[:120]})
    riscos.append(_risco("solicitacoes", "Pedidos de folga ou substituição sem decisão", "media" if pend else "baixa", pend,
                         "Instrutores pediram folga ou substituição e o coordenador ainda não decidiu.", "Decida em Solicitações dos instrutores.", "/solicitacoes"))

    # 10) EPIs a comprar/separar e entregar com prazo vencido ou próximo
    from app.services import epis
    av = epis.avisos(db, unidades, hoje)
    riscos.append(_risco("epis", "EPIs não entregues no prazo", "alta" if av["atrasados"] else "media" if av["proximos"] else "baixa",
                         [{"turma": i["turma"], "epi": i["nome"], "quantidade": i["quantidade"], "prazo": i["prazo"],
                           "estado": i["situacao_rotulo"]} for i in av["itens"]],
                         "EPIs que o curso exige e ainda não foram entregues à turma, com prazo vencido ou nos próximos 7 dias: sem EPI a aula prática não acontece.",
                         "Compre ou separe os EPIs e marque a entrega no controle de EPIs.", "/epis"))

    # 11) turmas fora do padrão de dias
    conf = conformidade(db, unidades)
    riscos.append(_risco("padrao_dias", "Turmas fora do padrão de dias", "baixa", conf,
                         "Turmas que não seguem 5 dias presenciais, 4 + 1 EAD ou só sábado (e não são de aperfeiçoamento/empresa).",
                         "Ajuste os dias da turma no cadastro.", "/regras"))

    riscos.sort(key=lambda r: (r["quantidade"] == 0, ORDEM[r["gravidade"]], -r["quantidade"]))
    ativos = [r for r in riscos if r["quantidade"]]
    return {"referencia": hoje.isoformat(), "fim": fim.isoformat(), "riscos": riscos, "gargalos": g["gargalos"],
            "resumo": {"alta": sum(1 for r in ativos if r["gravidade"] == "alta"), "media": sum(1 for r in ativos if r["gravidade"] == "media"),
                       "baixa": sum(1 for r in ativos if r["gravidade"] == "baixa"), "casos": sum(r["quantidade"] for r in ativos),
                       "aulas_futuras": len(futuras)}}
