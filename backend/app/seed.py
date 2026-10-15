"""Carga inicial obrigatória (perfis, parâmetros, configurações e usuário
administrador). Idempotente.

Uso:
    python -m app.seed                          # lê PLAN_ADMIN_EMAIL e PLAN_ADMIN_SENHA
    python -m app.seed --usuario-teste          # cria o administrador de TESTE (admin / admin@123)
    python -m app.seed --remover-usuario-teste  # remove/inativa o administrador de TESTE

O usuário de teste existe para validar a instalação antes de cadastrar os
usuários reais. Ele tem senha conhecida e por isso:
- NUNCA é criado com PLAN_AMBIENTE=producao (o comando recusa);
- a API registra um alerta e /api/saude o sinaliza enquanto estiver ativo;
- deve ser removido assim que houver um administrador real.
"""
import os
import sys

from sqlalchemy import select

from app.core.config import get_settings
from app.core.db import SessionLocal
from app.core.permissoes import PADRAO
from app.core.security import hash_senha
from app.models import Configuracao, ParametrosOtimizacao, PermissaoPerfil, Usuario
from app.solver.criterios import pesos_padrao

CONFIGS = {
    "limiares_ocupacao": ({"subutilizado_pct": 30.0, "demanda_excessiva_pct": 85.0, "instrutor_critico_pct": 90.0},
                          "Limiares para classificar ambientes subutilizados/sobrecarregados e instrutores críticos."),
    "geral": ({"nome_instituicao": "", "fuso_horario": "America/Sao_Paulo"}, "Parâmetros gerais da instituição."),
    "regras_aula": ({"turno_inteiro": True, "contagem": "hora_aula"},
                    "Composição das aulas: com 'turno inteiro', cada UC ocupa todas as aulas do turno no dia; aula parcial só no fechamento "
                    "da carga horária (dividindo o turno com outra UC que também esteja fechando). 'hora_aula': cada aula conta 1 h de carga horária."),
}


def executar(db, admin_email: str | None = None, admin_senha: str | None = None):
    # Perfis ainda sem configuração recebem as ações padrão. As migrações só acrescentam ações novas
    # (ex.: 0005), então um perfil que só tem essas ações ainda não foi configurado.
    acrescentadas_por_migracao = {"observacoes.gerenciar", "portal.instrutor"}
    for perfil, acoes in PADRAO.items():
        atuais = set(db.scalars(select(PermissaoPerfil.acao).where(PermissaoPerfil.perfil == perfil)))
        if atuais <= acrescentadas_por_migracao:
            for a in set(acoes) - atuais:
                db.add(PermissaoPerfil(perfil=perfil, acao=a))
    if not db.scalar(select(ParametrosOtimizacao).limit(1)):
        db.add(ParametrosOtimizacao(nome="Padrão", pesos=pesos_padrao(), limite_tempo_s=30, padrao=True))
    from app.core.estrutura import garantir_estrutura_fixa
    garantir_estrutura_fixa(db)  # unidades Beira Mar/Porto, áreas e turnos oficiais (normalmente já criados pela migração 0003)
    for k, (v, desc) in CONFIGS.items():
        if not db.get(Configuracao, k):
            db.add(Configuracao(chave=k, valor=v, descricao=desc))
    supabase = get_settings().auth_modo == "supabase"
    if admin_email and (admin_senha or supabase) and not db.scalar(select(Usuario).where(Usuario.email == admin_email.lower())):
        # Modo Supabase: a senha é definida no Supabase Auth (convite); o hash local fica inutilizável.
        db.add(Usuario(nome="Administrador", email=admin_email.lower(), senha_hash="!supabase" if supabase else hash_senha(admin_senha),
                       perfil="administrador", acesso_global=True))
    db.commit()


USUARIO_TESTE_LOGIN = "admin"
USUARIO_TESTE_SENHA = "admin@123"
USUARIO_TESTE_NOME = "Administrador de TESTE (remover antes da produção)"


def email_usuario_teste() -> str:
    """Modo local: login 'admin'. Modo Supabase: o Supabase Auth exige e-mail;
    use PLAN_USUARIO_TESTE_EMAIL (padrão admin@teste.local) e crie o mesmo
    usuário no painel do Supabase com a senha admin@123."""
    if get_settings().auth_modo == "supabase":
        return os.environ.get("PLAN_USUARIO_TESTE_EMAIL", "admin@teste.local").strip().lower()
    return USUARIO_TESTE_LOGIN


def criar_usuario_teste(db) -> Usuario:
    s = get_settings()
    if s.producao:
        raise SystemExit("Recusado: o usuário de teste (senha conhecida) não pode ser criado com PLAN_AMBIENTE=producao.")
    from app.services import auditoria
    login = email_usuario_teste()
    u = db.scalar(select(Usuario).where(Usuario.email == login))
    senha_hash = "!supabase" if s.auth_modo == "supabase" else hash_senha(USUARIO_TESTE_SENHA)
    if u is None:
        u = Usuario(nome=USUARIO_TESTE_NOME, email=login, senha_hash=senha_hash, perfil="administrador", acesso_global=True, ativo=True)
        db.add(u)
    else:
        u.nome, u.senha_hash, u.perfil, u.acesso_global, u.ativo = USUARIO_TESTE_NOME, senha_hash, "administrador", True, True
    db.flush()
    auditoria.registrar(db, "seed", "usuario.teste_criar", "usuarios", u.id, depois={"login": login, "ambiente": s.ambiente}, origem="seed")
    db.commit()
    return u


def remover_usuario_teste(db) -> str:
    """Exclui o usuário de teste; se ele já tiver histórico (FKs), apenas inativa."""
    from sqlalchemy.exc import IntegrityError

    from app.services import auditoria
    alvo = [x for x in {USUARIO_TESTE_LOGIN, email_usuario_teste()}]
    u = db.scalar(select(Usuario).where(Usuario.email.in_(alvo), Usuario.nome == USUARIO_TESTE_NOME))
    if u is None:
        return "Usuário de teste não encontrado."
    uid = u.id
    try:
        db.delete(u)
        db.flush()
        auditoria.registrar(db, "seed", "usuario.teste_remover", "usuarios", uid, origem="seed")
        db.commit()
        return "Usuário de teste excluído."
    except IntegrityError:
        db.rollback()
        u = db.get(Usuario, uid)
        u.ativo, u.senha_hash = False, "!removido"
        auditoria.registrar(db, "seed", "usuario.teste_inativar", "usuarios", uid, origem="seed")
        db.commit()
        return "Usuário de teste inativado (possui histórico de auditoria vinculado)."


def usuario_teste_ativo(db) -> bool:
    return bool(db.scalar(select(Usuario.id).where(Usuario.nome == USUARIO_TESTE_NOME, Usuario.ativo.is_(True))))


if __name__ == "__main__":
    if "--usuario-teste" in sys.argv and get_settings().producao:
        raise SystemExit("Recusado: o usuário de teste (senha conhecida) não pode ser criado com PLAN_AMBIENTE=producao.")
    if "--usuario-teste" in sys.argv or "--remover-usuario-teste" in sys.argv:
        with SessionLocal() as db:
            executar(db)  # garante perfis/parâmetros
            if "--remover-usuario-teste" in sys.argv:
                print(remover_usuario_teste(db))
            else:
                u = criar_usuario_teste(db)
                if get_settings().auth_modo == "supabase":
                    print(f"Usuário de teste cadastrado na plataforma: {u.email}. Crie o MESMO e-mail no Supabase "
                          f"(Authentication → Users → Add user) com a senha {USUARIO_TESTE_SENHA} e 'Auto Confirm User'.")
                else:
                    print(f"Usuário de teste pronto: login '{USUARIO_TESTE_LOGIN}', senha '{USUARIO_TESTE_SENHA}'. Remova antes da produção.")
        sys.exit(0)
    email, senha = os.environ.get("PLAN_ADMIN_EMAIL"), os.environ.get("PLAN_ADMIN_SENHA")
    if get_settings().auth_modo == "supabase":
        if not email:
            print("Defina PLAN_ADMIN_EMAIL (o mesmo e-mail do usuário no Supabase Auth) para criar o administrador.", file=sys.stderr)
        senha = None
    elif not email or not senha or len(senha) < 8:
        print("Defina PLAN_ADMIN_EMAIL e PLAN_ADMIN_SENHA (mín. 8 caracteres) para criar o administrador.", file=sys.stderr)
        senha = None
    with SessionLocal() as db:
        executar(db, email, senha)
    print("Carga inicial concluída.")
