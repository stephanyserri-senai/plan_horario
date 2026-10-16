"""Dashboard, capacidade/gargalos, recomendações, simulador, importação,
exportação, auditoria, configurações e aprendizado."""
from __future__ import annotations

import logging
import threading
import io
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Body, Depends, File, Form, UploadFile
from fastapi.responses import Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
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


# ============================================================================ consultas e ocupação
@router.get("/consultas/situacao")
def consulta_situacao(cenario_id: int, data: date, turno: str | None = None, ctx: Contexto = Depends(requer("alocacoes.ler")),
                      db: Session = Depends(get_db)):
    """Quem está onde num dia (e turno): instrutores e salas em aula, PL/PJ, bloqueio, livres ou fora da jornada."""
    from app.services import analise_ocupacao
    return analise_ocupacao.situacao_no_dia(db, cenario_id, data, turno, ctx.unidades)


@router.get("/consultas/ranking")
def consulta_ranking(cenario_id: int, inicio: date | None = None, fim: date | None = None, ctx: Contexto = Depends(requer("indicadores.ler")),
                     db: Session = Depends(get_db)):
    from app.services import analise_ocupacao
    d0, d1 = _periodo(db, cenario_id, inicio, fim)
    return analise_ocupacao.ranking(db, cenario_id, d0, d1, ctx.unidades)


@router.get("/consultas/serie")
def consulta_serie(cenario_id: int, inicio: date | None = None, fim: date | None = None, ctx: Contexto = Depends(requer("indicadores.ler")),
                   db: Session = Depends(get_db)):
    from app.services import analise_ocupacao
    d0, d1 = _periodo(db, cenario_id, inicio, fim)
    return analise_ocupacao.serie(db, cenario_id, d0, d1, ctx.unidades)


@router.get("/consultas/quadro-instrutores")
def consulta_quadro(cenario_id: int, simulacao_id: int | None = None, extra: str | None = None, ctx: Contexto = Depends(requer("indicadores.ler")),
                    db: Session = Depends(get_db)):
    """Análise do quadro de instrutores por área (precisa contratar?), com turmas hipotéticas `extra=area_id:n,...`."""
    from app.services import analise_ocupacao
    turmas_extra = {}
    for par in (extra or "").split(","):
        if ":" in par:
            a, n = par.split(":", 1)
            if a.strip().isdigit() and n.strip().isdigit() and int(n) > 0:
                turmas_extra[int(a)] = int(n)
    return analise_ocupacao.quadro_instrutores(db, cenario_id, ctx.unidades, simulacao_id=simulacao_id, turmas_extra=turmas_extra)


@router.get("/gargalos")
def analisar_gargalos(cenario_id: int, inicio: date | None = None, fim: date | None = None, unidade_id: int | None = None,
                      ctx: Contexto = Depends(requer("indicadores.ler")), db: Session = Depends(get_db)):
    d0, d1 = _periodo(db, cenario_id, inicio, fim)
    return gargalos.analisar(db, cenario_id, d0, d1, unidade_id or ctx.extra.get("filtro_unidade"))


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
    """Registra a simulação como job e a encaminha conforme PLAN_EXECUTOR:
    thread (processo local), fila (worker externo) ou síncrona."""
    sim = simulador.criar_simulacao_completa(db, ctx, d["parametros"], int(d["cenario_base_id"]), d.get("nome") or "Simulação completa",
                                             float(d.get("limite_tempo_s", 20)), bool(d.get("alternativas", True)))
    db.commit()
    modo = "sincrono" if d.get("sincrono") else get_settings().modo_executor
    sid, uid = sim.id, ctx.id

    def rodar():
        with SessionLocal() as s:
            try:
                simulador.processar_simulacao(s, sid, carregar_contexto(s, s.get(Usuario, uid)))
            except Exception:
                logging.getLogger("simulador").exception("Falha na simulação %s", sid)
    if modo == "sincrono":
        rodar()
        db.expire_all()
        sim = db.get(SimulacaoCapacidade, sid)
        return {"id": sim.id, "status": sim.status, "resultado": sim.resultado}
    if modo == "thread":
        threading.Thread(target=rodar, daemon=True).start()
        return {"id": sid, "status": "em_execucao", "mensagem": "Simulação completa iniciada; acompanhe na lista de simulações."}
    from app.services.acionador import acionar_worker
    acionar_worker()
    return {"id": sid, "status": "pendente", "mensagem": "Simulação enviada para processamento. O resultado aparece na lista de simulações "
                                                         "em alguns minutos; a página atualiza sozinha."}


@router.get("/simulador")
def listar_sim(ctx: Contexto = Depends(requer("simulacao.executar")), db: Session = Depends(get_db)):
    return [{"id": s.id, "nome": s.nome, "tipo": s.tipo, "status": s.status, "criado_em": s.criado_em.isoformat(), "cenario_base_id": s.cenario_base_id,
             "cenario_simulado_id": s.cenario_simulado_id,
             "viabilidade": (s.resultado or {}).get("viabilidade") or (s.resultado or {}).get("viabilidade_estimada")}
            for s in db.scalars(select(SimulacaoCapacidade).order_by(SimulacaoCapacidade.id.desc()).limit(100))]


@router.get("/simulador/{sid}/impacto")
def impacto_sim(sid: int, inicio: date | None = None, fim: date | None = None, ctx: Contexto = Depends(requer("simulacao.executar")),
                db: Session = Depends(get_db)):
    """Ocupação semana a semana sem e com as turmas simuladas, no recorte da turma (ou em `inicio`–`fim`)."""
    s = db.get(SimulacaoCapacidade, sid)
    if not s or not s.cenario_base_id:
        raise NaoEncontrado("Simulação não encontrada.")
    return simulador.impacto(db, s, inicio, fim, ctx.unidades)


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
    limite = get_settings().limite_upload_bytes
    if len(conteudo) > limite:
        raise EntradaInvalida(f"Arquivo maior que {limite / 1024 / 1024:.1f} MB.")
    try:
        mapa = json.loads(mapeamento) if mapeamento else None
    except ValueError:
        raise EntradaInvalida("Mapeamento inválido (JSON).")
    imp = importacao.gerar_previa(db, ctx, arquivo.filename, conteudo, tipo or None, planilha, mapa, cenario_id)
    db.commit()
    return {"id": imp.id, "tipo": imp.tipo, "mapeamento": imp.mapeamento, **imp.previa}


@router.post("/importacao/{iid}/remapear")
def remapear(iid: int, d: dict = Body(...), ctx: Contexto = Depends(requer("importacao.executar")), db: Session = Depends(get_db)):
    imp = db.get(Importacao, iid)
    if imp is None or imp.status != "previa" or imp.conteudo is None:
        raise NaoEncontrado("Prévia não disponível: envie o arquivo novamente.")
    imp = importacao.gerar_previa(db, ctx, imp.arquivo_nome, imp.conteudo, d.get("tipo") or imp.tipo, d.get("planilha"), d.get("mapeamento"),
                                  d.get("cenario_id", imp.cenario_id), importacao_id=iid)
    db.commit()
    return {"id": imp.id, "tipo": imp.tipo, "mapeamento": imp.mapeamento, **imp.previa}


@router.post("/importacao/{iid}/confirmar")
def confirmar(iid: int, d: dict = Body(default={}), ctx: Contexto = Depends(requer("importacao.executar")), db: Session = Depends(get_db)):
    rel = importacao.confirmar(db, ctx, iid, bool(d.get("ignorar_erros")))
    db.commit()
    return rel


@router.post("/importacao/{iid}/descartar")
def descartar(iid: int, ctx: Contexto = Depends(requer("importacao.executar")), db: Session = Depends(get_db)):
    imp = db.get(Importacao, iid)
    if imp and imp.status == "previa":
        imp.status = "descartada"
        imp.conteudo = None
        db.commit()
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
    return _arquivo(linhas, formato, f"importacao_{iid}", f"Relatório da importação #{iid} – {imp.arquivo_nome}", aba="importacao",
                    meta=_meta(db, ctx))


@router.get("/importacao/modelo/{tipo}")
def modelo(tipo: str, ctx: Contexto = Depends(get_contexto), db: Session = Depends(get_db)):
    from app.services.modelos_planilha import MODELOS, gerar_modelo
    if tipo in MODELOS:
        return Response(gerar_modelo(db, tipo), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        headers={"Content-Disposition": f'attachment; filename="modelo_{tipo}.xlsx"'})
    if tipo not in importacao.SPECS:
        raise NaoEncontrado("Tipo inexistente.")
    cols = {c: "" for c in importacao.SPECS[tipo]["campos"]}
    return _arquivo([cols], "xlsx", f"modelo_{tipo}", None)


# ============================================================================ exportação
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _arquivo(linhas, formato, nome, titulo, abas=None, aba="dados", meta=None):
    """XLSX ou PDF com o mesmo conteúdo (CSV ainda aceito por compatibilidade)."""
    if formato == "csv":
        return Response(exportacao.para_csv(linhas), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": f'attachment; filename="{nome}.csv"'})
    if formato == "pdf":
        return Response(exportacao.para_pdf(titulo or nome, linhas, abas=abas, meta=meta, aba=aba), media_type="application/pdf",
                        headers={"Content-Disposition": f'attachment; filename="{nome}.pdf"'})
    if formato == "xlsx":
        return Response(exportacao.para_xlsx(abas or {aba: linhas}, titulo, meta), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        headers={"Content-Disposition": f'attachment; filename="{nome}.xlsx"'})
    raise EntradaInvalida("Formato inválido: use xlsx ou pdf.")


def _meta(db, ctx, cenario_id=None, d0=None, d1=None, filtro=None) -> list[str]:
    """Linhas de identificação do relatório (semestre, período, filtro, quem gerou e quando)."""
    from datetime import datetime
    m = []
    if cenario_id:
        m.append(f"Semestre: {exportacao.nome_cenario(db, cenario_id)}")
    if d0 and d1:
        m.append(f"Período: {d0:%d/%m/%Y} a {d1:%d/%m/%Y}")
    if ctx.extra.get("filtro_unidade"):
        from app.models import Unidade
        un = db.get(Unidade, ctx.extra["filtro_unidade"])
        m.append(f"Unidade: {un.nome if un else ctx.extra['filtro_unidade']}")
    if filtro:
        m.append(f"Filtro: {filtro}")
    m.append(f"Gerado em {datetime.now():%d/%m/%Y %H:%M} por {getattr(ctx.usuario, 'nome', None) or 'usuário'}")
    return m


def _rotulo_filtro(db, filtro, filtro_id) -> str | None:
    if not filtro or not filtro_id:
        return None
    from app.models import Ambiente, Instrutor, Turma, Turno
    modelo = {"turma": (Turma, "codigo", "Turma"), "instrutor": (Instrutor, "nome", "Instrutor"), "ambiente": (Ambiente, "nome", "Sala"),
              "turno": (Turno, "nome", "Turno")}.get(filtro)
    if not modelo:
        return None
    obj = db.get(modelo[0], filtro_id)
    return f"{modelo[2]} {getattr(obj, modelo[1], filtro_id)}"


@router.get("/exportar/grade")
def exportar_grade(cenario_id: int, formato: str = "xlsx", filtro: str | None = None, filtro_id: int | None = None, inicio: date | None = None,
                   fim: date | None = None, semana: date | None = None, periodo: str | None = None, mes: str | None = None,
                   ctx: Contexto = Depends(requer("exportacao.executar")), db: Session = Depends(get_db)):
    """Lista de aulas; com `semana` ou `periodo` (semana | mes | semestre), o quadro horário × dia."""
    if periodo == "semana" and not semana:
        raise EntradaInvalida("Escolha a semana.")
    if periodo == "mes":
        try:
            ano, m = (int(x) for x in (mes or "").split("-")[:2])
            inicio = date(ano, m, 1)
            fim = date(ano + (m == 12), m % 12 + 1, 1) - timedelta(days=1)
        except ValueError:
            raise EntradaInvalida("Escolha o mês (AAAA-MM).")
    elif periodo == "semestre":
        inicio, fim = _periodo(db, cenario_id, None, None)
    elif semana:
        periodo = "semana"
        inicio = semana - timedelta(days=semana.weekday())
        fim = inicio + timedelta(days=6)
    linhas = exportacao.linhas_grade(db, cenario_id, filtro, filtro_id, inicio, fim, ctx.unidades)
    rot = _rotulo_filtro(db, filtro, filtro_id)
    auditoria.registrar(db, ctx, "exportacao.grade", "cenarios_planejamento", cenario_id,
                        depois={"formato": formato, "filtro": filtro, "filtro_id": filtro_id, "periodo": periodo})
    db.commit()
    if not periodo:
        d = [l["_data"] for l in linhas]
        return _arquivo(linhas, formato, "aulas", "Lista de aulas" + (f" – {rot}" if rot else ""), aba="grade",
                        meta=_meta(db, ctx, cenario_id, inicio or (min(d) if d else None), fim or (max(d) if d else None), rot))
    # quadro horário × dia: uma semana, um mês (semana a semana) ou o semestre inteiro
    MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"]
    nome_per = {"semana": f"semana de {inicio:%d/%m/%Y}", "mes": f"{MESES[inicio.month - 1]} de {inicio.year}", "semestre": "semestre inteiro"}[periodo]
    titulo = f"Grade horária – {nome_per}" + (f" – {rot}" if rot else "")
    arq = {"semana": "grade_semana", "mes": f"grade_{inicio:%Y_%m}", "semestre": "grade_semestre"}[periodo]
    fim_vis = inicio + timedelta(days=5) if periodo == "semana" else fim
    meta = _meta(db, ctx, cenario_id, inicio, fim_vis, rot)
    aulas_lista = linhas
    ead = exportacao.linhas_ead(db, inicio, fim, filtro, filtro_id, ctx.unidades)
    if ead:  # turmas 80-20: o dia EAD aparece nos quadros (não na lista de aulas)
        linhas = sorted(linhas + ead, key=lambda l: (l["_data"], l["_ini"], l["turma"]))
        meta = meta + ["EAD = dia de atividades a distância das turmas 80-20 (sem aula presencial)."]
    # quadro geral: uma linha por turma em cada horário, colorida pela turma (no Excel e no PDF)
    if periodo == "semana":
        geral, tipo_geral, tipo = exportacao.matriz_geral(linhas, inicio, inicio + timedelta(days=6), False), "geral_semana", "semana"
        por_turma = lambda ls: exportacao.matriz_semanal(ls, inicio, sem_turma=True)
    else:
        geral, tipo_geral, tipo = exportacao.matriz_geral(linhas, inicio, fim, True), "geral_periodo", "periodo"
        por_turma = lambda ls: exportacao.matriz_periodo(ls, inicio, fim, sem_turma=True)
    if formato == "pdf":
        return Response(exportacao.para_pdf(titulo, geral, meta=meta, aba=tipo_geral), media_type="application/pdf",
                        headers={"Content-Disposition": f'attachment; filename="{arq}.pdf"'})
    if formato != "xlsx":
        raise EntradaInvalida("Formato inválido: use xlsx ou pdf.")
    # planilha: visão geral + uma aba por turma + a lista das aulas do período
    nome_geral = "Todas as turmas"
    abas, tipos, titulos = {nome_geral: geral}, {nome_geral: tipo_geral}, {}
    cores = exportacao.cores_turmas(l["turma"] for l in linhas)
    for turma in sorted({l["turma"] for l in linhas}):
        abas[turma] = por_turma([l for l in linhas if l["turma"] == turma])
        tipos[turma], titulos[turma] = tipo, f"Grade horária – {nome_per} – turma {turma}"
    abas["Lista de aulas"], tipos["Lista de aulas"] = aulas_lista, "grade"
    return Response(exportacao.para_xlsx(abas, titulo, meta, tipos, titulos, cores), media_type=XLSX_MIME,
                    headers={"Content-Disposition": f'attachment; filename="{arq}.xlsx"'})


TITULOS_INDICADORES = {"ambientes": "Ocupação das salas e laboratórios", "instrutores": "Ocupação e carga horária dos instrutores",
                       "turmas": "Carga horária por turma e UC", "gargalos": "Gargalos de capacidade"}


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
        from app.models import Ambiente
        cod = {a.id: a.codigo for a in db.query(Ambiente).all()}
        for it in r["itens"]:  # salas pelo código, não pelo número interno
            it["ambientes_utilizados"] = [cod.get(x, x) for x in it.get("ambientes_utilizados") or []]
        linhas = exportacao.achatar(r["itens"])
        abas = {"turmas_ucs": linhas}
    elif tipo == "gargalos":
        r = gargalos.analisar(db, cenario_id, d0, d1, ctx.extra.get("filtro_unidade"))
        linhas = exportacao.achatar([{k: v for k, v in g.items() if k not in ("itens", "calculo")} for g in r["gargalos"]])
        abas = {"gargalos": linhas}
    else:
        raise NaoEncontrado("Relatório inexistente.")
    auditoria.registrar(db, ctx, "exportacao.indicadores", "cenarios_planejamento", cenario_id, depois={"tipo": tipo, "formato": formato})
    db.commit()
    nomes = {"ambientes": "ocupacao_salas", "instrutores": "ocupacao_instrutores", "turmas": "carga_horaria_turmas_ucs", "gargalos": "gargalos"}
    return _arquivo(linhas, formato, nomes[tipo], TITULOS_INDICADORES[tipo], abas, meta=_meta(db, ctx, cenario_id, d0, d1))


XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _xlsx(conteudo: bytes, nome: str) -> Response:
    return Response(conteudo, media_type=XLSX, headers={"Content-Disposition": f'attachment; filename="{nome}.xlsx"'})


def _rico(conteudo: bytes, formato: str, nome: str, titulo: str, meta: list[str]) -> Response:
    """Relatório com várias abas formatadas: a planilha como está ou o PDF gerado a partir dela."""
    if formato == "pdf":
        return Response(exportacao.planilha_para_pdf(conteudo, titulo, meta), media_type="application/pdf",
                        headers={"Content-Disposition": f'attachment; filename="{nome}.pdf"'})
    if formato != "xlsx":
        raise EntradaInvalida("Formato inválido: use xlsx ou pdf.")
    return _xlsx(conteudo, nome)


@router.get("/exportar/horario_turmas")
def exportar_horario_turmas(cenario_id: int, turma_id: int | None = None, formato: str = "xlsx", ctx: Contexto = Depends(requer("exportacao.executar")),
                            db: Session = Depends(get_db)):
    from app.services import exportacao_planilhas
    arq = exportacao_planilhas.horario_turmas(db, cenario_id, turma_id, ctx.unidades)
    auditoria.registrar(db, ctx, "exportacao.horario_turmas", "cenarios_planejamento", cenario_id, depois={"turma_id": turma_id, "formato": formato})
    db.commit()
    return _rico(arq, formato, "horario_turmas", "Horário das turmas", _meta(db, ctx, cenario_id, filtro=_rotulo_filtro(db, "turma", turma_id)))


@router.get("/exportar/agenda_instrutores")
def exportar_agenda_instrutores(cenario_id: int, instrutor_id: int | None = None, inicio: date | None = None, fim: date | None = None, formato: str = "xlsx",
                                ctx: Contexto = Depends(requer("exportacao.executar")), db: Session = Depends(get_db)):
    from app.services import exportacao_planilhas
    d0, d1 = _periodo(db, cenario_id, inicio, fim)
    arq = exportacao_planilhas.agenda_instrutores(db, cenario_id, d0, d1, instrutor_id, ctx.unidades, ctx.pode("dados_pessoais.ler"))
    auditoria.registrar(db, ctx, "exportacao.agenda_instrutores", "cenarios_planejamento", cenario_id, depois={"instrutor_id": instrutor_id, "formato": formato})
    db.commit()
    return _rico(arq, formato, "agenda_instrutores", "Agenda e ocupação dos instrutores",
                 _meta(db, ctx, cenario_id, d0, d1, _rotulo_filtro(db, "instrutor", instrutor_id)))


@router.get("/exportar/uso_ambientes")
def exportar_uso_ambientes(cenario_id: int, ambiente_id: int | None = None, inicio: date | None = None, fim: date | None = None, formato: str = "xlsx",
                           ctx: Contexto = Depends(requer("exportacao.executar")), db: Session = Depends(get_db)):
    from app.services import exportacao_planilhas
    d0, d1 = _periodo(db, cenario_id, inicio, fim)
    arq = exportacao_planilhas.uso_ambientes(db, cenario_id, d0, d1, ambiente_id, ctx.unidades)
    auditoria.registrar(db, ctx, "exportacao.uso_ambientes", "cenarios_planejamento", cenario_id, depois={"ambiente_id": ambiente_id, "formato": formato})
    db.commit()
    return _rico(arq, formato, "salas_e_laboratorios", "Uso das salas e laboratórios",
                 _meta(db, ctx, cenario_id, d0, d1, _rotulo_filtro(db, "ambiente", ambiente_id)))


@router.get("/exportar/pacote")
def exportar_pacote(cenario_id: int, formato: str = "xlsx", inicio: date | None = None, fim: date | None = None,
                    ctx: Contexto = Depends(requer("exportacao.executar")), db: Session = Depends(get_db)):
    """Todos os relatórios do semestre num ZIP (formato xlsx, pdf ou ambos)."""
    import zipfile
    formatos = ["xlsx", "pdf"] if formato == "ambos" else [formato]
    if any(f not in ("xlsx", "pdf") for f in formatos):
        raise EntradaInvalida("Formato inválido: use xlsx, pdf ou ambos.")
    geradores = [
        ("01_horario_turmas", lambda f: exportar_horario_turmas(cenario_id, None, formato=f, ctx=ctx, db=db)),
        ("02_agenda_instrutores", lambda f: exportar_agenda_instrutores(cenario_id, None, inicio, fim, formato=f, ctx=ctx, db=db)),
        ("03_salas_e_laboratorios", lambda f: exportar_uso_ambientes(cenario_id, None, inicio, fim, formato=f, ctx=ctx, db=db)),
        ("04_lista_de_aulas", lambda f: exportar_grade(cenario_id, f, inicio=inicio, fim=fim, ctx=ctx, db=db)),
        ("05_carga_horaria_turmas_ucs", lambda f: exportar_indicadores("turmas", cenario_id, f, inicio, fim, ctx=ctx, db=db)),
        ("06_ocupacao_salas", lambda f: exportar_indicadores("ambientes", cenario_id, f, inicio, fim, ctx=ctx, db=db)),
        ("07_ocupacao_instrutores", lambda f: exportar_indicadores("instrutores", cenario_id, f, inicio, fim, ctx=ctx, db=db)),
        ("08_gargalos", lambda f: exportar_indicadores("gargalos", cenario_id, f, inicio, fim, ctx=ctx, db=db)),
    ]
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for nome, gerar in geradores:
            for f in formatos:
                z.writestr(f"{nome}.{f}", gerar(f).body)
    sem = exportacao.nome_cenario(db, cenario_id).split(" (")[0]
    import unicodedata
    ascii_ = unicodedata.normalize("NFKD", sem).encode("ascii", "ignore").decode()  # cabeçalho HTTP só aceita ASCII
    arquivo = "relatorios_" + "".join(ch if ch.isalnum() else "_" for ch in ascii_).strip("_")[:60] + ".zip"
    return Response(buf.getvalue(), media_type="application/zip", headers={"Content-Disposition": f'attachment; filename="{arquivo}"'})


@router.get("/exportar/cadastro/{tipo}")
def exportar_cadastro(tipo: str, ctx: Contexto = Depends(requer("exportacao.executar")), db: Session = Depends(get_db)):
    """Cadastro atual no mesmo formato do modelo de importação: edite e reenvie em Importar planilha."""
    from app.services import exportacao_planilhas, modelos_planilha
    if tipo not in modelos_planilha.MODELOS:
        raise NaoEncontrado("Cadastro inexistente.")
    linhas = exportacao_planilhas.linhas_cadastro(db, tipo, ctx.unidades)
    if tipo == "levantamento_instrutores" and not ctx.pode("dados_pessoais.ler"):
        for l in linhas:
            l[2] = None  # e-mail é dado pessoal
    arq = modelos_planilha.gerar_modelo(db, tipo, linhas)
    auditoria.registrar(db, ctx, "exportacao.cadastro", tipo, None, depois={"linhas": len(linhas)})
    db.commit()
    return _xlsx(arq, f"cadastro_{tipo}")


@router.get("/exportar/comparativo")
def exportar_comparativo(cenarios_ids: str, formato: str = "xlsx", ctx: Contexto = Depends(requer("exportacao.executar")), db: Session = Depends(get_db)):
    ids = [int(x) for x in cenarios_ids.split(",")]
    r = cenarios.comparar(db, ids)
    linhas = []
    from app.solver.criterios import descricao_criterios
    desc = {c["criterio"]: c["descricao"] for c in descricao_criterios()}
    est = {"em_elaboracao": "Em edição", "em_validacao": "Em validação", "aguardando_aprovacao": "Aguardando aprovação", "aprovado": "Aprovado",
           "publicado": "Publicado", "arquivado": "Arquivado"}
    for c in r["cenarios"]:
        l = {"Versão": c["cenario"]["nome"], "Situação": est.get(c["cenario"]["estado"], c["cenario"]["estado"]),
             "Pontuação total (menor = melhor)": c["avaliacao"]["pontuacao_total"], "Aulas": c["indicadores"]["aulas"],
             "Horas programadas": c["indicadores"]["horas_programadas"], "Carga pendente (h)": c["carga_pendente_h"],
             "Ocupação das salas (%)": c["indicadores"]["taxa_ocupacao_ambientes_pct"],
             "Ocupação dos instrutores (%)": c["indicadores"]["ocupacao_media_instrutores_pct"], "Conflitos (bloqueios)": (c["validacao"] or {}).get("bloqueios")}
        for cr in c["avaliacao"]["criterios"]:
            l[f"{desc.get(cr['criterio'], cr['criterio'])} ({cr['unidade']})"] = cr["valor_bruto"]
        linhas.append(l)
    return _arquivo(linhas, formato, "comparativo_versoes", "Comparativo de versões (mesmos pesos)", aba="comparativo", meta=_meta(db, ctx))


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
    from app.services.regras_aula import CHAVE, regras_aula
    itens = [auditoria.snapshot(c) for c in db.scalars(select(Configuracao).order_by(Configuracao.chave))]
    if not any(c["chave"] == CHAVE for c in itens):  # regra padrão ainda não personalizada
        itens.append({"chave": CHAVE, "valor": regras_aula(db), "descricao": DESCRICAO_REGRAS})
    return itens


DESCRICAO_REGRAS = ("Composição das aulas: com 'turno inteiro', cada UC ocupa todas as aulas do turno no dia; aula parcial só no fechamento "
                    "da carga horária (dividindo o turno com outra UC que também esteja fechando). 'hora_aula': cada aula conta 1 h de carga horária.")


@router.put("/configuracoes/{chave}")
def salvar_config(chave: str, d: dict = Body(...), ctx: Contexto = Depends(requer("configuracoes.editar")), db: Session = Depends(get_db)):
    c = db.get(Configuracao, chave)
    from app.services.regras_aula import CHAVE, PADRAO
    if c is None and chave == CHAVE:
        c = Configuracao(chave=CHAVE, valor=dict(PADRAO), descricao=DESCRICAO_REGRAS)
        db.add(c)
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
