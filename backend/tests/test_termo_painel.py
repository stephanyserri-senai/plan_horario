"""Termo de horas no perfil: painel com o próximo mês (feito no fim do mês) e a sugestão do que entra nele — o dia em que foi
preciso contar com o horista fora do termo vai para o termo do mês seguinte."""
from datetime import date, datetime, timedelta

from fastapi.testclient import TestClient

from app.main import app
from app.models import TermoHoras
from app.services import alocacao as aloc
from app.services import termos
from tests.conftest import SEG, aula


def test_painel_sugere_o_dia_fora_do_termo_para_o_mes_seguinte(db, mundo):
    m = mundo
    m.i1.modalidade = "horista"
    db.add(TermoHoras(instrutor_id=m.i1.id, mes=SEG.replace(day=1), horas_aula=40, horas_outras=0, dias_semana=[1, 2]))
    db.commit()
    # aula numa segunda (fora do termo de agosto: só terça e quarta)
    aloc.criar_aula(db, m.ctx, m.cen.id, aula(m, db, m.t1, m.uc_a, instrutor=m.i1, ambiente=m.s1))
    db.commit()
    p = termos.painel(db, m.i1, m.cen.id, hoje=SEG + timedelta(days=20))
    ago = next(x for x in p["meses"] if x["mes"] == "2026-08")
    assert ago["situacao"] == "atual" and ago["dias_fora"] == [0] and ago["dias_com_aula"] == [0]
    assert p["proximo"]["mes"] == "2026-09" and p["proximo"]["prazo"] == "2026-08-31" and not p["proximo"]["tem_termo"]
    assert p["proximo"]["sugestao"]["dias_semana"] == [0, 1, 2]
    assert "segunda" in p["proximo"]["sugestao"]["motivos"][0] and "setembro" in p["proximo"]["sugestao"]["motivos"][0]


def test_portal_mostra_o_termo_ao_horista(db, mundo):
    m = mundo
    c = TestClient(app)
    h = {"Authorization": "Bearer " + c.post("/api/auth/login", json={"email": "admin@teste", "senha": "senha-forte-1"}).json()["token"]}
    m.i1.modalidade = "horista"
    db.add(TermoHoras(instrutor_id=m.i1.id, mes=date.today().replace(day=1), horas_aula=30, horas_outras=0))
    db.commit()
    r = c.get(f"/api/instrutores/{m.i1.id}/termos?cenario_id={m.cen.id}", headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["proximo"]["prazo"] and any(x["tem_termo"] for x in r.json()["meses"])


def test_termo_por_dia_e_turno(db, mundo):
    from app.core.errors import EntradaInvalida
    from app.services.validacao import AulaProposta, BaseDados, validar_aula
    m = mundo
    m.i1.modalidade = "horista"
    db.commit()
    ter, qua, sab = SEG + timedelta(days=1), SEG + timedelta(days=2), SEG + timedelta(days=5)
    grade = {ter.isoformat(): {"M": "aula"}, qua.isoformat(): {"V": "aula"}, sab.isoformat(): {"S": "pl"}}
    r = termos.salvar(db, m.ctx, m.i1, "2026-08", 20, 4, None, m.cen.id, agenda=grade)
    db.commit()
    assert r["agenda"][ter.isoformat()] == {"M": {"tipo": "aula"}} and r["dias_semana"] == [1, 2]
    assert r["resumo_agenda"]["turnos_aula"] == 2 and r["resumo_agenda"]["turnos_pl"] == 1
    # turno de sábado só "S"; data de outro mês recusada
    import pytest
    with pytest.raises(EntradaInvalida):
        termos.salvar(db, m.ctx, m.i1, "2026-08", 20, 0, agenda={sab.isoformat(): {"M": "aula"}})
    with pytest.raises(EntradaInvalida):
        termos.salvar(db, m.ctx, m.i1, "2026-08", 20, 0, agenda={"2026-09-01": {"M": "aula"}})
    db.rollback()
    # aula na terça de manhã: no termo; terça à tarde ou segunda: fora (alerta)
    tuc = m.tuc(db, m.t1, m.uc_a)
    def oc(dia, p):
        ini = datetime.combine(dia, m.periodos[p].hora_inicio)
        return [o.regra for o in validar_aula(BaseDados(db, m.cen.id), AulaProposta(turma_uc_id=tuc.id, inicio=ini, fim=ini + timedelta(minutes=100),
                                                                                    minutos_aula=100, instrutor_id=m.i1.id))]
    assert "TERMO_FORA_DOS_DIAS" not in oc(ter, 0)
    assert "TERMO_FORA_DOS_DIAS" in oc(SEG, 0)
    # ajuste por urgência inclui a célula (segunda de manhã)
    t = termos.ajustar(db, m.ctx, m.i1, "2026-08", "Substituição urgente", True, incluir_turnos=[{"data": SEG.isoformat(), "turno": "M"}])
    db.commit()
    assert t["agenda"][SEG.isoformat()] == {"M": {"tipo": "aula"}} and 0 in t["dias_semana"]
    assert "TERMO_FORA_DOS_DIAS" not in oc(SEG, 0)


def test_horario_de_entrada_e_saida_por_dia(db, mundo):
    from app.core.errors import EntradaInvalida
    from app.services.validacao import AulaProposta, BaseDados, validar_aula
    import pytest
    m = mundo
    m.i1.modalidade = "horista"
    db.commit()
    ter, qua = SEG + timedelta(days=1), SEG + timedelta(days=2)
    # terça 07:30–11:30, quarta 08:00–12:00 e uma tarde de 13:00–17:30 (4,5 h)
    grade = {ter.isoformat(): {"M": {"tipo": "aula", "ini": "07:30", "fim": "11:30"}},
             qua.isoformat(): {"M": {"tipo": "aula", "ini": "08:00", "fim": "12:00"}, "V": {"tipo": "pl", "ini": "13:00", "fim": "17:30"}}}
    r = termos.salvar(db, m.ctx, m.i1, "2026-08", 8, 4.5, None, m.cen.id, agenda=grade)
    db.commit()
    assert r["resumo_agenda"]["horas_aula"] == 8.0 and r["resumo_agenda"]["horas_pl"] == 4.5
    with pytest.raises(EntradaInvalida):  # horário fora da faixa do turno
        termos.salvar(db, m.ctx, m.i1, "2026-08", 8, 0, agenda={ter.isoformat(): {"M": {"tipo": "aula", "ini": "13:00", "fim": "17:00"}}})
    db.rollback()
    tuc = m.tuc(db, m.t1, m.uc_a)
    def oc(dia):  # aula 07:30–09:10
        ini = datetime.combine(dia, m.periodos[0].hora_inicio)
        return [o.regra for o in validar_aula(BaseDados(db, m.cen.id), AulaProposta(turma_uc_id=tuc.id, inicio=ini, fim=ini + timedelta(minutes=100),
                                                                                    minutos_aula=100, instrutor_id=m.i1.id))]
    assert "TERMO_FORA_DOS_DIAS" not in oc(ter)  # 07:30–11:30 cobre
    assert "TERMO_FORA_DOS_DIAS" in oc(qua)  # quarta começa às 08:00: aula às 07:30 fica fora
