"""Registro das entidades de cadastro e seus metadados (usados pela API
genérica e pelo frontend para montar tabelas e formulários)."""
from __future__ import annotations

from sqlalchemy import ARRAY, Boolean, Date, DateTime, Float, Integer, Numeric, String, Text, Time

from app.models import (
    Ambiente, Bloqueio, Calendario, CalendarioExcecao, CompetenciaInstrutor, Curso, DeslocamentoUnidade, DisponibilidadeAmbiente,
    DisponibilidadeInstrutor, HabilitacaoInstrutor, HorarioFuncionamento, Instrutor, InstrutorUnidade, MatrizCurricular, PeriodoHorario,
    Recurso, RecursoAmbiente, Setor, TipoAmbiente, Turma, TurmaUC, Turno, UCPrerequisito, UCRecurso, Unidade, UnidadeCurricular,
)

DIAS_OPCOES = [{"valor": i, "rotulo": d} for i, d in enumerate(["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"])]

ENTIDADES: dict[str, dict] = {
    "unidades": {"model": Unidade, "rotulo": "Unidades", "grupo": "Instituição", "label": "{codigo} – {nome}", "busca": ["codigo", "nome", "cidade"],
                 "unidade_col": "id", "opcoes": {"situacao": ["ativa", "inativa"]}},
    "setores": {"model": Setor, "rotulo": "Setores", "grupo": "Instituição", "label": "{nome}", "busca": ["nome", "responsavel"], "unidade_col": "unidade_id"},
    "deslocamentos": {"model": DeslocamentoUnidade, "rotulo": "Deslocamentos entre unidades", "grupo": "Instituição", "label": "{origem_id}→{destino_id}", "busca": []},
    "turnos": {"model": Turno, "rotulo": "Turnos", "grupo": "Calendário", "label": "{nome}", "busca": ["codigo", "nome"], "unidade_col": "unidade_id"},
    "periodos": {"model": PeriodoHorario, "rotulo": "Períodos / blocos de aula", "grupo": "Calendário", "label": "{ordem}º {hora_inicio}–{hora_fim}",
                 "busca": [], "unidade_col": "unidade_id", "dias": ["dias_semana"]},
    "calendarios": {"model": Calendario, "rotulo": "Calendários acadêmicos", "grupo": "Calendário", "label": "{nome}", "busca": ["nome"],
                    "unidade_col": "unidade_id", "dias": ["dias_letivos"]},
    "calendario_excecoes": {"model": CalendarioExcecao, "rotulo": "Feriados e exceções", "grupo": "Calendário", "label": "{data} {tipo}",
                            "busca": ["descricao", "tipo"], "opcoes": {"tipo": ["feriado", "recesso", "dia_letivo_extra", "horario_especial"]}},
    "horarios_funcionamento": {"model": HorarioFuncionamento, "rotulo": "Horários de funcionamento", "grupo": "Calendário", "label": "{dia_semana}",
                               "busca": [], "unidade_col": "unidade_id", "dia": ["dia_semana"]},
    "bloqueios": {"model": Bloqueio, "rotulo": "Bloqueios e indisponibilidades", "grupo": "Calendário", "label": "{alvo_tipo} {alvo_id}",
                  "busca": ["motivo", "tipo"], "opcoes": {"alvo_tipo": ["instrutor", "ambiente", "turma", "unidade", "recurso"],
                                                          "tipo": ["indisponibilidade", "manutencao", "atividade_administrativa", "atividade_pedagogica", "evento", "afastamento"]}},
    "cursos": {"model": Curso, "rotulo": "Cursos", "grupo": "Acadêmico", "label": "{codigo} – {nome}", "busca": ["codigo", "nome", "eixo_tecnologico"],
               "unidade_col": "unidade_id"},
    "matrizes": {"model": MatrizCurricular, "rotulo": "Matrizes curriculares", "grupo": "Acadêmico", "label": "{versao}", "busca": ["versao"],
                 "opcoes": {"situacao": ["rascunho", "vigente", "encerrada"]}},
    "ucs": {"model": UnidadeCurricular, "rotulo": "Unidades curriculares", "grupo": "Acadêmico", "label": "{codigo} – {nome}",
            "busca": ["codigo", "nome", "competencias"], "extras": {"tipos_ambiente_ids": {"tipo": "multiref", "ref": "tipos_ambiente", "rotulo": "Tipos de ambiente aceitos"}}},
    "uc_prerequisitos": {"model": UCPrerequisito, "rotulo": "Pré-requisitos de UCs", "grupo": "Acadêmico", "label": "{uc_id}", "busca": [], "pk": ["uc_id", "prerequisito_id"]},
    "uc_recursos": {"model": UCRecurso, "rotulo": "Equipamentos exigidos por UC", "grupo": "Acadêmico", "label": "{recurso_tipo}", "busca": ["recurso_tipo"],
                    "pk": ["uc_id", "recurso_tipo"]},
    "tipos_ambiente": {"model": TipoAmbiente, "rotulo": "Tipos de ambiente", "grupo": "Ambientes", "label": "{nome}", "busca": ["codigo", "nome"]},
    "ambientes": {"model": Ambiente, "rotulo": "Ambientes", "grupo": "Ambientes", "label": "{codigo} – {nome}", "busca": ["codigo", "nome", "predio", "localizacao"],
                  "unidade_col": "unidade_id", "opcoes": {"situacao": ["operacional", "manutencao", "interditado"]}},
    "disponibilidade_ambientes": {"model": DisponibilidadeAmbiente, "rotulo": "Disponibilidade de ambientes", "grupo": "Ambientes", "label": "{dia_semana}",
                                  "busca": [], "dia": ["dia_semana"]},
    "recursos": {"model": Recurso, "rotulo": "Recursos e equipamentos", "grupo": "Ambientes", "label": "{codigo} – {nome}", "busca": ["codigo", "nome", "tipo"],
                 "unidade_col": "unidade_id", "opcoes": {"situacao": ["disponivel", "manutencao", "indisponivel"]}},
    "recursos_ambientes": {"model": RecursoAmbiente, "rotulo": "Equipamentos instalados em ambientes", "grupo": "Ambientes", "label": "{recurso_id}", "busca": []},
    "turmas": {"model": Turma, "rotulo": "Turmas", "grupo": "Acadêmico", "label": "{codigo} – {nome}", "busca": ["codigo", "nome"], "unidade_col": "unidade_id",
               "dias": ["dias_possiveis"], "ocultar": ["simulacao_id"],
               "opcoes": {"situacao": ["planejada", "em_andamento", "concluida", "cancelada"]}},
    "turma_ucs": {"model": TurmaUC, "rotulo": "Ofertas (turma × UC)", "grupo": "Acadêmico", "label": "{turma_id}/{uc_id}", "busca": [],
                  "opcoes": {"situacao": ["prevista", "ofertada", "em_execucao", "concluida", "pendente", "cancelada"]}},
    "instrutores": {"model": Instrutor, "rotulo": "Instrutores", "grupo": "Instrutores", "label": "{nome} ({matricula})", "busca": ["nome", "matricula", "areas_competencia"],
                    "unidade_col": "unidade_id", "pessoais": ["email"], "opcoes": {"situacao": ["ativo", "afastado", "ferias", "desligado"]}},
    "instrutor_unidades": {"model": InstrutorUnidade, "rotulo": "Unidades de atuação", "grupo": "Instrutores", "label": "{unidade_id}", "busca": [],
                           "pk": ["instrutor_id", "unidade_id"]},
    "competencias": {"model": CompetenciaInstrutor, "rotulo": "Matriz de competências", "grupo": "Instrutores", "label": "{instrutor_id}/{uc_id}",
                     "busca": ["condicoes"], "opcoes": {"nivel": ["pleno", "supervisionado", "em_formacao"]}},
    "habilitacoes": {"model": HabilitacaoInstrutor, "rotulo": "Habilitações e certificações", "grupo": "Instrutores", "label": "{nome}", "busca": ["nome"]},
    "disponibilidade_instrutores": {"model": DisponibilidadeInstrutor, "rotulo": "Disponibilidade de instrutores", "grupo": "Instrutores",
                                    "label": "{dia_semana}", "busca": [], "dia": ["dia_semana"]},
}

# tabela -> chave da entidade (para referências)
TABELA_ENTIDADE = {cfg["model"].__tablename__: k for k, cfg in ENTIDADES.items()}
TABELA_ENTIDADE["unidades_curriculares"] = "ucs"
TABELA_ENTIDADE["matrizes_curriculares"] = "matrizes"
TABELA_ENTIDADE["turma_uc"] = "turma_ucs"
SOMENTE_LEITURA = {"id", "criado_em", "atualizado_em"}

ROTULOS = {
    "id": "ID", "codigo": "Código", "nome": "Nome", "situacao": "Situação", "ativo": "Ativo", "endereco": "Endereço", "responsavel": "Responsável",
    "regras_operacionais": "Regras operacionais", "descricao": "Descrição", "hora_inicio": "Início", "hora_fim": "Fim", "dia_semana": "Dia da semana",
    "dias_semana": "Dias da semana", "dias_letivos": "Dias letivos", "dias_possiveis": "Dias possíveis", "excepcional": "Horário excepcional",
    "data_inicio": "Data de início", "data_fim": "Data de término", "data_limite": "Data-limite", "carga_horaria_total": "Carga horária total (h)",
    "ch_teorica": "CH teórica (h)", "ch_pratica": "CH prática (h)", "ch_semanal_desejada": "CH semanal desejada (h)", "ch_realizada": "CH já realizada (h)",
    "duracao_bloco_periodos": "Períodos por encontro", "encontros_semanais": "Encontros semanais", "sequencia": "Sequência", "competencias": "Competências",
    "certificacao_exigida": "Certificação exigida", "capacidade_min": "Capacidade mínima", "capacidade_max": "Capacidade máxima",
    "divide_grupos": "Divide em grupos", "aulas_consecutivas": "Aulas consecutivas", "restricoes_pedagogicas": "Restrições pedagógicas",
    "prioridade": "Prioridade (1 = mais alta)", "capacidade_fisica": "Capacidade física", "capacidade_operacional": "Capacidade operacional",
    "maquinas": "Máquinas instaladas", "requisitos_seguranca": "Requisitos de segurança", "acessivel": "Acessível", "tempo_preparacao_min": "Preparação entre aulas (min)",
    "predio": "Prédio", "localizacao": "Localização", "quantidade_total": "Quantidade total", "movel": "Móvel (compartilhado)", "requer_reserva": "Requer reserva",
    "qtd_alunos": "Alunos", "capacidade_prevista": "Capacidade prevista", "num_grupos": "Nº de grupos", "necessidades_acessibilidade": "Requer acessibilidade",
    "restricoes": "Restrições", "matricula": "Matrícula", "email": "E-mail", "areas_competencia": "Áreas de competência",
    "carga_horaria_contratual": "Carga contratual (h/sem)", "limite_ch_letiva": "Limite letivo (h/sem)", "max_horas_dia": "Máx. horas/dia",
    "intervalo_minimo_h": "Descanso entre jornadas (h)", "restricoes_deslocamento": "Restrições de deslocamento", "nivel": "Nível de habilitação",
    "condicoes": "Condições", "valido_ate": "Válido até", "alvo_tipo": "Tipo de alvo", "alvo_id": "ID do alvo", "inicio": "Início", "fim": "Fim",
    "motivo": "Motivo", "tipo": "Tipo", "data": "Data", "versao": "Versão", "vigencia_inicio": "Início da vigência", "modalidade": "Modalidade",
    "eixo_tecnologico": "Eixo tecnológico", "turnos_possiveis": "Turnos possíveis", "minutos": "Minutos", "ordem": "Ordem", "especializado": "Especializado",
    "recurso_tipo": "Tipo de recurso", "quantidade": "Quantidade", "cidade": "Cidade", "modulo": "Módulo",
}
REFS = {"curso_id": "Curso", "matriz_id": "Matriz", "unidade_id": "Unidade", "calendario_id": "Calendário", "turno_id": "Turno", "turma_id": "Turma",
        "uc_id": "Unidade curricular", "instrutor_id": "Instrutor", "ambiente_id": "Ambiente", "recurso_id": "Recurso", "tipo_ambiente_id": "Tipo de ambiente",
        "prerequisito_id": "Pré-requisito", "origem_id": "Unidade de origem", "destino_id": "Unidade de destino", "matriz_origem_id": "Matriz de origem",
        "instrutor_preferido_id": "Instrutor preferido", "turno_preferencial_id": "Turno preferencial"}


def tipo_coluna(col) -> str:
    t = col.type
    if isinstance(t, Boolean):
        return "bool"
    if isinstance(t, (Integer,)):
        return "int"
    if isinstance(t, (Numeric, Float)):
        return "number"
    if isinstance(t, DateTime):
        return "datetime"
    if isinstance(t, Date):
        return "date"
    if isinstance(t, Time):
        return "time"
    if isinstance(t, ARRAY):
        return "int_array"
    if isinstance(t, Text):
        return "text"
    if isinstance(t, String):
        return "string"
    return "json"


def campos(chave: str) -> list[dict]:
    cfg = ENTIDADES[chave]
    res = []
    for col in cfg["model"].__table__.columns:
        if col.key in cfg.get("ocultar", []):
            continue
        f = {"nome": col.key, "tipo": tipo_coluna(col), "obrigatorio": not col.nullable and col.default is None and col.server_default is None
             and col.key not in SOMENTE_LEITURA and not (col.primary_key and col.key == "id"),
             "somente_leitura": col.key in SOMENTE_LEITURA,
             "rotulo": ROTULOS.get(col.key) or REFS.get(col.key) or col.key.replace("_", " ").capitalize()}
        fks = list(col.foreign_keys)
        if fks:
            f["tipo"] = "ref"
            f["ref"] = TABELA_ENTIDADE.get(fks[0].column.table.name)
        if col.key in cfg.get("opcoes", {}):
            f["tipo"] = "enum"
            f["opcoes"] = cfg["opcoes"][col.key]
        if col.key in cfg.get("dias", []):
            f["tipo"] = "dias"
            f["opcoes"] = DIAS_OPCOES
        if col.key in cfg.get("dia", []):
            f["tipo"] = "dia"
            f["opcoes"] = DIAS_OPCOES
        if col.key in cfg.get("pessoais", []):
            f["pessoal"] = True
        res.append(f)
    for nome, extra in cfg.get("extras", {}).items():
        res.append({"nome": nome, **extra, "obrigatorio": False, "somente_leitura": False})
    return res
