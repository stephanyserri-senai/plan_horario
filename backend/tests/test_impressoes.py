"""Pedidos de impressão: o instrutor pede pelo portal até a quinta-feira da semana anterior ao uso; a coordenação dá o retorno."""
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from app.core.errors import ConflitoValidacao
from app.main import app
from app.models import Notificacao
from app.services import impressoes


def test_prazo_e_quinta_da_semana_anterior():
    # uso na quarta 18/11/2026 → prazo na quinta 12/11; uso na segunda 16/11 → também 12/11
    assert impressoes.prazo_para(date(2026, 11, 18)) == date(2026, 11, 12)
    assert impressoes.prazo_para(date(2026, 11, 16)) == date(2026, 11, 12)
    assert impressoes.prazo_para(date(2026, 11, 21)) == date(2026, 11, 12)  # sábado da mesma semana


def test_pedido_fluxo_e_retorno(db, mundo, monkeypatch):
    m = mundo
    monkeypatch.setattr(impressoes, "hoje", lambda: date(2026, 11, 12))  # quinta-feira
    s = impressoes.criar(db, m.ctx, m.i1, {"titulo": "Apostila de NR-10", "data_uso": "2026-11-18", "copias": 30, "paginas": 12, "frente_verso": True})
    db.commit()
    assert s.prazo == date(2026, 11, 12) and s.status == "pendente"
    assert impressoes.serializar(db, s)["folhas"] == 180
    # na sexta já não dá para a semana seguinte
    monkeypatch.setattr(impressoes, "hoje", lambda: date(2026, 11, 13))
    with pytest.raises(ConflitoValidacao) as e:
        impressoes.criar(db, m.ctx, m.i1, {"titulo": "Prova", "data_uso": "2026-11-17", "copias": 30})
    assert e.value.codigo == "IMPRESSAO_FORA_DO_PRAZO"
    db.rollback()
    # coordenação: em produção → pronta (o instrutor é avisado) → entregue; não volta atrás
    impressoes.atender(db, m.ctx, s.id, "em_producao")
    impressoes.atender(db, m.ctx, s.id, "pronta", "Pronta para retirar na coordenação")
    db.commit()
    avisos = [n.titulo for n in db.query(Notificacao).filter(Notificacao.instrutor_id == m.i1.id)]
    assert any("pronta" in t for t in avisos)
    with pytest.raises(ConflitoValidacao):
        impressoes.atender(db, m.ctx, s.id, "pendente")
    impressoes.atender(db, m.ctx, s.id, "entregue")
    db.commit()
    assert impressoes.listar(db, instrutor_id=m.i1.id)[0]["status"] == "entregue"


def test_api_coordenacao(db, mundo, monkeypatch):
    m = mundo
    monkeypatch.setattr(impressoes, "hoje", lambda: date(2026, 11, 10))
    impressoes.criar(db, m.ctx, m.i2, {"titulo": "Lista de exercícios", "data_uso": "2026-11-19", "copias": 25})
    db.commit()
    c = TestClient(app)
    h = {"Authorization": "Bearer " + c.post("/api/auth/login", json={"email": "admin@teste", "senha": "senha-forte-1"}).json()["token"]}
    lst = c.get("/api/impressoes?status=pendente", headers=h).json()
    assert len(lst) == 1 and lst[0]["instrutor"] == m.i2.nome
    r = c.put(f"/api/impressoes/{lst[0]['id']}", json={"status": "recusada"}, headers=h)
    assert r.status_code == 422  # recusa precisa de motivo
    r = c.put(f"/api/impressoes/{lst[0]['id']}", json={"status": "pronta", "resposta": "Na sala dos professores"}, headers=h)
    assert r.status_code == 200 and r.json()["status"] == "pronta"


def test_pdf_do_pedido(db, mundo, monkeypatch):
    m = mundo
    monkeypatch.setattr(impressoes, "hoje", lambda: date(2026, 11, 10))
    s = impressoes.criar(db, m.ctx, m.i1, {"titulo": "Prova", "data_uso": "2026-11-19", "copias": 20})
    db.commit()
    with pytest.raises(Exception):
        impressoes.anexar_pdf(db, m.ctx, m.i1, s.id, "prova.docx", b"PK\x03\x04 nao e pdf")
    impressoes.anexar_pdf(db, m.ctx, m.i1, s.id, "prova.pdf", b"%PDF-1.4 conteudo")
    db.commit()
    d = impressoes.serializar(db, s)
    assert d["tem_pdf"] and d["arquivo_nome"] == "prova.pdf"
    c = TestClient(app)
    h = {"Authorization": "Bearer " + c.post("/api/auth/login", json={"email": "admin@teste", "senha": "senha-forte-1"}).json()["token"]}
    r = c.get(f"/api/impressoes/{s.id}/pdf", headers=h)
    assert r.status_code == 200 and r.content.startswith(b"%PDF") and r.headers["content-type"] == "application/pdf"
    with pytest.raises(Exception):  # acima de 4 MB
        impressoes.anexar_pdf(db, m.ctx, m.i1, s.id, "grande.pdf", b"%PDF" + b"0" * (impressoes.MAX_PDF + 1))
