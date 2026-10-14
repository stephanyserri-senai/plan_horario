"""Integração com o Supabase Auth.

O navegador autentica-se no Supabase (e-mail/senha, convite, recuperação) e
envia o access token (JWT) à API. A API valida o token NO SERVIDOR:
- chaves assimétricas (RS256/ES256) via JWKS publicado pelo projeto; ou
- segredo compartilhado HS256 legado (PLAN_SUPABASE_JWT_SECRET);
verificando assinatura, expiração, emissor e audiência "authenticated".

A autorização continua sendo a da plataforma: o usuário precisa existir em
`usuarios` (vinculado por auth_user_id ou, no primeiro acesso, pelo e-mail
confirmado) e seu perfil/escopo define o que pode fazer. Um login válido no
Supabase sem cadastro na plataforma NÃO recebe acesso.
"""
from __future__ import annotations

import logging

import httpx
import jwt
from jwt import PyJWKClient

from app.core.config import get_settings

log = logging.getLogger("auth")
_jwks: PyJWKClient | None = None


class TokenInvalido(Exception):
    pass


def _emissor() -> str:
    return get_settings().supabase_url.rstrip("/") + "/auth/v1"


def _cliente_jwks() -> PyJWKClient:
    global _jwks
    if _jwks is None:
        _jwks = PyJWKClient(_emissor() + "/.well-known/jwks.json", cache_keys=True, lifespan=3600, timeout=10)
    return _jwks


def verificar_token(token: str) -> dict:
    s = get_settings()
    try:
        cabecalho = jwt.get_unverified_header(token)
    except jwt.PyJWTError as e:
        raise TokenInvalido("Token malformado.") from e
    alg = cabecalho.get("alg")
    if alg == "HS256":
        if not s.supabase_jwt_secret:
            raise TokenInvalido("Token HS256 recebido, mas PLAN_SUPABASE_JWT_SECRET não está configurado.")
        chave = s.supabase_jwt_secret
    elif alg in ("RS256", "ES256"):
        try:
            chave = _cliente_jwks().get_signing_key_from_jwt(token).key
        except Exception as e:  # rede/JWKS indisponível ou kid desconhecido
            raise TokenInvalido(f"Não foi possível obter a chave de verificação do Supabase: {e}") from e
    else:
        raise TokenInvalido(f"Algoritmo de assinatura não aceito: {alg}")
    try:
        return jwt.decode(token, chave, algorithms=[alg], audience="authenticated", issuer=_emissor(),
                          options={"require": ["exp", "sub", "iss", "aud"]})
    except jwt.PyJWTError as e:
        raise TokenInvalido(str(e)) from e


def convidar_usuario(email: str) -> dict:
    """Envia convite do Supabase Auth (requer a chave service_role, usada
    exclusivamente no servidor). Retorna {"enviado": bool, "erro": str|None}."""
    s = get_settings()
    if not (s.supabase_url and s.supabase_service_role_key):
        return {"enviado": False, "erro": "PLAN_SUPABASE_SERVICE_ROLE_KEY não configurada: convide o usuário pelo painel do Supabase (Authentication → Users → Invite)."}
    params = {"redirect_to": s.url_publica} if s.url_publica else None
    try:
        r = httpx.post(_emissor() + "/invite", params=params, json={"email": email}, timeout=15,
                       headers={"apikey": s.supabase_service_role_key, "Authorization": f"Bearer {s.supabase_service_role_key}"})
    except httpx.HTTPError as e:
        return {"enviado": False, "erro": f"Falha de comunicação com o Supabase: {e}"}
    if r.status_code >= 400:
        log.warning("Convite Supabase recusado (%s): %s", r.status_code, r.text[:300])
        return {"enviado": False, "erro": f"Supabase recusou o convite ({r.status_code}): {r.text[:200]}"}
    return {"enviado": True, "erro": None}
