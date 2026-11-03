"""Senha inicial: no primeiro acesso o usuário só consegue trocar a senha; depois usa o sistema normalmente."""
from fastapi.testclient import TestClient

from app.core.security import hash_senha
from app.main import app
from app.models import Usuario


def test_primeiro_acesso_obriga_trocar_a_senha(db, mundo):
    db.add(Usuario(nome="Analista de Planejamento", email="analista.planejamento@teste", senha_hash=hash_senha("senha-inicial-1"),
                   perfil="planejador", acesso_global=True, ativo=True, trocar_senha=True))
    db.commit()
    c = TestClient(app)
    r = c.post("/api/auth/login", json={"email": "analista.planejamento@teste", "senha": "senha-inicial-1"})
    assert r.status_code == 200 and r.json()["usuario"]["trocar_senha"] is True
    h = {"Authorization": f"Bearer {r.json()['token']}"}
    assert c.get("/api/auth/me", headers=h).json()["trocar_senha"] is True
    assert c.get("/api/cenarios", headers=h).status_code == 403  # antes de trocar, nada além do login
    assert c.post("/api/auth/senha", json={"senha_atual": "senha-inicial-1", "nova_senha": "senha-inicial-1"}, headers=h).status_code == 422
    assert c.post("/api/auth/senha", json={"senha_atual": "senha-inicial-1", "nova_senha": "minha-senha-2026"}, headers=h).status_code == 200
    assert c.get("/api/auth/me", headers=h).json()["trocar_senha"] is False
    assert c.get("/api/cenarios", headers=h).status_code == 200
