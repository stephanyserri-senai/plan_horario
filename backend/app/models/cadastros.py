"""Cadastros e dados mestres.

Convenções:
- Tabelas em português, snake_case, no plural.
- `ativo` controla a inativação lógica (registros nunca são apagados fisicamente
  pelos cadastros, para preservar o histórico e as referências).
- Dias da semana: 0 = segunda ... 6 = domingo (ISO - 1).
"""
from datetime import date, datetime, time

from sqlalchemy import (
    ARRAY,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    Time,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class TimestampMixin:
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    atualizado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


# --------------------------------------------------------------------------- Unidades
class Unidade(TimestampMixin, Base):
    __tablename__ = "unidades"
    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(String(30), unique=True)
    nome: Mapped[str] = mapped_column(String(200))
    endereco: Mapped[str | None] = mapped_column(String(300))
    cidade: Mapped[str | None] = mapped_column(String(120))
    responsavel: Mapped[str | None] = mapped_column(String(200))
    regras_operacionais: Mapped[str | None] = mapped_column(Text)
    situacao: Mapped[str] = mapped_column(String(20), default="ativa")
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)


class Area(TimestampMixin, Base):
    """Área tecnológica de uma unidade (cadastro fixo da instituição)."""
    __tablename__ = "areas"
    id: Mapped[int] = mapped_column(primary_key=True)
    unidade_id: Mapped[int] = mapped_column(ForeignKey("unidades.id"), index=True)
    codigo: Mapped[str] = mapped_column(String(40), unique=True)
    nome: Mapped[str] = mapped_column(String(100))
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)


class Setor(TimestampMixin, Base):
    __tablename__ = "setores"
    id: Mapped[int] = mapped_column(primary_key=True)
    unidade_id: Mapped[int] = mapped_column(ForeignKey("unidades.id"), index=True)
    nome: Mapped[str] = mapped_column(String(200))
    responsavel: Mapped[str | None] = mapped_column(String(200))
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)


class DeslocamentoUnidade(Base):
    """Tempo mínimo de deslocamento de instrutores entre duas unidades."""
    __tablename__ = "deslocamentos_unidades"
    __table_args__ = (UniqueConstraint("origem_id", "destino_id"), CheckConstraint("minutos >= 0"))
    id: Mapped[int] = mapped_column(primary_key=True)
    origem_id: Mapped[int] = mapped_column(ForeignKey("unidades.id"))
    destino_id: Mapped[int] = mapped_column(ForeignKey("unidades.id"))
    minutos: Mapped[int] = mapped_column(Integer)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)


# --------------------------------------------------------------------------- Calendário
class Turno(TimestampMixin, Base):
    __tablename__ = "turnos"
    __table_args__ = (UniqueConstraint("unidade_id", "codigo"), CheckConstraint("hora_fim > hora_inicio"))
    id: Mapped[int] = mapped_column(primary_key=True)
    unidade_id: Mapped[int] = mapped_column(ForeignKey("unidades.id"), index=True)
    codigo: Mapped[str] = mapped_column(String(30))
    nome: Mapped[str] = mapped_column(String(100))
    hora_inicio: Mapped[time] = mapped_column(Time)
    hora_fim: Mapped[time] = mapped_column(Time)
    ordem: Mapped[int] = mapped_column(Integer, default=0)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)


class PeriodoHorario(TimestampMixin, Base):
    """Bloco elementar de aula de um turno (ex.: 1º horário 07:30–08:20)."""
    __tablename__ = "periodos_horarios"
    __table_args__ = (UniqueConstraint("turno_id", "ordem"), CheckConstraint("hora_fim > hora_inicio"))
    id: Mapped[int] = mapped_column(primary_key=True)
    unidade_id: Mapped[int] = mapped_column(ForeignKey("unidades.id"), index=True)
    turno_id: Mapped[int] = mapped_column(ForeignKey("turnos.id"), index=True)
    ordem: Mapped[int] = mapped_column(Integer)
    hora_inicio: Mapped[time] = mapped_column(Time)
    hora_fim: Mapped[time] = mapped_column(Time)
    # Dias em que o período existe (permite horários especiais, ex.: sábado).
    dias_semana: Mapped[list[int]] = mapped_column(ARRAY(Integer), default=lambda: [0, 1, 2, 3, 4])
    excepcional: Mapped[bool] = mapped_column(Boolean, default=False)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)


class Calendario(TimestampMixin, Base):
    __tablename__ = "calendarios"
    __table_args__ = (CheckConstraint("data_fim >= data_inicio"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    unidade_id: Mapped[int | None] = mapped_column(ForeignKey("unidades.id"), index=True)
    nome: Mapped[str] = mapped_column(String(200))
    data_inicio: Mapped[date] = mapped_column(Date)
    data_fim: Mapped[date] = mapped_column(Date)
    dias_letivos: Mapped[list[int]] = mapped_column(ARRAY(Integer), default=lambda: [0, 1, 2, 3, 4])
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)


class CalendarioExcecao(TimestampMixin, Base):
    """Feriados, recessos, dias letivos extras e horários especiais."""
    __tablename__ = "calendario_excecoes"
    __table_args__ = (
        CheckConstraint("tipo in ('feriado','recesso','dia_letivo_extra','horario_especial')"),
        UniqueConstraint("calendario_id", "data", "tipo"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    calendario_id: Mapped[int] = mapped_column(ForeignKey("calendarios.id"), index=True)
    data: Mapped[date] = mapped_column(Date, index=True)
    tipo: Mapped[str] = mapped_column(String(30))
    descricao: Mapped[str | None] = mapped_column(String(300))
    hora_inicio: Mapped[time | None] = mapped_column(Time)
    hora_fim: Mapped[time | None] = mapped_column(Time)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)


class HorarioFuncionamento(Base):
    __tablename__ = "horarios_funcionamento"
    __table_args__ = (CheckConstraint("dia_semana between 0 and 6"), CheckConstraint("hora_fim > hora_inicio"))
    id: Mapped[int] = mapped_column(primary_key=True)
    unidade_id: Mapped[int] = mapped_column(ForeignKey("unidades.id"), index=True)
    dia_semana: Mapped[int] = mapped_column(Integer)
    hora_inicio: Mapped[time] = mapped_column(Time)
    hora_fim: Mapped[time] = mapped_column(Time)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)


class Bloqueio(TimestampMixin, Base):
    """Indisponibilidade temporária de um recurso (instrutor, ambiente, turma,
    unidade ou recurso compartilhado): manutenção, afastamento, atividade
    administrativa, evento etc."""
    __tablename__ = "bloqueios"
    __table_args__ = (
        CheckConstraint("alvo_tipo in ('instrutor','ambiente','turma','unidade','recurso')"),
        CheckConstraint("fim > inicio"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    alvo_tipo: Mapped[str] = mapped_column(String(20), index=True)
    alvo_id: Mapped[int] = mapped_column(Integer, index=True)
    inicio: Mapped[datetime] = mapped_column(DateTime)
    fim: Mapped[datetime] = mapped_column(DateTime)
    tipo: Mapped[str] = mapped_column(String(40), default="indisponibilidade")
    motivo: Mapped[str | None] = mapped_column(String(300))
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)


# --------------------------------------------------------------------------- Cursos e UCs
class Curso(TimestampMixin, Base):
    __tablename__ = "cursos"
    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(String(30), unique=True)
    nome: Mapped[str] = mapped_column(String(200))
    modalidade: Mapped[str | None] = mapped_column(String(60))
    tipo: Mapped[str | None] = mapped_column(String(60))
    carga_horaria_total: Mapped[int | None] = mapped_column(Integer)
    eixo_tecnologico: Mapped[str | None] = mapped_column(String(120))
    unidade_id: Mapped[int | None] = mapped_column(ForeignKey("unidades.id"), index=True)
    area_id: Mapped[int | None] = mapped_column(ForeignKey("areas.id"), index=True)
    turnos_possiveis: Mapped[str | None] = mapped_column(String(200))
    situacao: Mapped[str] = mapped_column(String(20), default="ativo")
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)


class MatrizCurricular(TimestampMixin, Base):
    """Uma versão de matriz é imutável depois de utilizada por uma turma; novas
    alterações exigem uma nova versão (ver services/cadastros.py)."""
    __tablename__ = "matrizes_curriculares"
    __table_args__ = (UniqueConstraint("curso_id", "versao"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    curso_id: Mapped[int] = mapped_column(ForeignKey("cursos.id"), index=True)
    versao: Mapped[str] = mapped_column(String(30))
    vigencia_inicio: Mapped[date | None] = mapped_column(Date)
    situacao: Mapped[str] = mapped_column(String(20), default="rascunho")  # rascunho|vigente|encerrada
    matriz_origem_id: Mapped[int | None] = mapped_column(ForeignKey("matrizes_curriculares.id"))
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)


class TipoAmbiente(TimestampMixin, Base):
    __tablename__ = "tipos_ambiente"
    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(String(30), unique=True)
    nome: Mapped[str] = mapped_column(String(120))
    especializado: Mapped[bool] = mapped_column(Boolean, default=False)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)


class UnidadeCurricular(TimestampMixin, Base):
    __tablename__ = "unidades_curriculares"
    __table_args__ = (
        UniqueConstraint("matriz_id", "codigo"),
        CheckConstraint("carga_horaria_total > 0"),
        CheckConstraint("duracao_bloco_periodos >= 1"),
        CheckConstraint("encontros_semanais >= 1"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    matriz_id: Mapped[int] = mapped_column(ForeignKey("matrizes_curriculares.id"), index=True)
    codigo: Mapped[str] = mapped_column(String(30))
    nome: Mapped[str] = mapped_column(String(200))
    carga_horaria_total: Mapped[int] = mapped_column(Integer)
    ch_teorica: Mapped[int | None] = mapped_column(Integer)
    ch_pratica: Mapped[int | None] = mapped_column(Integer)
    ch_semanal_desejada: Mapped[float | None] = mapped_column(Numeric(6, 2))
    duracao_bloco_periodos: Mapped[int] = mapped_column(Integer, default=2)
    encontros_semanais: Mapped[int] = mapped_column(Integer, default=2)
    sequencia: Mapped[int] = mapped_column(Integer, default=1)
    modulo: Mapped[str | None] = mapped_column(String(60))
    competencias: Mapped[str | None] = mapped_column(Text)
    certificacao_exigida: Mapped[str | None] = mapped_column(String(200))
    capacidade_min: Mapped[int | None] = mapped_column(Integer)
    capacidade_max: Mapped[int | None] = mapped_column(Integer)
    divide_grupos: Mapped[bool] = mapped_column(Boolean, default=False)
    aulas_consecutivas: Mapped[bool] = mapped_column(Boolean, default=True)
    restricoes_pedagogicas: Mapped[str | None] = mapped_column(Text)
    prioridade: Mapped[int] = mapped_column(Integer, default=3)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)

    tipos_ambiente: Mapped[list["TipoAmbiente"]] = relationship(secondary="uc_tipos_ambiente", lazy="selectin")


class UCTipoAmbiente(Base):
    __tablename__ = "uc_tipos_ambiente"
    uc_id: Mapped[int] = mapped_column(ForeignKey("unidades_curriculares.id", ondelete="CASCADE"), primary_key=True)
    tipo_ambiente_id: Mapped[int] = mapped_column(ForeignKey("tipos_ambiente.id"), primary_key=True)


class UCPrerequisito(Base):
    __tablename__ = "uc_prerequisitos"
    __table_args__ = (CheckConstraint("uc_id <> prerequisito_id"),)
    uc_id: Mapped[int] = mapped_column(ForeignKey("unidades_curriculares.id", ondelete="CASCADE"), primary_key=True)
    prerequisito_id: Mapped[int] = mapped_column(ForeignKey("unidades_curriculares.id"), primary_key=True)


class UCRecurso(Base):
    """Equipamentos obrigatórios para realizar a UC."""
    __tablename__ = "uc_recursos"
    __table_args__ = (CheckConstraint("quantidade > 0"),)
    uc_id: Mapped[int] = mapped_column(ForeignKey("unidades_curriculares.id", ondelete="CASCADE"), primary_key=True)
    recurso_tipo: Mapped[str] = mapped_column(String(60), primary_key=True)
    quantidade: Mapped[int] = mapped_column(Integer, default=1)


# --------------------------------------------------------------------------- Ambientes e recursos
class Ambiente(TimestampMixin, Base):
    __tablename__ = "ambientes"
    __table_args__ = (
        CheckConstraint("capacidade_fisica > 0"),
        CheckConstraint("capacidade_operacional > 0 and capacidade_operacional <= capacidade_fisica"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(String(30), unique=True)
    nome: Mapped[str] = mapped_column(String(200))
    unidade_id: Mapped[int] = mapped_column(ForeignKey("unidades.id"), index=True)
    area_id: Mapped[int | None] = mapped_column(ForeignKey("areas.id"), index=True)
    todas_areas: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))  # atende qualquer área
    predio: Mapped[str | None] = mapped_column(String(100))
    localizacao: Mapped[str | None] = mapped_column(String(200))
    tipo_ambiente_id: Mapped[int] = mapped_column(ForeignKey("tipos_ambiente.id"), index=True)
    capacidade_fisica: Mapped[int] = mapped_column(Integer)
    capacidade_operacional: Mapped[int] = mapped_column(Integer)
    maquinas: Mapped[str | None] = mapped_column(Text)
    requisitos_seguranca: Mapped[str | None] = mapped_column(Text)
    acessivel: Mapped[bool] = mapped_column(Boolean, default=True)
    tempo_preparacao_min: Mapped[int] = mapped_column(Integer, default=0)
    situacao: Mapped[str] = mapped_column(String(20), default="operacional")  # operacional|manutencao|interditado
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)


class DisponibilidadeAmbiente(Base):
    """Janelas semanais do ambiente. Sem registros, vale o funcionamento da unidade."""
    __tablename__ = "disponibilidade_ambientes"
    __table_args__ = (CheckConstraint("dia_semana between 0 and 6"), CheckConstraint("hora_fim > hora_inicio"))
    id: Mapped[int] = mapped_column(primary_key=True)
    ambiente_id: Mapped[int] = mapped_column(ForeignKey("ambientes.id", ondelete="CASCADE"), index=True)
    dia_semana: Mapped[int] = mapped_column(Integer)
    hora_inicio: Mapped[time] = mapped_column(Time)
    hora_fim: Mapped[time] = mapped_column(Time)


class Recurso(TimestampMixin, Base):
    """Equipamento ou recurso compartilhado.

    `tipo` agrupa itens intercambiáveis (ex.: 'kit_clp'). Recursos fixos estão
    instalados em um ambiente (recursos_ambientes); recursos móveis formam um
    acervo da unidade e são reservados por aula (alocacao_recursos), limitados
    pela quantidade total em uso simultâneo.
    """
    __tablename__ = "recursos"
    __table_args__ = (CheckConstraint("quantidade_total >= 0"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(String(30), unique=True)
    nome: Mapped[str] = mapped_column(String(200))
    tipo: Mapped[str] = mapped_column(String(60), index=True)
    unidade_id: Mapped[int] = mapped_column(ForeignKey("unidades.id"), index=True)
    quantidade_total: Mapped[int] = mapped_column(Integer, default=1)
    movel: Mapped[bool] = mapped_column(Boolean, default=False)
    requer_reserva: Mapped[bool] = mapped_column(Boolean, default=True)
    situacao: Mapped[str] = mapped_column(String(20), default="disponivel")
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)


class RecursoAmbiente(Base):
    __tablename__ = "recursos_ambientes"
    __table_args__ = (UniqueConstraint("recurso_id", "ambiente_id"), CheckConstraint("quantidade > 0"))
    id: Mapped[int] = mapped_column(primary_key=True)
    recurso_id: Mapped[int] = mapped_column(ForeignKey("recursos.id", ondelete="CASCADE"), index=True)
    ambiente_id: Mapped[int] = mapped_column(ForeignKey("ambientes.id", ondelete="CASCADE"), index=True)
    quantidade: Mapped[int] = mapped_column(Integer, default=1)


# --------------------------------------------------------------------------- Turmas
class Turma(TimestampMixin, Base):
    __tablename__ = "turmas"
    __table_args__ = (
        CheckConstraint("data_fim >= data_inicio"),
        CheckConstraint("qtd_alunos >= 0"),
        CheckConstraint("num_grupos between 1 and 16"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(String(40), unique=True)
    nome: Mapped[str] = mapped_column(String(200))
    curso_id: Mapped[int] = mapped_column(ForeignKey("cursos.id"), index=True)
    matriz_id: Mapped[int] = mapped_column(ForeignKey("matrizes_curriculares.id"), index=True)
    unidade_id: Mapped[int] = mapped_column(ForeignKey("unidades.id"), index=True)
    area_id: Mapped[int | None] = mapped_column(ForeignKey("areas.id"), index=True)
    calendario_id: Mapped[int | None] = mapped_column(ForeignKey("calendarios.id"))
    turno_id: Mapped[int | None] = mapped_column(ForeignKey("turnos.id"))
    qtd_alunos: Mapped[int] = mapped_column(Integer, default=0)
    capacidade_prevista: Mapped[int | None] = mapped_column(Integer)
    data_inicio: Mapped[date] = mapped_column(Date)
    data_fim: Mapped[date] = mapped_column(Date)
    dias_possiveis: Mapped[list[int]] = mapped_column(ARRAY(Integer), default=lambda: [0, 1, 2, 3, 4])
    num_grupos: Mapped[int] = mapped_column(Integer, default=1)
    prioridade: Mapped[int] = mapped_column(Integer, default=3)
    necessidades_acessibilidade: Mapped[bool] = mapped_column(Boolean, default=False)
    restricoes: Mapped[str | None] = mapped_column(Text)
    situacao: Mapped[str] = mapped_column(String(20), default="planejada")
    # Turmas criadas pelo simulador ficam isoladas da operação real.
    simulacao_id: Mapped[int | None] = mapped_column(ForeignKey("simulacoes_capacidade.id", ondelete="CASCADE"), index=True)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)


class TurmaUC(TimestampMixin, Base):
    """Oferta curricular: combinação turma × UC, com controle de carga horária."""
    __tablename__ = "turma_uc"
    __table_args__ = (
        UniqueConstraint("turma_id", "uc_id"),
        CheckConstraint("situacao in ('prevista','ofertada','em_execucao','concluida','pendente','cancelada')"),
        CheckConstraint("ch_realizada >= 0"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    turma_id: Mapped[int] = mapped_column(ForeignKey("turmas.id", ondelete="CASCADE"), index=True)
    uc_id: Mapped[int] = mapped_column(ForeignKey("unidades_curriculares.id"), index=True)
    situacao: Mapped[str] = mapped_column(String(20), default="prevista")
    data_inicio: Mapped[date | None] = mapped_column(Date)
    data_limite: Mapped[date | None] = mapped_column(Date)
    ch_realizada: Mapped[float] = mapped_column(Numeric(7, 2), default=0)
    instrutor_preferido_id: Mapped[int | None] = mapped_column(ForeignKey("instrutores.id"))
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)


# --------------------------------------------------------------------------- Instrutores
class Instrutor(TimestampMixin, Base):
    __tablename__ = "instrutores"
    __table_args__ = (CheckConstraint("limite_ch_letiva <= carga_horaria_contratual"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    matricula: Mapped[str] = mapped_column(String(40), unique=True)
    nome: Mapped[str] = mapped_column(String(200))
    email: Mapped[str | None] = mapped_column(String(200))  # dado pessoal: visível só a perfis autorizados
    unidade_id: Mapped[int] = mapped_column(ForeignKey("unidades.id"), index=True)
    area_id: Mapped[int | None] = mapped_column(ForeignKey("areas.id"), index=True)
    todas_areas: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))  # atende qualquer área
    areas_competencia: Mapped[str | None] = mapped_column(Text)
    carga_horaria_contratual: Mapped[float] = mapped_column(Numeric(5, 2), default=40)
    limite_ch_letiva: Mapped[float] = mapped_column(Numeric(5, 2), default=30)
    max_horas_dia: Mapped[float] = mapped_column(Numeric(4, 2), default=8)
    intervalo_minimo_h: Mapped[float] = mapped_column(Numeric(4, 2), default=11)  # descanso entre jornadas
    turno_preferencial_id: Mapped[int | None] = mapped_column(ForeignKey("turnos.id"))
    restricoes_deslocamento: Mapped[str | None] = mapped_column(Text)
    situacao: Mapped[str] = mapped_column(String(20), default="ativo")
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)
    # última vez que o próprio instrutor atualizou os dados pelo portal
    atualizado_pelo_instrutor_em: Mapped[datetime | None] = mapped_column(DateTime)


class InstrutorUnidade(Base):
    """Unidades em que o instrutor pode atuar (além da unidade de vínculo)."""
    __tablename__ = "instrutor_unidades"
    instrutor_id: Mapped[int] = mapped_column(ForeignKey("instrutores.id", ondelete="CASCADE"), primary_key=True)
    unidade_id: Mapped[int] = mapped_column(ForeignKey("unidades.id"), primary_key=True)


class CompetenciaInstrutor(TimestampMixin, Base):
    """Matriz de competências instrutor × UC."""
    __tablename__ = "competencias_instrutores"
    __table_args__ = (
        UniqueConstraint("instrutor_id", "uc_id"),
        CheckConstraint("nivel in ('pleno','supervisionado','em_formacao')"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    instrutor_id: Mapped[int] = mapped_column(ForeignKey("instrutores.id", ondelete="CASCADE"), index=True)
    uc_id: Mapped[int] = mapped_column(ForeignKey("unidades_curriculares.id"), index=True)
    nivel: Mapped[str] = mapped_column(String(20), default="pleno")
    condicoes: Mapped[str | None] = mapped_column(Text)
    valido_ate: Mapped[date | None] = mapped_column(Date)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)


class HabilitacaoInstrutor(TimestampMixin, Base):
    """Certificações/habilitações (ex.: NR-10) exigidas por algumas UCs."""
    __tablename__ = "habilitacoes_instrutores"
    __table_args__ = (UniqueConstraint("instrutor_id", "nome"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    instrutor_id: Mapped[int] = mapped_column(ForeignKey("instrutores.id", ondelete="CASCADE"), index=True)
    nome: Mapped[str] = mapped_column(String(200))
    valido_ate: Mapped[date | None] = mapped_column(Date)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)


class DisponibilidadeInstrutor(Base):
    """Janelas semanais de disponibilidade para aulas. Sem registros, o instrutor
    é considerado indisponível (regra estrita, gera alerta de cadastro)."""
    __tablename__ = "disponibilidade_instrutores"
    __table_args__ = (CheckConstraint("dia_semana between 0 and 6"), CheckConstraint("hora_fim > hora_inicio"))
    id: Mapped[int] = mapped_column(primary_key=True)
    instrutor_id: Mapped[int] = mapped_column(ForeignKey("instrutores.id", ondelete="CASCADE"), index=True)
    dia_semana: Mapped[int] = mapped_column(Integer)
    hora_inicio: Mapped[time] = mapped_column(Time)
    hora_fim: Mapped[time] = mapped_column(Time)
    unidade_id: Mapped[int | None] = mapped_column(ForeignKey("unidades.id"))


class Configuracao(Base):
    """Parâmetros do sistema editáveis sem alterar código."""
    __tablename__ = "configuracoes"
    chave: Mapped[str] = mapped_column(String(80), primary_key=True)
    valor: Mapped[dict] = mapped_column(JSONB)
    descricao: Mapped[str | None] = mapped_column(Text)
    atualizado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class InstrutorArea(Base):
    """Outras áreas (além da principal) em que o instrutor também atua."""
    __tablename__ = "instrutor_areas"
    instrutor_id: Mapped[int] = mapped_column(ForeignKey("instrutores.id", ondelete="CASCADE"), primary_key=True)
    area_id: Mapped[int] = mapped_column(ForeignKey("areas.id"), primary_key=True)


class AmbienteArea(Base):
    """Outras áreas (além da principal) que podem usar o ambiente."""
    __tablename__ = "ambiente_areas"
    ambiente_id: Mapped[int] = mapped_column(ForeignKey("ambientes.id", ondelete="CASCADE"), primary_key=True)
    area_id: Mapped[int] = mapped_column(ForeignKey("areas.id"), primary_key=True)
