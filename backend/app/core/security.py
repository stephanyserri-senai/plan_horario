"""Senhas com bcrypt (nunca em texto puro) e tokens JWT."""
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.core.config import get_settings


def hash_senha(senha: str) -> str:
    return bcrypt.hashpw(senha.encode(), bcrypt.gensalt()).decode()


def verificar_senha(senha: str, senha_hash: str) -> bool:
    try:
        return bcrypt.checkpw(senha.encode(), senha_hash.encode())
    except ValueError:
        return False


def criar_token(usuario_id: int, perfil: str) -> str:
    s = get_settings()
    agora = datetime.now(timezone.utc)
    payload = {"sub": str(usuario_id), "perfil": perfil, "iat": agora, "exp": agora + timedelta(minutes=s.jwt_expira_minutos)}
    return jwt.encode(payload, s.jwt_secret, algorithm="HS256")


def decodificar_token(token: str) -> dict:
    return jwt.decode(token, get_settings().jwt_secret, algorithms=["HS256"])
