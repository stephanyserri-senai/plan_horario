from dataclasses import dataclass, field

from fastapi import Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

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


def get_contexto(authorization: str | None = Header(default=None), db: Session = Depends(get_db)) -> Contexto:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Autenticação necessária.")
    try:
        payload = decodificar_token(authorization.split(" ", 1)[1])
    except Exception:
        raise HTTPException(status_code=401, detail="Sessão inválida ou expirada.")
    usuario = db.get(Usuario, int(payload["sub"]))
    if not usuario or not usuario.ativo:
        raise HTTPException(status_code=401, detail="Usuário inativo.")
    return carregar_contexto(db, usuario)


def requer(acao: str):
    def dep(ctx: Contexto = Depends(get_contexto)) -> Contexto:
        ctx.exigir(acao)
        return ctx
    return dep
