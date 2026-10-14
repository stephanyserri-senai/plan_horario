"""Dashboard, capacidade/gargalos, recomendações, simulador, importação,
exportação, auditoria, configurações e aprendizado."""
from __future__ import annotations

import threading
from datetime import date, datetime

from fastapi import APIRouter, Body, Depends, File, Form, UploadFile
from fastapi.responses import Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.db import SessionLocal, get_db
from app.core.deps import Contexto, carregar_contexto, get_contexto, requer
from app.core.errors import EntradaInvalida, NaoEncontrado
from app.models import (
    CenarioPlanejamento, Configuracao, HistoricoAuditoria, Importacao, RegistroDecisao, SimulacaoCapacidade, Usuario,
)
from app.services import (
    auditoria, cenarios, exportacao, gargalos, importacao, indicadores, recomendacoes, simulador,
)

router = APIRouter(prefix="/api", tags=["análise"])


def _periodo(db, cenario_id, inicio, fim):
    cen = db.get(CenarioPlanejamento, cenario_id)
    if cen is None:
        raise NaoEncontrado("Cenário não encontrado.")
    d0, d1 = indicadores.periodo_padrao(db, cen)
    return (inicio or d0), (fim or d1)


# ============================================================================ indicadores
@router.get("/indicadores/ambientes")
def ind_ambientes(cenario_id: int, inicio: date | None = None, fim: date | None = None, unidade_id: int | None = None, tipo_ambiente_id: int | None = None,
                  ambiente_id: int | None = None, turno_id: int | None = None, ctx: Contexto = Depends(requer("indicadores.ler")), db: Session = Depends(get_db)):
    d0, d1 = _periodo(db, cenario_id, inicio, fim)
    return indicadores.ocupacao_ambientes(db, cenario_id, d0, d1, unidade_id, tipo_ambiente_id, ambiente_id, turno_id, ctx.unidades)


@router.get("/indicadores/instrutores")
def ind_instrutores(cenario_id: int, inicio: date | None = None, fim: date | None = None, unidade_id: int | None = None, instrutor_id: int | None = None,
                    ctx: Contexto = Depends(requer("indicadores.ler")), db: Session = Depends(get_db)):
    d0, d1 = _periodo(db, cenario_id, inicio, fim)
    return indicadores.ocupacao_instrutores(db, cenario_id, d0, d1, unidade_id, instrutor_id, ctx.unidades, ctx.pode("dados_pessoais.ler"))


@router.get("/indicadores/turmas")
def ind_turmas(cenario_id: int, data_referencia: date | None = None, turma_id: int | None = None, curso_id: int | None = None, unidade_id: int | None = None,
               ctx: Contexto = Depends(requer("indicadores.ler")), db: Session = Depends(get_db)):
    return indicadores.turmas_ucs(db, cenario_id, data_referencia, turma_id, curso_id, unidade_id, ctx.unidades)


@router.get("/indicadores/institucionais")
def ind_inst(cenario_id: int, inicio: date | None = None, fim: date | None = None, data_referencia: date | None = None,
             ctx: Contexto = Depends(requer("indicadores.ler")), db: Session = Depends(get_db)):
    d0, d1 = _periodo(db, cenario_id, inicio, fim)
    return indicadores.institucionais(db, cenario_id, d0, d1, ctx.unidades, data_referencia)


@router.get("/gargalos")
def analisar_gargalos(cenario_id: int, inicio: date | None = None, fim: date | None = None, unidade_id: int | None = None,
                      ctx: Contexto = Depends(requer("indicadores.ler")), db: Session = Depends(get_db)):
    d0, d1 = _periodo(db, cenario_id, inicio, fim)
    return gargalos.analisar(db, cenario_id, d0, d1, unidade_id)


# ============================================================================ recomendações
@router.get("/recomendacoes/nao_alocacao")
def rec_nao_alocacao(cenario_id: int, turma_uc_id: int, grupo: int | None = None, ctx: Contexto = Depends(requer("alocacoes.ler")), db: Session = Depends(get_db)):
    return recomendacoes.explicar_nao_alocacao(db, cenario_id, turma_uc_id, grupo)


@router.get("/recomendacoes/mudanca_turno")
def rec_turno(cenario_id: int, turma_id: int, turno_id: int, ctx: Contexto = Depends(requer("indicadores.ler")), db: Session = Depends(get_db)):
    return recomendacoes.impacto_mudanca_turno(db, cenario_id, turma_id, turno_id)


@router.get("/recomendacoes/ampliar_ambiente")
def rec_ampliar(cenario_id: int, ambiente_id: int, horas: float, ctx: Contexto = Depends(requer("indicadores.ler")), db: Session = Depends(get_db)):
    return recomendacoes.impacto_ampliar_ambiente(db, cenario_id, ambiente_id, horas)


@router.get("/recomendacoes/liberar_capacidade")
def rec_liberar(cenario_id: int, ctx: Contexto = Depends(requer("indicadores.ler")), db: Session = Depends(get_db)):
    return recomendacoes.liberar_capacidade(db, cenario_id)


@router.post("/recomendacoes/melhor_cenario")
def rec_melhor(d: dict = Body(...), ctx: Contexto = Depends(requer("indicadores.ler")), db: Session = Depends(get_db)):
    return recomendacoes.melhor_cenario(db, [int(x) for x in d["cenarios"]], d.get("criterio", "janelas_instrutores"), d.get("pesos"))


@router.get("/recomendacoes/ucs_risco")
def rec_risco(cenario_id: int, data_referencia: date | None = None, ctx: Contexto = Depends(requer("indicadores.ler")), db: Session = Depends(get_db)):
    return recomendacoes.ucs_em_risco(db, cenario_id, data_referencia)


# ============================================================================ simulador
@router.post("/simulador/agregada")
def sim_agregada(d: dict = Body(...), ctx: Contexto = Depends(requer("simulacao.executar")), db: Session = Depends(get_db)):
    r = simulador.simular_agregada(db, d["parametros"], int(d["cenario_base_id"]))
    sim = SimulacaoCapacidade(nome=d.get("nome") or "Simulação agregada", tipo="agregada", parametros=d["parametros"], cenario_base_id=int(d["cenario_base_id"]),
                              status="concluida", resultado=r, criado_por_id=ctx.id)
    db.add(sim)
    db.flush()
    auditoria.registrar(db, ctx, "simulacao.agregada", "simulacoes_capacidade", sim.id, depois={"viabilidade": r["viabilidade_estimada"]})
    db.commit()
    return {"id": sim.id, **r}


@router.post("/simulador/completa")
def sim_completa(d: dict = Body(...), ctx: Contexto = Depends(requer("simulacao.executar")), db: Session = Depends(get_db)):
    simulador._validar_parametros(db, d["parametros"])
    uid = ctx.id

    def rodar():
        with SessionLocal() as s:
            c = carregar_contexto(s, s.get(Usuario, uid))
            try:
                simulador.simular_completa(s, c, d["parametros"], int(d["cenario_base_id"]), d.get("nome") or "Simulação completa",
                                           float(d.get("limite_tempo_s", 20)), bool(d.get("alternativas", True)))
            except Exception as e:  # registra falha para consulta
                s.rollback()
                s.add(SimulacaoCapacidade(nome=d.get("nome") or "Simulação completa", tipo="completa", parametros=d["parametros"],
                                          cenario_base_id=int(d["cenario_base_id"]), status="falha", resultado={"erro": str(e)}, criado_por_id=uid))
                s.commit()
    if d.get("sincrono"):
        rodar()
        sim = db.scalars(select(SimulacaoCapacidade).where(SimulacaoCapacidade.criado_por_id == uid).order_by(SimulacaoCapacidade.id.desc())).first()
        return {"id": sim.id, "status": sim.status, "resultado": sim.resultado}
    threading.Thread(target=rodar, daemon=True).start()
    return {"status": "em_execucao", "mensagem": "Simulação completa iniciada; acompanhe na lista de simulações."}


@router.get("/simulador")
def listar_sim(ctx: Contexto = Depends(requer("simulacao.executar")), db: Session = Depends(get_db)):
    return [{"id": s.id, "nome": s.nome, "tipo": s.tipo, "status": s.status, "criado_em": s.criado_em.isoformat(), "cenario_base_id": s.cenario_base_id,
             "cenario_simulado_id": s.cenario_simulado_id,
             "viabilidade": (s.resultado or {}).get("viabilidade") or (s.resultado or {}).get("viabilidade_estimada")}
            for s in db.scalars(select(SimulacaoCapacidade).order_by(SimulacaoCapacidade.id.desc()).limit(100))]


@router.get("/simulador/{sid}")
def obter_sim(sid: int, ctx: Contexto = Depends(requer("simulacao.executar")), db: Session = Depends(get_db)):
    s = db.get(SimulacaoCapacidade, sid)
    if not s:
        raise NaoEncontrado("Simulação não encontrada.")
    return auditoria.snapshot(s)


@router.delete("/simulador/{sid}")
def remover_sim(sid: int, ctx: Contexto = Depends(requer("simulacao.executar")), db: Session = Depends(get_db)):
    simulador.remover_simulacao(db, ctx, sid)
    db.commit()
    return {"ok": True}


# ============================================================================ importação
@router.post("/importacao/previa")
async def previa(arquivo: UploadFile = File(...), tipo: str | None = Form(None), planilha: str | None = Form(None), mapeamento: str | None = Form(None),
                 cenario_id: int | None = Form(None), ctx: Contexto = Depends(requer("importacao.executar")), db: Session = Depends(get_db)):
    import json
    conteudo = await arquivo.read()
    if len(conteudo) > 20 * 1024 * 1024:
        raise EntradaInvalida("Arquivo maior que 20 MB.")
    imp = importacao.gerar_previa(db, ctx, arquivo.filename, conteudo, tipo or None, planilha, json.loads(mapeamento) if mapeamento else None, cenario_id)
    db.commit()
    _ARQUIVOS[imp.id] = (arquivo.filename, conteudo)
    return {"id": imp.id, "tipo": imp.tipo, "mapeamento": imp.mapeamento, **imp.previa}


_ARQUIVOS: dict[int, tuple[str, bytes]] = {}  # conteúdo mantido em memória apenas durante a prévia


@router.post("/importacao/{iid}/remapear")
def remapear(iid: int, d: dict = Body(...), ctx: Contexto = Depends(requer("importacao.executar")), db: Session = Depends(get_db)):
    imp = db.get(Importacao, iid)
    if imp is None or iid not in _ARQUIVOS:
        raise NaoEncontrado("Prévia expirada: envie o arquivo novamente.")
    nome, conteudo = _ARQUIVOS[iid]
    imp = importacao.gerar_previa(db, ctx, nome, conteudo, d.get("tipo") or imp.tipo, d.get("planilha"), d.get("mapeamento"),
                                  d.get("cenario_id", imp.cenario_id), importacao_id=iid)
    db.commit()
    return {"id": imp.id, "tipo": imp.tipo, "mapeamento": imp.mapeamento, **imp.previa}


@router.post("/importacao/{iid}/confirmar")
def confirmar(iid: int, d: dict = Body(default={}), ctx: Contexto = Depends(requer("importacao.executar")), db: Session = Depends(get_db)):
    rel = importacao.confirmar(db, ctx, iid, bool(d.get("ignorar_erros")))
    db.commit()
    _ARQUIVOS.pop(iid, None)
    return rel


@router.post("/importacao/{iid}/descartar")
def descartar(iid: int, ctx: Contexto = Depends(requer("importacao.executar")), db: Session = Depends(get_db)):
    imp = db.get(Importacao, iid)
    if imp and imp.status == "previa":
        imp.status = "descartada"
        db.commit()
    _ARQUIVOS.pop(iid, None)
    return {"ok": True}


@router.get("/importacao")
def listar_imp(ctx: Contexto = Depends(requer("importacao.executar")), db: Session = Depends(get_db)):
    return [{"id": i.id, "arquivo": i.arquivo_nome, "hash": i.arquivo_hash, "tipo": i.tipo, "status": i.status, "criado_em": i.criado_em.isoformat(),
             "confirmado_em": i.confirmado_em.isoformat() if i.confirmado_em else None, "relatorio": i.relatorio,
             "resumo": (i.previa or {}).get("resumo")} for i in db.scalars(select(Importacao).order_by(Importacao.id.desc()).limit(100))]


@router.get("/importacao/{iid}/relatorio")
def relatorio_imp(iid: int, formato: str = "xlsx", ctx: Contexto = Depends(requer("importacao.executar")), db: Session = Depends(get_db)):
    imp = db.get(Importacao, iid)
    if not imp:
        raise NaoEncontrado("Importação não encontrada.")
    linhas = [{"linha": i["linha"], "acao": i["acao"], "erros": "; ".join(i["erros"]), "avisos": "; ".join(i["avisos"])} for i in imp.previa["itens"]]
    for b in (imp.relatorio or {}).get("aulas_bloqueadas", []):
        linhas.append({"linha": b["linha"], "acao": "bloqueada_na_gravacao", "erros": b["motivo"], "avisos": ""})
    return _arquivo(linhas, formato, f"importacao_{iid}", f"Relatório da importação #{iid} – {imp.arquivo_nome}")


@router.get("/importacao/modelo/{tipo}")
def modelo(tipo: str, ctx: Contexto = Depends(get_contexto)):
    if tipo not in importacao.SPECS:
        raise NaoEncontrado("Tipo inexistente.")
    cols = {c: "" for c in importacao.SPECS[tipo]["campos"]}
    return _arquivo([cols], "xlsx", f"modelo_{tipo}", None)


# ============================================================================ exportação
def _arquivo(linhas, formato, nome, titulo, abas=None):
    if formato == "csv":
        return Response(exportacao.para_csv(linhas), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": f'attachment; filename="{nome}.csv"'})
    if formato == "pdf":
        return Response(exportacao.para_pdf(titulo or nome, linhas), media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{nome}.pdf"'})
    if formato == "xlsx":
        return Response(exportacao.para_xlsx(abas or {"dados": linhas}, titulo), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        headers={"Content-Disposition": f'attachment; filename="{nome}.xlsx"'})
    raise EntradaInvalida("Formato inválido (xlsx, csv, pdf).")


@router.get("/exportar/grade")
def exportar_grade(cenario_id: int, formato: str = "xlsx", filtro: str | None = None, filtro_id: int | None = None, inicio: date | None = None,
                   fim: date | None = None, semana: date | None = None, ctx: Contexto = Depends(requer("exportacao.executar")), db: Session = Depends(get_db)):
    linhas = exportacao.linhas_grade(db, cenario_id, filtro, filtro_id, inicio, fim, ctx.unidades)
    titulo = f"Grade horária – {exportacao.nome_cenario(db, cenario_id)}" + (f" – {filtro} #{filtro_id}" if filtro else "")
    auditoria.registrar(db, ctx, "exportacao.grade", "cenarios_planejamento", cenario_id, depois={"formato": formato, "filtro": filtro, "filtro_id": filtro_id})
    db.commit()
    if semana:
        matriz = exportacao.matriz_semanal(linhas, semana)
        if formato == "pdf":
            return Response(exportacao.para_pdf(titulo, matriz, f"Semana de {semana:%d/%m/%Y}"), media_type="application/pdf",
                            headers={"Content-Disposition": 'attachment; filename="grade_semana.pdf"'})
        return _arquivo(matriz, formato, "grade_semana", titulo, {"semana": matriz, "aulas": linhas})
    return _arquivo(linhas, formato, "grade", titulo)


@router.get("/exportar/indicadores/{tipo}")
def exportar_indicadores(tipo: str, cenario_id: int, formato: str = "xlsx", inicio: date | None = None, fim: date | None = None,
                         ctx: Contexto = Depends(requer("exportacao.executar")), db: Session = Depends(get_db)):
    d0, d1 = _periodo(db, cenario_id, inicio, fim)
    if tipo == "ambientes":
        r = indicadores.ocupacao_ambientes(db, cenario_id, d0, d1, unidades_permitidas=ctx.unidades)
        linhas, abas = r["ambientes"], {"ambientes": r["ambientes"], "por_turno": r["por_turno"], "por_dia": r["por_dia_semana"]}
    elif tipo == "instrutores":
        r = indicadores.ocupacao_instrutores(db, cenario_id, d0, d1, unidades_permitidas=ctx.unidades, mostrar_pessoais=ctx.pode("dados_pessoais.ler"))
        linhas = exportacao.achatar(r["instrutores"])
        abas = {"instrutores": linhas}
    elif tipo == "turmas":
        r = indicadores.turmas_ucs(db, cenario_id, unidades_permitidas=ctx.unidades)
        linhas = exportacao.achatar(r["itens"])
        abas = {"turmas_ucs": linhas}
    elif tipo == "gargalos":
        r = gargalos.analisar(db, cenario_id, d0, d1)
        linhas = exportacao.achatar([{k: v for k, v in g.items() if k != "itens"} for g in r["gargalos"]])
        abas = {"gargalos": linhas}
    else:
        raise NaoEncontrado("Relatório inexistente.")
    auditoria.registrar(db, ctx, "exportacao.indicadores", "cenarios_planejamento", cenario_id, depois={"tipo": tipo, "formato": formato})
    db.commit()
    return _arquivo(linhas, formato, f"indicadores_{tipo}", f"Indicadores – {tipo} – {exportacao.nome_cenario(db, cenario_id)} ({d0:%d/%m/%Y}–{d1:%d/%m/%Y})", abas)


@router.get("/exportar/comparativo")
def exportar_comparativo(cenarios_ids: str, formato: str = "xlsx", ctx: Contexto = Depends(requer("exportacao.executar")), db: Session = Depends(get_db)):
    ids = [int(x) for x in cenarios_ids.split(",")]
    r = cenarios.comparar(db, ids)
    linhas = []
    for c in r["cenarios"]:
        l = {"cenario": c["cenario"]["nome"], "estado": c["cenario"]["estado"], "pontuacao_total": c["avaliacao"]["pontuacao_total"],
             "aulas": c["indicadores"]["aulas"], "horas_programadas": c["indicadores"]["horas_programadas"], "carga_pendente_h": c["carga_pendente_h"],
             "ocupacao_ambientes_pct": c["indicadores"]["taxa_ocupacao_ambientes_pct"], "ocupacao_instrutores_pct": c["indicadores"]["ocupacao_media_instrutores_pct"],
             "bloqueios": (c["validacao"] or {}).get("bloqueios")}
        for cr in c["avaliacao"]["criterios"]:
            l[f"{cr['criterio']} ({cr['unidade']})"] = cr["valor_bruto"]
        linhas.append(l)
    return _arquivo(linhas, formato, "comparativo_cenarios", "Comparativo de cenários (mesmos pesos)")


@router.get("/exportar/simulacao/{sid}")
def exportar_sim(sid: int, formato: str = "xlsx", ctx: Contexto = Depends(requer("exportacao.executar")), db: Session = Depends(get_db)):
    s = db.get(SimulacaoCapacidade, sid)
    if not s:
        raise NaoEncontrado("Simulação não encontrada.")
    r = s.resultado or {}
    ag = r.get("agregada", r)
    linhas = [{"item": "viabilidade", "valor": r.get("viabilidade") or ag.get("viabilidade_estimada")},
              {"item": "carga adicional semanal (h)", "valor": ag.get("carga_horaria_adicional_semanal_h")},
              {"item": "déficit adicional (h)", "valor": ag.get("deficit_adicional_h")}]
    linhas += [{"item": f"gargalo: {g['recurso']}", "valor": g["descricao"]} for g in ag.get("gargalos_gerados", [])]
    linhas += [{"item": f"alternativa: {a['alternativa']}", "valor": f"viável={a.get('viavel')} {a.get('detalhes') or ''}"} for a in r.get("alternativas", [])]
    return _arquivo(linhas, formato, f"simulacao_{sid}", f"Simulação #{sid} – {s.nome}")


# ============================================================================ auditoria, configurações, aprendizado
@router.get("/auditoria")
def listar_auditoria(entidade: str | None = None, acao: str | None = None, usuario_id: int | None = None, inicio: date | None = None,
                     fim: date | None = None, pagina: int = 1, por_pagina: int = 50, ctx: Contexto = Depends(requer("auditoria.ler")), db: Session = Depends(get_db)):
    q = select(HistoricoAuditoria)
    if entidade:
        q = q.where(HistoricoAuditoria.entidade == entidade)
    if acao:
        q = q.where(HistoricoAuditoria.acao.ilike(f"{acao}%"))
    if usuario_id:
        q = q.where(HistoricoAuditoria.usuario_id == usuario_id)
    if inicio:
        q = q.where(HistoricoAuditoria.em >= datetime.combine(inicio, datetime.min.time()))
    if fim:
        q = q.where(HistoricoAuditoria.em <= datetime.combine(fim, datetime.max.time()))
    total = db.scalar(select(func.count()).select_from(q.subquery()))
    itens = db.scalars(q.order_by(HistoricoAuditoria.id.desc()).offset((pagina - 1) * por_pagina).limit(por_pagina)).all()
    return {"total": total, "itens": [auditoria.snapshot(h) for h in itens]}


@router.get("/configuracoes")
def listar_config(ctx: Contexto = Depends(get_contexto), db: Session = Depends(get_db)):
    return [auditoria.snapshot(c) for c in db.scalars(select(Configuracao).order_by(Configuracao.chave))]


@router.put("/configuracoes/{chave}")
def salvar_config(chave: str, d: dict = Body(...), ctx: Contexto = Depends(requer("configuracoes.editar")), db: Session = Depends(get_db)):
    c = db.get(Configuracao, chave)
    if c is None:
        raise NaoEncontrado("Configuração inexistente.")
    antes = c.valor
    if not isinstance(d.get("valor"), dict):
        raise EntradaInvalida("Valor deve ser um objeto JSON.")
    c.valor = {**c.valor, **d["valor"]}
    auditoria.registrar(db, ctx, "configuracao.alterar", "configuracoes", chave, antes=antes, depois=c.valor)
    db.commit()
    return auditoria.snapshot(c)


@router.get("/aprendizado/registros")
def registros(tipo: str | None = None, pagina: int = 1, ctx: Contexto = Depends(requer("aprendizado.gerenciar")), db: Session = Depends(get_db)):
    q = select(RegistroDecisao)
    if tipo:
        q = q.where(RegistroDecisao.tipo == tipo)
    total = db.scalar(select(func.count()).select_from(q.subquery()))
    return {"total": total, "itens": [auditoria.snapshot(r) for r in db.scalars(q.order_by(RegistroDecisao.id.desc()).offset((pagina - 1) * 50).limit(50))]}


@router.put("/aprendizado/registros/{rid}")
def revisar_registro(rid: int, d: dict = Body(...), ctx: Contexto = Depends(requer("aprendizado.gerenciar")), db: Session = Depends(get_db)):
    r = db.get(RegistroDecisao, rid)
    if r is None:
        raise NaoEncontrado("Registro não encontrado.")
    antes = auditoria.snapshot(r)
    for k in ("incluir_treinamento", "motivo"):
        if k in d:
            setattr(r, k, d[k])
    r.revisado = True
    auditoria.registrar(db, ctx, "aprendizado.revisar", "registros_decisao", rid, antes=antes, depois=auditoria.snapshot(r))
    db.commit()
    return auditoria.snapshot(r)


@router.delete("/aprendizado/registros/{rid}")
def excluir_registro(rid: int, ctx: Contexto = Depends(requer("aprendizado.gerenciar")), db: Session = Depends(get_db)):
    r = db.get(RegistroDecisao, rid)
    if r:
        auditoria.registrar(db, ctx, "aprendizado.excluir", "registros_decisao", rid, antes=auditoria.snapshot(r))
        db.delete(r)
        db.commit()
    return {"ok": True}


MINIMO_TREINO = 500


@router.get("/aprendizado/avaliacao")
def avaliacao_aprendizado(ctx: Contexto = Depends(requer("aprendizado.gerenciar")), db: Session = Depends(get_db)):
    """Fase 8 — avaliação de prontidão. Nenhum modelo é treinado enquanto não
    houver dados revisados suficientes; a linha de base é a função objetivo
    com pesos explícitos."""
    por_tipo = dict(db.execute(select(RegistroDecisao.tipo, func.count()).group_by(RegistroDecisao.tipo)).all())
    aptos = db.scalar(select(func.count()).select_from(RegistroDecisao).where(RegistroDecisao.incluir_treinamento.is_(True), RegistroDecisao.revisado.is_(True)))
    return {
        "registros_por_tipo": por_tipo, "registros_revisados_aptos": aptos, "minimo_para_treino": MINIMO_TREINO,
        "pronto_para_treinar": aptos >= MINIMO_TREINO,
        "linha_de_base": "Função objetivo com pesos configuráveis (regras explícitas) — em uso.",
        "protocolo": ["Separar dados revisados em treino (70%), validação (15%) e teste (15%) por período, sem vazamento entre cenários.",
                      "Modelo candidato: ranqueamento pareado (sugestão aceita × rejeitada) com regressão logística; redes neurais só se superarem esta referência.",
                      "Métrica: acurácia de ranqueamento/NDCG frente à linha de base (função objetivo).",
                      "Integração somente se houver ganho estatisticamente significativo no conjunto de teste; o modelo apenas reordena alternativas já validadas — nunca autoriza violação de restrição obrigatória."],
        "situacao": "Coletando e revisando registros de decisão; nenhum modelo de aprendizado está ativo." if aptos < MINIMO_TREINO
        else "Dados suficientes para iniciar a avaliação offline do modelo candidato.",
    }
