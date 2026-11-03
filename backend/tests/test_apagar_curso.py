"""Apagar curso: só sem turmas; leva versões, UCs, competências nessas UCs e EPIs; não mexe nos outros cursos."""
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.main import app
from app.models import CompetenciaInstrutor, Curso, EpiCurso, MatrizCurricular, Turma, UnidadeCurricular


def _cli():
    c = TestClient(app)
    tok = c.post("/api/auth/login", json={"email": "admin@teste", "senha": "senha-forte-1"}).json()["token"]
    c.headers.update({"Authorization": f"Bearer {tok}"})
    return c


def test_apagar_curso(db, mundo):
    m = mundo
    c = _cli()
    # com turmas: recusado, com o motivo
    p = c.get(f"/api/cursos/{m.curso.id}/exclusao").json()
    assert not p["pode_apagar"] and p["turmas"] == 2 and "turma" in p["motivo"]
    assert c.delete(f"/api/cursos/{m.curso.id}").status_code == 409
    # outro curso, sem turmas, com UC, competência e EPI
    novo = Curso(codigo="DEL", nome="Curso a apagar", unidade_id=m.unidade.id)
    db.add(novo)
    db.flush()
    mat = MatrizCurricular(curso_id=novo.id, versao="1", situacao="vigente")
    db.add(mat)
    db.flush()
    uc = UnidadeCurricular(matriz_id=mat.id, codigo="X", nome="UC X", carga_horaria_total=20)
    db.add(uc)
    db.flush()
    db.add(CompetenciaInstrutor(instrutor_id=m.i1.id, uc_id=uc.id, nivel="pleno", ativo=True))
    db.add(EpiCurso(curso_id=novo.id, nome="Óculos", quantidade_por_aluno=1))
    db.commit()
    p = c.get(f"/api/cursos/{novo.id}/exclusao").json()
    assert p["pode_apagar"] and (p["versoes"], p["ucs"], p["competencias"], p["epis"]) == (1, 1, 1, 1)
    nid, uid = novo.id, uc.id
    r = c.delete(f"/api/cursos/{nid}")
    assert r.status_code == 200, r.text
    db.expire_all()
    assert not db.scalar(select(func.count()).select_from(Curso).where(Curso.id == nid))
    assert not db.scalar(select(func.count()).select_from(UnidadeCurricular).where(UnidadeCurricular.id == uid))
    assert not db.scalar(select(func.count()).select_from(EpiCurso).where(EpiCurso.curso_id == nid))
    assert not db.scalar(select(func.count()).select_from(CompetenciaInstrutor).where(CompetenciaInstrutor.uc_id == uid))
    # o curso com turmas ficou intacto
    assert db.get(Curso, m.curso.id) and db.scalar(select(func.count()).select_from(Turma).where(Turma.curso_id == m.curso.id)) == 2
