# Imagem do backend com OR-Tools. Usada para o WORKER do otimizador
# (Render, Railway, Fly.io, Cloud Run, VM...) e, opcionalmente, para rodar a
# API completa fora da Vercel.
#   worker:  docker run --env-file .env plan-horario-backend
#   API:     docker run -p 8000:8000 --env-file .env plan-horario-backend uvicorn app.main:app --host 0.0.0.0 --port 8000
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

COPY requirements-api.txt requirements.txt ./
RUN pip install -r requirements.txt

COPY alembic.ini ./
COPY alembic ./alembic
COPY app ./app

RUN useradd --create-home --uid 10001 plan && chown -R plan /app
USER plan

CMD ["python", "-m", "app.worker"]
