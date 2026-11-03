"""O sábado do instrutor independe dos turnos de segunda a sexta: M (09–13), V (14–18), os dois ou nenhum."""
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.estrutura import garantir_estrutura_fixa
from app.main import app
from app.models import Area, DisponibilidadeInstrutor, Unidade


def test_sabado_independente_da_jornada(db, mundo):
    garantir_estrutura_fixa(db)
    db.commit()
    c = TestClient(app)
    h = {"Authorization": "Bearer " + c.post("/api/auth/login", json={"email": "admin@teste", "senha": "senha-forte-1"}).json()["token"]}
    bm = db.scalar(select(Unidade).where(Unidade.codigo == "BEIRA-MAR"))
    area = db.scalar(select(Area).where(Area.unidade_id == bm.id, Area.codigo == "ENERGIAS"))
    base = {"matricula": "SAB-1", "nome": "Instrutor Sábado", "area_id": area.id, "carga_horaria_contratual": 20, "max_horas_dia": 4,
            "jornada": "N", "disp_dias": [0, 1, 2, 3, 4], "disp_sabado": "V"}
    r = c.post("/api/cadastros/instrutores", json=base, headers=h)
    assert r.status_code == 200, r.text
    iid = r.json()["id"]

    def sab():
        return sorted((d.hora_inicio.strftime("%H:%M"), d.hora_fim.strftime("%H:%M")) for d in db.scalars(
            select(DisponibilidadeInstrutor).where(DisponibilidadeInstrutor.instrutor_id == iid, DisponibilidadeInstrutor.dia_semana == 5)))
    # noturno na semana e vespertino no sábado
    assert sab() == [("14:00", "18:00")]
    assert c.get(f"/api/cadastros/instrutores/{iid}", headers=h).json()["disp_sabado"] == "V"
    # muda só o sábado: M e V; a semana continua noturna
    inst = c.get(f"/api/cadastros/instrutores/{iid}", headers=h).json()
    assert c.put(f"/api/cadastros/instrutores/{iid}", json={**inst, "disp_sabado": "MV"}, headers=h).status_code == 200
    db.expire_all()
    assert sab() == [("09:00", "13:00"), ("14:00", "18:00")]
    assert c.get(f"/api/cadastros/instrutores/{iid}", headers=h).json()["jornada"] == "N"
    assert c.put(f"/api/cadastros/instrutores/{iid}", json={**inst, "disp_sabado": "X"}, headers=h).status_code == 422
    assert c.put(f"/api/cadastros/instrutores/{iid}", json={**inst, "disp_sabado": ""}, headers=h).status_code == 200
    db.expire_all()
    assert sab() == []


def test_aba_uniforme_no_perfil(db, mundo):
    c = TestClient(app)
    h = {"Authorization": "Bearer " + c.post("/api/auth/login", json={"email": "admin@teste", "senha": "senha-forte-1"}).json()["token"]}
    iid = mundo.i1.id
    r = c.put(f"/api/instrutores/{iid}/uniforme", json={"gestor_imediato": "Gestor da área", "jaleco_np": "44", "jaleco_pmg": "m",
                                                       "jaleco_num": "7", "tamanho_blusa": "g", "numero_botina": "41"}, headers=h)
    assert r.status_code == 200, r.text
    u = c.get(f"/api/instrutores/{iid}/perfil", headers=h).json()["dados"]
    assert u["gestor_imediato"] == "Gestor da área"
    assert u["uniforme"] == {"jaleco_np": "44", "jaleco_pmg": "M", "jaleco_num": "7", "tamanho_blusa": "G", "numero_botina": "41"}
    assert c.put(f"/api/instrutores/{iid}/uniforme", json={"jaleco_pmg": "Z"}, headers=h).status_code == 422
