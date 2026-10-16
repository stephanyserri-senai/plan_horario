"""Regras de composição das aulas (configuráveis em `configuracoes.regras_aula`).

Padrão da instituição:
- **turno inteiro**: cada UC ocupa o turno completo do dia (todas as aulas do
  turno, ex.: 4 aulas). A única exceção é o *fechamento de carga horária*: quando
  falta menos que um turno para a UC terminar, a última aula pode ser parcial e
  o restante do turno pode ser usado por outra UC que também esteja fechando.
- **contagem em minutos reais** (padrão): cada aula vale o tempo que dura (55 min de dia,
  50 min à noite, 60 min nas turmas PFP); o que falta para a carga da UC vira outra aula.
  Ex.: UC de 20 h no matutino = 1200 min ÷ 55 = 22 aulas (5 dias de 4 aulas + 2 aulas de fechamento).
  A opção "hora_aula" (cada aula = 1 h) continua disponível nas configurações, mas não é a regra da instituição.
"""
from __future__ import annotations

import math

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Configuracao, PeriodoHorario
from app.services.calendario import minutos

PADRAO = {"turno_inteiro": True, "contagem": "relogio"}
CHAVE = "regras_aula"


def regras_aula(db: Session) -> dict:
    cfg = db.get(Configuracao, CHAVE)
    return {**PADRAO, **(cfg.valor if cfg and isinstance(cfg.valor, dict) else {})}


def hora_aula(regras: dict) -> bool:
    return regras.get("contagem", "relogio") == "hora_aula"


def credito_periodo(regras: dict, p) -> int:
    """Minutos de carga horária que um período vale (60 em hora-aula; duração real caso contrário)."""
    ini, fim = (minutos(p.hora_inicio), minutos(p.hora_fim)) if hasattr(p, "hora_inicio") else (p.ini, p.fim)
    return 60 if hora_aula(regras) else fim - ini


def credito_bloco(regras: dict, bloco) -> int:
    return sum(credito_periodo(regras, p) for p in bloco)


def periodos_do_turno(db: Session, turno_id: int | None, dia_semana: int) -> list[PeriodoHorario]:
    """Períodos regulares (não excepcionais) do turno no dia da semana, em ordem."""
    if not turno_id:
        return []
    ps = db.scalars(select(PeriodoHorario).where(PeriodoHorario.turno_id == turno_id, PeriodoHorario.ativo.is_(True),
                                                 PeriodoHorario.excepcional.is_(False)).order_by(PeriodoHorario.ordem)).all()
    return [p for p in ps if dia_semana in (p.dias_semana or [])]


def periodos_para_fechar(regras: dict, restante_min: float, periodos: list) -> int:
    """Quantas aulas do turno são necessárias para fechar a carga restante."""
    if restante_min <= 0 or not periodos:
        return 0
    cred = credito_periodo(regras, periodos[0])
    return min(len(periodos), max(1, math.ceil(restante_min / cred - 1e-9)))


TURNOS_PADRAO = [
    # código, nome, aulas (início, duração em minutos) — intervalos ficam entre a 2ª e a 3ª aula
    ("M", "Manhã", [(7 * 60 + 30, 55), (8 * 60 + 25, 55), (9 * 60 + 40, 55), (10 * 60 + 35, 55)]),
    ("T", "Tarde", [(13 * 60 + 30, 55), (14 * 60 + 25, 55), (15 * 60 + 40, 55), (16 * 60 + 35, 55)]),
    ("N", "Noite", [(18 * 60 + 30, 50), (19 * 60 + 20, 50), (20 * 60 + 20, 50), (21 * 60 + 10, 50)]),  # 18:30–22:00, intervalo 20:10–20:20
]
# Sábado: turno próprio, 09:00–13:00 (4 aulas, intervalo 10:50–11:10), só aos sábados. Turma de sábado só tem aula presencial no sábado.
TURNO_SABADO = ("S", "Sábado", [(9 * 60, 55), (9 * 60 + 55, 55), (11 * 60 + 10, 55), (12 * 60 + 5, 55)])
# Turmas PFP: aula manhã e tarde, 08:00–12:00 e 13:00–17:00 (4 + 4 aulas; almoço 12:00–13:00), de segunda a sexta.
# Cada metade é um turno: a manhã (08–12) e a tarde (13–17) podem ter UCs e instrutores diferentes; na grade
# aparecem nas linhas da manhã e da tarde (o limiar de horário aceita 08:00 e 13:00).
TURNO_INTEGRAL = ("I", "Manhã e tarde (PFP)", [(h * 60, 60) for h in (8, 9, 10, 11, 13, 14, 15, 16)])
BLOCOS_PFP = [("08:00", "12:00", "M"), ("13:00", "17:00", "T")]  # cada bloco vale como o turno de mesmo código
INTERVALO_MAX_MIN = 30  # pausa maior que isso (ex.: almoço) separa dois blocos de aula no mesmo turno


def janelas_pfp(codigos_jornada) -> list[tuple[str, str]]:
    """Janelas extras para dar aula em turma PFP: quem é da manhã dá 08–12; quem é da tarde, 13–17."""
    cods = set(codigos_jornada)
    return [(a, b) for a, b, c in BLOCOS_PFP if c in cods]


def blocos(periodos: list) -> list[list]:
    """Períodos do turno agrupados em blocos contínuos (a pausa do almoço da PFP separa manhã e tarde)."""
    res: list[list] = []
    for p in periodos:
        ini = minutos(p.hora_inicio) if hasattr(p, "hora_inicio") else p.ini
        if res:
            ult = res[-1][-1]
            fim_ult = minutos(ult.hora_fim) if hasattr(ult, "hora_fim") else ult.fim
            if ini - fim_ult > INTERVALO_MAX_MIN:
                res.append([p])
                continue
            res[-1].append(p)
        else:
            res.append([p])
    return res


def bloco_da_hora(periodos: list, hora_min: int) -> list:
    """O bloco do turno em que a aula começa (o turno inteiro dela)."""
    bs = blocos(periodos)
    for b in bs:
        ini = minutos(b[0].hora_inicio) if hasattr(b[0], "hora_inicio") else b[0].ini
        fim = minutos(b[-1].hora_fim) if hasattr(b[-1], "hora_fim") else b[-1].fim
        if ini <= hora_min < fim:
            return b
    return bs[0] if bs else []
TURNOS_ESPECIAIS = {"S", "I"}  # não entram na jornada M/V/N do instrutor


HORAS_POR_TURNO = 4  # cada turno = 4 aulas


def turnos_por_dia(max_horas_dia) -> int:
    """Quantos turnos o instrutor pode assumir no mesmo dia: 4 h = 1, 8 h = 2, 12 h = 3."""
    return max(1, int(float(max_horas_dia or HORAS_POR_TURNO) // HORAS_POR_TURNO))


# Ocupação máxima com aulas: 90% dos turnos da jornada (40 h = 10 turnos → até 9 com aula; 20 h = 5 → até 4).
# O turno que sobra fica para planejamento (PL), projeto (PJ) ou reserva. Vale no cadastro, na importação,
# na validação das aulas e no gerador de horários.
OCUPACAO_MAXIMA = 0.9


def teto_letivo(carga_semanal) -> float:
    """Horas de aula por semana permitidas pela regra dos 90%, em turnos inteiros (40 h → 36 h; 20 h → 16 h)."""
    turnos = int(float(carga_semanal or 0) // HORAS_POR_TURNO)
    return float(int(turnos * OCUPACAO_MAXIMA + 1e-9) * HORAS_POR_TURNO)


def limite_letivo_efetivo(inst) -> float:
    """Limite semanal de aulas do instrutor: o cadastrado, sem passar dos 90% da jornada."""
    teto = teto_letivo(inst.carga_horaria_contratual)
    lim = float(inst.limite_ch_letiva or teto)
    return min(lim, teto) if teto > 0 else lim


def horas_dia_pela_carga(carga_semanal) -> float:
    """Jornada diária pela carga contratual em 5 dias (40 h/sem = 8 h/dia), limitada a 12 h."""
    return float(min(12, max(1, round(float(carga_semanal) / 5))))


# Turnos de trabalho do instrutor. V = vespertino (turno "T", tarde). Quem trabalha 8 h por dia (40 h/semana)
# faz dois turnos seguidos (MV ou VN); com menos horas, um turno só (M, V ou N).
JORNADAS = {"M": ["M"], "V": ["T"], "N": ["N"], "MV": ["M", "T"], "VN": ["T", "N"]}
ROTULO_JORNADA = {"M": "M – Manhã", "V": "V – Tarde (vespertino)", "N": "N – Noite", "MV": "MV – Manhã e tarde", "VN": "VN – Tarde e noite"}


def turnos_exigidos(max_horas_dia) -> int:
    """1 ou 2 turnos por dia: 8 h ou mais = 2 (MV ou VN); menos = 1 (M, V ou N)."""
    return 2 if float(max_horas_dia or 0) >= 2 * HORAS_POR_TURNO else 1


def jornadas_permitidas(max_horas_dia) -> list[str]:
    return ["MV", "VN"] if turnos_exigidos(max_horas_dia) == 2 else ["M", "V", "N"]


def jornada_dos_codigos(codigos) -> str | None:
    """Códigos de turno ({"M", "T"}) → jornada ("MV"); None se a combinação não for uma jornada válida."""
    cods = set(codigos)
    alvo = sorted(cods, key="MTN".index) if cods <= set("MTN") else None
    return next((j for j, cs in JORNADAS.items() if alvo is not None and cs == alvo), None)


def normalizar_jornada(valor: str) -> str | None:
    """Aceita "MV", "vn", "M", "Manhã; Tarde", "Tarde e noite"… e devolve a jornada ou None."""
    v = (valor or "").strip().upper()
    if v in JORNADAS:
        return v
    import unicodedata
    v = "".join(c for c in unicodedata.normalize("NFD", v) if unicodedata.category(c) != "Mn")
    cods = set()
    for parte, cod in (("MANHA", "M"), ("MATUTINO", "M"), ("TARDE", "T"), ("VESPERTINO", "T"), ("NOITE", "N"), ("NOTURNO", "N")):
        if parte in v:
            cods.add(cod)
    return jornada_dos_codigos(cods) if cods else None


def validar_jornada(jornada: str | None, max_horas_dia) -> str | None:
    """Mensagem de erro (ou None) para a jornada informada com as horas de aula por dia do instrutor."""
    permitidas = jornadas_permitidas(max_horas_dia)
    if jornada in permitidas:
        return None
    h = float(max_horas_dia or 0)
    if turnos_exigidos(h) == 2:
        return f"Com {h:g} h de aula por dia o instrutor trabalha dois turnos: escolha MV (manhã e tarde) ou VN (tarde e noite)."
    return f"Com {h:g} h de aula por dia o instrutor trabalha um turno: escolha M (manhã), V (tarde) ou N (noite)."

