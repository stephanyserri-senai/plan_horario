"""Substituição de instrutor (aula ou período, inclusive em semestre publicado) e notificações do instrutor no portal."""
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import app
from app.models import Alocacao, CenarioPlanejamento, ExcecaoAutorizada, Instrutor, Notificacao
from tests.test_otimizacao import executar


def _login(c, email, senha):
    r = c.post("/api/auth/login", json={"email": email, "senha": senha})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def test_substituicao_e_notificacoes(db, mundo, monkeypatch):
    m = mundo
    from datetime import date
    from app.services import substituicao
    monkeypatch.setattr(substituicao, "hoje", lambda: date(2026, 1, 5))  # substituições planejadas com antecedência
    assert executar(db, m).status == "concluida"
    aula = db.scalars(select(Alocacao).where(Alocacao.instrutor_id.isnot(None)).order_by(Alocacao.inicio)).first()
    titular = aula.instrutor_id
    c = TestClient(app)
    adm = _login(c, "admin@teste", "senha-forte-1")
    # candidatos para a aula: quem está livre (da área ou com justificativa) vem primeiro; o titular não aparece
    cand = c.get(f"/api/substituicoes/candidatos?cenario_id={m.cen.id}&alocacao_id={aula.id}", headers=adm).json()
    assert cand["aulas"] == 1 and all(i["id"] != titular for i in cand["instrutores"])
    livres = [i for i in cand["instrutores"] if i["grupo"] in ("recomendado", "excecao")]
    assert livres, cand
    assert [i["grupo"] for i in cand["instrutores"]] == sorted((i["grupo"] for i in cand["instrutores"]),
                                                              key=["recomendado", "excecao", "parcial", "indisponivel"].index)
    sub = db.get(Instrutor, livres[0]["id"])
    # instrutores com acesso ao portal (para conferir as notificações)
    for inst_id, email in ((titular, "tit@teste"), (sub.id, "sub@teste")):
        assert c.post(f"/api/instrutores/{inst_id}/acesso", json={"email": email, "senha": "senha-inst-123"}, headers=adm).status_code == 200
    h_tit, h_sub = _login(c, "tit@teste", "senha-inst-123"), _login(c, "sub@teste", "senha-inst-123")

    corpo = {"cenario_id": m.cen.id, "instrutor_id": titular, "inicio": aula.data.isoformat(), "fim": aula.data.isoformat(),
             "substituto_id": sub.id, "motivo": "curto"}
    assert c.post("/api/substituicoes", json=corpo, headers=adm).status_code in (400, 422)  # motivo obrigatório
    corpo["motivo"] = "Falta do titular por motivo de saúde"
    previa = c.post("/api/substituicoes", json={**corpo, "somente_validar": True}, headers=adm).json()
    assert previa["previa"] and previa["possiveis"] >= 1, (previa, cand)
    db.expire_all()
    assert db.get(Alocacao, aula.id).instrutor_id == titular  # a prévia não grava

    # semestre publicado: edição comum bloqueada, mas a substituição é permitida
    cen = db.get(CenarioPlanejamento, m.cen.id)
    cen.estado = "publicado"
    db.commit()
    r = c.post("/api/substituicoes", json=corpo, headers=adm)
    assert r.status_code == 200, r.text
    res = r.json()
    assert res["substituidas"] >= 1 and res["cenario_publicado"]
    db.expire_all()
    a = db.get(Alocacao, aula.id)
    assert a.instrutor_id == sub.id and a.instrutor_titular_id == titular and a.fixa and a.observacao.startswith("Substituição")
    grade = c.get(f"/api/grade?cenario_id={m.cen.id}&instrutor_id={sub.id}", headers=adm).json()
    assert any(g["id"] == aula.id and g["instrutor_titular"] for g in grade)
    lista = c.get(f"/api/substituicoes?cenario_id={m.cen.id}", headers=adm).json()
    assert lista and lista[0]["motivo"].startswith("Falta")

    # notificações: substituto e titular avisados; o substituto vê a aula marcada
    n_sub = c.get("/api/portal/notificacoes", headers=h_sub).json()
    n_tit = c.get("/api/portal/notificacoes", headers=h_tit).json()
    assert any("Você vai substituir" in n["titulo"] for n in n_sub) and any("vai substituir você" in n["titulo"] for n in n_tit)
    assert c.get("/api/portal/eu", headers=h_sub).json()["notificacoes_novas"] >= 1
    turmas = c.get("/api/portal/turmas", headers=h_sub).json()
    assert any(t["substituindo"] for s in turmas for t in s["turmas_ucs"])
    assert c.post("/api/portal/notificacoes/lidas", json={}, headers=h_sub).json()["marcadas"] >= 1
    assert c.get("/api/portal/eu", headers=h_sub).json()["notificacoes_novas"] == 0

    # desfazer devolve ao titular e avisa os dois
    r = c.post("/api/substituicoes/desfazer", json={"alocacao_ids": [x["alocacao_id"] for x in res["aulas"]]}, headers=adm)
    assert r.status_code == 200 and r.json()["desfeitas"] >= 1, r.text
    db.expire_all()
    assert db.get(Alocacao, aula.id).instrutor_id == titular and db.get(Alocacao, aula.id).instrutor_titular_id is None
    assert any("voltaram" in n["titulo"] for n in c.get("/api/portal/notificacoes", headers=h_tit).json())

    # alteração no cadastro pela coordenação gera aviso; a do próprio instrutor no portal, não
    antes = db.scalar(select(Notificacao).where(Notificacao.instrutor_id == sub.id).order_by(Notificacao.id.desc())).id
    inst = c.get(f"/api/cadastros/instrutores/{sub.id}", headers=adm).json()
    r = c.put(f"/api/cadastros/instrutores/{sub.id}", json={**inst, "carga_horaria_contratual": 20, "limite_ch_letiva": 16, "max_horas_dia": 4}, headers=adm)
    assert r.status_code == 200, r.text
    novas = c.get("/api/portal/notificacoes", headers=h_sub).json()
    assert novas[0]["titulo"] == "Seu cadastro foi atualizado" and "carga contratual" in novas[0]["texto"] and "nome" not in novas[0]["texto"]
    c.put("/api/portal/eu", json={"formacao": "Técnico em eletrotécnica"}, headers=h_sub)
    assert db.scalar(select(Notificacao).where(Notificacao.instrutor_id == sub.id).order_by(Notificacao.id.desc())).id == novas[0]["id"]
    assert antes < novas[0]["id"]
    # exceções de substituição só existem quando foram necessárias
    for e in db.scalars(select(ExcecaoAutorizada)):
        assert e.justificativa.startswith("Substituição")
