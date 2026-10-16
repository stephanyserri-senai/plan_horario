"""Gera docs/REGRAS_DE_NEGOCIO.md a partir do catálogo de regras (backend/app/services/regras_institucionais.py)."""
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "backend"))

from app.services.regras_institucionais import para_markdown  # noqa: E402

(RAIZ / "docs" / "REGRAS_DE_NEGOCIO.md").write_text(para_markdown(), encoding="utf-8")
print("Gerado docs/REGRAS_DE_NEGOCIO.md")
