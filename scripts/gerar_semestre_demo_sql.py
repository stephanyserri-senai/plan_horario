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
    # login de coordenação da demonstração (aprova as solicitações dos instrutores); só é criado se ainda não existir
    usuarios.append(
        f"INSERT INTO usuarios (nome, email, senha_hash, perfil, acesso_global, ativo)\n"
        f"VALUES ('Coordenação (demonstração)', 'coordenacao', {lit(hash_senha(senha))}, 'coordenador', true, true)\n"
        f"ON CONFLICT (email) DO NOTHING;")
    linhas = [
        "-- SEMESTRE COMPLETO DE DEMONSTRAÇÃO (2026/2) — gerado por scripts/gerar_semestre_demo_sql.py a partir de app/demo_semestre.py.",
        "-- ATENÇÃO: APAGA todos os dados (cursos, turmas, instrutores, salas, semestres, aulas, observações...) e carrega a demonstração.",
        "-- MANTÉM: unidades, áreas, turnos e horários oficiais, configurações, perfis e usuários (os de instrutor perdem o vínculo antigo).",
        "-- Requer as atualizações 0003 a 0021. Cole o arquivo inteiro no SQL Editor do Supabase e clique em Run.",
        "-- Conteúdo: 2 unidades, 11 áreas, 16 cursos, 19 turmas (manhã, tarde, noite, sábado e PFP de dia inteiro), 30 instrutores, 19 salas e laboratórios,",
        f"-- {resumo['aulas']} aulas geradas pelo gerador de horários, semestre PUBLICADO, aulas até 15/10 marcadas como realizadas,",
        "-- uma substituição, observações de instrutores, notificações do portal, instrutores mensalistas e horistas",
        "-- e turnos de planejamento (PL) / projeto (PJ) dos mensalistas, instrutores BÁSICOS (só AIB e qualificações:",
        "-- Rogério Lima, Tiago Barbosa, Wagner Prado e Sabrina Lopes), turmas 80-20 com a sexta EAD (HTC-LOG-21 e HTC-DDS-09),",
        "-- turma de SÁBADO (QUA-INF-01, 09:00–13:00), turma PFP de dia inteiro (PFP-OPL-01, 08–12 e 13–17, a partir de 19/10),",
        "-- UCs TRANSVERSAIS (INF-BAS, ADM-ATC), competências 'em partes' e",
        "-- SOLICITAÇÕES de instrutores (2 aguardando o coordenador, 1 aprovada, 1 recusada).",
        "-- CASOS PARA TESTAR CONFLITOS E AÇÕES:",
        "--  * licença médica de Fábio Teixeira (26/10 a 06/11) com aulas marcadas → resolver por substituição;",
        "--  * Laboratório de Automação e CLP (Beira Mar) em manutenção de 03/11 a 06/11 → trocar a sala;",
        "--  * ponto facultativo no Porto em 28/10 com aulas → remarcar;",
        "--  * turma nova HTC-ELT-1-14 (modular, 1º de 4 módulos; início 19/10) sem nenhuma aula → gerar horários só dela;",
        "--  * turmas modulares HTC-MEC-2-08 e HTC-MCT-3-04: o código sobe a cada semestre até o último módulo;",
        "--  * turma QUA-NRB-01 (NR-10 Básico, início 03/11) SEM INSTRUTOR POSSÍVEL: o único habilitado, Wagner Prado,",
        "--    já dá aula em 9 de 10 turnos (teto de 90%) → a geração explica quem poderia e sugere mudanças;",
        "--  * proposta de alteração 'Ajustes de novembro' (em edição) com aulas SEM INSTRUTOR (HTC-INS-02)",
        "--    e aulas SEM SALA (QUA-DGR-01) → alocar na grade, validar e submeter.",
        "-- Logins do portal do instrutor (senha " + senha + "): " + ", ".join(logins.values()) + ".",
        "-- Login de coordenação (perfil coordenador, senha " + senha + "): coordenacao — aprova as solicitações dos instrutores.",
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
        "  IF NOT EXISTS (SELECT 1 FROM turnos WHERE codigo = 'N' AND hora_inicio = '18:30' AND hora_fim = '22:00') THEN",
        "    RAISE EXCEPTION 'Aplique antes atualizacao_0006.sql (turno da noite das 18:30 às 22:00).';",
        "  END IF;",
        "  IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'instrutores' AND column_name = 'modalidade') THEN",
        "    RAISE EXCEPTION 'Aplique antes atualizacao_0007.sql (modalidade do instrutor: mensalista/horista).';",
        "  END IF;",
        "  IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'instrutores' AND column_name = 'nivel') THEN",
        "    RAISE EXCEPTION 'Aplique antes atualizacao_0009.sql (nível do instrutor e dias EAD da turma).';",
        "  END IF;",
        "  IF to_regclass('public.solicitacoes_instrutor') IS NULL OR NOT EXISTS (SELECT 1 FROM turnos WHERE codigo = 'S') THEN",
        "    RAISE EXCEPTION 'Aplique antes atualizacao_0010.sql (coordenador, solicitações, UC transversal e turno de sábado).';",
        "  END IF;",
        "  IF NOT EXISTS (SELECT 1 FROM turnos WHERE codigo = 'I') THEN",
        "    RAISE EXCEPTION 'Aplique antes atualizacao_0011.sql (turno integral das turmas PFP).';",
        "  END IF;",
        "  IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'matrizes_curriculares' AND column_name = 'tipo_oferta') THEN",
        "    RAISE EXCEPTION 'Aplique antes atualizacao_0012.sql (PFP manhã e tarde, contagem em minutos e versões da matriz por oferta).';",
        "  END IF;",
        "  IF to_regclass('public.epis_turma') IS NULL THEN",
        "    RAISE EXCEPTION 'Aplique antes atualizacao_0013.sql (EPIs por curso e controle por turma).';",
        "  END IF;",
        "  IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'cursos' AND column_name = 'dispensa_epi') THEN",
        "    RAISE EXCEPTION 'Aplique antes atualizacao_0014.sql (cursos que não precisam de EPI).';",
        "  END IF;",
        "  IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'turmas' AND column_name = 'modulos') THEN",
        "    RAISE EXCEPTION 'Aplique antes atualizacao_0015.sql (turmas modulares e reposição aos sábados).';",
        "  END IF;",
        "  IF to_regclass('public.pdi_itens') IS NULL THEN",
        "    RAISE EXCEPTION 'Aplique antes atualizacao_0016.sql (PDI dos instrutores).';",
        "  END IF;",
        "  IF to_regclass('public.termos_horas') IS NULL THEN",
        "    RAISE EXCEPTION 'Aplique antes atualizacao_0017.sql (termo de horas dos horistas).';",
        "  END IF;",
        "  IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'termos_horas' AND column_name = 'dias_semana') THEN",
        "    RAISE EXCEPTION 'Aplique antes atualizacao_0018.sql (dias do termo de horas).';",
        "  END IF;",
        "  IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'unidades_curriculares' AND column_name = 'modalidade') THEN",
        "    RAISE EXCEPTION 'Aplique antes atualizacao_0019.sql (UC presencial ou EAD).';",
        "  END IF;",
        "  IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'termos_horas' AND column_name = 'agenda') THEN",
        "    RAISE EXCEPTION 'Aplique antes atualizacao_0020.sql (termo de horas por dia e turno).';",
        "  END IF;",
        "  IF to_regclass('public.solicitacoes_impressao') IS NULL THEN",
        "    RAISE EXCEPTION 'Aplique antes atualizacao_0021.sql (pedidos de impressão).';",
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
