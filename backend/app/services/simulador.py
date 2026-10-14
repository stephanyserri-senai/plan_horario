"""Simulador de novas ofertas.

- Simulação AGREGADA: acrescenta a demanda das novas turmas à análise de
  gargalos (fluxo máximo) sem gravar nada no planejamento.
- Simulação COMPLETA: cria turmas isoladas (turmas.simulacao_id), copia o
  cenário base para um cenário do tipo 'simulacao' e executa o gerador de
  horários apenas para as novas turmas, mantendo todo o resto fixo. Os
  horários publicados nunca são alterados; cenários de simulação nunca são
  publicados. A viabilidade final só é afirmada quando existe uma grade que
  respeita todas as restrições.
"""
from __future__ import annotations

import copy
import math
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import EntradaInvalida, NaoEncontrado
from app.models import (
    CenarioPlanejamento,
    Curso,
    ExecucaoOtimizacao,
    MatrizCurricular,
    SimulacaoCapacidade,
    Turma,
    TurmaUC,
    Turno,
    UnidadeCurricular,
)
from app.services import auditoria, cenarios, gargalos, indicadores, otimizacao
from app.services.planejamento import ambientes_compativeis, instrutores_elegiveis, minutos_por_periodo


def _ucs_da_oferta(db: Session, p: dict) -> list[UnidadeCurricular]:
    q = select(UnidadeCurricular).where(UnidadeCurricular.matriz_id == p["matriz_id"], UnidadeCurricular.ativo.is_(True))
    if p.get("uc_ids"):
        q = q.where(UnidadeCurricular.id.in_(p["uc_ids"]))
    return db.scalars(q.order_by(UnidadeCurricular.sequencia, UnidadeCurricular.id)).all()


def _validar_parametros(db: Session, p: dict):
    for k in ("curso_id", "matriz_id", "unidade_id", "quantidade_turmas", "alunos_por_turma", "data_inicio", "data_fim"):
        if p.get(k) in (None, ""):
            raise EntradaInvalida(f"Parâmetro obrigatório ausente: {k}")
    if not db.get(Curso, p["curso_id"]) or not db.get(MatrizCurricular, p["matriz_id"]):
        raise EntradaInvalida("Curso ou matriz inexistente.")
    if date.fromisoformat(p["data_fim"]) < date.fromisoformat(p["data_inicio"]):
        raise EntradaInvalida("A data de término deve ser posterior ao início.")


def _distribuir_ucs(ucs, d0: date, d1: date, sequencial: bool):
    """Janela de execução de cada UC: em paralelo (todo o período) ou
    sequencial (proporcional à carga horária, na ordem da matriz)."""
    if not sequencial:
        return {u.id: (d0, d1) for u in ucs}
    total = sum(u.carga_horaria_total for u in ucs) or 1
    dias = (d1 - d0).days + 1
    res, cur = {}, d0
    for u in ucs:
        n = max(7, round(dias * u.carga_horaria_total / total))
        fim = min(d1, cur + timedelta(days=n - 1))
        res[u.id] = (cur, fim)
        cur = fim + timedelta(days=1)
    return res


def simular_agregada(db: Session, p: dict, cenario_base_id: int) -> dict:
    _validar_parametros(db, p)
    d0, d1 = date.fromisoformat(p["data_inicio"]), date.fromisoformat(p["data_fim"])
    ucs = _ucs_da_oferta(db, p)
    if not ucs:
        raise EntradaInvalida("A matriz selecionada não possui UCs.")
    janelas = _distribuir_ucs(ucs, d0, d1, p.get("ucs_sequenciais", True))
    fake = Turma(id=-1, codigo="SIM", nome="Simulada", curso_id=p["curso_id"], matriz_id=p["matriz_id"], unidade_id=p["unidade_id"],
                 qtd_alunos=p["alunos_por_turma"], num_grupos=p.get("num_grupos", 1), data_inicio=d0, data_fim=d1,
                 turno_id=p.get("turno_id"), dias_possiveis=p.get("dias_semana", [0, 1, 2, 3, 4]), necessidades_acessibilidade=p.get("acessibilidade", False))
    mpp = minutos_por_periodo(db, p["unidade_id"])
    extras = []
    for n in range(int(p["quantidade_turmas"])):
        for uc in ucs:
            grupos = fake.num_grupos if (uc.divide_grupos and fake.num_grupos > 1) else 1
            ambs = ambientes_compativeis(db, uc, fake, grupos > 1)
            insts = instrutores_elegiveis(db, uc, p["unidade_id"], d0)
            ini, fim = janelas[uc.id]
            encontros = p.get("encontros_semanais") or uc.encontros_semanais
            for g in range(grupos):
                extras.append(gargalos.Demanda(
                    chave=f"sim{n}-{uc.id}-{g}", turma_id=-(n + 1), turma_codigo=f"NOVA-{n + 1}", turno_id=p.get("turno_id"),
                    unidade_id=p["unidade_id"], uc_id=uc.id, uc_codigo=uc.codigo, horas_semana=encontros * uc.duracao_bloco_periodos * mpp / 60,
                    tamanho=math.ceil(fake.qtd_alunos / grupos), tipos=frozenset(t.id for t in uc.tipos_ambiente),
                    ambientes=[a["id"] for a in ambs], instrutores=[i["id"] for i in insts],
                    recursos_moveis={a["id"]: a["requer_recursos_moveis"] for a in ambs}, restante_h=uc.carga_horaria_total,
                    data_inicio=ini, data_limite=fim, virtual=True))
    antes = gargalos.analisar(db, cenario_base_id, d0, d1, unidade_id=p["unidade_id"])
    depois = gargalos.analisar(db, cenario_base_id, d0, d1, unidade_id=p["unidade_id"], demandas_extras=extras)
    amb = indicadores.ocupacao_ambientes(db, cenario_base_id, d0, d1, unidade_id=p["unidade_id"])
    ins = indicadores.ocupacao_instrutores(db, cenario_base_id, d0, d1, unidade_id=p["unidade_id"])
    turnos = {t.id: t.nome for t in db.scalars(select(Turno).where(Turno.unidade_id == p["unidade_id"]))}
    horas_adicionais = sum(e.horas_semana for e in extras)
    novos_garg = [g for g in depois["gargalos"] if any(i.get("virtual") for i in g.get("itens", []))]
    deficit_novo = sum(g["deficit_h"] for g in depois["gargalos"]) - sum(g["deficit_h"] for g in antes["gargalos"])
    compat_por_uc = []
    for uc in ucs:
        ambs = ambientes_compativeis(db, uc, fake, uc.divide_grupos and fake.num_grupos > 1)
        insts = instrutores_elegiveis(db, uc, p["unidade_id"], d0)
        compat_por_uc.append({"uc": uc.codigo, "nome": uc.nome, "ambientes_compativeis": [a["codigo"] for a in ambs],
                              "instrutores_habilitados": [i["nome"] for i in insts]})
    if deficit_novo <= 0.01 and all(c["ambientes_compativeis"] and c["instrutores_habilitados"] for c in compat_por_uc):
        viab = "provavel"
    elif any(not c["ambientes_compativeis"] or not c["instrutores_habilitados"] for c in compat_por_uc):
        viab = "inviavel_sem_novos_recursos"
    else:
        viab = "condicionada"
    condicoes = sorted({a for g in novos_garg for a in g.get("alternativas", [])})
    return {
        "tipo": "agregada",
        "viabilidade_estimada": viab,
        "aviso": "Estimativa de capacidade agregada (semanal). Confirme com a simulação completa de horários.",
        "carga_horaria_adicional_semanal_h": round(horas_adicionais, 1),
        "compatibilidade_por_uc": compat_por_uc,
        "capacidade_por_turno": [{"turno": t["turno"], "taxa_ocupacao_atual_pct": t["taxa_ocupacao_pct"],
                                  "horas_ociosas": round(t["horas_disponiveis"] - t["horas_ocupadas"], 1)} for t in amb["por_turno"]],
        "laboratorios": [{"codigo": a["codigo"], "taxa_ocupacao_pct": a["taxa_ocupacao_pct"], "horas_ociosas": a["horas_ociosas"]}
                         for a in amb["ambientes"] if a["especializado"]],
        "instrutores_com_folga": [{"nome": i["nome"], "restante_semanal_h": i["restante_semanal_h"]} for i in ins["instrutores"] if i["restante_semanal_h"] > 0],
        "gargalos_gerados": novos_garg, "deficit_adicional_h": round(max(deficit_novo, 0), 1),
        "antes": {"gargalos": len(antes["gargalos"]), "deficit_h": round(sum(g["deficit_h"] for g in antes["gargalos"]), 1), "resumo": antes["resumo"]},
        "depois": {"gargalos": len(depois["gargalos"]), "deficit_h": round(sum(g["deficit_h"] for g in depois["gargalos"]), 1), "resumo": depois["resumo"]},
        "condicoes_necessarias": condicoes, "turnos": turnos,
    }


def _criar_turmas_simuladas(db: Session, sim: SimulacaoCapacidade, p: dict) -> list[Turma]:
    d0, d1 = date.fromisoformat(p["data_inicio"]), date.fromisoformat(p["data_fim"])
    ucs = _ucs_da_oferta(db, p)
    janelas = _distribuir_ucs(ucs, d0, d1, p.get("ucs_sequenciais", True))
    turmas = []
    for n in range(int(p["quantidade_turmas"])):
        t = Turma(codigo=f"SIM{sim.id}-{n + 1}", nome=f"Simulação {sim.id} – turma {n + 1}", curso_id=p["curso_id"], matriz_id=p["matriz_id"],
                  unidade_id=p["unidade_id"], calendario_id=p.get("calendario_id"), turno_id=p.get("turno_id"), qtd_alunos=p["alunos_por_turma"],
                  data_inicio=d0, data_fim=d1, dias_possiveis=p.get("dias_semana", [0, 1, 2, 3, 4]), num_grupos=p.get("num_grupos", 1),
                  necessidades_acessibilidade=p.get("acessibilidade", False), situacao="planejada", simulacao_id=sim.id)
        db.add(t)
        db.flush()
        for uc in ucs:
            ini, fim = janelas[uc.id]
            db.add(TurmaUC(turma_id=t.id, uc_id=uc.id, situacao="prevista", data_inicio=ini, data_limite=fim))
        turmas.append(t)
    db.flush()
    return turmas


def criar_simulacao_completa(db: Session, ctx, p: dict, cenario_base_id: int, nome: str, limite_tempo_s: float = 30,
                             alternativas: bool = True) -> SimulacaoCapacidade:
    """Registra a simulação completa como job 'pendente' (processado por
    `processar_simulacao` no worker, numa thread local ou de forma síncrona)."""
    _validar_parametros(db, p)
    base = db.get(CenarioPlanejamento, cenario_base_id)
    if base is None:
        raise NaoEncontrado("Cenário base não encontrado.")
    from app.core.config import get_settings
    limite = max(1.0, min(float(limite_tempo_s), float(get_settings().solver_limite_max_s)))
    sim = SimulacaoCapacidade(nome=nome, tipo="completa", parametros={**p, "_execucao": {"limite_tempo_s": limite, "alternativas": bool(alternativas)}},
                              cenario_base_id=base.id, status="pendente", criado_por_id=getattr(ctx, "id", None))
    db.add(sim)
    db.flush()
    auditoria.registrar(db, ctx, "simulacao.solicitar", "simulacoes_capacidade", sim.id, depois={"nome": nome, "cenario_base_id": base.id})
    return sim


def reivindicar_simulacao(db: Session, worker: str) -> int | None:
    from datetime import datetime
    sim = db.scalars(select(SimulacaoCapacidade).where(SimulacaoCapacidade.status == "pendente", SimulacaoCapacidade.tipo == "completa")
                     .order_by(SimulacaoCapacidade.id).limit(1).with_for_update(skip_locked=True)).first()
    if sim is None:
        db.rollback()
        return None
    agora = datetime.now()
    sim.status, sim.worker, sim.iniciado_em, sim.heartbeat_em = "executando", worker, agora, agora
    db.commit()
    return sim.id


def processar_simulacao(db: Session, sim_id: int, ctx=None) -> SimulacaoCapacidade:
    """Executa a simulação completa. Em caso de erro, desfaz o que foi criado
    (cenário e turmas simuladas) e registra a falha."""
    from datetime import datetime
    sim = db.get(SimulacaoCapacidade, sim_id)
    if sim is None:
        raise NaoEncontrado("Simulação não encontrada.")
    if ctx is None and sim.criado_por_id:
        from app.core.deps import carregar_contexto
        from app.models import Usuario
        u = db.get(Usuario, sim.criado_por_id)
        ctx = carregar_contexto(db, u) if u else None
    try:
        return _processar(db, sim, ctx)
    except Exception as e:
        db.rollback()
        sim = db.get(SimulacaoCapacidade, sim_id)
        if sim.cenario_simulado_id:
            c = db.get(CenarioPlanejamento, sim.cenario_simulado_id)
            if c:
                db.delete(c)
        for t in db.scalars(select(Turma).where(Turma.simulacao_id == sim.id)):
            db.delete(t)
        sim.cenario_simulado_id = None
        sim.status, sim.resultado, sim.finalizado_em = "falha", {"erro": str(e)}, datetime.now()
        db.commit()
        raise


def simular_completa(db: Session, ctx, p: dict, cenario_base_id: int, nome: str, limite_tempo_s: float = 30, alternativas: bool = True) -> SimulacaoCapacidade:
    """Cria e processa imediatamente (modo síncrono)."""
    sim = criar_simulacao_completa(db, ctx, p, cenario_base_id, nome, limite_tempo_s, alternativas)
    db.commit()
    return processar_simulacao(db, sim.id, ctx)


def _processar(db: Session, sim: SimulacaoCapacidade, ctx) -> SimulacaoCapacidade:
    from datetime import datetime
    p = {k: v for k, v in sim.parametros.items() if k != "_execucao"}
    execucao = sim.parametros.get("_execucao", {})
    limite_tempo_s = float(execucao.get("limite_tempo_s", 30))
    alternativas = bool(execucao.get("alternativas", True))
    nome = sim.nome
    base = db.get(CenarioPlanejamento, sim.cenario_base_id)
    if base is None:
        raise NaoEncontrado("Cenário base não encontrado.")
    sim.status, sim.iniciado_em = "executando", sim.iniciado_em or datetime.now()
    cen = cenarios.criar(db, ctx, f"Simulação: {nome}", base.unidade_id, base.periodo_inicio, base.periodo_fim,
                         f"Simulação sobre o cenário #{base.id}", "simulacao", base.id)
    cenarios.copiar_aulas(db, base.id, cen.id)
    sim.cenario_simulado_id = cen.id
    turmas = _criar_turmas_simuladas(db, sim, p)
    db.commit()
    agregada = simular_agregada(db, p, base.id)

    def rodar(params: dict, aplicar: bool):
        """Gera horários só para as turmas simuladas; tudo o mais é ocupação fixa."""
        originais = {t.id: (t.turno_id, list(t.dias_possiveis), t.data_inicio, t.data_fim) for t in turmas}
        for t in turmas:
            t.turno_id = params.get("turno_id")
            t.dias_possiveis = params.get("dias_semana", [0, 1, 2, 3, 4])
        db.flush()
        entrada, meta = otimizacao.montar_entrada(db, cen, {"tipo": "simulacao"}, params.get("pesos") or {}, limite_tempo_s, "completo")
        saida = otimizacao.resolver(entrada)
        res = {"status_solver": saida.status, "motivo": saida.motivo, "tempo_s": round(saida.tempo_s, 2), "atividades": len(entrada.atividades),
               "nao_alocados": saida.nao_alocados[:20], "diagnosticos": saida.diagnosticos[:20] + meta["ajustes"]}
        if aplicar and saida.status in ("OTIMA", "VIAVEL"):
            res["aplicacao"] = otimizacao.aplicar_resultado(db, ctx, cen, saida, meta, None)
        else:
            for t in turmas:
                t.turno_id, t.dias_possiveis, t.data_inicio, t.data_fim = originais[t.id]
        return res

    principal = rodar(p, aplicar=True)
    db.commit()
    resultado = {"agregada": agregada, "completa": principal, "cenario_simulado_id": cen.id}
    viavel = principal["status_solver"] in ("OTIMA", "VIAVEL") and not principal.get("aplicacao", {}).get("riscos_conclusao")
    if viavel:
        resultado["comparacao"] = {
            "atual": indicadores.resumo_cenario(db, base.id),
            "com_novas_turmas": indicadores.resumo_cenario(db, cen.id),
        }
        resultado["viabilidade"] = "viavel"
        resultado["mensagem"] = "Existe uma grade que respeita todas as restrições obrigatórias com as novas turmas."
    else:
        resultado["viabilidade"] = {"INVIAVEL": "inviavel_comprovado", "SEM_SOLUCAO_NO_LIMITE": "indeterminado"}.get(principal["status_solver"], "condicionada")
        resultado["mensagem"] = ("O solver provou que não há grade viável nas condições informadas." if principal["status_solver"] == "INVIAVEL"
                                 else "Não foi possível confirmar a viabilidade nas condições e limites de busca informados.")
        if alternativas:
            alts = []
            turnos = db.scalars(select(Turno).where(Turno.unidade_id == p["unidade_id"], Turno.ativo.is_(True))).all()
            for t in turnos:
                if t.id == p.get("turno_id"):
                    continue
                q = {**copy.deepcopy(p), "turno_id": t.id}
                r = rodar(q, aplicar=False)
                alts.append({"alternativa": f"Alterar o turno para {t.nome}", "o_que_muda": {"turno_id": t.id},
                             "status_solver": r["status_solver"], "viavel": r["status_solver"] in ("OTIMA", "VIAVEL"), "detalhes": r["motivo"]})
            dias_ext = sorted(set(p.get("dias_semana", [0, 1, 2, 3, 4])) | {5})
            if dias_ext != sorted(p.get("dias_semana", [0, 1, 2, 3, 4])):
                r = rodar({**copy.deepcopy(p), "dias_semana": dias_ext}, aplicar=False)
                alts.append({"alternativa": "Distribuir a carga horária incluindo o sábado", "o_que_muda": {"dias_semana": dias_ext},
                             "status_solver": r["status_solver"], "viavel": r["status_solver"] in ("OTIMA", "VIAVEL"), "detalhes": r["motivo"]})
            if int(p["quantidade_turmas"]) > 1:
                alts.append({"alternativa": "Redimensionar a oferta", "o_que_muda": {"quantidade_turmas": int(p["quantidade_turmas"]) - 1},
                             "status_solver": None, "viavel": None,
                             "detalhes": "Reexecute a simulação com menos turmas; a análise agregada indica o déficit por recurso."})
            alts.append({"alternativa": "Disponibilizar recursos/ambientes adicionais", "o_que_muda": None, "status_solver": None, "viavel": None,
                         "detalhes": "; ".join(agregada["condicoes_necessarias"]) or "Ver gargalos gerados."})
            resultado["alternativas"] = alts
            db.rollback()
    sim = db.get(SimulacaoCapacidade, sim.id)
    sim.resultado = resultado
    sim.status = "concluida"
    sim.finalizado_em = datetime.now()
    auditoria.registrar(db, ctx, "simulacao.executar", "simulacoes_capacidade", sim.id, depois={"viabilidade": resultado["viabilidade"]})
    db.commit()
    return sim


def remover_simulacao(db: Session, ctx, sim_id: int):
    sim = db.get(SimulacaoCapacidade, sim_id)
    if sim is None:
        raise NaoEncontrado("Simulação não encontrada.")
    if sim.cenario_simulado_id:
        c = db.get(CenarioPlanejamento, sim.cenario_simulado_id)
        if c:
            db.delete(c)
            db.flush()
    db.delete(sim)  # turmas simuladas são removidas em cascata
    auditoria.registrar(db, ctx, "simulacao.remover", "simulacoes_capacidade", sim_id)
    _ = ExecucaoOtimizacao
