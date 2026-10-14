"""Gera backend/sql/demo_recarregar.sql: remove e recarrega os dados de
demonstração (prefixo DEMO-) pelo SQL Editor do Supabase.

Equivale a `python -m app.demo recarregar`. Os dados são produzidos pelo próprio
app/demo.py dentro de uma transação que é desfeita (o banco local não muda) e
convertidos em INSERTs. Tudo fica num único bloco `DO $$ ... $$`: o SQL Editor
executa o bloco inteiro de uma vez (não depende de BEGIN/COMMIT nem de a sessão
ser mantida entre comandos). Referências à estrutura fixa (unidades, áreas e
turnos) são resolvidas pelo código, não pelo id.
Uso: python scripts/gerar_demo_sql.py
"""
import json
import sys
from datetime import date, datetime, time
from decimal import Decimal
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "backend"))

from sqlalchemy import text  # noqa: E402

from app.core.db import SessionLocal  # noqa: E402
from app.demo import REMOCAO, carregar  # noqa: E402
from app.models import Base  # noqa: E402

DEMO_TURMAS = "SELECT id FROM turmas WHERE codigo LIKE 'DEMO-%'"
DEMO_UCS = "SELECT id FROM unidades_curriculares WHERE codigo LIKE 'DEMO-%'"
DEMO_INSTR = "SELECT id FROM instrutores WHERE matricula LIKE 'DEMO-%'"
# (tabela, filtro das linhas da demonstração) — na ordem de inserção
TABELAS = [
    ("calendarios", "nome LIKE 'DEMO-%'"),
    ("calendario_excecoes", "calendario_id IN (SELECT id FROM calendarios WHERE nome LIKE 'DEMO-%')"),
    ("tipos_ambiente", "codigo LIKE 'DEMO-%'"),
    ("ambientes", "codigo LIKE 'DEMO-%'"),
    ("recursos", "codigo LIKE 'DEMO-%'"),
    ("recursos_ambientes", "recurso_id IN (SELECT id FROM recursos WHERE codigo LIKE 'DEMO-%')"),
    ("cursos", "codigo LIKE 'DEMO-%'"),
    ("matrizes_curriculares", "curso_id IN (SELECT id FROM cursos WHERE codigo LIKE 'DEMO-%')"),
    ("unidades_curriculares", "codigo LIKE 'DEMO-%'"),
    ("uc_tipos_ambiente", f"uc_id IN ({DEMO_UCS})"),
    ("uc_recursos", f"uc_id IN ({DEMO_UCS})"),
    ("instrutores", "matricula LIKE 'DEMO-%'"),
    ("competencias_instrutores", f"instrutor_id IN ({DEMO_INSTR})"),
    ("habilitacoes_instrutores", f"instrutor_id IN ({DEMO_INSTR})"),
    ("disponibilidade_instrutores", f"instrutor_id IN ({DEMO_INSTR})"),
    ("turmas", "codigo LIKE 'DEMO-%'"),
    ("turma_uc", f"turma_id IN ({DEMO_TURMAS})"),
    ("cenarios_planejamento", "nome LIKE 'DEMO-%'"),
]
IGNORAR = {"id", "criado_em", "atualizado_em"}


def lit(v) -> str:
    if v is None:
        return "NULL"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float, Decimal)):
        return str(v)
    if isinstance(v, (date, time, datetime)):
        return f"'{v.isoformat()}'"
    if isinstance(v, (list, tuple)):
        return "'{" + ",".join(str(x) for x in v) + "}'"
    if isinstance(v, dict):
        return "'" + json.dumps(v, ensure_ascii=False).replace("'", "''") + "'::jsonb"
    return "'" + str(v).replace("'", "''") + "'"


def main():
    nomes = {t for t, _ in TABELAS}
    corpo = []
    with SessionLocal() as db:
        try:
            for sql in REMOCAO:
                db.execute(text(sql))
            commit = db.commit
            db.commit = db.flush  # carregar() chama commit no final; aqui tudo fica na transação desfeita abaixo
            try:
                carregar(db)
            finally:
                db.commit = commit
            # chaves naturais da estrutura fixa
            un_cod = dict(db.execute(text("SELECT id, codigo FROM unidades")).all())
            area_cod = dict(db.execute(text("SELECT id, codigo FROM areas")).all())
            turno_cod = {r[0]: (un_cod[r[1]], r[2]) for r in db.execute(text("SELECT id, unidade_id, codigo FROM turnos")).all()}
            fixas = {
                "unidades": lambda v: f"(SELECT id FROM unidades WHERE codigo = {lit(un_cod[v])})",
                "areas": lambda v: f"(SELECT id FROM areas WHERE codigo = {lit(area_cod[v])})",
                "turnos": lambda v: (f"(SELECT t.id FROM turnos t JOIN unidades u ON u.id = t.unidade_id "
                                     f"WHERE u.codigo = {lit(turno_cod[v][0])} AND t.codigo = {lit(turno_cod[v][1])})"),
            }
            for tabela, filtro in TABELAS:
                tab = Base.metadata.tables[tabela]
                fks = {fk.parent.name: fk.column.table.name for fk in tab.foreign_keys}
                gerados = {c.name for c in tab.columns if c.computed is not None}
                cols = [c.name for c in tab.columns if c.name not in IGNORAR and c.name not in gerados]
                tem_id = "id" in tab.columns
                for row in db.execute(text(f"SELECT * FROM {tabela} WHERE {filtro} ORDER BY 1")).mappings():
                    vals = []
                    for c in cols:
                        v = row[c]
                        if tabela == "cenarios_planejamento" and c in ("estado", "versao", "lock_version"):
                            v = {"estado": "em_elaboracao", "versao": 1, "lock_version": 0}[c]
                        if c in fks and v is not None:
                            alvo = fks[c]
                            if alvo in nomes:
                                vals.append(f"(SELECT novo FROM _demo_ids WHERE tabela = '{alvo}' AND antigo = {v})")
                                continue
                            if alvo in fixas:
                                vals.append(fixas[alvo](v))
                                continue
                            v = None  # referências fora da demonstração (ex.: usuário criador) não são copiadas
                        vals.append(lit(v))
                    ins = f"INSERT INTO {tabela} ({', '.join(cols)}) VALUES ({', '.join(vals)})"
                    if tem_id:
                        corpo.append(f"  WITH n AS ({ins} RETURNING id) INSERT INTO _demo_ids SELECT '{tabela}', {row['id']}, id FROM n;")
                    else:
                        corpo.append(f"  {ins};")
        finally:
            db.rollback()
    linhas = [
        "-- Dados de DEMONSTRAÇÃO (prefixo DEMO-) — gerado por scripts/gerar_demo_sql.py a partir de app/demo.py.",
        "-- Pré-requisito: atualização 0003 aplicada (unidades Beira Mar/Porto, áreas e turnos oficiais).",
        "-- Remove a demonstração anterior (somente registros DEMO-, incluindo o cenário DEMO e suas aulas) e carrega a nova",
        "-- na unidade Beira Mar. NÃO use em produção. Pode ser executado mais de uma vez.",
        "-- Cole o arquivo inteiro no SQL Editor e clique em Run.",
        "DO $$",
        "BEGIN",
        "  IF NOT EXISTS (SELECT 1 FROM pg_tables WHERE schemaname = 'public' AND tablename = 'areas')",
        "     OR NOT EXISTS (SELECT 1 FROM unidades WHERE codigo = 'BEIRA-MAR') THEN",
        "    RAISE EXCEPTION 'Aplique antes backend/sql/atualizacao_0003.sql (unidades, áreas e turnos oficiais).';",
        "  END IF;",
        "",
        "  -- 1) Remoção da demonstração anterior (somente registros DEMO-)",
        *[f"  {sql};" for sql in REMOCAO],
        "",
        "  -- 2) Nova demonstração",
        "  DROP TABLE IF EXISTS _demo_ids;",
        "  CREATE TEMP TABLE _demo_ids (tabela text, antigo int, novo int);",
        *corpo,
        "  DROP TABLE _demo_ids;",
        "END $$;",
        "",
        "-- 3) Conferência",
        "SELECT (SELECT count(*) FROM cursos WHERE codigo LIKE 'DEMO-%') AS cursos,",
        "       (SELECT count(*) FROM unidades_curriculares WHERE codigo LIKE 'DEMO-%') AS ucs,",
        "       (SELECT count(*) FROM turmas WHERE codigo LIKE 'DEMO-%') AS turmas,",
        "       (SELECT count(*) FROM instrutores WHERE matricula LIKE 'DEMO-%') AS instrutores,",
        "       (SELECT count(*) FROM cenarios_planejamento WHERE nome LIKE 'DEMO-%') AS cenarios;",
    ]
    destino = RAIZ / "backend" / "sql" / "demo_recarregar.sql"
    destino.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    print(f"Gerado {destino.relative_to(RAIZ)} ({len(corpo)} inserções)")


if __name__ == "__main__":
    main()
