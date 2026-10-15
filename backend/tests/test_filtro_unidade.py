"""Filtro de unidade do topo (cabeçalho X-Unidade): reduz as consultas à unidade escolhida, nunca amplia o escopo
e não afeta gravações; a lista de unidades continua completa para poder trocar o filtro."""
from fastapi.testclient import TestClient

from app.main import app
from app.models import Unidade


def test_filtro_unidade(db, mundo):
    m = mundo
    outra = Unidade(codigo="OUTRA", nome="Outra unidade", situacao="ativa")
    db.add(outra)
    db.commit()
    c = TestClient(app)
    h = {"Authorization": "Bearer " + c.post("/api/auth/login", json={"email": "admin@teste", "senha": "senha-forte-1"}).json()["token"]}
    da = {**h, "X-Unidade": str(m.unidade.id)}
    fora = {**h, "X-Unidade": str(outra.id)}
    total = c.get("/api/cadastros/turmas", headers=h).json()["total"]
    assert total >= 2 and c.get("/api/cadastros/turmas", headers=da).json()["total"] == total
    assert c.get("/api/cadastros/turmas", headers=fora).json()["total"] == 0
    assert c.get("/api/cadastros/turmas/opcoes", headers=fora).json() == []
    assert c.get("/api/cadastros/ucs", headers=fora).json()["total"] == 0  # por relação (curso da unidade)
    assert len(c.get("/api/cadastros/unidades/opcoes", headers=fora).json()) >= 2  # dá para trocar o filtro
    assert c.get("/api/cadastros/unidades", headers=fora).json()["total"] >= 2
    # gravação não é afetada pelo filtro
    r = c.put(f"/api/cadastros/turmas/{m.t1.id}", json={"qtd_alunos": 29}, headers=fora)
    assert r.status_code == 200, r.text
    # relatórios seguem o filtro e dizem qual unidade
    r = c.get(f"/api/exportar/grade?cenario_id={m.cen.id}&formato=xlsx", headers=fora)
    assert r.status_code == 200
