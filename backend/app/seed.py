"""Carga inicial obrigatória (perfis, parâmetros, configurações e usuário
administrador). Idempotente.

Uso:  python -m app.seed  (lê PLAN_ADMIN_EMAIL e PLAN_ADMIN_SENHA)
"""
import os
import sys

from sqlalchemy import select

from app.core.db import SessionLocal
from app.core.permissoes import PADRAO
from app.core.security import hash_senha
from app.models import Configuracao, ParametrosOtimizacao, PermissaoPerfil, Usuario
from app.solver.criterios import pesos_padrao

CONFIGS = {
    "limiares_ocupacao": ({"subutilizado_pct": 30.0, "demanda_excessiva_pct": 85.0, "instrutor_critico_pct": 90.0},
                          "Limiares para classificar ambientes subutilizados/sobrecarregados e instrutores críticos."),
    "geral": ({"nome_instituicao": "", "fuso_horario": "America/Sao_Paulo"}, "Parâmetros gerais da instituição."),
}


def executar(db, admin_email: str | None = None, admin_senha: str | None = None):
    if not db.scalar(select(PermissaoPerfil).limit(1)):
        for perfil, acoes in PADRAO.items():
            for a in acoes:
                db.add(PermissaoPerfil(perfil=perfil, acao=a))
    if not db.scalar(select(ParametrosOtimizacao).limit(1)):
        db.add(ParametrosOtimizacao(nome="Padrão", pesos=pesos_padrao(), limite_tempo_s=30, padrao=True))
    for k, (v, desc) in CONFIGS.items():
        if not db.get(Configuracao, k):
            db.add(Configuracao(chave=k, valor=v, descricao=desc))
    if admin_email and admin_senha and not db.scalar(select(Usuario).where(Usuario.email == admin_email.lower())):
        db.add(Usuario(nome="Administrador", email=admin_email.lower(), senha_hash=hash_senha(admin_senha), perfil="administrador", acesso_global=True))
    db.commit()


if __name__ == "__main__":
    email, senha = os.environ.get("PLAN_ADMIN_EMAIL"), os.environ.get("PLAN_ADMIN_SENHA")
    if not email or not senha or len(senha) < 8:
        print("Defina PLAN_ADMIN_EMAIL e PLAN_ADMIN_SENHA (mín. 8 caracteres) para criar o administrador.", file=sys.stderr)
    with SessionLocal() as db:
        executar(db, email, senha)
    print("Carga inicial concluída.")
