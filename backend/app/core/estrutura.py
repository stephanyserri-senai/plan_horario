"""Estrutura FIXA da instituição: unidades e áreas tecnológicas.

Estes registros são criados pela migração 0003 e não podem ser incluídos,
excluídos ou renomeados pela aplicação (a API recusa). Para mudar a estrutura,
é preciso uma nova migração revisada.
"""
UNIDADES = [
    # código, nome
    ("BEIRA-MAR", "Unidade Beira Mar"),
    ("PORTO", "Unidade Porto"),
]

AREAS = [
    # código, nome, unidade
    ("AUTOMACAO", "AUTOMAÇÃO", "BEIRA-MAR"),
    ("ENERGIAS", "ENERGIAS", "BEIRA-MAR"),
    ("AUTOMOTIVA", "AUTOMOTIVA", "BEIRA-MAR"),
    ("MECATRONICA", "MECATRÔNICA", "BEIRA-MAR"),
    ("MECANICA", "MECÂNICA", "BEIRA-MAR"),
    ("INSTRUMENTACAO", "INSTRUMENTAÇÃO", "BEIRA-MAR"),
    ("LOGISTICA", "LOGÍSTICA", "PORTO"),
    ("PORTOS", "PORTOS", "PORTO"),
    ("DDS-TI", "DDS/TI", "PORTO"),
    ("ECONOMIA-CRIATIVA", "ECONOMIA CRIATIVA", "PORTO"),
    ("GESTAO", "GESTÃO", "PORTO"),
]

CODIGOS_UNIDADES = {c for c, _ in UNIDADES}


def _criar_turno(db, u, ordem, cod, nome, aulas, dias):
    from datetime import time

    from app.models import PeriodoHorario, Turno
    hm = lambda m: time(m // 60, m % 60)  # noqa: E731
    t = Turno(unidade_id=u.id, codigo=cod, nome=nome, hora_inicio=hm(aulas[0][0]), hora_fim=hm(aulas[-1][0] + aulas[-1][1]), ordem=ordem, ativo=True)
    db.add(t)
    db.flush()
    for i, (ini, dur) in enumerate(aulas, 1):
        db.add(PeriodoHorario(unidade_id=u.id, turno_id=t.id, ordem=i, hora_inicio=hm(ini), hora_fim=hm(ini + dur),
                              dias_semana=list(dias), excepcional=False, ativo=True))


def garantir_estrutura_fixa(db) -> dict:
    """Cria (se faltarem) as unidades, as áreas e os turnos padrão das unidades fixas.
    Nunca altera nem remove registros existentes."""
    from datetime import time

    from sqlalchemy import func, select

    from app.models import Area, PeriodoHorario, Turno, Unidade
    from app.services.regras_aula import TURNO_INTEGRAL, TURNO_SABADO, TURNOS_PADRAO
    criados = {"unidades": 0, "areas": 0, "turnos": 0}
    unidades = {}
    for cod, nome in UNIDADES:
        u = db.scalar(select(Unidade).where(Unidade.codigo == cod))
        if u is None:
            u = Unidade(codigo=cod, nome=nome, situacao="ativa", ativo=True)
            db.add(u)
            db.flush()
            criados["unidades"] += 1
        unidades[cod] = u
    for cod, nome, un in AREAS:
        if not db.scalar(select(Area).where(Area.codigo == cod)):
            db.add(Area(codigo=cod, nome=nome, unidade_id=unidades[un].id, ativo=True))
            criados["areas"] += 1
    hm = lambda m: time(m // 60, m % 60)  # noqa: E731
    for u in unidades.values():
        if db.scalar(select(func.count()).select_from(Turno).where(Turno.unidade_id == u.id)):
            if not db.scalar(select(Turno).where(Turno.unidade_id == u.id, Turno.codigo == TURNO_SABADO[0])):
                _criar_turno(db, u, len(TURNOS_PADRAO) + 1, *TURNO_SABADO, [5])  # turno de sábado (migração 0010)
                criados["turnos"] += 1
            if not db.scalar(select(Turno).where(Turno.unidade_id == u.id, Turno.codigo == TURNO_INTEGRAL[0])):
                _criar_turno(db, u, len(TURNOS_PADRAO) + 2, *TURNO_INTEGRAL, [0, 1, 2, 3, 4])  # turmas PFP (migração 0011)
                criados["turnos"] += 1
            continue
        for ordem, (cod, nome, aulas) in enumerate([*TURNOS_PADRAO, TURNO_SABADO, TURNO_INTEGRAL], 1):
            if cod in (TURNO_SABADO[0], TURNO_INTEGRAL[0]):
                _criar_turno(db, u, ordem, cod, nome, aulas, [5] if cod == TURNO_SABADO[0] else [0, 1, 2, 3, 4])
                criados["turnos"] += 1
                continue
            t = Turno(unidade_id=u.id, codigo=cod, nome=nome, hora_inicio=hm(aulas[0][0]), hora_fim=hm(aulas[-1][0] + aulas[-1][1]), ordem=ordem, ativo=True)
            db.add(t)
            db.flush()
            for i, (ini, dur) in enumerate(aulas, 1):
                db.add(PeriodoHorario(unidade_id=u.id, turno_id=t.id, ordem=i, hora_inicio=hm(ini), hora_fim=hm(ini + dur),
                                      dias_semana=[0, 1, 2, 3, 4], excepcional=False, ativo=True))
            criados["turnos"] += 1
    db.flush()
    return criados
