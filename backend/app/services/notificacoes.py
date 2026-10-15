"""Notificações do instrutor no portal: avisos de tudo o que muda para ele."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import Notificacao


def notificar(db: Session, instrutor_id: int | None, tipo: str, titulo: str, texto: str | None = None, aba: str | None = None, ctx=None):
    """Registra um aviso para o instrutor. Não avisa o próprio instrutor sobre o que ele mesmo fez no portal."""
    if not instrutor_id:
        return
    if ctx is not None and getattr(getattr(ctx, "usuario", None), "instrutor_id", None) == instrutor_id:
        return
    db.add(Notificacao(instrutor_id=instrutor_id, tipo=tipo, titulo=titulo[:200], texto=texto, aba=aba, lida=False))


ROTULO_CAMPO = {
    "nome": "nome", "email": "e-mail", "unidade_id": "unidade", "area_id": "área principal", "todas_areas": "atende todas as áreas",
    "carga_horaria_contratual": "carga contratual", "limite_ch_letiva": "limite de aulas por semana", "max_horas_dia": "horas de aula por dia",
    "turno_preferencial_id": "turno preferencial", "situacao": "situação", "ativo": "situação no cadastro", "areas_competencia": "formação e especialidades",
    "intervalo_minimo_h": "descanso entre jornadas", "restricoes_deslocamento": "restrições de deslocamento", "matricula": "matrícula",
    "areas_ids": "outras áreas", "ucs_competencia": "UCs que ministra", "disp_turnos": "turnos disponíveis", "disp_dias": "dias disponíveis",
}

# cadastros ligados a um instrutor e o texto do aviso quando alguém da coordenação os altera
CADASTROS_DO_INSTRUTOR = {
    "competencias": ("UCs que você ministra", "dados"),
    "habilitacoes": ("suas certificações", "dados"),
    "disponibilidade_instrutores": ("sua disponibilidade", "dados"),
    "instrutor_unidades": ("unidades em que você atua", "dados"),
}


def avisar_alteracao_cadastro(db: Session, ctx, instrutor_id: int, campos: list[str], acao: str = "alterou"):
    nomes = sorted({ROTULO_CAMPO.get(c, c.replace("_", " ")) for c in campos if not c.startswith("_") and c not in ("atualizado_em", "criado_em")})
    if not nomes:
        return
    quem = getattr(getattr(ctx, "usuario", None), "nome", None) or "A coordenação"
    notificar(db, instrutor_id, "cadastro", "Seu cadastro foi atualizado", f"{quem} {acao}: {', '.join(nomes)}.", "dados", ctx)
