"""Autenticação, usuários, perfis e escopos de acesso."""
from datetime import datetime

from fastapi import APIRouter, Body, Depends
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import Contexto, carregar_contexto, get_contexto, requer
from app.core.errors import AcessoNegado, ConflitoValidacao, EntradaInvalida, NaoEncontrado
from app.core.permissoes import ACOES, PERFIS
from app.core.security import criar_token, hash_senha, verificar_senha
from app.models import PermissaoEscopo, PermissaoPerfil, Usuario
from app.services import auditoria

router = APIRouter(prefix="/api", tags=["segurança"])


def _usuario(u: Usuario, db: Session) -> dict:
    escopos = db.scalars(select(PermissaoEscopo).where(PermissaoEscopo.usuario_id == u.id)).all()
    return {"id": u.id, "nome": u.nome, "email": u.email, "perfil": u.perfil, "acesso_global": u.acesso_global, "ativo": u.ativo,
            "ultimo_acesso": u.ultimo_acesso.isoformat() if u.ultimo_acesso else None,
            "escopos": [{"tipo": e.escopo_tipo, "id": e.escopo_id} for e in escopos]}


@router.post("/auth/login")
def login(dados: dict = Body(...), db: Session = Depends(get_db)):
    u = db.scalars(select(Usuario).where(Usuario.email == str(dados.get("email", "")).strip().lower())).first()
    if not u or not u.ativo or not verificar_senha(str(dados.get("senha", "")), u.senha_hash):
        auditoria.registrar(db, None, "auth.falha", "usuarios", None, depois={"email": dados.get("email")})
        db.commit()
        raise AcessoNegado("E-mail ou senha inválidos.", codigo="CREDENCIAIS_INVALIDAS")
    u.ultimo_acesso = datetime.now()
    auditoria.registrar(db, carregar_contexto(db, u), "auth.login", "usuarios", u.id)
    db.commit()
    return {"token": criar_token(u.id, u.perfil), "usuario": _usuario(u, db)}


@router.get("/auth/me")
def me(ctx: Contexto = Depends(get_contexto), db: Session = Depends(get_db)):
    return {**_usuario(ctx.usuario, db), "acoes": sorted(ctx.acoes),
            "escopo": {"unidades": sorted(ctx.unidades) if ctx.unidades is not None else None,
                       "cursos": sorted(ctx.cursos) if ctx.cursos is not None else None,
                       "turmas": sorted(ctx.turmas) if ctx.turmas is not None else None}}


@router.post("/auth/senha")
def trocar_senha(dados: dict = Body(...), ctx: Contexto = Depends(get_contexto), db: Session = Depends(get_db)):
    u = db.get(Usuario, ctx.id)
    if not verificar_senha(dados.get("senha_atual", ""), u.senha_hash):
        raise AcessoNegado("Senha atual incorreta.")
    if len(dados.get("nova_senha", "")) < 8:
        raise EntradaInvalida("A nova senha deve ter ao menos 8 caracteres.")
    u.senha_hash = hash_senha(dados["nova_senha"])
    auditoria.registrar(db, ctx, "auth.trocar_senha", "usuarios", u.id)
    db.commit()
    return {"ok": True}


@router.get("/usuarios")
def listar(ctx: Contexto = Depends(requer("usuarios.gerenciar")), db: Session = Depends(get_db)):
    return [_usuario(u, db) for u in db.scalars(select(Usuario).order_by(Usuario.nome))]


@router.post("/usuarios")
def criar(dados: dict = Body(...), ctx: Contexto = Depends(requer("usuarios.gerenciar")), db: Session = Depends(get_db)):
    if dados.get("perfil") not in PERFIS:
        raise EntradaInvalida(f"Perfil inválido. Opções: {', '.join(PERFIS)}")
    if len(dados.get("senha", "")) < 8:
        raise EntradaInvalida("A senha deve ter ao menos 8 caracteres.")
    u = Usuario(nome=dados["nome"], email=dados["email"].strip().lower(), senha_hash=hash_senha(dados["senha"]), perfil=dados["perfil"],
                acesso_global=bool(dados.get("acesso_global")), ativo=True)
    try:
        db.add(u)
        db.flush()
    except IntegrityError:
        db.rollback()
        raise ConflitoValidacao("Já existe usuário com este e-mail.")
    _salvar_escopos(db, u.id, dados.get("escopos", []))
    auditoria.registrar(db, ctx, "usuario.criar", "usuarios", u.id, depois=auditoria.snapshot(u))
    db.commit()
    return _usuario(u, db)


def _salvar_escopos(db, uid, escopos):
    db.execute(delete(PermissaoEscopo).where(PermissaoEscopo.usuario_id == uid))
    for e in escopos or []:
        db.add(PermissaoEscopo(usuario_id=uid, escopo_tipo=e["tipo"], escopo_id=int(e["id"])))


@router.put("/usuarios/{uid}")
def atualizar(uid: int, dados: dict = Body(...), ctx: Contexto = Depends(requer("usuarios.gerenciar")), db: Session = Depends(get_db)):
    u = db.get(Usuario, uid)
    if u is None:
        raise NaoEncontrado("Usuário não encontrado.")
    antes = auditoria.snapshot(u)
    for k in ("nome", "perfil", "acesso_global", "ativo"):
        if k in dados:
            setattr(u, k, dados[k])
    if u.perfil not in PERFIS:
        raise EntradaInvalida("Perfil inválido.")
    if dados.get("senha"):
        if len(dados["senha"]) < 8:
            raise EntradaInvalida("A senha deve ter ao menos 8 caracteres.")
        u.senha_hash = hash_senha(dados["senha"])
    if "escopos" in dados:
        _salvar_escopos(db, uid, dados["escopos"])
    auditoria.registrar(db, ctx, "usuario.alterar", "usuarios", uid, antes=antes, depois=auditoria.snapshot(u))
    db.commit()
    return _usuario(u, db)


@router.get("/perfis")
def perfis(ctx: Contexto = Depends(get_contexto), db: Session = Depends(get_db)):
    matriz = {p: sorted(db.scalars(select(PermissaoPerfil.acao).where(PermissaoPerfil.perfil == p))) for p in PERFIS}
    return {"perfis": PERFIS, "acoes": ACOES, "matriz": matriz}


@router.put("/perfis/{perfil}")
def atualizar_perfil(perfil: str, dados: dict = Body(...), ctx: Contexto = Depends(requer("usuarios.gerenciar")), db: Session = Depends(get_db)):
    if perfil not in PERFIS:
        raise NaoEncontrado("Perfil inexistente.")
    acoes = [a for a in dados.get("acoes", []) if a in ACOES]
    if perfil == "administrador" and "usuarios.gerenciar" not in acoes:
        raise ConflitoValidacao("O administrador não pode perder a permissão de gerenciar usuários.")
    antes = sorted(db.scalars(select(PermissaoPerfil.acao).where(PermissaoPerfil.perfil == perfil)))
    db.execute(delete(PermissaoPerfil).where(PermissaoPerfil.perfil == perfil))
    for a in acoes:
        db.add(PermissaoPerfil(perfil=perfil, acao=a))
    auditoria.registrar(db, ctx, "perfil.alterar", "permissoes_perfil", perfil, antes={"acoes": antes}, depois={"acoes": acoes})
    db.commit()
    return {"perfil": perfil, "acoes": acoes}
