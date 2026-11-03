"""Diárias (recursos extras) para instrutores em eventos e projetos: a supervisão registra, aprova ou recusa e marca como paga."""
from fastapi.testclient import TestClient

from app.main import app
from app.models import Notificacao


def _cli():
    c = TestClient(app)
    tok = c.post("/api/auth/login", json={"email": "admin@teste", "senha": "senha-forte-1"}).json()["token"]
    c.headers.update({"Authorization": f"Bearer {tok}"})
    return c


def test_fluxo_das_diarias(db, mundo):
    m = mundo
    c = _cli()
    base = {"instrutor_id": m.i1.id, "motivo": "evento", "titulo": "Feira de robótica", "destino": "Linhares",
            "data_inicio": "2026-09-10", "data_fim": "2026-09-11", "quantidade": "1,5", "valor_unitario": "120,00",
            "outros_recursos": "carro da unidade"}
    # validações: mais diárias que dias, fração que não é meia, motivo inválido, período invertido
    assert c.post("/api/diarias", json={**base, "quantidade": 3}).status_code == 422
    assert c.post("/api/diarias", json={**base, "quantidade": 1.3}).status_code == 422
    assert c.post("/api/diarias", json={**base, "motivo": "ferias"}).status_code == 422
    assert c.post("/api/diarias", json={**base, "data_fim": "2026-09-01"}).status_code == 422
    r = c.post("/api/diarias", json=base)
    assert r.status_code == 200, r.text
    s = r.json()
    assert s["status"] == "solicitada" and s["quantidade"] == 1.5 and s["valor_total"] == 180.0 and s["dias"] == 2
    # alterar enquanto solicitada
    r = c.put(f"/api/diarias/{s['id']}", json={"quantidade": 2})
    assert r.status_code == 200 and r.json()["valor_total"] == 240.0
    # paga só depois de aprovada; recusa exige motivo
    assert c.post(f"/api/diarias/{s['id']}/situacao", json={"status": "paga"}).status_code == 409
    assert c.post(f"/api/diarias/{s['id']}/situacao", json={"status": "recusada"}).status_code == 422
    assert c.post(f"/api/diarias/{s['id']}/situacao", json={"status": "aprovada"}).json()["status"] == "aprovada"
    assert c.put(f"/api/diarias/{s['id']}", json={"quantidade": 1}).status_code == 409
    r = c.post(f"/api/diarias/{s['id']}/situacao", json={"status": "paga", "pago_em": "2026-09-20"}).json()
    assert r["status"] == "paga" and r["pago_em"] == "2026-09-20"
    lista = c.get("/api/diarias").json()
    assert lista["totais"]["paga"]["valor"] == 240.0 and lista["instrutores"]
    avisos = [n.titulo for n in db.query(Notificacao).filter(Notificacao.instrutor_id == m.i1.id)]
    assert any("solicitadas" in a for a in avisos) and any("aprovadas" in a for a in avisos) and any("pagas" in a for a in avisos)
