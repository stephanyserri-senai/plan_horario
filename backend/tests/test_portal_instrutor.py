"""Portal do instrutor: acesso criado pela coordenação, o instrutor atualiza os próprios dados (direto no cadastro),
vê as turmas/UCs e horários atribuídos e envia observações que a coordenação lê e responde."""
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import app
from app.models import Alocacao, HabilitacaoInstrutor, Instrutor, TurmaUC, Usuario
from tests.test_otimizacao import executar


def _login(c, email, senha):
    r = c.post("/api/auth/login", json={"email": email, "senha": senha})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def test_portal_do_instrutor_ponta_a_ponta(db, mundo):
    m = mundo
    assert executar(db, m).status == "concluida"
    aula = db.scalars(select(Alocacao).where(Alocacao.instrutor_id.isnot(None))).first()
    inst = db.get(Instrutor, aula.instrutor_id)
    outra_tuc = db.scalars(select(TurmaUC).where(TurmaUC.id.notin_(select(Alocacao.turma_uc_id).where(Alocacao.instrutor_id == inst.id)))).first()
    c = TestClient(app)
    adm = _login(c, "admin@teste", "senha-forte-1")

    # coordenação libera o acesso (login local: senha inicial)
    r = c.post(f"/api/instrutores/{inst.id}/acesso", json={"email": "prof@teste", "senha": "curta"}, headers=adm)
    assert r.status_code == 422 or r.status_code == 400
    r = c.post(f"/api/instrutores/{inst.id}/acesso", json={"email": "prof@teste", "senha": "senha-prof-123"}, headers=adm)
    assert r.status_code == 200, r.text
    assert c.post(f"/api/instrutores/{inst.id}/acesso", json={"email": "x@teste", "senha": "senha-prof-123"}, headers=adm).status_code == 409
    assert c.get(f"/api/cadastros/instrutores/{inst.id}", headers=adm).json()["_acesso_portal"]["email"] == "prof@teste"

    h = _login(c, "prof@teste", "senha-prof-123")
    me = c.get("/api/auth/me", headers=h).json()
    assert me["perfil"] == "instrutor" and me["acoes"] == ["portal.instrutor"] and me["instrutor_id"] == inst.id
    # só o portal: nada de cadastros, grade ou semestres de outros
    for url in ("/api/cenarios", "/api/cadastros/instrutores", "/api/observacoes-instrutores", f"/api/painel?cenario_id={m.cen.id}"):
        assert c.get(url, headers=h).status_code == 403, url

    # meus dados: atualiza direto no cadastro
    eu = c.get("/api/portal/eu", headers=h).json()
    assert eu["nome"] == inst.nome and eu["turnos"]
    ucs = c.get("/api/portal/ucs", headers=h).json()
    r = c.put("/api/portal/eu", json={"certificacoes": ["NR-10", "NR-12"], "formacao": "Eng. elétrica; 10 anos de manutenção",
                                       "disp_turnos": [eu["turnos"][0]["id"]], "disp_dias": [0, 1, 2, 3, 4],
                                       "ucs_competencia": [{"uc_id": u["id"], "nivel": "pleno"} for g in ucs for u in g["ucs"]][:2]}, headers=h)
    assert r.status_code == 200, r.text
    db.expire_all()
    i2 = db.get(Instrutor, inst.id)
    assert i2.atualizado_pelo_instrutor_em is not None and i2.areas_competencia.startswith("Eng.")
    assert sorted(h_.nome for h_ in db.scalars(select(HabilitacaoInstrutor).where(HabilitacaoInstrutor.instrutor_id == inst.id,
                                                                                    HabilitacaoInstrutor.ativo.is_(True)))) == ["NR-10", "NR-12"]
    # não pode se dar UC de fora das áreas dele
    assert c.put("/api/portal/eu", json={"ucs_competencia": [{"uc_id": 999999, "nivel": "pleno"}]}, headers=h).status_code == 409

    # minhas turmas e horários
    sems = c.get("/api/portal/turmas", headers=h).json()
    assert sems and sems[0]["turmas_ucs"] and sems[0]["aulas"]
    item = sems[0]["turmas_ucs"][0]
    assert item["horarios"] and item["turma_codigo"]
    assert c.get(f"/api/portal/agenda?cenario_id={sems[0]['cenario_id']}", headers=h).status_code == 200

    # observações: só sobre o que é dele
    r = c.post("/api/portal/observacoes", json={"turma_uc_id": item["turma_uc_id"], "tipo": "recurso", "texto": "Preciso do kit de CLP nas aulas práticas."}, headers=h)
    assert r.status_code == 200, r.text
    if outra_tuc:
        assert c.post("/api/portal/observacoes", json={"turma_uc_id": outra_tuc.id, "texto": "teste"}, headers=h).status_code == 403
    painel = c.get(f"/api/painel?cenario_id={m.cen.id}", headers=adm).json()
    assert any("observação" in a["texto"] for a in painel["atencao"])
    lista = c.get("/api/observacoes-instrutores?status=nova", headers=adm).json()
    assert len(lista) == 1 and lista[0]["instrutor"] == inst.nome
    r = c.put(f"/api/observacoes-instrutores/{lista[0]['id']}", json={"resposta": "Reservado o kit para as quintas.", "status": "resolvida"}, headers=adm)
    assert r.status_code == 200 and r.json()["respondido_por"]
    minhas = c.get("/api/portal/observacoes", headers=h).json()
    assert minhas[0]["status"] == "resolvida" and minhas[0]["resposta"].startswith("Reservado")

    # usuário instrutor sem vínculo recebe mensagem clara
    u = db.scalar(select(Usuario).where(Usuario.email == "prof@teste"))
    u.instrutor_id = None
    db.commit()
    r = c.get("/api/portal/eu", headers=h)
    assert r.status_code == 403 and "coordenação" in r.text


def test_sql_do_instrutor_de_teste(db, mundo):
    """backend/sql/instrutor_teste_portal.sql: roda duas vezes sem duplicar e o login do portal funciona."""
    from pathlib import Path

    from sqlalchemy import text

    from app.core.estrutura import garantir_estrutura_fixa
    garantir_estrutura_fixa(db)
    db.commit()
    sql = (Path(__file__).resolve().parents[1] / "sql" / "instrutor_teste_portal.sql").read_text(encoding="utf-8")
    conn = db.connection().connection.driver_connection
    for _ in range(2):
        conn.execute(sql.encode())
    conn.commit()
    assert db.scalar(text("SELECT count(*) FROM usuarios WHERE email = 'instrutor.teste'")) == 1
    assert db.scalar(text("SELECT count(*) FROM disponibilidade_instrutores d JOIN instrutores i ON i.id = d.instrutor_id WHERE i.matricula = 'TESTE-PORTAL'")) == 10
    c = TestClient(app)
    h = _login(c, "instrutor.teste", "instrutor@123")
    eu = c.get("/api/portal/eu", headers=h).json()
    assert eu["matricula"] == "TESTE-PORTAL" and eu["area_principal"]["nome"] == "ENERGIAS" and len(eu["disp_turnos"]) == 2
    assert eu["notificacoes_novas"] == 1
