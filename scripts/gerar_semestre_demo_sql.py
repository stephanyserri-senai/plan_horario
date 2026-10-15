"""Gera backend/sql/demo_semestre_completo.sql: LIMPA os dados e carrega um semestre completo de demonstração.

O semestre é montado por app/demo_semestre.py num banco TEMPORÁRIO (criado e apagado aqui), com os
próprios serviços da plataforma: cadastros, gerador de horários, validação, publicação, substituição e
notificações. O resultado vira INSERTs num único bloco DO $$ … $$ (o SQL Editor executa o bloco inteiro).
Referências à estrutura fixa (unidades, áreas, turnos e períodos) são resolvidas pelo código.

Uso: python scripts/gerar_semestre_demo_sql.py   (requer o PostgreSQL local de desenvolvimento)
"""
import json
import os
import sys
import uuid
from datetime import date, datetime, time
from decimal import Decimal
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "backend"))
BASE = os.environ.get("PLAN_DEMO_BASE_URL", "postgresql+psycopg://plan:plan@localhost:5432")
NOME_DB = f"plan_demo_{uuid.uuid4().hex[:6]}"
URL = f"{BASE}/{NOME_DB}"
os.environ["PLAN_DATABASE_URL"] = URL
os.environ.setdefault("PLAN_AMBIENTE", "teste")

from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.dialects.postgresql import JSONB  # noqa: E402
from sqlalchemy.types import ARRAY  # noqa: E402

# Tabelas que NÃO são copiadas: estrutura fixa, configuração, usuários e registros internos/derivados.
NAO_COPIAR = {"unidades", "areas", "turnos", "periodos_horarios", "configuracoes", "parametros_otimizacao", "permissoes_perfil", "usuarios",
              "permissoes", "historico_auditoria", "importacoes", "simulacoes_capacidade", "alembic_version",
              "versoes_planejamento"}  # cópias completas da grade a cada transição: deixariam o arquivo grande demais
ADMIN = "(SELECT id FROM usuarios WHERE perfil = 'administrador' AND ativo ORDER BY id LIMIT 1)"


def lit(v, tipo=None) -> str:
    if v is None:
        return "NULL"
    if isinstance(tipo, JSONB):
        return "'" + json.dumps(v, ensure_ascii=False, default=str).replace("'", "''") + "'::jsonb"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float, Decimal)):
        return str(v)
    if isinstance(v, (date, time, datetime)):
        return f"'{v.isoformat()}'"
    if isinstance(tipo, ARRAY) or isinstance(v, (list, tuple)):
        return "'{" + ",".join(str(x) for x in v) + "}'"
    return "'" + str(v).replace("'", "''") + "'"


def montar_banco():
    from alembic import command
    from alembic.config import Config
    adm = create_engine(f"{BASE}/postgres", isolation_level="AUTOCOMMIT")
    with adm.connect() as c:
        c.execute(text(f"CREATE DATABASE {NOME_DB}"))
    cfg = Config(str(RAIZ / "backend" / "alembic.ini"))
    cfg.set_main_option("script_location", str(RAIZ / "backend" / "alembic"))
    os.environ["ALEMBIC_DATABASE_URL"] = URL
    command.upgrade(cfg, "head")


def apagar_banco():
    from app.core.db import get_engine
    get_engine().dispose()
    adm = create_engine(f"{BASE}/postgres", isolation_level="AUTOCOMMIT")
    with adm.connect() as c:
        c.execute(text(f"DROP DATABASE IF EXISTS {NOME_DB} WITH (FORCE)"))


def main():
    montar_banco()
    try:
        from app.core.db import SessionLocal, reset_engine
        reset_engine(URL)
        from app import seed
        from app.core.deps import carregar_contexto
        from app.core.estrutura import garantir_estrutura_fixa
        from app.demo_semestre import LOGINS_PORTAL, SENHA_PORTAL, montar
        from app.models import Base, Usuario
        with SessionLocal() as db:
            seed.executar(db, "admin.demo@local", "senha-demo-123")
            garantir_estrutura_fixa(db)
            db.commit()
            admin = db.query(Usuario).filter(Usuario.email == "admin.demo@local").one()
            resumo = montar(db, carregar_contexto(db, admin))
            print("Semestre montado:", resumo)
            corpo = gerar_insercoes(db, Base)
        escrever(corpo, resumo, LOGINS_PORTAL, SENHA_PORTAL)
    finally:
        apagar_banco()


def gerar_insercoes(db, Base) -> list[str]:
    un_cod = dict(db.execute(text("SELECT id, codigo FROM unidades")).all())
    area_cod = dict(db.execute(text("SELECT id, codigo FROM areas")).all())
    turno_cod = {r[0]: (un_cod[r[1]], r[2]) for r in db.execute(text("SELECT id, unidade_id, codigo FROM turnos")).all()}
    periodo = {r[0]: (turno_cod[r[1]], r[2]) for r in db.execute(text("SELECT id, turno_id, ordem FROM periodos_horarios")).all()}

    def sub_turno(v):
        u, t = turno_cod[v]
        return f"(SELECT t.id FROM turnos t JOIN unidades u ON u.id = t.unidade_id WHERE u.codigo = {lit(u)} AND t.codigo = {lit(t)})"

    fixas = {
        "unidades": lambda v: f"(SELECT id FROM unidades WHERE codigo = {lit(un_cod[v])})",
        "areas": lambda v: f"(SELECT id FROM areas WHERE codigo = {lit(area_cod[v])})",
        "turnos": sub_turno,
        "periodos_horarios": lambda v: f"(SELECT id FROM periodos_horarios WHERE turno_id = {sub_turno_por(periodo[v][0])} AND ordem = {periodo[v][1]})",
    }

    def sub_turno_por(chave):
        u, t = chave
        return f"(SELECT t.id FROM turnos t JOIN unidades u ON u.id = t.unidade_id WHERE u.codigo = {lit(u)} AND t.codigo = {lit(t)})"

    tabelas = [t for t in Base.metadata.sorted_tables if t.name not in NAO_COPIAR]
    nomes = {t.name for t in tabelas}
    corpo = []
    # Depois da limpeza (TRUNCATE … RESTART IDENTITY) as tabelas estão vazias: as linhas entram com os MESMOS ids
    # do banco temporário, em lotes, e as sequências são acertadas no fim.
    for tab in tabelas:
        fks = {fk.parent.name: fk.column.table.name for fk in tab.foreign_keys}
        gerados = {c.name for c in tab.columns if c.computed is not None}
        cols = [c for c in tab.columns if c.name not in {"criado_em", "atualizado_em"} and c.name not in gerados]
        linhas = db.execute(text(f"SELECT * FROM {tab.name} ORDER BY 1")).mappings().all()
        if not linhas:
            continue
        tuplas = []
        for row in linhas:
            vals = []
            for c in cols:
                v = row[c.name]
                if c.name in fks and v is not None and fks[c.name] not in nomes:
                    alvo = fks[c.name]
                    if alvo in fixas:
                        vals.append(fixas[alvo](v))
                    elif alvo == "usuarios":
                        vals.append(ADMIN if not c.nullable else "NULL")
                    else:
                        vals.append("NULL")
                    continue
                vals.append(lit(v, c.type))
            tuplas.append("(" + ", ".join(vals) + ")")
        corpo.append(f"  -- {tab.name}: {len(linhas)}")
        for i in range(0, len(tuplas), 150):
            corpo.append(f"  INSERT INTO {tab.name} ({', '.join(c.name for c in cols)}) VALUES\n    " + ",\n    ".join(tuplas[i:i + 150]) + ";")
        if "id" in tab.columns:
            corpo.append(f"  PERFORM setval(pg_get_serial_sequence('{tab.name}', 'id'), (SELECT max(id) FROM {tab.name}));")
    return corpo


def escrever(corpo, resumo, logins, senha):
    from app.core.security import hash_senha
    limpeza = (RAIZ / "backend" / "sql" / "limpar_dados_teste.sql").read_text(encoding="utf-8")
    bloco_limpeza = limpeza[limpeza.index("DO $$"):limpeza.index("END $$;") + len("END $$;")]
    usuarios = []
    for mat, login in logins.items():
        h = hash_senha(senha)
        usuarios.append(
            f"INSERT INTO usuarios (nome, email, senha_hash, perfil, acesso_global, ativo, instrutor_id)\n"
            f"SELECT i.nome, {lit(login)}, {lit(h)}, 'instrutor', false, true, i.id FROM instrutores i WHERE i.matricula = {lit(mat)}\n"
            f"ON CONFLICT (email) DO UPDATE SET instrutor_id = EXCLUDED.instrutor_id, ativo = true, senha_hash = EXCLUDED.senha_hash "
            f"WHERE usuarios.perfil = 'instrutor';")
    linhas = [
        "-- SEMESTRE COMPLETO DE DEMONSTRAÇÃO (2026/2) — gerado por scripts/gerar_semestre_demo_sql.py a partir de app/demo_semestre.py.",
        "-- ATENÇÃO: APAGA todos os dados (cursos, turmas, instrutores, salas, semestres, aulas, observações...) e carrega a demonstração.",
        "-- MANTÉM: unidades, áreas, turnos e horários oficiais, configurações, perfis e usuários (os de instrutor perdem o vínculo antigo).",
        "-- Requer as atualizações 0003, 0004 e 0005. Cole o arquivo inteiro no SQL Editor do Supabase e clique em Run.",
        "-- Conteúdo: 2 unidades, 11 áreas, 11 cursos, 13 turmas (manhã, tarde e noite), 29 instrutores, 19 salas e laboratórios,",
        f"-- {resumo['aulas']} aulas geradas pelo gerador de horários, semestre PUBLICADO, aulas até 15/10 marcadas como realizadas,",
        "-- uma substituição, observações de instrutores e as notificações do portal.",
        "-- Logins do portal do instrutor (senha " + senha + "): " + ", ".join(logins.values()) + ".",
        "",
        "-- 1) Limpeza (igual a limpar_dados_teste.sql)",
        bloco_limpeza,
        "",
        "-- 2) Semestre de demonstração",
        "DO $$",
        "BEGIN",
        "  IF to_regclass('public.notificacoes') IS NULL THEN",
        "    RAISE EXCEPTION 'Aplique antes atualizacao_0005.sql (portal do instrutor, notificações e substituição).';",
        "  END IF;",
        "  IF EXISTS (SELECT 1 FROM turmas) OR EXISTS (SELECT 1 FROM instrutores) THEN",
        "    RAISE EXCEPTION 'A limpeza (parte 1) não foi executada: rode o arquivo inteiro.';",
        "  END IF;",
        *corpo,
        "END $$;",
        "",
        "-- 3) Acesso ao portal de alguns instrutores (a senha fica só como hash bcrypt)",
        *usuarios,
        "",
        "-- 4) Conferência",
        "SELECT (SELECT count(*) FROM cursos) AS cursos, (SELECT count(*) FROM turmas) AS turmas, (SELECT count(*) FROM instrutores) AS instrutores,",
        "       (SELECT count(*) FROM ambientes) AS salas, (SELECT count(*) FROM alocacoes) AS aulas,",
        "       (SELECT estado FROM cenarios_planejamento ORDER BY id LIMIT 1) AS semestre,",
        "       (SELECT count(*) FROM usuarios WHERE perfil = 'instrutor' AND instrutor_id IS NOT NULL) AS logins_portal;",
    ]
    destino = RAIZ / "backend" / "sql" / "demo_semestre_completo.sql"
    destino.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    print(f"Gerado {destino.relative_to(RAIZ)} ({destino.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
