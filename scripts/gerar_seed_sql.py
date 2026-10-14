"""Gera backend/sql/seed_inicial.sql: dados iniciais obrigatórios (perfis,
pesos padrão, configurações) e, opcionalmente, o usuário de TESTE.

Equivale a `python -m app.seed` + `python -m app.seed --usuario-teste`, para
quem prefere aplicar pelo SQL Editor do Supabase. Idempotente (ON CONFLICT).
Uso: python scripts/gerar_seed_sql.py
"""
import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "backend"))

from app.core.permissoes import PADRAO  # noqa: E402
from app.core.security import hash_senha  # noqa: E402
from app.seed import CONFIGS, USUARIO_TESTE_LOGIN, USUARIO_TESTE_NOME, USUARIO_TESTE_SENHA  # noqa: E402
from app.solver.criterios import pesos_padrao  # noqa: E402


def q(v: str) -> str:
    return "'" + v.replace("'", "''") + "'"


linhas = [
    "-- Dados iniciais da Plataforma de Planejamento Acadêmico (gerado por scripts/gerar_seed_sql.py).",
    "-- Aplique DEPOIS de schema_completo.sql. Pode ser executado mais de uma vez (idempotente).",
    "BEGIN;",
    "",
    "-- Permissões padrão de cada perfil",
]
for perfil, acoes in PADRAO.items():
    for a in acoes:
        linhas.append(f"INSERT INTO permissoes_perfil (perfil, acao) VALUES ({q(perfil)}, {q(a)}) ON CONFLICT DO NOTHING;")
linhas += ["", "-- Conjunto de pesos padrão do otimizador",
           f"INSERT INTO parametros_otimizacao (nome, pesos, limite_tempo_s, padrao, versao, ativo) VALUES ('Padrão', {q(json.dumps(pesos_padrao()))}::jsonb, 30, true, 1, true) ON CONFLICT (nome) DO NOTHING;",
           "", "-- Configurações"]
for chave, (valor, desc) in CONFIGS.items():
    linhas.append(f"INSERT INTO configuracoes (chave, valor, descricao) VALUES ({q(chave)}, {q(json.dumps(valor, ensure_ascii=False))}::jsonb, {q(desc)}) ON CONFLICT (chave) DO NOTHING;")
linhas += [
    "",
    "-- USUÁRIO DE TESTE (login: admin / senha: admin@123) — SOMENTE homologação.",
    "-- Remova antes da produção: DELETE FROM usuarios WHERE email = 'admin' AND nome LIKE 'Administrador de TESTE%';",
    f"INSERT INTO usuarios (nome, email, senha_hash, perfil, acesso_global, ativo) VALUES ({q(USUARIO_TESTE_NOME)}, {q(USUARIO_TESTE_LOGIN)}, "
    f"{q(hash_senha(USUARIO_TESTE_SENHA))}, 'administrador', true, true) ON CONFLICT (email) DO NOTHING;",
    "",
    "COMMIT;",
    "",
]
(RAIZ / "backend" / "sql" / "seed_inicial.sql").write_text("\n".join(linhas))
print("Gerado backend/sql/seed_inicial.sql")
