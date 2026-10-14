"""Entrada da função Python serverless da Vercel.

A Vercel encaminha /api/* para este arquivo (ver vercel.json) e procura a
variável `app` (aplicação ASGI). O código do backend fica em backend/app.
"""
import os
import sys

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_RAIZ, "backend"))

from app.main import app  # noqa: E402,F401
