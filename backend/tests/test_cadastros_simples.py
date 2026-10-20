"""Cadastros enxutos: o que vem de outro cadastro é preenchido sozinho (turma pelo curso, unidade pela área),
código da turma = sigla + número + tipo, e o instrutor recebe UCs e disponibilidade no próprio cadastro."""
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.estrutura import garantir_estrutura_fixa
from app.main import app
from app.models import Area, CompetenciaInstrutor, DisponibilidadeInstrutor, Turma, TurmaUC, Turno, Unidade


def _login(c):
    r = c.post("/api/auth/login", json={"email": "admin@teste", "senha": "senha-forte-1"})
    return {"Authorization": f"Bearer {r.json()['token']}"}


def test_cadastros_preenchem_campos_repetidos(db, mundo):
    garantir_estrutura_fixa(db)
    db.commit()
    c = TestClient(app)
    h = _login(c)
    bm = db.scalar(select(Unidade).where(Unidade.codigo == "BEIRA-MAR"))
    energ = db.scalar(select(Area).where(Area.unidade_id == bm.id, Area.codigo == "ENERGIAS"))
    manha = db.scalar(select(Turno).where(Turno.unidade_id == bm.id, Turno.codigo == "M"))
    # curso: só a área; a unidade vem dela
    r = c.post("/api/cadastros/cursos", json={"codigo": "ELT", "nome": "Técnico em Eletrotécnica", "area_id": energ.id}, headers=h)
    assert r.status_code == 200, r.text
    curso = r.json()
    assert curso["unidade_id"] == bm.id
    mat = c.post("/api/cadastros/matrizes", json={"curso_id": curso["id"], "versao": "2026.1", "situacao": "rascunho"}, headers=h).json()
    uc = c.post("/api/cadastros/ucs", json={"matriz_id": mat["id"], "codigo": "FEL", "nome": "Fundamentos de Eletricidade", "carga_horaria_total": 40}, headers=h)
    assert uc.status_code == 200, uc.text
    uc = uc.json()
    assert uc["duracao_bloco_periodos"] == 4
    # prévia do código
    p = c.get(f"/api/cadastros-apoio/codigo-turma?curso_id={curso['id']}&numero=12&tipo=htc", headers=h).json()
    assert p == {"codigo": "HTC-ELT-12", "existe": False, "sigla": "ELT", "matriz": "2026.1", "modular": None}
    # turma: curso + número + tipo; matriz, área, unidade, código e nome automáticos
    r = c.post("/api/cadastros/turmas", json={"curso_id": curso["id"], "_numero": "12", "_tipo_oferta": "HTC", "turno_id": manha.id,
                                              "qtd_alunos": 30, "data_inicio": "2026-08-03", "data_fim": "2026-12-18"}, headers=h)
    assert r.status_code == 200, r.text
    t = r.json()
    assert t["codigo"] == "HTC-ELT-12" and t["matriz_id"] == mat["id"] and t["unidade_id"] == bm.id and t["area_id"] == energ.id
    assert t["_numero"] == "12" and t["_tipo_oferta"] == "HTC"
    assert "Habilitação técnica" in t["nome"] and "Manhã" in t["nome"]
    assert db.scalar(select(TurmaUC).where(TurmaUC.turma_id == t["id"])) is not None  # UCs ligadas
    # sem número: mensagem clara
    r = c.post("/api/cadastros/turmas", json={"curso_id": curso["id"]}, headers=h)
    assert r.status_code in (400, 422) and "número da turma" in r.text
    # mudar o número reescreve código e nome gerado
    r = c.put(f"/api/cadastros/turmas/{t['id']}", json={**t, "_numero": "13"}, headers=h)
    assert r.status_code == 200, r.text
    assert db.get(Turma, t["id"]).codigo == "HTC-ELT-13"
    # UCs das áreas escolhidas
    lista = c.get(f"/api/cadastros-apoio/ucs-por-area?areas={energ.id}", headers=h).json()
    assert lista[0]["ucs"][0]["codigo"] == "FEL"
    # instrutor: unidade pela área, UCs e disponibilidade no mesmo formulário
    r = c.post("/api/cadastros/instrutores", json={"matricula": "M1", "nome": "Maria", "area_id": energ.id,
                                                   "ucs_competencia": [{"uc_id": uc["id"], "nivel": "pleno"}],
                                                   "carga_horaria_contratual": 20, "disp_turnos": [manha.id], "disp_dias": [0, 2, 4]}, headers=h)
    assert r.status_code == 200, r.text
    i = r.json()
    assert i["unidade_id"] == bm.id and i["ucs_competencia"] == [{"uc_id": uc["id"], "nivel": "pleno"}]
    assert i["disp_turnos"] == [manha.id] and i["disp_dias"] == [0, 2, 4] and i["jornada"] == "M"
    janelas = {(d.dia_semana, d.hora_inicio.strftime("%H:%M"), d.hora_fim.strftime("%H:%M"))
               for d in db.scalars(select(DisponibilidadeInstrutor).where(DisponibilidadeInstrutor.instrutor_id == i["id"]))}
    # o turno da manhã nos 3 dias e, por ser da manhã, a metade 08–12 das turmas PFP
    assert {(d, h) for d, h, _ in janelas} == {(d, h) for d in (0, 2, 4) for h in (manha.hora_inicio.strftime("%H:%M"), "08:00")}
    # desmarcar a UC inativa a competência (sem apagar histórico)
    r = c.put(f"/api/cadastros/instrutores/{i['id']}", json={"ucs_competencia": []}, headers=h)
    assert r.status_code == 200 and r.json()["ucs_competencia"] == []
    assert db.scalar(select(CompetenciaInstrutor).where(CompetenciaInstrutor.instrutor_id == i["id"])).ativo is False
    # horas por dia vêm da carga contratual e limitam os turnos por dia (4 h = 1 turno; 8 h = 2)
    tarde = db.scalar(select(Turno).where(Turno.unidade_id == bm.id, Turno.codigo == "T"))
    r = c.post("/api/cadastros/instrutores", json={"matricula": "M2", "nome": "Paulo", "area_id": energ.id, "carga_horaria_contratual": 20,
                                                   "disp_turnos": [manha.id, tarde.id]}, headers=h)
    assert r.status_code == 409 and "um turno" in r.text
    r = c.post("/api/cadastros/instrutores", json={"matricula": "M2", "nome": "Paulo", "area_id": energ.id, "carga_horaria_contratual": 40,
                                                   "disp_turnos": [manha.id, tarde.id]}, headers=h)
    assert r.status_code == 200, r.text
    assert float(r.json()["max_horas_dia"]) == 8 and sorted(r.json()["disp_turnos"]) == sorted([manha.id, tarde.id])
    assert r.json()["jornada"] == "MV"
    # turnos de trabalho pelo código: 40 h exige dois turnos seguidos (MV ou VN); manhã e noite não é jornada
    base3 = {"matricula": "M3", "nome": "Rita", "area_id": energ.id, "carga_horaria_contratual": 40}
    assert c.post("/api/cadastros/instrutores", json={**base3, "jornada": "M"}, headers=h).status_code == 409
    assert c.post("/api/cadastros/instrutores", json={**base3, "jornada": "Manhã; Noite"}, headers=h).status_code in (400, 422)
    r = c.post("/api/cadastros/instrutores", json={**base3, "jornada": "VN"}, headers=h)
    assert r.status_code == 200 and r.json()["jornada"] == "VN"
    # mudar a carga para 20 h sem ajustar os turnos fica bloqueado; ajustando junto, passa
    rita = {k: v for k, v in r.json().items() if k not in ("jornada", "disp_turnos", "disp_dias")}  # como o formulário envia
    r = c.put(f"/api/cadastros/instrutores/{rita['id']}", json={**rita, "carga_horaria_contratual": 20, "limite_ch_letiva": 16, "max_horas_dia": 4}, headers=h)
    assert r.status_code == 409 and "Ajuste os turnos" in r.text
    r = c.put(f"/api/cadastros/instrutores/{rita['id']}", json={**rita, "carga_horaria_contratual": 20, "limite_ch_letiva": 16, "max_horas_dia": 4,
                                                                "jornada": "N"}, headers=h)
    assert r.status_code == 200 and r.json()["jornada"] == "N"
    # turma: o turno precisa ser da unidade do curso
    porto_noite = db.scalar(select(Turno).join(Unidade).where(Unidade.codigo == "PORTO", Turno.codigo == "N"))
    r = c.post("/api/cadastros/turmas", json={"curso_id": curso["id"], "_numero": "77", "_tipo_oferta": "HTC", "turno_id": porto_noite.id,
                                              "data_inicio": "2026-08-03", "data_fim": "2026-12-18"}, headers=h)
    assert r.status_code == 409 and "outra unidade" in r.text
    # metadados: campos automáticos ficam fora do formulário
    meta = {m["chave"]: m for m in c.get("/api/meta/entidades", headers=h).json()}
    sec = {f["nome"]: f["secao"] for f in meta["turmas"]["campos"]}
    assert sec["unidade_id"] == "auto" and sec["codigo"] == "auto" and sec["_numero"] == "principal" and sec["matriz_id"] == "avancado"


def test_regra_dos_90_por_cento_no_cadastro(db, mundo):
    """Aulas em no máximo 90% dos turnos da jornada: 40 h → 36 h (9 de 10 turnos); 20 h → 16 h (4 de 5)."""
    from app.services.regras_aula import teto_letivo
    assert (teto_letivo(40), teto_letivo(20), teto_letivo(30)) == (36.0, 16.0, 24.0)
    c = TestClient(app)
    r = c.post("/api/auth/login", json={"email": "admin@teste", "senha": "senha-forte-1"})
    h = {"Authorization": f"Bearer {r.json()['token']}"}
    i = mundo.i1
    r = c.put(f"/api/cadastros/instrutores/{i.id}", json={"limite_ch_letiva": 38}, headers=h)
    assert r.status_code == 409 and "90%" in r.json()["erro"] and "36" in r.json()["erro"]
    assert c.put(f"/api/cadastros/instrutores/{i.id}", json={"limite_ch_letiva": 36}, headers=h).status_code == 200
