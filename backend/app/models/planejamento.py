"""Planejamento: cenários, atividades recorrentes, alocações (aulas datadas),
otimização, simulação, validação, auditoria e registros para aprendizado."""
from datetime import date, datetime

from sqlalchemy import (
    ARRAY,
    Boolean,
    CheckConstraint,
    Column,
    Computed,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    LargeBinary,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, TSRANGE, ExcludeConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base

ESTADOS_CENARIO = (
    "em_elaboracao",
    "em_otimizacao",
    "em_validacao",
    "aguardando_aprovacao",
    "aprovado",
    "publicado",
    "arquivado",
)

# Todos os grupos de uma turma (máx. 16). Uma aula com a turma inteira ocupa
# todos os grupos; a aula de um grupo k ocupa apenas {k}. A sobreposição de
# arrays (&&) na exclusion constraint implementa a regra de divisão em grupos.
TODOS_GRUPOS = list(range(1, 17))


class CenarioPlanejamento(Base):
    __tablename__ = "cenarios_planejamento"
    __table_args__ = (
        CheckConstraint("estado in ('" + "','".join(ESTADOS_CENARIO) + "')"),
        CheckConstraint("tipo in ('planejamento','proposta','simulacao')"),
        Index(
            "uq_um_publicado_por_unidade",
            text("coalesce(unidade_id, 0)"),
            unique=True,
            postgresql_where=text("estado = 'publicado'"),
        ),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(200))
    descricao: Mapped[str | None] = mapped_column(Text)
    unidade_id: Mapped[int | None] = mapped_column(ForeignKey("unidades.id"), index=True)
    tipo: Mapped[str] = mapped_column(String(20), default="planejamento")
    estado: Mapped[str] = mapped_column(String(30), default="em_elaboracao")
    versao: Mapped[int] = mapped_column(Integer, default=1)
    cenario_origem_id: Mapped[int | None] = mapped_column(ForeignKey("cenarios_planejamento.id"))
    periodo_inicio: Mapped[date | None] = mapped_column(Date)
    periodo_fim: Mapped[date | None] = mapped_column(Date)
    autor_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    aprovado_por_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    publicado_em: Mapped[datetime | None] = mapped_column(DateTime)
    parametros: Mapped[dict | None] = mapped_column(JSONB)
    indicadores: Mapped[dict | None] = mapped_column(JSONB)
    resultado_validacao: Mapped[dict | None] = mapped_column(JSONB)
    # Controle otimista de concorrência sobre o cenário como um todo.
    lock_version: Mapped[int] = mapped_column(Integer, default=1)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    atualizado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class VersaoPlanejamento(Base):
    """Fotografia imutável das alocações de um cenário (para comparar/restaurar)."""
    __tablename__ = "versoes_planejamento"
    __table_args__ = (UniqueConstraint("cenario_id", "numero"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    cenario_id: Mapped[int] = mapped_column(ForeignKey("cenarios_planejamento.id", ondelete="CASCADE"), index=True)
    numero: Mapped[int] = mapped_column(Integer)
    estado: Mapped[str] = mapped_column(String(30))
    motivo: Mapped[str | None] = mapped_column(Text)
    snapshot: Mapped[list] = mapped_column(JSONB)
    indicadores: Mapped[dict | None] = mapped_column(JSONB)
    autor_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class ExcecaoAutorizada(Base):
    """Autorização documentada para uma exceção (aula em feriado, carga
    horária excedente etc.). Uma alocação só pode usar a exceção do tipo certo."""
    __tablename__ = "excecoes_autorizadas"
    __table_args__ = (CheckConstraint("tipo in ('feriado_bloqueio','carga_horaria','regra_academica','reposicao')", name="excecoes_autorizadas_tipo_check"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    tipo: Mapped[str] = mapped_column(String(30))
    justificativa: Mapped[str] = mapped_column(Text)
    autorizado_por_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"))
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Atividade(Base):
    """Padrão semanal recorrente (turma × UC × grupo em um dia/horário)."""
    __tablename__ = "atividades"
    __table_args__ = (CheckConstraint("dia_semana between 0 and 6"), CheckConstraint("num_periodos >= 1"))
    id: Mapped[int] = mapped_column(primary_key=True)
    cenario_id: Mapped[int] = mapped_column(ForeignKey("cenarios_planejamento.id", ondelete="CASCADE"), index=True)
    turma_uc_id: Mapped[int] = mapped_column(ForeignKey("turma_uc.id", ondelete="CASCADE"), index=True)
    grupo: Mapped[int | None] = mapped_column(Integer)
    instrutor_id: Mapped[int | None] = mapped_column(ForeignKey("instrutores.id"))
    ambiente_id: Mapped[int | None] = mapped_column(ForeignKey("ambientes.id"))
    dia_semana: Mapped[int] = mapped_column(Integer)
    periodo_inicio_id: Mapped[int] = mapped_column(ForeignKey("periodos_horarios.id"))
    num_periodos: Mapped[int] = mapped_column(Integer)
    data_inicio: Mapped[date] = mapped_column(Date)
    data_fim: Mapped[date] = mapped_column(Date)
    fixa: Mapped[bool] = mapped_column(Boolean, default=False)
    origem: Mapped[str] = mapped_column(String(20), default="manual")
    execucao_id: Mapped[int | None] = mapped_column(ForeignKey("execucoes_otimizacao.id", ondelete="SET NULL"))
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Alocacao(Base):
    """Aula datada. A integridade contra sobreposições é garantida pelo banco
    via exclusion constraints (GiST) — inclusive sob concorrência."""
    __tablename__ = "alocacoes"
    __table_args__ = (
        CheckConstraint("fim > inicio"),
        CheckConstraint("fim_ambiente >= fim"),
        CheckConstraint("status in ('programada','realizada','cancelada')"),
        CheckConstraint("minutos_aula > 0"),
        ExcludeConstraint(
            (Column("cenario_id"), "="),
            (Column("instrutor_id"), "="),
            (Column("intervalo"), "&&"),
            name="excl_alocacao_instrutor",
            using="gist",
            where=text("status <> 'cancelada' AND instrutor_id IS NOT NULL"),
        ),
        ExcludeConstraint(
            (Column("cenario_id"), "="),
            (Column("ambiente_id"), "="),
            (Column("intervalo_ambiente"), "&&"),
            name="excl_alocacao_ambiente",
            using="gist",
            where=text("status <> 'cancelada' AND ambiente_id IS NOT NULL"),
        ),
        ExcludeConstraint(
            (Column("cenario_id"), "="),
            (Column("turma_id"), "="),
            (Column("grupos"), "&&"),
            (Column("intervalo"), "&&"),
            name="excl_alocacao_turma_grupos",
            using="gist",
            where=text("status <> 'cancelada'"),
            ops={"grupos": "gist__int_ops"},
        ),
        Index("ix_alocacoes_cenario_data", "cenario_id", "data"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    cenario_id: Mapped[int] = mapped_column(ForeignKey("cenarios_planejamento.id", ondelete="CASCADE"), index=True)
    atividade_id: Mapped[int | None] = mapped_column(ForeignKey("atividades.id", ondelete="SET NULL"), index=True)
    turma_uc_id: Mapped[int] = mapped_column(ForeignKey("turma_uc.id", ondelete="CASCADE"), index=True)
    turma_id: Mapped[int] = mapped_column(ForeignKey("turmas.id", ondelete="CASCADE"), index=True)
    uc_id: Mapped[int] = mapped_column(ForeignKey("unidades_curriculares.id"), index=True)
    grupo: Mapped[int | None] = mapped_column(Integer)
    grupos: Mapped[list[int]] = mapped_column(ARRAY(Integer))
    instrutor_id: Mapped[int | None] = mapped_column(ForeignKey("instrutores.id"), index=True)
    # substituição: instrutor titular original (o substituto fica em instrutor_id)
    instrutor_titular_id: Mapped[int | None] = mapped_column(ForeignKey("instrutores.id", ondelete="SET NULL"))
    ambiente_id: Mapped[int | None] = mapped_column(ForeignKey("ambientes.id"), index=True)
    data: Mapped[date] = mapped_column(Date)
    inicio: Mapped[datetime] = mapped_column(DateTime)
    fim: Mapped[datetime] = mapped_column(DateTime)
    # fim + tempo de preparação do ambiente (setup entre atividades)
    fim_ambiente: Mapped[datetime] = mapped_column(DateTime)
    minutos_aula: Mapped[int] = mapped_column(Integer)
    intervalo = mapped_column(TSRANGE, Computed("tsrange(inicio, fim, '[)')", persisted=True))
    intervalo_ambiente = mapped_column(TSRANGE, Computed("tsrange(inicio, fim_ambiente, '[)')", persisted=True))
    status: Mapped[str] = mapped_column(String(20), default="programada")
    fixa: Mapped[bool] = mapped_column(Boolean, default=False)
    origem: Mapped[str] = mapped_column(String(20), default="manual")
    observacao: Mapped[str | None] = mapped_column(Text)
    excecao_id: Mapped[int | None] = mapped_column(ForeignKey("excecoes_autorizadas.id"))
    versao: Mapped[int] = mapped_column(Integer, default=1)
    criado_por_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    atualizado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class AlocacaoRecurso(Base):
    """Reserva de recurso móvel/compartilhado para uma aula."""
    __tablename__ = "alocacao_recursos"
    __table_args__ = (CheckConstraint("quantidade > 0"),)
    alocacao_id: Mapped[int] = mapped_column(ForeignKey("alocacoes.id", ondelete="CASCADE"), primary_key=True)
    recurso_id: Mapped[int] = mapped_column(ForeignKey("recursos.id"), primary_key=True)
    quantidade: Mapped[int] = mapped_column(Integer, default=1)


class ParametrosOtimizacao(Base):
    """Conjunto nomeado de pesos. Cada execução guarda uma cópia imutável."""
    __tablename__ = "parametros_otimizacao"
    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(120), unique=True)
    pesos: Mapped[dict] = mapped_column(JSONB)
    limite_tempo_s: Mapped[int] = mapped_column(Integer, default=30)
    padrao: Mapped[bool] = mapped_column(Boolean, default=False)
    versao: Mapped[int] = mapped_column(Integer, default=1)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)
    atualizado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class ExecucaoOtimizacao(Base):
    __tablename__ = "execucoes_otimizacao"
    __table_args__ = (
        CheckConstraint("status in ('pendente','executando','concluida','falha','cancelada')"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    cenario_id: Mapped[int] = mapped_column(ForeignKey("cenarios_planejamento.id", ondelete="CASCADE"), index=True)
    escopo: Mapped[dict] = mapped_column(JSONB)
    parametros: Mapped[dict] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(20), default="pendente")
    # OTIMA | VIAVEL | SEM_SOLUCAO_NO_LIMITE | INVIAVEL | MODELO_INVALIDO | SEM_DEMANDA
    status_solver: Mapped[str | None] = mapped_column(String(30))
    motivo_termino: Mapped[str | None] = mapped_column(Text)
    objetivo: Mapped[float | None] = mapped_column(Float)
    limite_inferior: Mapped[float | None] = mapped_column(Float)
    tempo_s: Mapped[float | None] = mapped_column(Float)
    diagnosticos: Mapped[list | None] = mapped_column(JSONB)
    resultado: Mapped[dict | None] = mapped_column(JSONB)
    criado_por_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    iniciado_em: Mapped[datetime | None] = mapped_column(DateTime)
    finalizado_em: Mapped[datetime | None] = mapped_column(DateTime)
    # Fila: identificação do worker que processa e último sinal de vida.
    worker: Mapped[str | None] = mapped_column(String(120))
    heartbeat_em: Mapped[datetime | None] = mapped_column(DateTime)


class ResultadoOtimizacao(Base):
    """Pontuação por critério da função objetivo em uma execução."""
    __tablename__ = "resultados_otimizacao"
    id: Mapped[int] = mapped_column(primary_key=True)
    execucao_id: Mapped[int] = mapped_column(ForeignKey("execucoes_otimizacao.id", ondelete="CASCADE"), index=True)
    criterio: Mapped[str] = mapped_column(String(60))
    valor_bruto: Mapped[float] = mapped_column(Float)
    peso: Mapped[float] = mapped_column(Float)
    pontos: Mapped[float] = mapped_column(Float)


class SimulacaoCapacidade(Base):
    __tablename__ = "simulacoes_capacidade"
    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(200))
    tipo: Mapped[str] = mapped_column(String(20), default="agregada")  # agregada|completa
    parametros: Mapped[dict] = mapped_column(JSONB)
    cenario_base_id: Mapped[int | None] = mapped_column(ForeignKey("cenarios_planejamento.id", ondelete="SET NULL"))
    cenario_simulado_id: Mapped[int | None] = mapped_column(ForeignKey("cenarios_planejamento.id", ondelete="SET NULL"))
    status: Mapped[str] = mapped_column(String(20), default="pendente")
    resultado: Mapped[dict | None] = mapped_column(JSONB)
    criado_por_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    iniciado_em: Mapped[datetime | None] = mapped_column(DateTime)
    finalizado_em: Mapped[datetime | None] = mapped_column(DateTime)
    worker: Mapped[str | None] = mapped_column(String(120))
    heartbeat_em: Mapped[datetime | None] = mapped_column(DateTime)


class Validacao(Base):
    __tablename__ = "validacoes"
    id: Mapped[int] = mapped_column(primary_key=True)
    cenario_id: Mapped[int] = mapped_column(ForeignKey("cenarios_planejamento.id", ondelete="CASCADE"), index=True)
    total_bloqueios: Mapped[int] = mapped_column(Integer, default=0)
    total_alertas: Mapped[int] = mapped_column(Integer, default=0)
    total_preferencias: Mapped[int] = mapped_column(Integer, default=0)
    total_recomendacoes: Mapped[int] = mapped_column(Integer, default=0)
    executado_por_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    executado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class OcorrenciaValidacao(Base):
    __tablename__ = "ocorrencias_validacao"
    __table_args__ = (
        CheckConstraint("severidade in ('bloqueio','alerta','preferencia','recomendacao')"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    validacao_id: Mapped[int] = mapped_column(ForeignKey("validacoes.id", ondelete="CASCADE"), index=True)
    severidade: Mapped[str] = mapped_column(String(20))
    regra: Mapped[str] = mapped_column(String(60))
    descricao: Mapped[str] = mapped_column(Text)
    recurso_tipo: Mapped[str | None] = mapped_column(String(20))
    recurso_id: Mapped[int | None] = mapped_column(Integer)
    data: Mapped[date | None] = mapped_column(Date)
    inicio: Mapped[datetime | None] = mapped_column(DateTime)
    fim: Mapped[datetime | None] = mapped_column(DateTime)
    turma_id: Mapped[int | None] = mapped_column(Integer)
    uc_id: Mapped[int | None] = mapped_column(Integer)
    instrutor_id: Mapped[int | None] = mapped_column(Integer)
    ambiente_id: Mapped[int | None] = mapped_column(Integer)
    alocacao_id: Mapped[int | None] = mapped_column(Integer)
    origem: Mapped[str | None] = mapped_column(String(30))


class Importacao(Base):
    __tablename__ = "importacoes"
    id: Mapped[int] = mapped_column(primary_key=True)
    arquivo_nome: Mapped[str] = mapped_column(String(300))
    arquivo_hash: Mapped[str] = mapped_column(String(64), index=True)
    tipo: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(20), default="previa")  # previa|confirmada|descartada|falha
    mapeamento: Mapped[dict | None] = mapped_column(JSONB)
    previa: Mapped[dict | None] = mapped_column(JSONB)
    relatorio: Mapped[dict | None] = mapped_column(JSONB)
    cenario_id: Mapped[int | None] = mapped_column(ForeignKey("cenarios_planejamento.id", ondelete="SET NULL"))
    # Conteúdo do arquivo durante a prévia (persistido: funções serverless não compartilham memória).
    # É descartado (NULL) após confirmar ou descartar a importação.
    conteudo: Mapped[bytes | None] = mapped_column(LargeBinary, deferred=True)
    criado_por_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    confirmado_em: Mapped[datetime | None] = mapped_column(DateTime)


class RegistroDecisao(Base):
    """Infraestrutura para aprendizado de preferências (Fase 8).

    Cada registro é uma decisão humana ou sugestão do sistema. Só entram no
    treinamento os registros com `incluir_treinamento = true`, que podem ser
    revisados, corrigidos e excluídos por um administrador."""
    __tablename__ = "registros_decisao"
    __table_args__ = (
        CheckConstraint(
            "tipo in ('sugestao','selecao','rejeicao','alteracao_manual','aprovacao','reprovacao','preferencia','resultado_cenario')"
        ),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    tipo: Mapped[str] = mapped_column(String(30), index=True)
    cenario_id: Mapped[int | None] = mapped_column(ForeignKey("cenarios_planejamento.id", ondelete="SET NULL"))
    alocacao_id: Mapped[int | None] = mapped_column(Integer)
    dados: Mapped[dict] = mapped_column(JSONB)
    motivo: Mapped[str | None] = mapped_column(Text)
    incluir_treinamento: Mapped[bool] = mapped_column(Boolean, default=False)
    revisado: Mapped[bool] = mapped_column(Boolean, default=False)
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class HistoricoAuditoria(Base):
    __tablename__ = "historico_auditoria"
    __table_args__ = (Index("ix_auditoria_entidade", "entidade", "entidade_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"), index=True)
    usuario_nome: Mapped[str | None] = mapped_column(String(200))
    acao: Mapped[str] = mapped_column(String(40), index=True)
    entidade: Mapped[str] = mapped_column(String(60))
    entidade_id: Mapped[str | None] = mapped_column(String(60))
    antes: Mapped[dict | None] = mapped_column(JSONB)
    depois: Mapped[dict | None] = mapped_column(JSONB)
    motivo: Mapped[str | None] = mapped_column(Text)
    origem: Mapped[str | None] = mapped_column(String(40))
    em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)


class Usuario(Base):
    __tablename__ = "usuarios"
    __table_args__ = (
        CheckConstraint("perfil in ('administrador','planejador','coordenador','instrutor','observador')", name="usuarios_perfil_check"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(200))
    email: Mapped[str] = mapped_column(String(200), unique=True)
    senha_hash: Mapped[str] = mapped_column(String(200))
    # Vínculo com o usuário do Supabase Auth (auth.users.id) quando PLAN_AUTH_MODO=supabase.
    auth_user_id: Mapped[str | None] = mapped_column(String(36), unique=True)
    perfil: Mapped[str] = mapped_column(String(20))
    # perfil "instrutor": o cadastro de instrutor que este usuário pode ver e atualizar pelo portal
    instrutor_id: Mapped[int | None] = mapped_column(ForeignKey("instrutores.id", ondelete="SET NULL"), unique=True)
    acesso_global: Mapped[bool] = mapped_column(Boolean, default=False)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    ultimo_acesso: Mapped[datetime | None] = mapped_column(DateTime)


class ObservacaoInstrutor(Base):
    """Observação/sugestão que o instrutor envia pelo portal sobre uma turma × UC atribuída a ele."""
    __tablename__ = "observacoes_instrutor"
    __table_args__ = (CheckConstraint("status in ('nova','lida','resolvida')", name="observacoes_instrutor_status_check"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    instrutor_id: Mapped[int] = mapped_column(ForeignKey("instrutores.id", ondelete="CASCADE"), index=True)
    turma_uc_id: Mapped[int | None] = mapped_column(ForeignKey("turma_uc.id", ondelete="CASCADE"), index=True)
    tipo: Mapped[str] = mapped_column(String(30), default="sugestao")
    texto: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="nova", server_default="nova")
    resposta: Mapped[str | None] = mapped_column(Text)
    respondido_por_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id", ondelete="SET NULL"))
    respondido_em: Mapped[datetime | None] = mapped_column(DateTime)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class SolicitacaoInstrutor(Base):
    """Pedido do instrutor pelo portal (folga ou substituição), com justificativa, decidido pelo coordenador."""
    __tablename__ = "solicitacoes_instrutor"
    __table_args__ = (
        CheckConstraint("tipo in ('folga','substituicao')", name="solicitacoes_tipo_check"),
        CheckConstraint("status in ('pendente','aprovada','recusada','cancelada')", name="solicitacoes_status_check"),
        CheckConstraint("data_fim >= data_inicio", name="solicitacoes_datas_check"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    instrutor_id: Mapped[int] = mapped_column(ForeignKey("instrutores.id", ondelete="CASCADE"), index=True)
    tipo: Mapped[str] = mapped_column(String(20))
    data_inicio: Mapped[date] = mapped_column(Date)
    data_fim: Mapped[date] = mapped_column(Date)
    turnos: Mapped[list[int]] = mapped_column(ARRAY(Integer), default=list, server_default=text("'{}'"))  # vazio = o dia todo
    justificativa: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="pendente", server_default="pendente")
    resposta: Mapped[str | None] = mapped_column(Text)
    decidido_por_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id", ondelete="SET NULL"))
    decidido_em: Mapped[datetime | None] = mapped_column(DateTime)
    efeitos: Mapped[dict | None] = mapped_column(JSONB)  # o que a aprovação fez (bloqueio criado, aulas substituídas...)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class SolicitacaoImpressao(Base):
    """Pedido de impressão do instrutor (material de aula), feito pelo portal até a quinta-feira da semana anterior ao uso;
    a coordenação atende e dá o retorno (em produção, pronta para retirar, entregue ou recusada)."""
    __tablename__ = "solicitacoes_impressao"
    __table_args__ = (
        CheckConstraint("status in ('pendente','em_producao','pronta','entregue','recusada','cancelada')", name="impressao_status_check"),
        CheckConstraint("copias > 0", name="impressao_copias_check"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    instrutor_id: Mapped[int] = mapped_column(ForeignKey("instrutores.id", ondelete="CASCADE"), index=True)
    turma_id: Mapped[int | None] = mapped_column(ForeignKey("turmas.id", ondelete="SET NULL"))
    titulo: Mapped[str] = mapped_column(String(200))
    descricao: Mapped[str | None] = mapped_column(Text)
    arquivo_url: Mapped[str | None] = mapped_column(String(500))  # link do arquivo (Drive, OneDrive...), para PDF grande
    arquivo_nome: Mapped[str | None] = mapped_column(String(200))  # PDF enviado com o pedido (até 4 MB)
    arquivo_tamanho: Mapped[int | None] = mapped_column(Integer)
    arquivo_pdf: Mapped[bytes | None] = mapped_column(LargeBinary, deferred=True)
    copias: Mapped[int] = mapped_column(Integer)
    paginas: Mapped[int | None] = mapped_column(Integer)
    frente_verso: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    colorido: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    data_uso: Mapped[date] = mapped_column(Date)  # dia em que o material será usado
    prazo: Mapped[date] = mapped_column(Date)  # quinta-feira da semana anterior ao uso
    status: Mapped[str] = mapped_column(String(20), default="pendente", server_default="pendente")
    resposta: Mapped[str | None] = mapped_column(Text)  # retorno da coordenação (ex.: pronto na sala 12)
    atendido_por_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id", ondelete="SET NULL"))
    atendido_em: Mapped[datetime | None] = mapped_column(DateTime)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Notificacao(Base):
    """Aviso para o instrutor no portal (mudança no cadastro dele, substituição, horário publicado, resposta...)."""
    __tablename__ = "notificacoes"
    id: Mapped[int] = mapped_column(primary_key=True)
    instrutor_id: Mapped[int] = mapped_column(ForeignKey("instrutores.id", ondelete="CASCADE"), index=True)
    tipo: Mapped[str] = mapped_column(String(30))
    titulo: Mapped[str] = mapped_column(String(200))
    texto: Mapped[str | None] = mapped_column(Text)
    aba: Mapped[str | None] = mapped_column(String(20))  # aba do portal relacionada: turmas, dados, obs
    lida: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class PermissaoEscopo(Base):
    """Restringe um usuário a unidades, cursos ou turmas específicas."""
    __tablename__ = "permissoes"
    __table_args__ = (
        CheckConstraint("escopo_tipo in ('unidade','curso','turma')"),
        UniqueConstraint("usuario_id", "escopo_tipo", "escopo_id"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id", ondelete="CASCADE"), index=True)
    escopo_tipo: Mapped[str] = mapped_column(String(20))
    escopo_id: Mapped[int] = mapped_column(Integer)


class PermissaoPerfil(Base):
    """Ações autorizadas por perfil (configuráveis pelo administrador)."""
    __tablename__ = "permissoes_perfil"
    perfil: Mapped[str] = mapped_column(String(20), primary_key=True)
    acao: Mapped[str] = mapped_column(String(60), primary_key=True)
