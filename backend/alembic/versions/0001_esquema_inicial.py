"""esquema inicial

Revision ID: 0001
Revises: 
Create Date: 2026-10-14 11:15:50.510854
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects import postgresql

revision = '0001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # Extensões necessárias para as exclusion constraints (GiST sobre escalares e int[]).
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")
    op.execute("CREATE EXTENSION IF NOT EXISTS intarray")
    op.create_table('bloqueios',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('alvo_tipo', sa.String(length=20), nullable=False),
    sa.Column('alvo_id', sa.Integer(), nullable=False),
    sa.Column('inicio', sa.DateTime(), nullable=False),
    sa.Column('fim', sa.DateTime(), nullable=False),
    sa.Column('tipo', sa.String(length=40), nullable=False),
    sa.Column('motivo', sa.String(length=300), nullable=True),
    sa.Column('ativo', sa.Boolean(), nullable=False),
    sa.Column('criado_em', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.Column('atualizado_em', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("alvo_tipo in ('instrutor','ambiente','turma','unidade','recurso')"),
    sa.CheckConstraint('fim > inicio'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_bloqueios_alvo_id'), 'bloqueios', ['alvo_id'], unique=False)
    op.create_index(op.f('ix_bloqueios_alvo_tipo'), 'bloqueios', ['alvo_tipo'], unique=False)
    op.create_table('configuracoes',
    sa.Column('chave', sa.String(length=80), nullable=False),
    sa.Column('valor', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('descricao', sa.Text(), nullable=True),
    sa.Column('atualizado_em', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('chave')
    )
    op.create_table('parametros_otimizacao',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('nome', sa.String(length=120), nullable=False),
    sa.Column('pesos', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('limite_tempo_s', sa.Integer(), nullable=False),
    sa.Column('padrao', sa.Boolean(), nullable=False),
    sa.Column('versao', sa.Integer(), nullable=False),
    sa.Column('ativo', sa.Boolean(), nullable=False),
    sa.Column('atualizado_em', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('nome')
    )
    op.create_table('permissoes_perfil',
    sa.Column('perfil', sa.String(length=20), nullable=False),
    sa.Column('acao', sa.String(length=60), nullable=False),
    sa.PrimaryKeyConstraint('perfil', 'acao')
    )
    op.create_table('tipos_ambiente',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('codigo', sa.String(length=30), nullable=False),
    sa.Column('nome', sa.String(length=120), nullable=False),
    sa.Column('especializado', sa.Boolean(), nullable=False),
    sa.Column('ativo', sa.Boolean(), nullable=False),
    sa.Column('criado_em', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.Column('atualizado_em', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('codigo')
    )
    op.create_table('unidades',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('codigo', sa.String(length=30), nullable=False),
    sa.Column('nome', sa.String(length=200), nullable=False),
    sa.Column('endereco', sa.String(length=300), nullable=True),
    sa.Column('cidade', sa.String(length=120), nullable=True),
    sa.Column('responsavel', sa.String(length=200), nullable=True),
    sa.Column('regras_operacionais', sa.Text(), nullable=True),
    sa.Column('situacao', sa.String(length=20), nullable=False),
    sa.Column('ativo', sa.Boolean(), nullable=False),
    sa.Column('criado_em', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.Column('atualizado_em', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('codigo')
    )
    op.create_table('usuarios',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('nome', sa.String(length=200), nullable=False),
    sa.Column('email', sa.String(length=200), nullable=False),
    sa.Column('senha_hash', sa.String(length=200), nullable=False),
    sa.Column('perfil', sa.String(length=20), nullable=False),
    sa.Column('acesso_global', sa.Boolean(), nullable=False),
    sa.Column('ativo', sa.Boolean(), nullable=False),
    sa.Column('criado_em', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.Column('ultimo_acesso', sa.DateTime(), nullable=True),
    sa.CheckConstraint("perfil in ('administrador','planejador','coordenador','gestor','consulta')"),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('email')
    )
    op.create_table('ambientes',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('codigo', sa.String(length=30), nullable=False),
    sa.Column('nome', sa.String(length=200), nullable=False),
    sa.Column('unidade_id', sa.Integer(), nullable=False),
    sa.Column('predio', sa.String(length=100), nullable=True),
    sa.Column('localizacao', sa.String(length=200), nullable=True),
    sa.Column('tipo_ambiente_id', sa.Integer(), nullable=False),
    sa.Column('capacidade_fisica', sa.Integer(), nullable=False),
    sa.Column('capacidade_operacional', sa.Integer(), nullable=False),
    sa.Column('maquinas', sa.Text(), nullable=True),
    sa.Column('requisitos_seguranca', sa.Text(), nullable=True),
    sa.Column('acessivel', sa.Boolean(), nullable=False),
    sa.Column('tempo_preparacao_min', sa.Integer(), nullable=False),
    sa.Column('situacao', sa.String(length=20), nullable=False),
    sa.Column('ativo', sa.Boolean(), nullable=False),
    sa.Column('criado_em', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.Column('atualizado_em', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('capacidade_fisica > 0'),
    sa.CheckConstraint('capacidade_operacional > 0 and capacidade_operacional <= capacidade_fisica'),
    sa.ForeignKeyConstraint(['tipo_ambiente_id'], ['tipos_ambiente.id'], ),
    sa.ForeignKeyConstraint(['unidade_id'], ['unidades.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('codigo')
    )
    op.create_index(op.f('ix_ambientes_tipo_ambiente_id'), 'ambientes', ['tipo_ambiente_id'], unique=False)
    op.create_index(op.f('ix_ambientes_unidade_id'), 'ambientes', ['unidade_id'], unique=False)
    op.create_table('calendarios',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('unidade_id', sa.Integer(), nullable=True),
    sa.Column('nome', sa.String(length=200), nullable=False),
    sa.Column('data_inicio', sa.Date(), nullable=False),
    sa.Column('data_fim', sa.Date(), nullable=False),
    sa.Column('dias_letivos', sa.ARRAY(sa.Integer()), nullable=False),
    sa.Column('ativo', sa.Boolean(), nullable=False),
    sa.Column('criado_em', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.Column('atualizado_em', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('data_fim >= data_inicio'),
    sa.ForeignKeyConstraint(['unidade_id'], ['unidades.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_calendarios_unidade_id'), 'calendarios', ['unidade_id'], unique=False)
    op.create_table('cenarios_planejamento',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('nome', sa.String(length=200), nullable=False),
    sa.Column('descricao', sa.Text(), nullable=True),
    sa.Column('unidade_id', sa.Integer(), nullable=True),
    sa.Column('tipo', sa.String(length=20), nullable=False),
    sa.Column('estado', sa.String(length=30), nullable=False),
    sa.Column('versao', sa.Integer(), nullable=False),
    sa.Column('cenario_origem_id', sa.Integer(), nullable=True),
    sa.Column('periodo_inicio', sa.Date(), nullable=True),
    sa.Column('periodo_fim', sa.Date(), nullable=True),
    sa.Column('autor_id', sa.Integer(), nullable=True),
    sa.Column('aprovado_por_id', sa.Integer(), nullable=True),
    sa.Column('publicado_em', sa.DateTime(), nullable=True),
    sa.Column('parametros', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('indicadores', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('resultado_validacao', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('lock_version', sa.Integer(), nullable=False),
    sa.Column('criado_em', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.Column('atualizado_em', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("estado in ('em_elaboracao','em_otimizacao','em_validacao','aguardando_aprovacao','aprovado','publicado','arquivado')"),
    sa.CheckConstraint("tipo in ('planejamento','proposta','simulacao')"),
    sa.ForeignKeyConstraint(['aprovado_por_id'], ['usuarios.id'], ),
    sa.ForeignKeyConstraint(['autor_id'], ['usuarios.id'], ),
    sa.ForeignKeyConstraint(['cenario_origem_id'], ['cenarios_planejamento.id'], ),
    sa.ForeignKeyConstraint(['unidade_id'], ['unidades.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_cenarios_planejamento_unidade_id'), 'cenarios_planejamento', ['unidade_id'], unique=False)
    op.create_index('uq_um_publicado_por_unidade', 'cenarios_planejamento', [sa.literal_column('coalesce(unidade_id, 0)')], unique=True, postgresql_where=sa.text("estado = 'publicado'"))
    op.create_table('cursos',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('codigo', sa.String(length=30), nullable=False),
    sa.Column('nome', sa.String(length=200), nullable=False),
    sa.Column('modalidade', sa.String(length=60), nullable=True),
    sa.Column('tipo', sa.String(length=60), nullable=True),
    sa.Column('carga_horaria_total', sa.Integer(), nullable=True),
    sa.Column('eixo_tecnologico', sa.String(length=120), nullable=True),
    sa.Column('unidade_id', sa.Integer(), nullable=True),
    sa.Column('turnos_possiveis', sa.String(length=200), nullable=True),
    sa.Column('situacao', sa.String(length=20), nullable=False),
    sa.Column('ativo', sa.Boolean(), nullable=False),
    sa.Column('criado_em', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.Column('atualizado_em', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['unidade_id'], ['unidades.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('codigo')
    )
    op.create_index(op.f('ix_cursos_unidade_id'), 'cursos', ['unidade_id'], unique=False)
    op.create_table('deslocamentos_unidades',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('origem_id', sa.Integer(), nullable=False),
    sa.Column('destino_id', sa.Integer(), nullable=False),
    sa.Column('minutos', sa.Integer(), nullable=False),
    sa.Column('ativo', sa.Boolean(), nullable=False),
    sa.CheckConstraint('minutos >= 0'),
    sa.ForeignKeyConstraint(['destino_id'], ['unidades.id'], ),
    sa.ForeignKeyConstraint(['origem_id'], ['unidades.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('origem_id', 'destino_id')
    )
    op.create_table('excecoes_autorizadas',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tipo', sa.String(length=30), nullable=False),
    sa.Column('justificativa', sa.Text(), nullable=False),
    sa.Column('autorizado_por_id', sa.Integer(), nullable=False),
    sa.Column('criado_em', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("tipo in ('feriado_bloqueio','carga_horaria')"),
    sa.ForeignKeyConstraint(['autorizado_por_id'], ['usuarios.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('historico_auditoria',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('usuario_id', sa.Integer(), nullable=True),
    sa.Column('usuario_nome', sa.String(length=200), nullable=True),
    sa.Column('acao', sa.String(length=40), nullable=False),
    sa.Column('entidade', sa.String(length=60), nullable=False),
    sa.Column('entidade_id', sa.String(length=60), nullable=True),
    sa.Column('antes', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('depois', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('motivo', sa.Text(), nullable=True),
    sa.Column('origem', sa.String(length=40), nullable=True),
    sa.Column('em', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['usuario_id'], ['usuarios.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_auditoria_entidade', 'historico_auditoria', ['entidade', 'entidade_id'], unique=False)
    op.create_index(op.f('ix_historico_auditoria_acao'), 'historico_auditoria', ['acao'], unique=False)
    op.create_index(op.f('ix_historico_auditoria_em'), 'historico_auditoria', ['em'], unique=False)
    op.create_index(op.f('ix_historico_auditoria_usuario_id'), 'historico_auditoria', ['usuario_id'], unique=False)
    op.create_table('horarios_funcionamento',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('unidade_id', sa.Integer(), nullable=False),
    sa.Column('dia_semana', sa.Integer(), nullable=False),
    sa.Column('hora_inicio', sa.Time(), nullable=False),
    sa.Column('hora_fim', sa.Time(), nullable=False),
    sa.Column('ativo', sa.Boolean(), nullable=False),
    sa.CheckConstraint('dia_semana between 0 and 6'),
    sa.CheckConstraint('hora_fim > hora_inicio'),
    sa.ForeignKeyConstraint(['unidade_id'], ['unidades.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_horarios_funcionamento_unidade_id'), 'horarios_funcionamento', ['unidade_id'], unique=False)
    op.create_table('permissoes',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('usuario_id', sa.Integer(), nullable=False),
    sa.Column('escopo_tipo', sa.String(length=20), nullable=False),
    sa.Column('escopo_id', sa.Integer(), nullable=False),
    sa.CheckConstraint("escopo_tipo in ('unidade','curso','turma')"),
    sa.ForeignKeyConstraint(['usuario_id'], ['usuarios.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('usuario_id', 'escopo_tipo', 'escopo_id')
    )
    op.create_index(op.f('ix_permissoes_usuario_id'), 'permissoes', ['usuario_id'], unique=False)
    op.create_table('recursos',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('codigo', sa.String(length=30), nullable=False),
    sa.Column('nome', sa.String(length=200), nullable=False),
    sa.Column('tipo', sa.String(length=60), nullable=False),
    sa.Column('unidade_id', sa.Integer(), nullable=False),
    sa.Column('quantidade_total', sa.Integer(), nullable=False),
    sa.Column('movel', sa.Boolean(), nullable=False),
    sa.Column('requer_reserva', sa.Boolean(), nullable=False),
    sa.Column('situacao', sa.String(length=20), nullable=False),
    sa.Column('ativo', sa.Boolean(), nullable=False),
    sa.Column('criado_em', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.Column('atualizado_em', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('quantidade_total >= 0'),
    sa.ForeignKeyConstraint(['unidade_id'], ['unidades.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('codigo')
    )
    op.create_index(op.f('ix_recursos_tipo'), 'recursos', ['tipo'], unique=False)
    op.create_index(op.f('ix_recursos_unidade_id'), 'recursos', ['unidade_id'], unique=False)
    op.create_table('setores',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('unidade_id', sa.Integer(), nullable=False),
    sa.Column('nome', sa.String(length=200), nullable=False),
    sa.Column('responsavel', sa.String(length=200), nullable=True),
    sa.Column('ativo', sa.Boolean(), nullable=False),
    sa.Column('criado_em', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.Column('atualizado_em', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['unidade_id'], ['unidades.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_setores_unidade_id'), 'setores', ['unidade_id'], unique=False)
    op.create_table('turnos',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('unidade_id', sa.Integer(), nullable=False),
    sa.Column('codigo', sa.String(length=30), nullable=False),
    sa.Column('nome', sa.String(length=100), nullable=False),
    sa.Column('hora_inicio', sa.Time(), nullable=False),
    sa.Column('hora_fim', sa.Time(), nullable=False),
    sa.Column('ordem', sa.Integer(), nullable=False),
    sa.Column('ativo', sa.Boolean(), nullable=False),
    sa.Column('criado_em', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.Column('atualizado_em', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('hora_fim > hora_inicio'),
    sa.ForeignKeyConstraint(['unidade_id'], ['unidades.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('unidade_id', 'codigo')
    )
    op.create_index(op.f('ix_turnos_unidade_id'), 'turnos', ['unidade_id'], unique=False)
    op.create_table('calendario_excecoes',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('calendario_id', sa.Integer(), nullable=False),
    sa.Column('data', sa.Date(), nullable=False),
    sa.Column('tipo', sa.String(length=30), nullable=False),
    sa.Column('descricao', sa.String(length=300), nullable=True),
    sa.Column('hora_inicio', sa.Time(), nullable=True),
    sa.Column('hora_fim', sa.Time(), nullable=True),
    sa.Column('ativo', sa.Boolean(), nullable=False),
    sa.Column('criado_em', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.Column('atualizado_em', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("tipo in ('feriado','recesso','dia_letivo_extra','horario_especial')"),
    sa.ForeignKeyConstraint(['calendario_id'], ['calendarios.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('calendario_id', 'data', 'tipo')
    )
    op.create_index(op.f('ix_calendario_excecoes_calendario_id'), 'calendario_excecoes', ['calendario_id'], unique=False)
    op.create_index(op.f('ix_calendario_excecoes_data'), 'calendario_excecoes', ['data'], unique=False)
    op.create_table('disponibilidade_ambientes',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('ambiente_id', sa.Integer(), nullable=False),
    sa.Column('dia_semana', sa.Integer(), nullable=False),
    sa.Column('hora_inicio', sa.Time(), nullable=False),
    sa.Column('hora_fim', sa.Time(), nullable=False),
    sa.CheckConstraint('dia_semana between 0 and 6'),
    sa.CheckConstraint('hora_fim > hora_inicio'),
    sa.ForeignKeyConstraint(['ambiente_id'], ['ambientes.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_disponibilidade_ambientes_ambiente_id'), 'disponibilidade_ambientes', ['ambiente_id'], unique=False)
    op.create_table('execucoes_otimizacao',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('cenario_id', sa.Integer(), nullable=False),
    sa.Column('escopo', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('parametros', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('status_solver', sa.String(length=30), nullable=True),
    sa.Column('motivo_termino', sa.Text(), nullable=True),
    sa.Column('objetivo', sa.Float(), nullable=True),
    sa.Column('limite_inferior', sa.Float(), nullable=True),
    sa.Column('tempo_s', sa.Float(), nullable=True),
    sa.Column('diagnosticos', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('resultado', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('criado_por_id', sa.Integer(), nullable=True),
    sa.Column('criado_em', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.Column('iniciado_em', sa.DateTime(), nullable=True),
    sa.Column('finalizado_em', sa.DateTime(), nullable=True),
    sa.CheckConstraint("status in ('pendente','executando','concluida','falha','cancelada')"),
    sa.ForeignKeyConstraint(['cenario_id'], ['cenarios_planejamento.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['criado_por_id'], ['usuarios.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_execucoes_otimizacao_cenario_id'), 'execucoes_otimizacao', ['cenario_id'], unique=False)
    op.create_table('importacoes',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('arquivo_nome', sa.String(length=300), nullable=False),
    sa.Column('arquivo_hash', sa.String(length=64), nullable=False),
    sa.Column('tipo', sa.String(length=40), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('mapeamento', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('previa', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('relatorio', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('cenario_id', sa.Integer(), nullable=True),
    sa.Column('criado_por_id', sa.Integer(), nullable=True),
    sa.Column('criado_em', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.Column('confirmado_em', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['cenario_id'], ['cenarios_planejamento.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['criado_por_id'], ['usuarios.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_importacoes_arquivo_hash'), 'importacoes', ['arquivo_hash'], unique=False)
    op.create_table('instrutores',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('matricula', sa.String(length=40), nullable=False),
    sa.Column('nome', sa.String(length=200), nullable=False),
    sa.Column('email', sa.String(length=200), nullable=True),
    sa.Column('unidade_id', sa.Integer(), nullable=False),
    sa.Column('areas_competencia', sa.Text(), nullable=True),
    sa.Column('carga_horaria_contratual', sa.Numeric(precision=5, scale=2), nullable=False),
    sa.Column('limite_ch_letiva', sa.Numeric(precision=5, scale=2), nullable=False),
    sa.Column('max_horas_dia', sa.Numeric(precision=4, scale=2), nullable=False),
    sa.Column('intervalo_minimo_h', sa.Numeric(precision=4, scale=2), nullable=False),
    sa.Column('turno_preferencial_id', sa.Integer(), nullable=True),
    sa.Column('restricoes_deslocamento', sa.Text(), nullable=True),
    sa.Column('situacao', sa.String(length=20), nullable=False),
    sa.Column('ativo', sa.Boolean(), nullable=False),
    sa.Column('criado_em', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.Column('atualizado_em', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('limite_ch_letiva <= carga_horaria_contratual'),
    sa.ForeignKeyConstraint(['turno_preferencial_id'], ['turnos.id'], ),
    sa.ForeignKeyConstraint(['unidade_id'], ['unidades.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('matricula')
    )
    op.create_index(op.f('ix_instrutores_unidade_id'), 'instrutores', ['unidade_id'], unique=False)
    op.create_table('matrizes_curriculares',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('curso_id', sa.Integer(), nullable=False),
    sa.Column('versao', sa.String(length=30), nullable=False),
    sa.Column('vigencia_inicio', sa.Date(), nullable=True),
    sa.Column('situacao', sa.String(length=20), nullable=False),
    sa.Column('matriz_origem_id', sa.Integer(), nullable=True),
    sa.Column('ativo', sa.Boolean(), nullable=False),
    sa.Column('criado_em', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.Column('atualizado_em', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['curso_id'], ['cursos.id'], ),
    sa.ForeignKeyConstraint(['matriz_origem_id'], ['matrizes_curriculares.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('curso_id', 'versao')
    )
    op.create_index(op.f('ix_matrizes_curriculares_curso_id'), 'matrizes_curriculares', ['curso_id'], unique=False)
    op.create_table('periodos_horarios',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('unidade_id', sa.Integer(), nullable=False),
    sa.Column('turno_id', sa.Integer(), nullable=False),
    sa.Column('ordem', sa.Integer(), nullable=False),
    sa.Column('hora_inicio', sa.Time(), nullable=False),
    sa.Column('hora_fim', sa.Time(), nullable=False),
    sa.Column('dias_semana', sa.ARRAY(sa.Integer()), nullable=False),
    sa.Column('excepcional', sa.Boolean(), nullable=False),
    sa.Column('ativo', sa.Boolean(), nullable=False),
    sa.Column('criado_em', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.Column('atualizado_em', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('hora_fim > hora_inicio'),
    sa.ForeignKeyConstraint(['turno_id'], ['turnos.id'], ),
    sa.ForeignKeyConstraint(['unidade_id'], ['unidades.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('turno_id', 'ordem')
    )
    op.create_index(op.f('ix_periodos_horarios_turno_id'), 'periodos_horarios', ['turno_id'], unique=False)
    op.create_index(op.f('ix_periodos_horarios_unidade_id'), 'periodos_horarios', ['unidade_id'], unique=False)
    op.create_table('recursos_ambientes',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('recurso_id', sa.Integer(), nullable=False),
    sa.Column('ambiente_id', sa.Integer(), nullable=False),
    sa.Column('quantidade', sa.Integer(), nullable=False),
    sa.CheckConstraint('quantidade > 0'),
    sa.ForeignKeyConstraint(['ambiente_id'], ['ambientes.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['recurso_id'], ['recursos.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('recurso_id', 'ambiente_id')
    )
    op.create_index(op.f('ix_recursos_ambientes_ambiente_id'), 'recursos_ambientes', ['ambiente_id'], unique=False)
    op.create_index(op.f('ix_recursos_ambientes_recurso_id'), 'recursos_ambientes', ['recurso_id'], unique=False)
    op.create_table('registros_decisao',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tipo', sa.String(length=30), nullable=False),
    sa.Column('cenario_id', sa.Integer(), nullable=True),
    sa.Column('alocacao_id', sa.Integer(), nullable=True),
    sa.Column('dados', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('motivo', sa.Text(), nullable=True),
    sa.Column('incluir_treinamento', sa.Boolean(), nullable=False),
    sa.Column('revisado', sa.Boolean(), nullable=False),
    sa.Column('usuario_id', sa.Integer(), nullable=True),
    sa.Column('criado_em', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("tipo in ('sugestao','selecao','rejeicao','alteracao_manual','aprovacao','reprovacao','preferencia','resultado_cenario')"),
    sa.ForeignKeyConstraint(['cenario_id'], ['cenarios_planejamento.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['usuario_id'], ['usuarios.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_registros_decisao_tipo'), 'registros_decisao', ['tipo'], unique=False)
    op.create_table('simulacoes_capacidade',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('nome', sa.String(length=200), nullable=False),
    sa.Column('tipo', sa.String(length=20), nullable=False),
    sa.Column('parametros', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('cenario_base_id', sa.Integer(), nullable=True),
    sa.Column('cenario_simulado_id', sa.Integer(), nullable=True),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('resultado', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('criado_por_id', sa.Integer(), nullable=True),
    sa.Column('criado_em', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['cenario_base_id'], ['cenarios_planejamento.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['cenario_simulado_id'], ['cenarios_planejamento.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['criado_por_id'], ['usuarios.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('validacoes',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('cenario_id', sa.Integer(), nullable=False),
    sa.Column('total_bloqueios', sa.Integer(), nullable=False),
    sa.Column('total_alertas', sa.Integer(), nullable=False),
    sa.Column('total_preferencias', sa.Integer(), nullable=False),
    sa.Column('total_recomendacoes', sa.Integer(), nullable=False),
    sa.Column('executado_por_id', sa.Integer(), nullable=True),
    sa.Column('executado_em', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['cenario_id'], ['cenarios_planejamento.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['executado_por_id'], ['usuarios.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_validacoes_cenario_id'), 'validacoes', ['cenario_id'], unique=False)
    op.create_table('versoes_planejamento',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('cenario_id', sa.Integer(), nullable=False),
    sa.Column('numero', sa.Integer(), nullable=False),
    sa.Column('estado', sa.String(length=30), nullable=False),
    sa.Column('motivo', sa.Text(), nullable=True),
    sa.Column('snapshot', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('indicadores', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('autor_id', sa.Integer(), nullable=True),
    sa.Column('criado_em', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['autor_id'], ['usuarios.id'], ),
    sa.ForeignKeyConstraint(['cenario_id'], ['cenarios_planejamento.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('cenario_id', 'numero')
    )
    op.create_index(op.f('ix_versoes_planejamento_cenario_id'), 'versoes_planejamento', ['cenario_id'], unique=False)
    op.create_table('disponibilidade_instrutores',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('instrutor_id', sa.Integer(), nullable=False),
    sa.Column('dia_semana', sa.Integer(), nullable=False),
    sa.Column('hora_inicio', sa.Time(), nullable=False),
    sa.Column('hora_fim', sa.Time(), nullable=False),
    sa.Column('unidade_id', sa.Integer(), nullable=True),
    sa.CheckConstraint('dia_semana between 0 and 6'),
    sa.CheckConstraint('hora_fim > hora_inicio'),
    sa.ForeignKeyConstraint(['instrutor_id'], ['instrutores.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['unidade_id'], ['unidades.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_disponibilidade_instrutores_instrutor_id'), 'disponibilidade_instrutores', ['instrutor_id'], unique=False)
    op.create_table('habilitacoes_instrutores',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('instrutor_id', sa.Integer(), nullable=False),
    sa.Column('nome', sa.String(length=200), nullable=False),
    sa.Column('valido_ate', sa.Date(), nullable=True),
    sa.Column('ativo', sa.Boolean(), nullable=False),
    sa.Column('criado_em', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.Column('atualizado_em', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['instrutor_id'], ['instrutores.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('instrutor_id', 'nome')
    )
    op.create_index(op.f('ix_habilitacoes_instrutores_instrutor_id'), 'habilitacoes_instrutores', ['instrutor_id'], unique=False)
    op.create_table('instrutor_unidades',
    sa.Column('instrutor_id', sa.Integer(), nullable=False),
    sa.Column('unidade_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['instrutor_id'], ['instrutores.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['unidade_id'], ['unidades.id'], ),
    sa.PrimaryKeyConstraint('instrutor_id', 'unidade_id')
    )
    op.create_table('ocorrencias_validacao',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('validacao_id', sa.Integer(), nullable=False),
    sa.Column('severidade', sa.String(length=20), nullable=False),
    sa.Column('regra', sa.String(length=60), nullable=False),
    sa.Column('descricao', sa.Text(), nullable=False),
    sa.Column('recurso_tipo', sa.String(length=20), nullable=True),
    sa.Column('recurso_id', sa.Integer(), nullable=True),
    sa.Column('data', sa.Date(), nullable=True),
    sa.Column('inicio', sa.DateTime(), nullable=True),
    sa.Column('fim', sa.DateTime(), nullable=True),
    sa.Column('turma_id', sa.Integer(), nullable=True),
    sa.Column('uc_id', sa.Integer(), nullable=True),
    sa.Column('instrutor_id', sa.Integer(), nullable=True),
    sa.Column('ambiente_id', sa.Integer(), nullable=True),
    sa.Column('alocacao_id', sa.Integer(), nullable=True),
    sa.Column('origem', sa.String(length=30), nullable=True),
    sa.CheckConstraint("severidade in ('bloqueio','alerta','preferencia','recomendacao')"),
    sa.ForeignKeyConstraint(['validacao_id'], ['validacoes.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_ocorrencias_validacao_validacao_id'), 'ocorrencias_validacao', ['validacao_id'], unique=False)
    op.create_table('resultados_otimizacao',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('execucao_id', sa.Integer(), nullable=False),
    sa.Column('criterio', sa.String(length=60), nullable=False),
    sa.Column('valor_bruto', sa.Float(), nullable=False),
    sa.Column('peso', sa.Float(), nullable=False),
    sa.Column('pontos', sa.Float(), nullable=False),
    sa.ForeignKeyConstraint(['execucao_id'], ['execucoes_otimizacao.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_resultados_otimizacao_execucao_id'), 'resultados_otimizacao', ['execucao_id'], unique=False)
    op.create_table('turmas',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('codigo', sa.String(length=40), nullable=False),
    sa.Column('nome', sa.String(length=200), nullable=False),
    sa.Column('curso_id', sa.Integer(), nullable=False),
    sa.Column('matriz_id', sa.Integer(), nullable=False),
    sa.Column('unidade_id', sa.Integer(), nullable=False),
    sa.Column('calendario_id', sa.Integer(), nullable=True),
    sa.Column('turno_id', sa.Integer(), nullable=True),
    sa.Column('qtd_alunos', sa.Integer(), nullable=False),
    sa.Column('capacidade_prevista', sa.Integer(), nullable=True),
    sa.Column('data_inicio', sa.Date(), nullable=False),
    sa.Column('data_fim', sa.Date(), nullable=False),
    sa.Column('dias_possiveis', sa.ARRAY(sa.Integer()), nullable=False),
    sa.Column('num_grupos', sa.Integer(), nullable=False),
    sa.Column('prioridade', sa.Integer(), nullable=False),
    sa.Column('necessidades_acessibilidade', sa.Boolean(), nullable=False),
    sa.Column('restricoes', sa.Text(), nullable=True),
    sa.Column('situacao', sa.String(length=20), nullable=False),
    sa.Column('simulacao_id', sa.Integer(), nullable=True),
    sa.Column('ativo', sa.Boolean(), nullable=False),
    sa.Column('criado_em', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.Column('atualizado_em', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('data_fim >= data_inicio'),
    sa.CheckConstraint('num_grupos between 1 and 16'),
    sa.CheckConstraint('qtd_alunos >= 0'),
    sa.ForeignKeyConstraint(['calendario_id'], ['calendarios.id'], ),
    sa.ForeignKeyConstraint(['curso_id'], ['cursos.id'], ),
    sa.ForeignKeyConstraint(['matriz_id'], ['matrizes_curriculares.id'], ),
    sa.ForeignKeyConstraint(['simulacao_id'], ['simulacoes_capacidade.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['turno_id'], ['turnos.id'], ),
    sa.ForeignKeyConstraint(['unidade_id'], ['unidades.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('codigo')
    )
    op.create_index(op.f('ix_turmas_curso_id'), 'turmas', ['curso_id'], unique=False)
    op.create_index(op.f('ix_turmas_matriz_id'), 'turmas', ['matriz_id'], unique=False)
    op.create_index(op.f('ix_turmas_simulacao_id'), 'turmas', ['simulacao_id'], unique=False)
    op.create_index(op.f('ix_turmas_unidade_id'), 'turmas', ['unidade_id'], unique=False)
    op.create_table('unidades_curriculares',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('matriz_id', sa.Integer(), nullable=False),
    sa.Column('codigo', sa.String(length=30), nullable=False),
    sa.Column('nome', sa.String(length=200), nullable=False),
    sa.Column('carga_horaria_total', sa.Integer(), nullable=False),
    sa.Column('ch_teorica', sa.Integer(), nullable=True),
    sa.Column('ch_pratica', sa.Integer(), nullable=True),
    sa.Column('ch_semanal_desejada', sa.Numeric(precision=6, scale=2), nullable=True),
    sa.Column('duracao_bloco_periodos', sa.Integer(), nullable=False),
    sa.Column('encontros_semanais', sa.Integer(), nullable=False),
    sa.Column('sequencia', sa.Integer(), nullable=False),
    sa.Column('modulo', sa.String(length=60), nullable=True),
    sa.Column('competencias', sa.Text(), nullable=True),
    sa.Column('certificacao_exigida', sa.String(length=200), nullable=True),
    sa.Column('capacidade_min', sa.Integer(), nullable=True),
    sa.Column('capacidade_max', sa.Integer(), nullable=True),
    sa.Column('divide_grupos', sa.Boolean(), nullable=False),
    sa.Column('aulas_consecutivas', sa.Boolean(), nullable=False),
    sa.Column('restricoes_pedagogicas', sa.Text(), nullable=True),
    sa.Column('prioridade', sa.Integer(), nullable=False),
    sa.Column('ativo', sa.Boolean(), nullable=False),
    sa.Column('criado_em', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.Column('atualizado_em', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('carga_horaria_total > 0'),
    sa.CheckConstraint('duracao_bloco_periodos >= 1'),
    sa.CheckConstraint('encontros_semanais >= 1'),
    sa.ForeignKeyConstraint(['matriz_id'], ['matrizes_curriculares.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('matriz_id', 'codigo')
    )
    op.create_index(op.f('ix_unidades_curriculares_matriz_id'), 'unidades_curriculares', ['matriz_id'], unique=False)
    op.create_table('competencias_instrutores',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('instrutor_id', sa.Integer(), nullable=False),
    sa.Column('uc_id', sa.Integer(), nullable=False),
    sa.Column('nivel', sa.String(length=20), nullable=False),
    sa.Column('condicoes', sa.Text(), nullable=True),
    sa.Column('valido_ate', sa.Date(), nullable=True),
    sa.Column('ativo', sa.Boolean(), nullable=False),
    sa.Column('criado_em', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.Column('atualizado_em', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("nivel in ('pleno','supervisionado','em_formacao')"),
    sa.ForeignKeyConstraint(['instrutor_id'], ['instrutores.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['uc_id'], ['unidades_curriculares.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('instrutor_id', 'uc_id')
    )
    op.create_index(op.f('ix_competencias_instrutores_instrutor_id'), 'competencias_instrutores', ['instrutor_id'], unique=False)
    op.create_index(op.f('ix_competencias_instrutores_uc_id'), 'competencias_instrutores', ['uc_id'], unique=False)
    op.create_table('turma_uc',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('turma_id', sa.Integer(), nullable=False),
    sa.Column('uc_id', sa.Integer(), nullable=False),
    sa.Column('situacao', sa.String(length=20), nullable=False),
    sa.Column('data_inicio', sa.Date(), nullable=True),
    sa.Column('data_limite', sa.Date(), nullable=True),
    sa.Column('ch_realizada', sa.Numeric(precision=7, scale=2), nullable=False),
    sa.Column('instrutor_preferido_id', sa.Integer(), nullable=True),
    sa.Column('ativo', sa.Boolean(), nullable=False),
    sa.Column('criado_em', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.Column('atualizado_em', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("situacao in ('prevista','ofertada','em_execucao','concluida','pendente','cancelada')"),
    sa.CheckConstraint('ch_realizada >= 0'),
    sa.ForeignKeyConstraint(['instrutor_preferido_id'], ['instrutores.id'], ),
    sa.ForeignKeyConstraint(['turma_id'], ['turmas.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['uc_id'], ['unidades_curriculares.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('turma_id', 'uc_id')
    )
    op.create_index(op.f('ix_turma_uc_turma_id'), 'turma_uc', ['turma_id'], unique=False)
    op.create_index(op.f('ix_turma_uc_uc_id'), 'turma_uc', ['uc_id'], unique=False)
    op.create_table('uc_prerequisitos',
    sa.Column('uc_id', sa.Integer(), nullable=False),
    sa.Column('prerequisito_id', sa.Integer(), nullable=False),
    sa.CheckConstraint('uc_id <> prerequisito_id'),
    sa.ForeignKeyConstraint(['prerequisito_id'], ['unidades_curriculares.id'], ),
    sa.ForeignKeyConstraint(['uc_id'], ['unidades_curriculares.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('uc_id', 'prerequisito_id')
    )
    op.create_table('uc_recursos',
    sa.Column('uc_id', sa.Integer(), nullable=False),
    sa.Column('recurso_tipo', sa.String(length=60), nullable=False),
    sa.Column('quantidade', sa.Integer(), nullable=False),
    sa.CheckConstraint('quantidade > 0'),
    sa.ForeignKeyConstraint(['uc_id'], ['unidades_curriculares.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('uc_id', 'recurso_tipo')
    )
    op.create_table('uc_tipos_ambiente',
    sa.Column('uc_id', sa.Integer(), nullable=False),
    sa.Column('tipo_ambiente_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['tipo_ambiente_id'], ['tipos_ambiente.id'], ),
    sa.ForeignKeyConstraint(['uc_id'], ['unidades_curriculares.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('uc_id', 'tipo_ambiente_id')
    )
    op.create_table('atividades',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('cenario_id', sa.Integer(), nullable=False),
    sa.Column('turma_uc_id', sa.Integer(), nullable=False),
    sa.Column('grupo', sa.Integer(), nullable=True),
    sa.Column('instrutor_id', sa.Integer(), nullable=True),
    sa.Column('ambiente_id', sa.Integer(), nullable=True),
    sa.Column('dia_semana', sa.Integer(), nullable=False),
    sa.Column('periodo_inicio_id', sa.Integer(), nullable=False),
    sa.Column('num_periodos', sa.Integer(), nullable=False),
    sa.Column('data_inicio', sa.Date(), nullable=False),
    sa.Column('data_fim', sa.Date(), nullable=False),
    sa.Column('fixa', sa.Boolean(), nullable=False),
    sa.Column('origem', sa.String(length=20), nullable=False),
    sa.Column('execucao_id', sa.Integer(), nullable=True),
    sa.Column('criado_em', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('dia_semana between 0 and 6'),
    sa.CheckConstraint('num_periodos >= 1'),
    sa.ForeignKeyConstraint(['ambiente_id'], ['ambientes.id'], ),
    sa.ForeignKeyConstraint(['cenario_id'], ['cenarios_planejamento.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['execucao_id'], ['execucoes_otimizacao.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['instrutor_id'], ['instrutores.id'], ),
    sa.ForeignKeyConstraint(['periodo_inicio_id'], ['periodos_horarios.id'], ),
    sa.ForeignKeyConstraint(['turma_uc_id'], ['turma_uc.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_atividades_cenario_id'), 'atividades', ['cenario_id'], unique=False)
    op.create_index(op.f('ix_atividades_turma_uc_id'), 'atividades', ['turma_uc_id'], unique=False)
    op.create_table('alocacoes',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('cenario_id', sa.Integer(), nullable=False),
    sa.Column('atividade_id', sa.Integer(), nullable=True),
    sa.Column('turma_uc_id', sa.Integer(), nullable=False),
    sa.Column('turma_id', sa.Integer(), nullable=False),
    sa.Column('uc_id', sa.Integer(), nullable=False),
    sa.Column('grupo', sa.Integer(), nullable=True),
    sa.Column('grupos', sa.ARRAY(sa.Integer()), nullable=False),
    sa.Column('instrutor_id', sa.Integer(), nullable=True),
    sa.Column('ambiente_id', sa.Integer(), nullable=True),
    sa.Column('data', sa.Date(), nullable=False),
    sa.Column('inicio', sa.DateTime(), nullable=False),
    sa.Column('fim', sa.DateTime(), nullable=False),
    sa.Column('fim_ambiente', sa.DateTime(), nullable=False),
    sa.Column('minutos_aula', sa.Integer(), nullable=False),
    sa.Column('intervalo', postgresql.TSRANGE(), sa.Computed("tsrange(inicio, fim, '[)')", persisted=True), nullable=True),
    sa.Column('intervalo_ambiente', postgresql.TSRANGE(), sa.Computed("tsrange(inicio, fim_ambiente, '[)')", persisted=True), nullable=True),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('fixa', sa.Boolean(), nullable=False),
    sa.Column('origem', sa.String(length=20), nullable=False),
    sa.Column('observacao', sa.Text(), nullable=True),
    sa.Column('excecao_id', sa.Integer(), nullable=True),
    sa.Column('versao', sa.Integer(), nullable=False),
    sa.Column('criado_por_id', sa.Integer(), nullable=True),
    sa.Column('criado_em', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.Column('atualizado_em', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    postgresql.ExcludeConstraint((sa.column('cenario_id'), '='), (sa.column('ambiente_id'), '='), (sa.column('intervalo_ambiente'), '&&'), where=sa.text("status <> 'cancelada' AND ambiente_id IS NOT NULL"), using='gist', name='excl_alocacao_ambiente'),
    postgresql.ExcludeConstraint((sa.column('cenario_id'), '='), (sa.column('instrutor_id'), '='), (sa.column('intervalo'), '&&'), where=sa.text("status <> 'cancelada' AND instrutor_id IS NOT NULL"), using='gist', name='excl_alocacao_instrutor'),
    postgresql.ExcludeConstraint((sa.column('cenario_id'), '='), (sa.column('turma_id'), '='), (sa.column('grupos'), '&&'), (sa.column('intervalo'), '&&'), where=sa.text("status <> 'cancelada'"), using='gist', name='excl_alocacao_turma_grupos', ops={'grupos': 'gist__int_ops'}),
    sa.CheckConstraint("status in ('programada','realizada','cancelada')"),
    sa.CheckConstraint('fim > inicio'),
    sa.CheckConstraint('fim_ambiente >= fim'),
    sa.CheckConstraint('minutos_aula > 0'),
    sa.ForeignKeyConstraint(['ambiente_id'], ['ambientes.id'], ),
    sa.ForeignKeyConstraint(['atividade_id'], ['atividades.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['cenario_id'], ['cenarios_planejamento.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['criado_por_id'], ['usuarios.id'], ),
    sa.ForeignKeyConstraint(['excecao_id'], ['excecoes_autorizadas.id'], ),
    sa.ForeignKeyConstraint(['instrutor_id'], ['instrutores.id'], ),
    sa.ForeignKeyConstraint(['turma_id'], ['turmas.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['turma_uc_id'], ['turma_uc.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['uc_id'], ['unidades_curriculares.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_alocacoes_ambiente_id'), 'alocacoes', ['ambiente_id'], unique=False)
    op.create_index(op.f('ix_alocacoes_atividade_id'), 'alocacoes', ['atividade_id'], unique=False)
    op.create_index('ix_alocacoes_cenario_data', 'alocacoes', ['cenario_id', 'data'], unique=False)
    op.create_index(op.f('ix_alocacoes_cenario_id'), 'alocacoes', ['cenario_id'], unique=False)
    op.create_index(op.f('ix_alocacoes_instrutor_id'), 'alocacoes', ['instrutor_id'], unique=False)
    op.create_index(op.f('ix_alocacoes_turma_id'), 'alocacoes', ['turma_id'], unique=False)
    op.create_index(op.f('ix_alocacoes_turma_uc_id'), 'alocacoes', ['turma_uc_id'], unique=False)
    op.create_index(op.f('ix_alocacoes_uc_id'), 'alocacoes', ['uc_id'], unique=False)
    op.create_table('alocacao_recursos',
    sa.Column('alocacao_id', sa.Integer(), nullable=False),
    sa.Column('recurso_id', sa.Integer(), nullable=False),
    sa.Column('quantidade', sa.Integer(), nullable=False),
    sa.CheckConstraint('quantidade > 0'),
    sa.ForeignKeyConstraint(['alocacao_id'], ['alocacoes.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['recurso_id'], ['recursos.id'], ),
    sa.PrimaryKeyConstraint('alocacao_id', 'recurso_id')
    )


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_table('alocacao_recursos')
    op.drop_index(op.f('ix_alocacoes_uc_id'), table_name='alocacoes')
    op.drop_index(op.f('ix_alocacoes_turma_uc_id'), table_name='alocacoes')
    op.drop_index(op.f('ix_alocacoes_turma_id'), table_name='alocacoes')
    op.drop_index(op.f('ix_alocacoes_instrutor_id'), table_name='alocacoes')
    op.drop_index(op.f('ix_alocacoes_cenario_id'), table_name='alocacoes')
    op.drop_index('ix_alocacoes_cenario_data', table_name='alocacoes')
    op.drop_index(op.f('ix_alocacoes_atividade_id'), table_name='alocacoes')
    op.drop_index(op.f('ix_alocacoes_ambiente_id'), table_name='alocacoes')
    op.drop_table('alocacoes')
    op.drop_index(op.f('ix_atividades_turma_uc_id'), table_name='atividades')
    op.drop_index(op.f('ix_atividades_cenario_id'), table_name='atividades')
    op.drop_table('atividades')
    op.drop_table('uc_tipos_ambiente')
    op.drop_table('uc_recursos')
    op.drop_table('uc_prerequisitos')
    op.drop_index(op.f('ix_turma_uc_uc_id'), table_name='turma_uc')
    op.drop_index(op.f('ix_turma_uc_turma_id'), table_name='turma_uc')
    op.drop_table('turma_uc')
    op.drop_index(op.f('ix_competencias_instrutores_uc_id'), table_name='competencias_instrutores')
    op.drop_index(op.f('ix_competencias_instrutores_instrutor_id'), table_name='competencias_instrutores')
    op.drop_table('competencias_instrutores')
    op.drop_index(op.f('ix_unidades_curriculares_matriz_id'), table_name='unidades_curriculares')
    op.drop_table('unidades_curriculares')
    op.drop_index(op.f('ix_turmas_unidade_id'), table_name='turmas')
    op.drop_index(op.f('ix_turmas_simulacao_id'), table_name='turmas')
    op.drop_index(op.f('ix_turmas_matriz_id'), table_name='turmas')
    op.drop_index(op.f('ix_turmas_curso_id'), table_name='turmas')
    op.drop_table('turmas')
    op.drop_index(op.f('ix_resultados_otimizacao_execucao_id'), table_name='resultados_otimizacao')
    op.drop_table('resultados_otimizacao')
    op.drop_index(op.f('ix_ocorrencias_validacao_validacao_id'), table_name='ocorrencias_validacao')
    op.drop_table('ocorrencias_validacao')
    op.drop_table('instrutor_unidades')
    op.drop_index(op.f('ix_habilitacoes_instrutores_instrutor_id'), table_name='habilitacoes_instrutores')
    op.drop_table('habilitacoes_instrutores')
    op.drop_index(op.f('ix_disponibilidade_instrutores_instrutor_id'), table_name='disponibilidade_instrutores')
    op.drop_table('disponibilidade_instrutores')
    op.drop_index(op.f('ix_versoes_planejamento_cenario_id'), table_name='versoes_planejamento')
    op.drop_table('versoes_planejamento')
    op.drop_index(op.f('ix_validacoes_cenario_id'), table_name='validacoes')
    op.drop_table('validacoes')
    op.drop_table('simulacoes_capacidade')
    op.drop_index(op.f('ix_registros_decisao_tipo'), table_name='registros_decisao')
    op.drop_table('registros_decisao')
    op.drop_index(op.f('ix_recursos_ambientes_recurso_id'), table_name='recursos_ambientes')
    op.drop_index(op.f('ix_recursos_ambientes_ambiente_id'), table_name='recursos_ambientes')
    op.drop_table('recursos_ambientes')
    op.drop_index(op.f('ix_periodos_horarios_unidade_id'), table_name='periodos_horarios')
    op.drop_index(op.f('ix_periodos_horarios_turno_id'), table_name='periodos_horarios')
    op.drop_table('periodos_horarios')
    op.drop_index(op.f('ix_matrizes_curriculares_curso_id'), table_name='matrizes_curriculares')
    op.drop_table('matrizes_curriculares')
    op.drop_index(op.f('ix_instrutores_unidade_id'), table_name='instrutores')
    op.drop_table('instrutores')
    op.drop_index(op.f('ix_importacoes_arquivo_hash'), table_name='importacoes')
    op.drop_table('importacoes')
    op.drop_index(op.f('ix_execucoes_otimizacao_cenario_id'), table_name='execucoes_otimizacao')
    op.drop_table('execucoes_otimizacao')
    op.drop_index(op.f('ix_disponibilidade_ambientes_ambiente_id'), table_name='disponibilidade_ambientes')
    op.drop_table('disponibilidade_ambientes')
    op.drop_index(op.f('ix_calendario_excecoes_data'), table_name='calendario_excecoes')
    op.drop_index(op.f('ix_calendario_excecoes_calendario_id'), table_name='calendario_excecoes')
    op.drop_table('calendario_excecoes')
    op.drop_index(op.f('ix_turnos_unidade_id'), table_name='turnos')
    op.drop_table('turnos')
    op.drop_index(op.f('ix_setores_unidade_id'), table_name='setores')
    op.drop_table('setores')
    op.drop_index(op.f('ix_recursos_unidade_id'), table_name='recursos')
    op.drop_index(op.f('ix_recursos_tipo'), table_name='recursos')
    op.drop_table('recursos')
    op.drop_index(op.f('ix_permissoes_usuario_id'), table_name='permissoes')
    op.drop_table('permissoes')
    op.drop_index(op.f('ix_horarios_funcionamento_unidade_id'), table_name='horarios_funcionamento')
    op.drop_table('horarios_funcionamento')
    op.drop_index(op.f('ix_historico_auditoria_usuario_id'), table_name='historico_auditoria')
    op.drop_index(op.f('ix_historico_auditoria_em'), table_name='historico_auditoria')
    op.drop_index(op.f('ix_historico_auditoria_acao'), table_name='historico_auditoria')
    op.drop_index('ix_auditoria_entidade', table_name='historico_auditoria')
    op.drop_table('historico_auditoria')
    op.drop_table('excecoes_autorizadas')
    op.drop_table('deslocamentos_unidades')
    op.drop_index(op.f('ix_cursos_unidade_id'), table_name='cursos')
    op.drop_table('cursos')
    op.drop_index('uq_um_publicado_por_unidade', table_name='cenarios_planejamento', postgresql_where=sa.text("estado = 'publicado'"))
    op.drop_index(op.f('ix_cenarios_planejamento_unidade_id'), table_name='cenarios_planejamento')
    op.drop_table('cenarios_planejamento')
    op.drop_index(op.f('ix_calendarios_unidade_id'), table_name='calendarios')
    op.drop_table('calendarios')
    op.drop_index(op.f('ix_ambientes_unidade_id'), table_name='ambientes')
    op.drop_index(op.f('ix_ambientes_tipo_ambiente_id'), table_name='ambientes')
    op.drop_table('ambientes')
    op.drop_table('usuarios')
    op.drop_table('unidades')
    op.drop_table('tipos_ambiente')
    op.drop_table('permissoes_perfil')
    op.drop_table('parametros_otimizacao')
    op.drop_table('configuracoes')
    op.drop_index(op.f('ix_bloqueios_alvo_tipo'), table_name='bloqueios')
    op.drop_index(op.f('ix_bloqueios_alvo_id'), table_name='bloqueios')
    op.drop_table('bloqueios')
