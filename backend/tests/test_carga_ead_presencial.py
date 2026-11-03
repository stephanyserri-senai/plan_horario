"""Carga horária TOTAL = EaD + PRESENCIAL por UC: importação, cadastro, gerador, impacto/correção do planejamento.

Casos obrigatórios: AIT PAGANTE (1.200 h = 200 EaD + 1.000 presenciais; Prototipagem de negócios inovadores 24 h = 8 EaD +
16 presenciais), INST PAGANTE (1.280 h = 256 EaD + 1.024 presenciais; Manutenção de Sistemas de Instrumentação 80 h
totalmente EaD), carga presencial zero, reimportação sem duplicar e públicos independentes."""
from sqlalchemy import func, select

from app.core.estrutura import garantir_estrutura_fixa
from app.models import Alocacao, Curso, MatrizCurricular, UnidadeCurricular
from app.services import carga_uc, importacao, otimizacao
from tests.conftest import aula
from tests.test_otimizacao import executar

CAB = ("Código do curso;Nome do curso;Área;Modalidade;Versão da matriz;Público / versão do curso;Código da UC;Nome da UC;"
       "Carga horária da UC (h) *;Modalidade da UC;Carga horária EaD (h);Carga horária presencial (h)\n")


def _linhas(curso, nome, area, publico, ucs):
    return "".join(f"{curso};{nome};{area};presencial;2026.1;{publico};{c};{n};{t};{mod};{e};{p}\n" for c, n, t, mod, e, p in ucs)


AIT_PAGANTE = [("PNI", "Prototipagem de negócios inovadores", 24, "semipresencial", 8, ""),  # presencial calculada: 16
               ("AUT1", "Automação industrial", 400, "", 192, 208),
               ("AUT2", "Controladores programáveis", 776, "presencial", "", "")]
INST_PAGANTE = [("MSI", "Manutenção de Sistemas de Instrumentação", 80, "EAD", "", 0),  # presencial zero, EaD calculada: 80
                ("INS1", "Instrumentação básica", 200, "", 176, 24),
                ("INS2", "Malhas de controle", 1000, "", 0, 1000)]


def _importar(db, ctx, csv_, opcoes=None):
    imp = importacao.gerar_previa(db, ctx, "estrutura.csv", csv_.encode(), tipo="estrutura_curricular", opcoes=opcoes)
    db.commit()
    return imp


def _confirmar(db, ctx, imp):
    rel = importacao.confirmar(db, ctx, imp.id)
    db.commit()
    return rel


def _matriz(db, curso, publico):
    c = db.scalar(select(Curso).where(Curso.codigo == curso))
    return db.scalar(select(MatrizCurricular).where(MatrizCurricular.curso_id == c.id, MatrizCurricular.tipo_oferta == publico))


def _somas(db, mat):
    return db.execute(select(func.sum(UnidadeCurricular.carga_horaria_total), func.sum(UnidadeCurricular.carga_horaria_ead),
                             func.sum(UnidadeCurricular.carga_horaria_presencial), func.count())
                      .where(UnidadeCurricular.matriz_id == mat.id)).one()


def test_ait_e_inst_pagante_importados_com_divisao(db, mundo):
    garantir_estrutura_fixa(db)
    db.commit()
    m = mundo
    csv_ = CAB + _linhas("AIT", "Técnico em Automação Industrial", "AUTOMAÇÃO", "PAGANTE", AIT_PAGANTE) \
        + _linhas("INST", "Técnico em Instrumentação", "INSTRUMENTAÇÃO", "PAGANTE", INST_PAGANTE)
    imp = _importar(db, m.ctx, csv_)
    assert imp.previa["resumo"]["erro"] == 0, [i["erros"] for i in imp.previa["itens"] if i["erros"]]
    por = {(x["curso"], x["publico"]): x for x in imp.previa["cargas"]["matrizes"]}
    assert (por[("AIT", "PAGANTE")]["total"], por[("AIT", "PAGANTE")]["ead"], por[("AIT", "PAGANTE")]["presencial"]) == (1200, 200, 1000)
    assert (por[("INST", "PAGANTE")]["total"], por[("INST", "PAGANTE")]["ead"], por[("INST", "PAGANTE")]["presencial"]) == (1280, 256, 1024)
    _confirmar(db, m.ctx, imp)
    ait, inst = _matriz(db, "AIT", "PAGANTE"), _matriz(db, "INST", "PAGANTE")
    assert tuple(_somas(db, ait))[:3] == (1200, 200, 1000)
    assert tuple(_somas(db, inst))[:3] == (1280, 256, 1024)
    pni = db.scalar(select(UnidadeCurricular).where(UnidadeCurricular.matriz_id == ait.id, UnidadeCurricular.codigo == "PNI"))
    assert (pni.carga_horaria_total, pni.carga_horaria_ead, pni.carga_horaria_presencial, pni.modalidade) == (24, 8, 16, "semipresencial")
    msi = db.scalar(select(UnidadeCurricular).where(UnidadeCurricular.matriz_id == inst.id, UnidadeCurricular.codigo == "MSI"))
    assert (msi.carga_horaria_total, msi.carga_horaria_ead, msi.carga_horaria_presencial, msi.modalidade) == (80, 80, 0, "ead")
    assert pni.divisao_confirmada and msi.divisao_confirmada
    # a modalidade do curso (coluna "Modalidade") não foi propagada às UCs; o curso passou a prever UCs com EaD
    curso = db.scalar(select(Curso).where(Curso.codigo == "AIT"))
    assert curso.modalidade == "presencial" and curso.preve_ead
    # reimportar a mesma matriz não duplica
    imp2 = _importar(db, m.ctx, csv_)
    assert {i["acao"] for i in imp2.previa["itens"]} == {"sem_alteracao"}
    _confirmar(db, m.ctx, imp2)
    assert _somas(db, ait)[3] == 3 and _somas(db, inst)[3] == 3


def test_publicos_independentes_e_correcao_por_reimportacao(db, mundo):
    garantir_estrutura_fixa(db)
    db.commit()
    m = mundo
    sedu = [("PNI", "Prototipagem de negócios inovadores", 24, "presencial", 0, 24)]
    csv_ = CAB + _linhas("AIT", "Técnico em Automação Industrial", "AUTOMAÇÃO", "PAGANTE", AIT_PAGANTE[:1]) \
        + _linhas("AIT", "Técnico em Automação Industrial", "AUTOMAÇÃO", "SEDU", sedu)
    _confirmar(db, m.ctx, _importar(db, m.ctx, csv_))
    # corrigir a divisão do PAGANTE (mesma total) numa versão já cadastrada: atualiza só o PAGANTE
    corr = CAB + _linhas("AIT", "Técnico em Automação Industrial", "AUTOMAÇÃO", "PAGANTE",
                         [("PNI", "Prototipagem de negócios inovadores", 24, "", 12, 12)])
    imp = _importar(db, m.ctx, corr)
    assert imp.previa["itens"][0]["acao"] == "atualizar"
    _confirmar(db, m.ctx, imp)
    pag, sed = _matriz(db, "AIT", "PAGANTE"), _matriz(db, "AIT", "SEDU")
    assert tuple(_somas(db, pag)) == (24, 12, 12, 1)
    assert tuple(_somas(db, sed)) == (24, 0, 24, 1)


def test_conflitos_e_planilha_antiga(db, mundo):
    garantir_estrutura_fixa(db)
    db.commit()
    m = mundo
    ruins = [("X1", "Modalidade não bate", 24, "presencial", 8, ""),
             ("X2", "Soma diferente", 24, "", 8, 10),
             ("X3", "Negativa", 24, "", -4, ""),
             ("X4", "Parcela maior que a total", 24, "", "", 30),
             ("X5", "Semipresencial sem as horas", 24, "semipresencial", "", "")]
    imp = _importar(db, m.ctx, CAB + _linhas("AIT", "Técnico em Automação Industrial", "AUTOMAÇÃO", "PAGANTE", ruins))
    assert [i["acao"] for i in imp.previa["itens"]] == ["erro"] * 5
    assert imp.previa["cargas"]["inconsistencias"] == 5
    # planilha antiga (sem as colunas): não assume presencial; pede a distribuição e só então importa
    antiga = ("Código do curso;Nome do curso;Área;Código da UC;Nome da UC;Carga horária da UC (h)\n"
              "AIT;Técnico em Automação Industrial;AUTOMAÇÃO;OLD1;UC antiga;40\n")
    imp = _importar(db, m.ctx, antiga)
    assert imp.previa["cargas"]["divisao_pendente"] == 1 and imp.previa["resumo"]["erro"] == 1
    imp = importacao.gerar_previa(db, m.ctx, "estrutura.csv", antiga.encode(), tipo="estrutura_curricular", importacao_id=imp.id,
                                  opcoes={"distribuicao": {"tipo": "percentual_ead", "valor": 20}})
    db.commit()
    assert imp.previa["resumo"]["erro"] == 0 and imp.previa["cargas"]["ead"] == 8 and imp.previa["cargas"]["presencial"] == 32


def test_regras_de_carga():
    r = carga_uc.resolver("24", "8", None, "semipresencial")
    assert (r["carga_horaria_presencial"], r["modalidade"]) == (16, "semipresencial")
    assert carga_uc.resolver(80, None, 0, None)["modalidade"] == "ead"
    assert carga_uc.resolver(40, "", "", "presencial")["carga_horaria_presencial"] == 40
    assert carga_uc.resolver(40, None, None, None).get("pendente")
    for args in ((24, 8, 10, None), (24, -1, None, None), (24, 0, 24, "ead"), (24, "8,5", None, None)):
        try:
            carga_uc.resolver(*args)
            raise AssertionError(args)
        except carga_uc.ErroCarga:
            pass


def test_gerador_usa_so_a_carga_presencial(db, mundo):
    """UC de 40 h com 20 h EaD: o gerador programa só as 20 h presenciais; UC totalmente EaD não gera aula nem reserva."""
    m = mundo
    m.uc_a.carga_horaria_ead, m.uc_a.carga_horaria_presencial, m.uc_a.modalidade = 20, 20, "semipresencial"
    m.uc_b.carga_horaria_ead, m.uc_b.carga_horaria_presencial, m.uc_b.modalidade = 40, 0, "ead"
    db.commit()
    ucs = {t.uc_id for t in otimizacao.turma_ucs_do_escopo(db, m.cen, {"tipo": "instituicao"})}
    assert m.uc_b.id not in ucs and m.uc_a.id in ucs
    ex = executar(db, m)
    assert ex.status == "concluida"
    for turma in (m.t1, m.t2):
        mins_a = db.scalar(select(func.coalesce(func.sum(Alocacao.minutos_aula), 0)).where(
            Alocacao.cenario_id == m.cen.id, Alocacao.turma_id == turma.id, Alocacao.uc_id == m.uc_a.id))
        assert 0 < mins_a <= 20 * 60, mins_a
        assert not db.scalar(select(func.count()).select_from(Alocacao).where(Alocacao.turma_id == turma.id, Alocacao.uc_id == m.uc_b.id))


def test_validacao_bloqueia_aula_presencial_de_uc_so_ead(db, mundo):
    from app.services.alocacao import criar_aula
    from app.core.errors import ConflitoValidacao
    m = mundo
    m.uc_b.carga_horaria_ead, m.uc_b.carga_horaria_presencial, m.uc_b.modalidade = 40, 0, "ead"
    db.commit()
    try:
        criar_aula(db, m.ctx, m.cen.id, aula(m, db, m.t1, m.uc_b, instrutor=m.i1, ambiente=m.s1))
        raise AssertionError("deveria bloquear")
    except ConflitoValidacao as e:
        assert "UC_SO_EAD" in str(e.detalhes) or "totalmente EaD" in str(e.detalhes) + e.mensagem


def test_impacto_e_correcao_preservam_realizadas(db, mundo):
    from app.services import correcao_carga
    from app.services.alocacao import criar_aula
    m = mundo
    from datetime import timedelta
    from tests.conftest import SEG
    a1, a2, a3 = (criar_aula(db, m.ctx, m.cen.id, aula(m, db, m.t1, m.uc_a, d=SEG + timedelta(days=7 * k), instrutor=m.i1, ambiente=m.s1))[0]
                  for k in range(3))
    db.commit()
    a1.status = "realizada"
    por_aula = a1.minutos_aula
    # nova divisão: só cabe 1 aula presencial (o resto é EaD)
    m.uc_a.carga_horaria_presencial = por_aula // 60 or 1
    m.uc_a.carga_horaria_ead = 40 - m.uc_a.carga_horaria_presencial
    m.uc_a.modalidade = "semipresencial"
    db.commit()
    imp = correcao_carga.impacto(db, m.cen.id)
    item = next(i for i in imp["itens"] if i["uc"] == "A" and i["turma"] == m.t1.codigo)
    assert item["aulas_a_remover"] == 2 and item["presencial_h"] == m.uc_a.carga_horaria_presencial
    r = correcao_carga.aplicar(db, m.ctx, m.cen.id)
    db.commit()
    assert r["aulas_removidas"] == 2
    ids = {a.id for a in db.scalars(select(Alocacao).where(Alocacao.cenario_id == m.cen.id, Alocacao.uc_id == m.uc_a.id, Alocacao.turma_id == m.t1.id))}
    assert a1.id in ids and a2.id not in ids and a3.id not in ids  # a realizada ficou
