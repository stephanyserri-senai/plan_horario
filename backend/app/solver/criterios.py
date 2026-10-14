"""Critérios da função objetivo: nome, unidade de medida e peso padrão.

Escala documentada: pontos = peso × valor bruto (na unidade indicada).
Todos os critérios são de minimização. Os pesos usados em cada execução e em
cada comparação são registrados junto com o resultado, e a comparação entre
cenários recalcula todos os cenários com o MESMO conjunto de pesos — assim
uma mudança de escala nunca distorce a comparação silenciosamente.

Restrições obrigatórias NÃO aparecem aqui: nunca são convertidas em
penalidades (ficam como restrições rígidas no solver e bloqueios na
validação central).
"""

CRITERIOS = {
    "demanda_nao_atendida": ("encontros semanais não alocados", "Demanda não atendida (somente no modo parcial)", 1000.0),
    "prazos": ("encontros não alocados × urgência", "Priorizar UCs com prazo de conclusão mais próximo", 200.0),
    "janelas_instrutores": ("períodos vagos/semana", "Minimizar janelas entre aulas dos instrutores", 10.0),
    "janelas_turmas": ("períodos vagos/semana", "Minimizar janelas entre aulas das turmas", 15.0),
    "ocupacao_inadequada": ("% de capacidade ociosa por encontro", "Maximizar ocupação adequada dos ambientes", 0.2),
    "deslocamentos": ("dias com deslocamento/semana", "Reduzir deslocamentos de instrutores entre unidades", 30.0),
    "equilibrio_carga": ("% da maior ocupação letiva", "Equilibrar a carga horária entre instrutores", 2.0),
    "concentracao_dias": ("encontros excedentes no mesmo dia", "Evitar concentração de aulas da mesma UC em um dia", 20.0),
    "preferencia_turno": ("encontros fora do turno preferido", "Respeitar preferências de turno dos instrutores", 5.0),
    "aulas_isoladas": ("dias com carga abaixo do mínimo", "Evitar dias com aulas isoladas para a turma", 10.0),
    "especializado_desnecessario": ("encontros", "Reduzir uso desnecessário de ambientes especializados", 8.0),
    "horarios_excepcionais": ("encontros", "Evitar horários excepcionais", 15.0),
    "mudancas_vigente": ("encontros alterados", "Minimizar mudanças em relação ao cenário vigente (publicado)", 25.0),
    "preservar_aprovados": ("encontros alterados", "Preservar horários já aprovados no cenário", 40.0),
}

PARAMETROS_EXTRAS = {
    "min_periodos_dia": (2, "Mínimo de períodos por dia de aula da turma (abaixo disso é 'aula isolada')"),
}


def pesos_padrao() -> dict[str, float]:
    p = {k: v[2] for k, v in CRITERIOS.items()}
    p.update({k: v[0] for k, v in PARAMETROS_EXTRAS.items()})
    return p


def normalizar_pesos(pesos: dict | None) -> dict[str, float]:
    base = pesos_padrao()
    for k, v in (pesos or {}).items():
        if k in base:
            base[k] = float(v)
    return base


def descricao_criterios():
    return [{"criterio": k, "unidade": u, "descricao": d, "peso_padrao": p} for k, (u, d, p) in CRITERIOS.items()]
