from dataclasses import dataclass, field

from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_db
from app.core.errors import AcessoNegado
from app.core.security import decodificar_token
from app.models import PermissaoEscopo, PermissaoPerfil, Usuario


@dataclass
class Contexto:
    """Usuário autenticado + ações autorizadas + escopo de dados."""
    usuario: Usuario
    acoes: set[str]
    unidades: set[int] | None = None  # None = todas
    cursos: set[int] | None = None
    turmas: set[int] | None = None
    extra: dict = field(default_factory=dict)

    @property
    def id(self):
        return self.usuario.id

    def pode(self, acao: str) -> bool:
        return acao in self.acoes

    def exigir(self, acao: str):
        if acao not in self.acoes:
            raise AcessoNegado(f"Seu perfil ({self.usuario.perfil}) não possui a permissão '{acao}'.")

    def acessa_unidade(self, unidade_id: int | None) -> bool:
        return self.unidades is None or unidade_id is None or unidade_id in self.unidades

    def exigir_unidade(self, unidade_id: int | None):
        if not self.acessa_unidade(unidade_id):
            raise AcessoNegado("Registro fora do escopo de unidades autorizado para o seu usuário.")

    def acessa_turma(self, turma) -> bool:
        if not self.acessa_unidade(turma.unidade_id):
            return False
        if self.cursos is not None and turma.curso_id not in self.cursos:
            return False
        if self.turmas is not None and turma.id not in self.turmas:
            return False
        return True


def carregar_contexto(db: Session, usuario: Usuario) -> Contexto:
    acoes = set(db.scalars(select(PermissaoPerfil.acao).where(PermissaoPerfil.perfil == usuario.perfil)))
    ctx = Contexto(usuario=usuario, acoes=acoes)
    if usuario.perfil == "administrador" or usuario.acesso_global:
        return ctx
    escopos = db.scalars(select(PermissaoEscopo).where(PermissaoEscopo.usuario_id == usuario.id)).all()
    por_tipo: dict[str, set[int]] = {}
    for e in escopos:
        por_tipo.setdefault(e.escopo_tipo, set()).add(e.escopo_id)
    if not escopos:
        # Sem acesso global e sem escopo cadastrado: nenhum dado de unidade.
        ctx.unidades = set()
        return ctx
    ctx.unidades = por_tipo.get("unidade")  # None = sem restrição por unidade
    ctx.cursos = por_tipo.get("curso")
    ctx.turmas = por_tipo.get("turma")
    return ctx


def _usuario_supabase(db: Session, token: str) -> Usuario:
    from sqlalchemy import func

    from app.core.supabase_auth import TokenInvalido, verificar_token
    from app.services import auditoria
    try:
        claims = verificar_token(token)
    except TokenInvalido as e:
        raise HTTPException(status_code=401, detail=f"Sessão inválida ou expirada. ({e})")
    sub, email = claims.get("sub"), (claims.get("email") or "").strip().lower()
    usuario = db.scalars(select(Usuario).where(Usuario.auth_user_id == sub)).first()
    if usuario is None and email:
        # Primeiro acesso: vincula pelo e-mail cadastrado pelo administrador.
        usuario = db.scalars(select(Usuario).where(func.lower(Usuario.email) == email, Usuario.auth_user_id.is_(None))).first()
        if usuario is not None:
            usuario.auth_user_id = sub
            auditoria.registrar(db, None, "auth.vincular_supabase", "usuarios", usuario.id, depois={"auth_user_id": sub, "email": email})
            db.commit()
    if usuario is None:
        raise HTTPException(status_code=403, detail="Usuário autenticado, mas sem cadastro na plataforma. Solicite acesso ao administrador.")
    return usuario


def aplicar_filtro_unidade(ctx: Contexto, unidade: str | None) -> Contexto:
    """Filtro de unidade escolhido na tela (cabeçalho X-Unidade): só para CONSULTAS, reduz o escopo do usuário àquela
    unidade — nunca amplia. O escopo real fica em ctx.extra["unidades_escopo"] (para listas como a de unidades)."""
    if not unidade or not str(unidade).isdigit():
        return ctx
    u = int(unidade)
    ctx.extra["unidades_escopo"] = ctx.unidades
    ctx.extra["filtro_unidade"] = u
    ctx.unidades = {u} if ctx.unidades is None else (ctx.unidades & {u})
    return ctx


def get_contexto(request: Request, authorization: str | None = Header(default=None), x_unidade: str | None = Header(default=None),
                 db: Session = Depends(get_db)) -> Contexto:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Autenticação necessária.")
    token = authorization.split(" ", 1)[1].strip()
    if get_settings().auth_modo == "supabase":
        usuario = _usuario_supabase(db, token)
    else:
        try:
            payload = decodificar_token(token)
        except Exception:
            raise HTTPException(status_code=401, detail="Sessão inválida ou expirada.")
        usuario = db.get(Usuario, int(payload["sub"]))
    if not usuario or not usuario.ativo:
        raise HTTPException(status_code=401, detail="Usuário inativo.")
    ctx = carregar_contexto(db, usuario)
    if request.method == "GET":  # gravações nunca são afetadas pelo filtro da tela
        aplicar_filtro_unidade(ctx, x_unidade)
    return ctx


def requer(acao: str):
    def dep(ctx: Contexto = Depends(get_contexto)) -> Contexto:
        ctx.exigir(acao)
        return ctx
    return dep
