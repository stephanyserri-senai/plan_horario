"""Preparação para Vercel + Supabase: fila/worker, Supabase Auth, RLS,
importação sem estado em memória, API sem OR-Tools, configuração e SQL das migrações."""
import os
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text

from app.core.config import Settings, get_settings, normalizar_url_banco
from app.core.db import SessionLocal
from app.models import Alocacao, ExecucaoOtimizacao, Importacao, SimulacaoCapacidade, Usuario
from app.services import otimizacao, simulador
from tests.conftest import URL

RAIZ = Path(__file__).resolve().parents[2]


# ------------------------------------------------------------------ configuração
def test_normalizacao_da_url_do_supabase():
    u = normalizar_url_banco("postgres://postgres.abc:s%40nha@aws-0-sa-east-1.pooler.supabase.com:6543/postgres?pgbouncer=true")
    assert u.startswith("postgresql+psycopg://postgres.abc:s%40nha@")
    assert "sslmode=require" in u and "pgbouncer" not in u
    assert normalizar_url_banco("postgresql://u:p@localhost/x") == "postgresql+psycopg://u:p@localhost/x"
    # senha com '@' não codificado (caso real do primeiro deploy)
    u2 = normalizar_url_banco("postgresql://postgres.ref:abc@x26@aws-1-sa-east-1.pooler.supabase.com:6543/postgres")
    assert "postgres.ref:abc%40x26@aws-1-sa-east-1.pooler.supabase.com:6543/postgres" in u2
    from sqlalchemy.engine import make_url
    m = make_url(u2)
    assert m.password == "abc@x26" and m.host == "aws-1-sa-east-1.pooler.supabase.com"


def test_pooler_transacao_usa_nullpool_sem_prepared_statements():
    from sqlalchemy.pool import NullPool

    from app.core import db as dbmod
    eng = dbmod.criar_engine("postgresql://u:p@aws-0-x.pooler.supabase.com:6543/postgres")
    assert isinstance(eng.pool, NullPool)
    eng.dispose()


def test_espacos_e_tabulacoes_nas_variaveis_sao_ignorados(monkeypatch):
    monkeypatch.setenv("PLAN_AMBIENTE", "\thomologacao ")
    monkeypatch.setenv("PLAN_AUTH_MODO", " local\n")
    s = Settings()
    assert s.ambiente == "homologacao" and s.auth_modo == "local"


def test_validacao_de_configuracao_em_producao():
    s = Settings(ambiente="producao", database_url="postgresql://u:p@localhost/x", jwt_secret="dev-curto")
    erros = " ".join(s.validar())
    assert "PLAN_JWT_SECRET" in erros and "localhost" in erros
    s2 = Settings(ambiente="producao", auth_modo="supabase", database_url="postgresql://u:p@db.x.supabase.co/postgres")
    assert any("SUPABASE_URL" in e for e in s2.validar())


def test_requirements_da_vercel_identicos_e_sem_ortools():
    raiz = (RAIZ / "requirements.txt").read_text()
    api = (RAIZ / "backend" / "requirements-api.txt").read_text()
    assert raiz == api
    assert "ortools" not in "\n".join(l for l in raiz.splitlines() if not l.startswith("#"))


def test_api_importa_sem_ortools():
    """A função da Vercel não tem OR-Tools: a API (inclusive gargalos) deve carregar sem ele."""
    codigo = (
        "import sys; sys.modules['ortools'] = None\n"
        f"sys.path.insert(0, {str(RAIZ)!r})\n"
        "import importlib; m = importlib.import_module('api.index')\n"
        "import app.services.gargalos, app.services.simulador, app.services.recomendacoes\n"
        "from app.services.fluxo import SimpleMaxFlow\n"
        "assert m.app is not None\n"
        "print('ok')\n"
    )
    env = {**os.environ, "PLAN_DATABASE_URL": URL, "VERCEL": "1"}
    r = subprocess.run([sys.executable, "-c", codigo], capture_output=True, text=True, env=env, cwd=str(RAIZ / "backend"))
    assert r.returncode == 0, r.stderr[-2000:]
    assert get_settings().modo_executor in ("thread", "fila", "sincrono")


def test_saude_informa_fila_e_migracao(mundo):
    from app.main import app
    r = TestClient(app).get("/api/saude").json()
    assert r["status"] == "ok" and r["migracao"] == "0006" and "execucoes_pendentes" in r["fila"]


# ------------------------------------------------------------------ RLS / Data API do Supabase
def test_rls_habilitado_e_papeis_publicos_sem_acesso(db):
    """Simula os papéis 'anon' e 'authenticated' do Supabase com os privilégios
    padrão (GRANT ALL) e reaplica a migração: depois dela, nenhum dos dois lê
    ou escreve tabelas, e todas as tabelas têm RLS habilitado."""
    from alembic import command
    from alembic.config import Config
    for papel in ("anon", "authenticated"):
        db.execute(text(f"DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='{papel}') THEN CREATE ROLE {papel} NOLOGIN; END IF; END $$"))
        db.execute(text(f"GRANT USAGE ON SCHEMA public TO {papel}"))
        db.execute(text(f"GRANT ALL ON ALL TABLES IN SCHEMA public TO {papel}"))
    db.commit()
    cfg = Config(str(RAIZ / "backend" / "alembic.ini"))
    cfg.set_main_option("script_location", str(RAIZ / "backend" / "alembic"))
    command.downgrade(cfg, "0001")
    command.upgrade(cfg, "head")
    sem_rls = db.execute(text("SELECT relname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
                              "WHERE n.nspname='public' AND c.relkind='r' AND NOT c.relrowsecurity")).scalars().all()
    assert sem_rls == []
    for papel in ("anon", "authenticated"):
        for tabela in ("usuarios", "alocacoes", "historico_auditoria", "importacoes"):
            assert not db.scalar(text(f"SELECT has_table_privilege('{papel}', 'public.{tabela}', 'SELECT')"))
            assert not db.scalar(text(f"SELECT has_table_privilege('{papel}', 'public.{tabela}', 'INSERT')"))
    db.execute(text("SET ROLE anon"))
    with pytest.raises(Exception) as e:
        db.execute(text("SELECT * FROM usuarios"))
    assert "permission denied" in str(e.value)
    db.rollback()


def test_sql_offline_das_migracoes_reproduz_banco_novo():
    """`alembic upgrade head --sql` gera o SQL versionável que cria o banco do zero."""
    base = URL.rsplit("/", 1)[0]
    r = subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head", "--sql"], capture_output=True, text=True,
                       cwd=str(RAIZ / "backend"), env={**os.environ, "ALEMBIC_DATABASE_URL": URL})
    assert r.returncode == 0, r.stderr[-1500:]
    sql = r.stdout
    assert "EXCLUDE USING gist" in sql and "ENABLE ROW LEVEL SECURITY" in sql
    assert "%%" not in sql  # editores SQL (Supabase) não convertem '%%'
    assert sql == (RAIZ / "backend" / "sql" / "schema_completo.sql").read_text(), "regenere com scripts/gerar_sql_migracoes.sh"
    nome = f"plan_sqlcheck_{uuid.uuid4().hex[:6]}"
    from sqlalchemy import create_engine
    adm = create_engine(base + "/postgres", isolation_level="AUTOCOMMIT")
    with adm.connect() as c:
        c.execute(text(f"CREATE DATABASE {nome}"))
    try:
        # Executa o texto EXATAMENTE como um editor SQL (sem interpretação de '%' pelo driver).
        import psycopg
        dsn = f"{base}/{nome}".replace("postgresql+psycopg://", "postgresql://")
        with psycopg.connect(dsn, autocommit=True) as conn:
            conn.execute(sql.encode())
            conn.execute((RAIZ / "backend" / "sql" / "seed_inicial.sql").read_bytes())
            conn.execute((RAIZ / "backend" / "sql" / "seed_inicial.sql").read_bytes())  # idempotente
            for _ in range(2):  # demonstração pelo SQL Editor: remove a anterior e recarrega
                conn.execute((RAIZ / "backend" / "sql" / "demo_recarregar.sql").read_bytes())
        eng = create_engine(f"{base}/{nome}")
        with eng.connect() as c:
            assert c.scalar(text("SELECT count(*) FROM usuarios WHERE email = 'admin'")) == 1
            assert c.scalar(text("SELECT count(*) FROM pg_class cl JOIN pg_namespace n ON n.oid = cl.relnamespace "
                                 "WHERE n.nspname = 'public' AND cl.relkind = 'r' AND NOT cl.relrowsecurity")) == 0
            assert c.scalar(text("SELECT version_num FROM alembic_version")) == "0006"
            assert c.scalar(text("SELECT count(*) FROM pg_constraint WHERE conname LIKE 'excl_alocacao_%'")) == 3
            # estrutura fixa da instituição (migração 0003), idêntica a app/core/estrutura.py
            from app.core.estrutura import AREAS, UNIDADES
            assert sorted(c.execute(text("SELECT codigo, nome FROM unidades WHERE codigo IN ('BEIRA-MAR','PORTO')")).all()) == sorted(UNIDADES)
            assert sorted(c.execute(text("SELECT a.codigo, a.nome, u.codigo FROM areas a JOIN unidades u ON u.id = a.unidade_id")).all()) == sorted(AREAS)
            assert c.scalar(text("SELECT count(*) FROM periodos_horarios p JOIN unidades u ON u.id = p.unidade_id WHERE u.codigo IN ('BEIRA-MAR','PORTO')")) == 24
            assert c.scalar(text("SELECT count(*) FROM turma_uc tu JOIN turmas t ON t.id = tu.turma_id WHERE t.codigo LIKE 'DEMO-%'")) == 12
            assert c.scalar(text("SELECT valor->>'contagem' FROM configuracoes WHERE chave = 'regras_aula'")) == "hora_aula"
        eng.dispose()
    finally:
        with adm.connect() as c:
            c.execute(text(f"DROP DATABASE IF EXISTS {nome} WITH (FORCE)"))
        adm.dispose()


# ------------------------------------------------------------------ fila / worker
def _criar_execucao(db, m, cenario_id=None):
    ex = otimizacao.criar_execucao(db, m.ctx, cenario_id or m.cen.id, {"tipo": "turma", "ids": [m.t1.id]}, limite_tempo_s=15)
    db.commit()
    return ex.id


def test_fila_processada_pelo_worker(db, mundo):
    from app import worker
    eid = _criar_execucao(db, mundo)
    assert db.get(ExecucaoOtimizacao, eid).status == "pendente"
    assert worker.processar_um("teste-worker") is True
    db.expire_all()
    ex = db.get(ExecucaoOtimizacao, eid)
    assert ex.status == "concluida" and ex.status_solver in ("OTIMA", "VIAVEL") and ex.worker == "teste-worker"
    assert db.scalar(select(func.count()).select_from(Alocacao)) > 0
    assert worker.processar_um("teste-worker") is False  # fila vazia


def test_dois_workers_nunca_pegam_o_mesmo_job(db, mundo):
    m = mundo
    e1 = _criar_execucao(db, m)
    from app.services import cenarios
    outro = cenarios.criar(db, m.ctx, "Outro cenário", m.unidade.id)
    db.commit()
    e2 = _criar_execucao(db, m, outro.id)
    s1, s2 = SessionLocal(), SessionLocal()
    try:
        # worker A trava o primeiro job (transação aberta); worker B deve pegar o segundo
        bloqueado = s1.scalars(select(ExecucaoOtimizacao).where(ExecucaoOtimizacao.id == e1).with_for_update()).first()
        assert bloqueado is not None
        assert otimizacao.reivindicar_execucao(s2, "B") == e2
        s1.rollback()
        resultados = []
        barreira = threading.Barrier(2)

        def pegar(nome):
            with SessionLocal() as s:
                barreira.wait()
                resultados.append(otimizacao.reivindicar_execucao(s, nome))
        th = [threading.Thread(target=pegar, args=(n,)) for n in ("C", "D")]
        [t.start() for t in th]
        [t.join() for t in th]
        assert sorted(resultados, key=lambda x: (x is None, x)) == [e1, None]
    finally:
        s1.close()
        s2.close()


def test_recuperacao_por_heartbeat_expirado(db, mundo):
    m = mundo
    eid = _criar_execucao(db, m)
    ex = db.get(ExecucaoOtimizacao, eid)
    ex.status, ex.heartbeat_em, ex.iniciado_em = "executando", datetime.now(), datetime.now()
    db.commit()
    assert otimizacao.recuperar_execucoes_interrompidas(db, somente_expiradas=True) == 0  # worker vivo: intocado
    ex = db.get(ExecucaoOtimizacao, eid)
    ex.heartbeat_em = datetime.now() - timedelta(seconds=get_settings().worker_heartbeat_expira_s + 60)
    db.commit()
    assert otimizacao.recuperar_execucoes_interrompidas(db, somente_expiradas=True) == 1
    db.expire_all()
    assert db.get(ExecucaoOtimizacao, eid).status == "falha"
    assert db.get(type(m.cen), m.cen.id).estado == "em_elaboracao"


def test_simulacao_completa_pela_fila(db, mundo):
    from app import worker
    m = mundo
    p = {"curso_id": m.curso.id, "matriz_id": m.matriz.id, "unidade_id": m.unidade.id, "quantidade_turmas": 1, "alunos_por_turma": 16,
         "data_inicio": "2026-08-03", "data_fim": "2026-12-18", "turno_id": m.manha.id, "dias_semana": [0, 1, 2, 3, 4], "calendario_id": m.cal.id,
         "ucs_sequenciais": False}
    sim = simulador.criar_simulacao_completa(db, m.ctx, p, m.cen.id, "Fila", limite_tempo_s=10, alternativas=False)
    db.commit()
    assert sim.status == "pendente"
    assert worker.processar_um("w") is True
    db.expire_all()
    s = db.get(SimulacaoCapacidade, sim.id)
    assert s.status == "concluida" and s.resultado["viabilidade"] == "viavel"


# ------------------------------------------------------------------ importação sem estado em memória
def test_previa_de_importacao_persistida_no_banco(db, mundo):
    from app.main import app
    c = TestClient(app)
    h = {"Authorization": "Bearer " + c.post("/api/auth/login", json={"email": "admin@teste", "senha": "senha-forte-1"}).json()["token"]}
    csv = "Matrícula;Nome;Unidade\nZ1;Fulano;U1\n".encode()
    r = c.post("/api/importacao/previa", files={"arquivo": ("i.csv", csv, "text/csv")}, data={"tipo": "instrutores"}, headers=h)
    assert r.status_code == 200, r.text
    iid = r.json()["id"]
    db.expire_all()
    assert db.get(Importacao, iid).conteudo == csv  # outra instância serverless consegue remapear
    r = c.post(f"/api/importacao/{iid}/remapear", json={"mapeamento": {"nome": "Nome"}}, headers=h)
    assert r.status_code == 200 and r.json()["resumo"]["criar"] == 1
    assert c.post(f"/api/importacao/{iid}/confirmar", json={}, headers=h).status_code == 200
    db.expire_all()
    assert db.get(Importacao, iid).conteudo is None  # arquivo descartado após confirmar


# ------------------------------------------------------------------ Supabase Auth
SEGREDO = "segredo-de-teste-supabase-com-mais-de-32-caracteres"
SUPA = "https://projeto-teste.supabase.co"


@pytest.fixture
def modo_supabase(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "auth_modo", "supabase")
    monkeypatch.setattr(s, "supabase_url", SUPA)
    monkeypatch.setattr(s, "supabase_anon_key", "chave-anon-publica")
    monkeypatch.setattr(s, "supabase_jwt_secret", SEGREDO)
    monkeypatch.setattr(s, "supabase_service_role_key", "SERVICE-ROLE-SECRETA")
    return s


def token_supabase(email, sub=None, **extra):
    agora = int(time.time())
    claims = {"sub": sub or str(uuid.uuid4()), "email": email, "aud": "authenticated", "iss": SUPA + "/auth/v1", "iat": agora,
              "exp": agora + 3600, "role": "authenticated", **extra}
    return jwt.encode(claims, SEGREDO, algorithm="HS256")


def test_supabase_auth_vincula_usuario_e_aplica_perfil(db, mundo, modo_supabase):
    from app.main import app
    c = TestClient(app)
    cfg = c.get("/api/auth/config").json()
    assert cfg["modo"] == "supabase" and cfg["supabase_anon_key"] == "chave-anon-publica"
    assert "SERVICE-ROLE" not in str(cfg) and SEGREDO not in str(cfg)  # segredos nunca vão ao navegador
    assert c.post("/api/auth/login", json={"email": "admin@teste", "senha": "senha-forte-1"}).status_code == 422
    sub = str(uuid.uuid4())
    r = c.get("/api/auth/me", headers={"Authorization": "Bearer " + token_supabase("ADMIN@teste", sub)})
    assert r.status_code == 200 and r.json()["perfil"] == "administrador"
    db.expire_all()
    assert db.scalar(select(Usuario.auth_user_id).where(Usuario.email == "admin@teste")) == sub
    # login válido no Supabase, mas sem cadastro na plataforma: sem acesso
    assert c.get("/api/auth/me", headers={"Authorization": "Bearer " + token_supabase("intruso@x.com")}).status_code == 403


@pytest.mark.parametrize("caso", ["expirado", "audiencia", "emissor", "assinatura", "alg_none"])
def test_supabase_tokens_invalidos_sao_recusados(db, mundo, modo_supabase, caso):
    from app.main import app
    agora = int(time.time())
    if caso == "expirado":
        tok = token_supabase("admin@teste", exp=agora - 10)
    elif caso == "audiencia":
        tok = token_supabase("admin@teste", aud="anon")
    elif caso == "emissor":
        tok = token_supabase("admin@teste", iss="https://outro.supabase.co/auth/v1")
    elif caso == "assinatura":
        tok = jwt.encode({"sub": "x", "email": "admin@teste", "aud": "authenticated", "iss": SUPA + "/auth/v1", "exp": agora + 60},
                         "outro-segredo-qualquer-com-32-caracteres!!", algorithm="HS256")
    else:
        tok = jwt.encode({"sub": "x", "email": "admin@teste", "aud": "authenticated", "iss": SUPA + "/auth/v1", "exp": agora + 60}, None, algorithm="none")
    assert TestClient(app).get("/api/auth/me", headers={"Authorization": "Bearer " + tok}).status_code == 401


def test_supabase_tokens_assimetricos_via_jwks(db, mundo, modo_supabase, monkeypatch):
    from cryptography.hazmat.primitives.asymmetric import ec

    from app.core import supabase_auth
    from app.main import app
    chave = ec.generate_private_key(ec.SECP256R1())

    class JWKSFalso:
        def get_signing_key_from_jwt(self, _tok):
            return type("K", (), {"key": chave.public_key()})()
    monkeypatch.setattr(supabase_auth, "_cliente_jwks", lambda: JWKSFalso())
    agora = int(time.time())
    tok = jwt.encode({"sub": str(uuid.uuid4()), "email": "admin@teste", "aud": "authenticated", "iss": SUPA + "/auth/v1", "exp": agora + 60},
                     chave, algorithm="ES256", headers={"kid": "k1"})
    assert TestClient(app).get("/api/auth/me", headers={"Authorization": "Bearer " + tok}).status_code == 200


def test_usuario_teste_e_recusado_em_producao(db, mundo, monkeypatch):
    from app import seed
    u = seed.criar_usuario_teste(db)
    assert u.email == "admin" and seed.usuario_teste_ativo(db)
    from app.main import app
    r = TestClient(app).post("/api/auth/login", json={"email": "admin", "senha": "admin@123"})
    assert r.status_code == 200 and r.json()["usuario"]["perfil"] == "administrador"
    assert TestClient(app).get("/api/saude").json()["usuario_teste_ativo"] is True
    assert "excluído" in seed.remover_usuario_teste(db) or "inativado" in seed.remover_usuario_teste(db)
    db.expire_all()
    assert not seed.usuario_teste_ativo(db)
    monkeypatch.setattr(get_settings(), "ambiente", "producao")
    with pytest.raises(SystemExit):
        seed.criar_usuario_teste(db)


def test_env_example_legivel_e_sem_segredos_reais():
    s = Settings(_env_file=str(RAIZ / ".env.example"))
    for campo in ("supabase_jwt_secret", "supabase_service_role_key", "supabase_anon_key", "supabase_url", "database_url"):
        assert not str(getattr(s, campo)).startswith("#"), campo  # comentário lido como valor
    texto = (RAIZ / ".env.example").read_text()
    assert "eyJhbGciOi" not in texto and "sb_secret_" not in texto
    assert s.supabase_jwt_secret == "" and s.supabase_service_role_key == ""


# ------------------------------------------------------------------ acionamento automático e primeiros passos
def _login(c):
    return {"Authorization": "Bearer " + c.post("/api/auth/login", json={"email": "admin@teste", "senha": "senha-forte-1"}).json()["token"]}


def test_acionamento_do_worker_no_github(monkeypatch):
    """Com PLAN_GITHUB_TOKEN, a fila dispara o workflow na hora; sem token, nada é chamado."""
    from app.services import acionador
    chamadas = []

    class Resp:
        status = 204
        def __enter__(self): return self
        def __exit__(self, *a): return False

    def falso_urlopen(req, timeout=None):
        chamadas.append((req.full_url, req.headers.get("Authorization"), req.data))
        return Resp()
    monkeypatch.setattr(acionador.urllib.request, "urlopen", falso_urlopen)
    monkeypatch.setenv("PLAN_EXECUTOR", "fila")
    monkeypatch.delenv("PLAN_GITHUB_TOKEN", raising=False)
    get_settings.cache_clear()
    try:
        assert acionador.acionar_worker(forcar=True) == "nao_configurado" and not chamadas
        monkeypatch.setenv("PLAN_GITHUB_TOKEN", "tok-teste")
        monkeypatch.setenv("VERCEL_GIT_REPO_OWNER", "dono")
        monkeypatch.setenv("VERCEL_GIT_REPO_SLUG", "repo")
        monkeypatch.setenv("VERCEL_GIT_COMMIT_REF", "principal")
        get_settings.cache_clear()
        assert acionador.acionar_worker(forcar=True) == "acionado"
        url, auth, corpo = chamadas[-1]
        assert url == "https://api.github.com/repos/dono/repo/actions/workflows/worker.yml/dispatches"
        assert auth == "Bearer tok-teste" and b'"principal"' in corpo
        assert acionador.acionar_worker() == "recente" and len(chamadas) == 1  # sem rajadas

        def erro(req, timeout=None):
            raise acionador.urllib.error.HTTPError(req.full_url, 401, "x", {}, None)
        monkeypatch.setattr(acionador.urllib.request, "urlopen", erro)
        assert acionador.acionar_worker(forcar=True) == "falhou"
    finally:
        get_settings.cache_clear()


def test_token_do_github_nao_e_exposto(monkeypatch, mundo):
    monkeypatch.setenv("PLAN_GITHUB_TOKEN", "segredo-github-123")
    get_settings.cache_clear()
    try:
        from app.main import app
        c = TestClient(app)
        h = _login(c)
        for rota in ("/api/auth/config", "/api/saude", "/api/processamento"):
            assert "segredo-github-123" not in c.get(rota, headers=h).text
    finally:
        get_settings.cache_clear()


def test_status_de_processamento_e_primeiros_passos(db, mundo):
    from app.main import app
    c = TestClient(app)
    h = _login(c)
    _criar_execucao(db, mundo)
    st = c.get("/api/processamento", headers=h).json()
    assert st["pendentes"]["execucoes"] == 1 and st["pendentes"]["espera_min"] >= 0
    assert c.post("/api/processamento/acionar", headers=h).json()["mensagem"]
    pp = c.get(f"/api/primeiros-passos?cenario_id={mundo.cen.id}", headers=h).json()
    feitos = {p["chave"]: p["feito"] for p in pp["passos"]}
    assert feitos["unidades"] and feitos["turmas"] and feitos["cenario"] and not feitos["grade"]
    assert pp["total"] == len(pp["passos"]) and 0 < pp["concluidos"] < pp["total"]


def test_dados_do_acompanhamento(db, mundo):
    """Painel de acompanhamento: turmas×UCs com instrutores/prazos e instrutores com turmas, UCs e horas por dia."""
    from datetime import date as _d
    from app.services import alocacao, indicadores
    from tests.conftest import aula
    alocacao.criar_aula(db, mundo.ctx, mundo.cen.id, aula(mundo, db, mundo.t1, mundo.uc_a, instrutor=mundo.i1, ambiente=mundo.s1))
    db.commit()
    tu = indicadores.turmas_ucs(db, mundo.cen.id, _d(2020, 1, 1))
    item = next(i for i in tu["itens"] if i["programada_h"] > 0)
    assert item["instrutores"] == [mundo.i1.nome] and item["proxima_aula"] and item["turma_id"] == mundo.t1.id
    d0, d1 = indicadores.periodo_padrao(db, mundo.cen)
    ins = indicadores.ocupacao_instrutores(db, mundo.cen.id, d0, d1)
    linha = next(l for l in ins["instrutores"] if l["instrutor_id"] == mundo.i1.id)
    assert linha["turmas_lista"] == [mundo.t1.codigo] and sum(linha["por_dia_semana_h"].values()) > 0 and "limiares" in ins


def _comandos_sql(texto: str) -> list[str]:
    """Separa um script em comandos (respeitando blocos $$ ... $$), como um editor SQL."""
    cmds, atual, dentro = [], [], False
    for linha in texto.splitlines():
        if linha.strip().startswith("--") and not dentro:
            continue
        atual.append(linha)
        if linha.count("$$") % 2 == 1:
            dentro = not dentro
        if not dentro and linha.rstrip().endswith(";"):
            cmd = "\n".join(atual).strip()
            if cmd.strip(";").strip():
                cmds.append(cmd)
            atual = []
    return cmds


def test_scripts_do_sql_editor_funcionam_comando_a_comando():
    """Pior caso do SQL Editor do Supabase: cada comando numa conexão nova (BEGIN/COMMIT sem efeito).
    Banco na 0002 → atualizacao_0003.sql → demo_recarregar.sql (2x)."""
    import psycopg
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine
    base = URL.rsplit("/", 1)[0]
    nome = f"plan_editor_{uuid.uuid4().hex[:6]}"
    adm = create_engine(base + "/postgres", isolation_level="AUTOCOMMIT")
    with adm.connect() as c:
        c.execute(text(f"CREATE DATABASE {nome}"))
    try:
        url = f"{base}/{nome}"
        cfg = Config(str(RAIZ / "backend" / "alembic.ini"))
        cfg.set_main_option("script_location", str(RAIZ / "backend" / "alembic"))
        os.environ["ALEMBIC_DATABASE_URL"] = url
        try:
            command.upgrade(cfg, "0002")
        finally:
            os.environ.pop("ALEMBIC_DATABASE_URL", None)
        dsn = url.replace("postgresql+psycopg://", "postgresql://")
        sql_dir = RAIZ / "backend" / "sql"
        for arq, vezes in (("atualizacao_0003.sql", 1), ("atualizacao_0004.sql", 1), ("atualizacao_0005.sql", 1), ("atualizacao_0006.sql", 1), ("seed_inicial.sql", 1), ("demo_recarregar.sql", 2)):
            for _ in range(vezes):
                for cmd in _comandos_sql((sql_dir / arq).read_text(encoding="utf-8")):
                    with psycopg.connect(dsn, autocommit=True) as conn:
                        conn.execute(cmd.encode())
        eng = create_engine(url)
        with eng.connect() as c:
            assert c.scalar(text("SELECT version_num FROM alembic_version")) == "0006"
            assert c.scalar(text("SELECT count(*) FROM areas")) == 11
            assert c.scalar(text("SELECT count(*) FROM turmas WHERE codigo LIKE 'DEMO-%'")) == 3
            assert c.scalar(text("SELECT count(*) FROM turma_uc tu JOIN turmas t ON t.id = tu.turma_id WHERE t.codigo LIKE 'DEMO-%'")) == 12
            assert c.scalar(text("SELECT count(*) FROM turmas t JOIN unidades u ON u.id = t.unidade_id WHERE u.codigo = 'BEIRA-MAR' AND t.area_id IS NOT NULL")) == 3
            assert c.scalar(text("SELECT count(*) FROM turnos t JOIN unidades u ON u.id = t.unidade_id WHERE u.codigo = 'BEIRA-MAR'")) == 3
            c.execute(text("INSERT INTO unidades (codigo, nome, situacao, ativo) VALUES ('TESTE', 'UNIDADE TESTE', 'ativa', true)"))
            c.commit()
        eng.dispose()
        # limpeza dos dados de teste (comando a comando, como no editor)
        for cmd in _comandos_sql((sql_dir / "limpar_dados_teste.sql").read_text(encoding="utf-8")):
            with psycopg.connect(dsn, autocommit=True) as conn:
                conn.execute(cmd.encode())
        eng = create_engine(url)
        with eng.connect() as c:
            cont = lambda t: c.scalar(text(f"SELECT count(*) FROM {t}"))  # noqa: E731
            assert (cont("unidades"), cont("areas"), cont("turnos"), cont("periodos_horarios")) == (2, 11, 6, 24)
            assert all(cont(t) == 0 for t in ("cursos", "turmas", "instrutores", "ambientes", "cenarios_planejamento", "unidades_curriculares",
                                               "tipos_ambiente", "calendarios", "alocacoes"))
            assert cont("usuarios") >= 1 and cont("permissoes_perfil") > 0 and cont("parametros_otimizacao") > 0
            assert c.scalar(text("SELECT valor->>'contagem' FROM configuracoes WHERE chave = 'regras_aula'")) == "hora_aula"
        eng.dispose()
    finally:
        with adm.connect() as c:
            c.execute(text(f"DROP DATABASE IF EXISTS {nome} WITH (FORCE)"))
        adm.dispose()


def test_sql_do_semestre_de_demonstracao():
    """demo_semestre_completo.sql (SQL Editor, comando a comando, duas vezes): limpa, carrega o semestre publicado e o sistema funciona em cima dele."""
    import psycopg
    from alembic import command
    from alembic.config import Config
    from fastapi.testclient import TestClient
    from sqlalchemy import create_engine

    from app.core.db import reset_engine
    from app.main import app
    base = URL.rsplit("/", 1)[0]
    nome = f"plan_demo_{uuid.uuid4().hex[:6]}"
    adm = create_engine(base + "/postgres", isolation_level="AUTOCOMMIT")
    with adm.connect() as c:
        c.execute(text(f"CREATE DATABASE {nome}"))
    url = f"{base}/{nome}"
    try:
        cfg = Config(str(RAIZ / "backend" / "alembic.ini"))
        cfg.set_main_option("script_location", str(RAIZ / "backend" / "alembic"))
        os.environ["ALEMBIC_DATABASE_URL"] = url
        try:
            command.upgrade(cfg, "head")
        finally:
            os.environ.pop("ALEMBIC_DATABASE_URL", None)
        dsn = url.replace("postgresql+psycopg://", "postgresql://")
        sql_dir = RAIZ / "backend" / "sql"
        for arq in ("seed_inicial.sql", "demo_recarregar.sql", "demo_semestre_completo.sql", "demo_semestre_completo.sql"):
            for cmd in _comandos_sql((sql_dir / arq).read_text(encoding="utf-8")):
                with psycopg.connect(dsn, autocommit=True) as conn:
                    conn.execute(cmd.encode())
        eng = create_engine(url)
        with eng.connect() as c:
            cont = lambda t: c.scalar(text(f"SELECT count(*) FROM {t}"))  # noqa: E731
            assert (cont("turmas"), cont("cursos"), cont("instrutores"), cont("alocacoes")) == (13, 11, 29, 909)
            assert c.scalar(text("SELECT count(*) FROM turmas WHERE codigo LIKE 'DEMO-%'")) == 0  # a demonstração antiga foi limpa
            assert c.scalar(text("SELECT estado FROM cenarios_planejamento")) == "publicado"
            assert cont("notificacoes") > 0 and cont("observacoes_instrutor") == 3
            assert c.scalar(text("SELECT count(*) FROM alocacoes WHERE instrutor_titular_id IS NOT NULL")) == 1
            assert c.scalar(text("SELECT count(*) FROM usuarios WHERE perfil = 'instrutor' AND instrutor_id IS NOT NULL")) == 4
            # sequências acertadas: novos registros não colidem
            c.execute(text("INSERT INTO tipos_ambiente (codigo, nome, especializado, ativo) VALUES ('NOVO', 'Novo', false, true)"))
            c.rollback()
        eng.dispose()
        reset_engine(url)
        try:
            cli = TestClient(app)
            h = {"Authorization": "Bearer " + cli.post("/api/auth/login", json={"email": "admin", "senha": "admin@123"}).json()["token"]}
            cen = cli.get("/api/cenarios", headers=h).json()[0]
            painel = cli.get(f"/api/painel?cenario_id={cen['id']}", headers=h).json()
            assert painel["indicadores"]["aulas"] == 909 and painel["indicadores"]["pct_com_horario"] == 100
            assert cli.post(f"/api/cenarios/{cen['id']}/validar", headers=h).json()["resumo"]["bloqueios"] == 0
            assert any(e["chave"] == "conferir" and e["status"] == "ok" for e in painel["etapas"]), painel["etapas"]
            prop = cli.post(f"/api/cenarios/{cen['id']}/proposta", json={"nome": "Ajustes de novembro"}, headers=h)
            assert prop.status_code == 200, prop.text
            hi = {"Authorization": "Bearer " + cli.post("/api/auth/login", json={"email": "juliana.prates", "senha": "portal@2026"}).json()["token"]}
            turmas = cli.get("/api/portal/turmas", headers=hi).json()
            assert turmas and turmas[0]["publicado"] and turmas[0]["turmas_ucs"]
            assert cli.get("/api/portal/notificacoes", headers=hi).json()
        finally:
            reset_engine(URL)
        # limpar tudo depois da apresentação (o login da Juliana deixou registro na auditoria)
        for cmd in _comandos_sql((sql_dir / "limpar_dados_teste.sql").read_text(encoding="utf-8")):
            with psycopg.connect(dsn, autocommit=True) as conn:
                conn.execute(cmd.encode())
        eng = create_engine(url)
        with eng.connect() as c:
            cont = lambda t: c.scalar(text(f"SELECT count(*) FROM {t}"))  # noqa: E731
            assert all(cont(t) == 0 for t in ("turmas", "instrutores", "alocacoes", "notificacoes", "observacoes_instrutor", "cenarios_planejamento"))
            assert c.scalar(text("SELECT count(*) FROM usuarios WHERE perfil = 'instrutor'")) == 0
            assert c.scalar(text("SELECT count(*) FROM usuarios WHERE email = 'admin'")) == 1
            assert cont("historico_auditoria") > 0 and (cont("unidades"), cont("areas")) == (2, 11)
        eng.dispose()
    finally:
        with adm.connect() as c:
            c.execute(text(f"DROP DATABASE IF EXISTS {nome} WITH (FORCE)"))


def test_migracao_0006_noite_1830_2200_desloca_aulas():
    """Semestre montado com a noite antiga (18:20–21:50); a 0006 leva turno, períodos, aulas e disponibilidades para 18:30–22:00 sem conflitos."""
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine

    from app import seed
    from app.core.db import SessionLocal, reset_engine
    from app.core.deps import carregar_contexto
    from app.demo_semestre import montar
    from app.models import Usuario
    from app.services import cenarios
    base = URL.rsplit("/", 1)[0]
    nome = f"plan_noite_{uuid.uuid4().hex[:6]}"
    adm = create_engine(base + "/postgres", isolation_level="AUTOCOMMIT")
    with adm.connect() as c:
        c.execute(text(f"CREATE DATABASE {nome}"))
    url = f"{base}/{nome}"
    cfg = Config(str(RAIZ / "backend" / "alembic.ini"))
    cfg.set_main_option("script_location", str(RAIZ / "backend" / "alembic"))
    os.environ["ALEMBIC_DATABASE_URL"] = url
    try:
        command.upgrade(cfg, "0005")
        reset_engine(url)
        with SessionLocal() as db:
            seed.executar(db, "adm@noite", "senha-forte-9")
            db.commit()
            ctx = carregar_contexto(db, db.query(Usuario).filter(Usuario.email == "adm@noite").one())
            r = montar(db, ctx, limite_s=60)
            antes = db.execute(text("SELECT count(*) FROM alocacoes WHERE inicio::time = '18:20'")).scalar()
            assert antes > 0
        command.upgrade(cfg, "0006")
        command.upgrade(cfg, "0006")  # idempotente
        with SessionLocal() as db:
            q = lambda s: db.execute(text(s)).scalar()  # noqa: E731
            assert q("SELECT count(*) FROM alocacoes WHERE inicio::time = '18:20' OR fim::time = '21:50'") == 0
            assert q("SELECT count(*) FROM alocacoes WHERE inicio::time = '18:30' AND fim::time = '22:00'") == antes
            assert q("SELECT count(*) FROM turnos WHERE codigo = 'N' AND hora_inicio = '18:30' AND hora_fim = '22:00'") == 2
            assert [str(x) for x in db.execute(text("SELECT p.hora_inicio FROM periodos_horarios p JOIN turnos t ON t.id = p.turno_id "
                                                   "JOIN unidades u ON u.id = t.unidade_id WHERE t.codigo = 'N' AND u.codigo = 'PORTO' ORDER BY p.ordem")).scalars()] == \
                ["18:30:00", "19:20:00", "20:20:00", "21:10:00"]
            assert q("SELECT count(*) FROM disponibilidade_instrutores WHERE hora_fim = '21:50'") == 0
            v = cenarios.validar(db, ctx, r["cenario_id"])
            assert v["resumo"]["bloqueios"] == 0, v["resumo"]
    finally:
        os.environ.pop("ALEMBIC_DATABASE_URL", None)
        reset_engine(URL)
        with adm.connect() as c:
            c.execute(text(f"DROP DATABASE IF EXISTS {nome} WITH (FORCE)"))
