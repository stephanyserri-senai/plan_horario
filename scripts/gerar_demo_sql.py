"""Gera backend/sql/demo_recarregar.sql: remove e recarrega os dados de
demonstração (prefixo DEMO-) pelo SQL Editor do Supabase.

Equivale a `python -m app.demo recarregar`. Os dados são produzidos pelo próprio
app/demo.py dentro de uma transação que é desfeita (o banco local não muda) e
convertidos em INSERTs com os ids remapeados.
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
from app.demo import carregar  # noqa: E402
from app.models import Base  # noqa: E402

# (tabela, filtro SQL que seleciona as linhas da demonstração) — na ordem de inserção
TABELAS = [
    ("unidades", "codigo = 'DEMO-U1'"),
    ("turnos", "unidade_id IN (SELECT id FROM unidades WHERE codigo = 'DEMO-U1')"),
    ("periodos_horarios", "unidade_id IN (SELECT id FROM unidades WHERE codigo = 'DEMO-U1')"),
    ("calendarios", "unidade_id IN (SELECT id FROM unidades WHERE codigo = 'DEMO-U1')"),
    ("calendario_excecoes", "calendario_id IN (SELECT id FROM calendarios WHERE unidade_id IN (SELECT id FROM unidades WHERE codigo = 'DEMO-U1'))"),
    ("tipos_ambiente", "codigo LIKE 'DEMO-%'"),
    ("ambientes", "unidade_id IN (SELECT id FROM unidades WHERE codigo = 'DEMO-U1')"),
    ("recursos", "unidade_id IN (SELECT id FROM unidades WHERE codigo = 'DEMO-U1')"),
    ("recursos_ambientes", "recurso_id IN (SELECT id FROM recursos WHERE codigo LIKE 'DEMO-%')"),
    ("cursos", "codigo LIKE 'DEMO-%'"),
    ("matrizes_curriculares", "curso_id IN (SELECT id FROM cursos WHERE codigo LIKE 'DEMO-%')"),
    ("unidades_curriculares", "codigo LIKE 'DEMO-%'"),
    ("uc_tipos_ambiente", "uc_id IN (SELECT id FROM unidades_curriculares WHERE codigo LIKE 'DEMO-%')"),
    ("uc_recursos", "uc_id IN (SELECT id FROM unidades_curriculares WHERE codigo LIKE 'DEMO-%')"),
    ("instrutores", "matricula LIKE 'DEMO-%'"),
    ("competencias_instrutores", "instrutor_id IN (SELECT id FROM instrutores WHERE matricula LIKE 'DEMO-%')"),
    ("habilitacoes_instrutores", "instrutor_id IN (SELECT id FROM instrutores WHERE matricula LIKE 'DEMO-%')"),
    ("disponibilidade_instrutores", "instrutor_id IN (SELECT id FROM instrutores WHERE matricula LIKE 'DEMO-%')"),
    ("turmas", "codigo LIKE 'DEMO-%'"),
    ("turma_uc", "turma_id IN (SELECT id FROM turmas WHERE codigo LIKE 'DEMO-%')"),
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
    linhas_sql = []
    with SessionLocal() as db:
        try:
            # recarrega dentro de uma transação que é desfeita no final, para ler exatamente o que app/demo.py produz
            remover_sem_commit(db)
            carregar_sem_commit(db)
            for tabela, filtro in TABELAS:
                tab = Base.metadata.tables[tabela]
                fks = {}
                for fk in tab.foreign_keys:
                    fks[fk.parent.name] = fk.column.table.name
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
                            if fks[c] in nomes:
                                vals.append(f"(SELECT novo FROM _demo_ids WHERE tabela = '{fks[c]}' AND antigo = {v})")
                                continue
                            v = None  # referências fora da demonstração (ex.: usuário criador) não são copiadas
                        vals.append(lit(v))
                    ins = f"INSERT INTO {tabela} ({', '.join(cols)}) VALUES ({', '.join(vals)})"
                    if tem_id:
                        linhas_sql.append(f"WITH n AS ({ins} RETURNING id) INSERT INTO _demo_ids SELECT '{tabela}', {row['id']}, id FROM n;")
                    else:
                        linhas_sql.append(ins + ";")
        finally:
            db.rollback()
    cab = [
        "-- Dados de DEMONSTRAÇÃO (prefixo DEMO-) — gerado por scripts/gerar_demo_sql.py a partir de app/demo.py.",
        "-- Remove a demonstração anterior (somente registros DEMO-, incluindo o cenário DEMO e suas aulas) e carrega a nova.",
        "-- NÃO use em produção. Pode ser executado mais de uma vez.",
        "BEGIN;",
        "",
        "-- 1) Regra de composição das aulas (turno inteiro + hora-aula); não altera se já existir",
        "INSERT INTO configuracoes (chave, valor, descricao) VALUES ('regras_aula', '{\"turno_inteiro\": true, \"contagem\": \"hora_aula\"}'::jsonb,",
        "  'Composição das aulas: com ''turno inteiro'', cada UC ocupa todas as aulas do turno no dia; aula parcial só no fechamento da carga horária "
        "(dividindo o turno com outra UC que também esteja fechando). ''hora_aula'': cada aula conta 1 h de carga horária.')",
        "ON CONFLICT (chave) DO NOTHING;",
        "",
        "-- 2) Remoção da demonstração anterior",
        *REMOCAO,
        "",
        "-- 3) Nova demonstração",
        "CREATE TEMP TABLE _demo_ids (tabela text, antigo int, novo int) ON COMMIT DROP;",
    ]
    rod = [
        "",
        "-- 4) Conferência",
        "SELECT (SELECT count(*) FROM turnos t JOIN unidades u ON u.id = t.unidade_id WHERE u.codigo = 'DEMO-U1') AS turnos,",
        "       (SELECT count(*) FROM periodos_horarios p JOIN unidades u ON u.id = p.unidade_id WHERE u.codigo = 'DEMO-U1') AS aulas_por_dia,",
        "       (SELECT count(*) FROM unidades_curriculares WHERE codigo LIKE 'DEMO-%') AS ucs,",
        "       (SELECT count(*) FROM turmas WHERE codigo LIKE 'DEMO-%') AS turmas,",
        "       (SELECT count(*) FROM cenarios_planejamento WHERE nome LIKE 'DEMO-%') AS cenarios;",
        "COMMIT;",
    ]
    destino = RAIZ / "backend" / "sql" / "demo_recarregar.sql"
    destino.write_text("\n".join(cab + linhas_sql + rod) + "\n", encoding="utf-8")
    print(f"Gerado {destino.relative_to(RAIZ)} ({len(linhas_sql)} inserções)")


REMOCAO = [
    "DELETE FROM cenarios_planejamento WHERE unidade_id IN (SELECT id FROM unidades WHERE codigo = 'DEMO-U1');",
    "DELETE FROM turmas WHERE unidade_id IN (SELECT id FROM unidades WHERE codigo = 'DEMO-U1');",
    "DELETE FROM competencias_instrutores WHERE instrutor_id IN (SELECT id FROM instrutores WHERE unidade_id IN (SELECT id FROM unidades WHERE codigo = 'DEMO-U1'));",
    "DELETE FROM instrutores WHERE unidade_id IN (SELECT id FROM unidades WHERE codigo = 'DEMO-U1');",
    "DELETE FROM uc_tipos_ambiente WHERE uc_id IN (SELECT u.id FROM unidades_curriculares u JOIN matrizes_curriculares m ON m.id = u.matriz_id JOIN cursos c ON c.id = m.curso_id WHERE c.unidade_id IN (SELECT id FROM unidades WHERE codigo = 'DEMO-U1'));",
    "DELETE FROM uc_recursos WHERE uc_id IN (SELECT u.id FROM unidades_curriculares u JOIN matrizes_curriculares m ON m.id = u.matriz_id JOIN cursos c ON c.id = m.curso_id WHERE c.unidade_id IN (SELECT id FROM unidades WHERE codigo = 'DEMO-U1'));",
    "DELETE FROM unidades_curriculares WHERE matriz_id IN (SELECT m.id FROM matrizes_curriculares m JOIN cursos c ON c.id = m.curso_id WHERE c.unidade_id IN (SELECT id FROM unidades WHERE codigo = 'DEMO-U1'));",
    "DELETE FROM matrizes_curriculares WHERE curso_id IN (SELECT id FROM cursos WHERE unidade_id IN (SELECT id FROM unidades WHERE codigo = 'DEMO-U1'));",
    "DELETE FROM cursos WHERE unidade_id IN (SELECT id FROM unidades WHERE codigo = 'DEMO-U1');",
    "DELETE FROM recursos_ambientes WHERE ambiente_id IN (SELECT id FROM ambientes WHERE unidade_id IN (SELECT id FROM unidades WHERE codigo = 'DEMO-U1'));",
    "DELETE FROM recursos WHERE unidade_id IN (SELECT id FROM unidades WHERE codigo = 'DEMO-U1');",
    "DELETE FROM ambientes WHERE unidade_id IN (SELECT id FROM unidades WHERE codigo = 'DEMO-U1');",
    "DELETE FROM tipos_ambiente WHERE codigo LIKE 'DEMO-%';",
    "DELETE FROM calendario_excecoes WHERE calendario_id IN (SELECT id FROM calendarios WHERE unidade_id IN (SELECT id FROM unidades WHERE codigo = 'DEMO-U1'));",
    "DELETE FROM calendarios WHERE unidade_id IN (SELECT id FROM unidades WHERE codigo = 'DEMO-U1');",
    "DELETE FROM periodos_horarios WHERE unidade_id IN (SELECT id FROM unidades WHERE codigo = 'DEMO-U1');",
    "DELETE FROM turnos WHERE unidade_id IN (SELECT id FROM unidades WHERE codigo = 'DEMO-U1');",
    "DELETE FROM unidades WHERE codigo = 'DEMO-U1';",
]


def remover_sem_commit(db):
    for sql in REMOCAO:
        db.execute(text(sql))


def carregar_sem_commit(db):
    commit_original = db.commit
    db.commit = db.flush  # carregar() chama commit no final; aqui só gravamos na transação
    try:
        carregar(db)
    finally:
        db.commit = commit_original


if __name__ == "__main__":
    main()
