BEGIN;

CREATE TABLE alembic_version (
    version_num VARCHAR(32) NOT NULL, 
    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);

-- Running upgrade  -> 0001

CREATE EXTENSION IF NOT EXISTS btree_gist;

CREATE EXTENSION IF NOT EXISTS intarray;

CREATE TABLE bloqueios (
    id SERIAL NOT NULL, 
    alvo_tipo VARCHAR(20) NOT NULL, 
    alvo_id INTEGER NOT NULL, 
    inicio TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
    fim TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
    tipo VARCHAR(40) NOT NULL, 
    motivo VARCHAR(300), 
    ativo BOOLEAN NOT NULL, 
    criado_em TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
    atualizado_em TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    CHECK (alvo_tipo in ('instrutor','ambiente','turma','unidade','recurso')), 
    CHECK (fim > inicio)
);

CREATE INDEX ix_bloqueios_alvo_id ON bloqueios (alvo_id);

CREATE INDEX ix_bloqueios_alvo_tipo ON bloqueios (alvo_tipo);

CREATE TABLE configuracoes (
    chave VARCHAR(80) NOT NULL, 
    valor JSONB NOT NULL, 
    descricao TEXT, 
    atualizado_em TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (chave)
);

CREATE TABLE parametros_otimizacao (
    id SERIAL NOT NULL, 
    nome VARCHAR(120) NOT NULL, 
    pesos JSONB NOT NULL, 
    limite_tempo_s INTEGER NOT NULL, 
    padrao BOOLEAN NOT NULL, 
    versao INTEGER NOT NULL, 
    ativo BOOLEAN NOT NULL, 
    atualizado_em TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    UNIQUE (nome)
);

CREATE TABLE permissoes_perfil (
    perfil VARCHAR(20) NOT NULL, 
    acao VARCHAR(60) NOT NULL, 
    PRIMARY KEY (perfil, acao)
);

CREATE TABLE tipos_ambiente (
    id SERIAL NOT NULL, 
    codigo VARCHAR(30) NOT NULL, 
    nome VARCHAR(120) NOT NULL, 
    especializado BOOLEAN NOT NULL, 
    ativo BOOLEAN NOT NULL, 
    criado_em TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
    atualizado_em TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    UNIQUE (codigo)
);

CREATE TABLE unidades (
    id SERIAL NOT NULL, 
    codigo VARCHAR(30) NOT NULL, 
    nome VARCHAR(200) NOT NULL, 
    endereco VARCHAR(300), 
    cidade VARCHAR(120), 
    responsavel VARCHAR(200), 
    regras_operacionais TEXT, 
    situacao VARCHAR(20) NOT NULL, 
    ativo BOOLEAN NOT NULL, 
    criado_em TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
    atualizado_em TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    UNIQUE (codigo)
);

CREATE TABLE usuarios (
    id SERIAL NOT NULL, 
    nome VARCHAR(200) NOT NULL, 
    email VARCHAR(200) NOT NULL, 
    senha_hash VARCHAR(200) NOT NULL, 
    perfil VARCHAR(20) NOT NULL, 
    acesso_global BOOLEAN NOT NULL, 
    ativo BOOLEAN NOT NULL, 
    criado_em TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
    ultimo_acesso TIMESTAMP WITHOUT TIME ZONE, 
    PRIMARY KEY (id), 
    CHECK (perfil in ('administrador','planejador','coordenador','gestor','consulta')), 
    UNIQUE (email)
);

CREATE TABLE ambientes (
    id SERIAL NOT NULL, 
    codigo VARCHAR(30) NOT NULL, 
    nome VARCHAR(200) NOT NULL, 
    unidade_id INTEGER NOT NULL, 
    predio VARCHAR(100), 
    localizacao VARCHAR(200), 
    tipo_ambiente_id INTEGER NOT NULL, 
    capacidade_fisica INTEGER NOT NULL, 
    capacidade_operacional INTEGER NOT NULL, 
    maquinas TEXT, 
    requisitos_seguranca TEXT, 
    acessivel BOOLEAN NOT NULL, 
    tempo_preparacao_min INTEGER NOT NULL, 
    situacao VARCHAR(20) NOT NULL, 
    ativo BOOLEAN NOT NULL, 
    criado_em TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
    atualizado_em TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    CHECK (capacidade_fisica > 0), 
    CHECK (capacidade_operacional > 0 and capacidade_operacional <= capacidade_fisica), 
    FOREIGN KEY(tipo_ambiente_id) REFERENCES tipos_ambiente (id), 
    FOREIGN KEY(unidade_id) REFERENCES unidades (id), 
    UNIQUE (codigo)
);

CREATE INDEX ix_ambientes_tipo_ambiente_id ON ambientes (tipo_ambiente_id);

CREATE INDEX ix_ambientes_unidade_id ON ambientes (unidade_id);

CREATE TABLE calendarios (
    id SERIAL NOT NULL, 
    unidade_id INTEGER, 
    nome VARCHAR(200) NOT NULL, 
    data_inicio DATE NOT NULL, 
    data_fim DATE NOT NULL, 
    dias_letivos INTEGER[] NOT NULL, 
    ativo BOOLEAN NOT NULL, 
    criado_em TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
    atualizado_em TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    CHECK (data_fim >= data_inicio), 
    FOREIGN KEY(unidade_id) REFERENCES unidades (id)
);

CREATE INDEX ix_calendarios_unidade_id ON calendarios (unidade_id);

CREATE TABLE cenarios_planejamento (
    id SERIAL NOT NULL, 
    nome VARCHAR(200) NOT NULL, 
    descricao TEXT, 
    unidade_id INTEGER, 
    tipo VARCHAR(20) NOT NULL, 
    estado VARCHAR(30) NOT NULL, 
    versao INTEGER NOT NULL, 
    cenario_origem_id INTEGER, 
    periodo_inicio DATE, 
    periodo_fim DATE, 
    autor_id INTEGER, 
    aprovado_por_id INTEGER, 
    publicado_em TIMESTAMP WITHOUT TIME ZONE, 
    parametros JSONB, 
    indicadores JSONB, 
    resultado_validacao JSONB, 
    lock_version INTEGER NOT NULL, 
    criado_em TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
    atualizado_em TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    CHECK (estado in ('em_elaboracao','em_otimizacao','em_validacao','aguardando_aprovacao','aprovado','publicado','arquivado')), 
    CHECK (tipo in ('planejamento','proposta','simulacao')), 
    FOREIGN KEY(aprovado_por_id) REFERENCES usuarios (id), 
    FOREIGN KEY(autor_id) REFERENCES usuarios (id), 
    FOREIGN KEY(cenario_origem_id) REFERENCES cenarios_planejamento (id), 
    FOREIGN KEY(unidade_id) REFERENCES unidades (id)
);

CREATE INDEX ix_cenarios_planejamento_unidade_id ON cenarios_planejamento (unidade_id);

CREATE UNIQUE INDEX uq_um_publicado_por_unidade ON cenarios_planejamento (coalesce(unidade_id, 0)) WHERE estado = 'publicado';

CREATE TABLE cursos (
    id SERIAL NOT NULL, 
    codigo VARCHAR(30) NOT NULL, 
    nome VARCHAR(200) NOT NULL, 
    modalidade VARCHAR(60), 
    tipo VARCHAR(60), 
    carga_horaria_total INTEGER, 
    eixo_tecnologico VARCHAR(120), 
    unidade_id INTEGER, 
    turnos_possiveis VARCHAR(200), 
    situacao VARCHAR(20) NOT NULL, 
    ativo BOOLEAN NOT NULL, 
    criado_em TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
    atualizado_em TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(unidade_id) REFERENCES unidades (id), 
    UNIQUE (codigo)
);

CREATE INDEX ix_cursos_unidade_id ON cursos (unidade_id);

CREATE TABLE deslocamentos_unidades (
    id SERIAL NOT NULL, 
    origem_id INTEGER NOT NULL, 
    destino_id INTEGER NOT NULL, 
    minutos INTEGER NOT NULL, 
    ativo BOOLEAN NOT NULL, 
    PRIMARY KEY (id), 
    CHECK (minutos >= 0), 
    FOREIGN KEY(destino_id) REFERENCES unidades (id), 
    FOREIGN KEY(origem_id) REFERENCES unidades (id), 
    UNIQUE (origem_id, destino_id)
);

CREATE TABLE excecoes_autorizadas (
    id SERIAL NOT NULL, 
    tipo VARCHAR(30) NOT NULL, 
    justificativa TEXT NOT NULL, 
    autorizado_por_id INTEGER NOT NULL, 
    criado_em TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    CHECK (tipo in ('feriado_bloqueio','carga_horaria')), 
    FOREIGN KEY(autorizado_por_id) REFERENCES usuarios (id)
);

CREATE TABLE historico_auditoria (
    id SERIAL NOT NULL, 
    usuario_id INTEGER, 
    usuario_nome VARCHAR(200), 
    acao VARCHAR(40) NOT NULL, 
    entidade VARCHAR(60) NOT NULL, 
    entidade_id VARCHAR(60), 
    antes JSONB, 
    depois JSONB, 
    motivo TEXT, 
    origem VARCHAR(40), 
    em TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(usuario_id) REFERENCES usuarios (id)
);

CREATE INDEX ix_auditoria_entidade ON historico_auditoria (entidade, entidade_id);

CREATE INDEX ix_historico_auditoria_acao ON historico_auditoria (acao);

CREATE INDEX ix_historico_auditoria_em ON historico_auditoria (em);

CREATE INDEX ix_historico_auditoria_usuario_id ON historico_auditoria (usuario_id);

CREATE TABLE horarios_funcionamento (
    id SERIAL NOT NULL, 
    unidade_id INTEGER NOT NULL, 
    dia_semana INTEGER NOT NULL, 
    hora_inicio TIME WITHOUT TIME ZONE NOT NULL, 
    hora_fim TIME WITHOUT TIME ZONE NOT NULL, 
    ativo BOOLEAN NOT NULL, 
    PRIMARY KEY (id), 
    CHECK (dia_semana between 0 and 6), 
    CHECK (hora_fim > hora_inicio), 
    FOREIGN KEY(unidade_id) REFERENCES unidades (id)
);

CREATE INDEX ix_horarios_funcionamento_unidade_id ON horarios_funcionamento (unidade_id);

CREATE TABLE permissoes (
    id SERIAL NOT NULL, 
    usuario_id INTEGER NOT NULL, 
    escopo_tipo VARCHAR(20) NOT NULL, 
    escopo_id INTEGER NOT NULL, 
    PRIMARY KEY (id), 
    CHECK (escopo_tipo in ('unidade','curso','turma')), 
    FOREIGN KEY(usuario_id) REFERENCES usuarios (id) ON DELETE CASCADE, 
    UNIQUE (usuario_id, escopo_tipo, escopo_id)
);

CREATE INDEX ix_permissoes_usuario_id ON permissoes (usuario_id);

CREATE TABLE recursos (
    id SERIAL NOT NULL, 
    codigo VARCHAR(30) NOT NULL, 
    nome VARCHAR(200) NOT NULL, 
    tipo VARCHAR(60) NOT NULL, 
    unidade_id INTEGER NOT NULL, 
    quantidade_total INTEGER NOT NULL, 
    movel BOOLEAN NOT NULL, 
    requer_reserva BOOLEAN NOT NULL, 
    situacao VARCHAR(20) NOT NULL, 
    ativo BOOLEAN NOT NULL, 
    criado_em TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
    atualizado_em TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    CHECK (quantidade_total >= 0), 
    FOREIGN KEY(unidade_id) REFERENCES unidades (id), 
    UNIQUE (codigo)
);

CREATE INDEX ix_recursos_tipo ON recursos (tipo);

CREATE INDEX ix_recursos_unidade_id ON recursos (unidade_id);

CREATE TABLE setores (
    id SERIAL NOT NULL, 
    unidade_id INTEGER NOT NULL, 
    nome VARCHAR(200) NOT NULL, 
    responsavel VARCHAR(200), 
    ativo BOOLEAN NOT NULL, 
    criado_em TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
    atualizado_em TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(unidade_id) REFERENCES unidades (id)
);

CREATE INDEX ix_setores_unidade_id ON setores (unidade_id);

CREATE TABLE turnos (
    id SERIAL NOT NULL, 
    unidade_id INTEGER NOT NULL, 
    codigo VARCHAR(30) NOT NULL, 
    nome VARCHAR(100) NOT NULL, 
    hora_inicio TIME WITHOUT TIME ZONE NOT NULL, 
    hora_fim TIME WITHOUT TIME ZONE NOT NULL, 
    ordem INTEGER NOT NULL, 
    ativo BOOLEAN NOT NULL, 
    criado_em TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
    atualizado_em TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    CHECK (hora_fim > hora_inicio), 
    FOREIGN KEY(unidade_id) REFERENCES unidades (id), 
    UNIQUE (unidade_id, codigo)
);

CREATE INDEX ix_turnos_unidade_id ON turnos (unidade_id);

CREATE TABLE calendario_excecoes (
    id SERIAL NOT NULL, 
    calendario_id INTEGER NOT NULL, 
    data DATE NOT NULL, 
    tipo VARCHAR(30) NOT NULL, 
    descricao VARCHAR(300), 
    hora_inicio TIME WITHOUT TIME ZONE, 
    hora_fim TIME WITHOUT TIME ZONE, 
    ativo BOOLEAN NOT NULL, 
    criado_em TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
    atualizado_em TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    CHECK (tipo in ('feriado','recesso','dia_letivo_extra','horario_especial')), 
    FOREIGN KEY(calendario_id) REFERENCES calendarios (id), 
    UNIQUE (calendario_id, data, tipo)
);

CREATE INDEX ix_calendario_excecoes_calendario_id ON calendario_excecoes (calendario_id);

CREATE INDEX ix_calendario_excecoes_data ON calendario_excecoes (data);

CREATE TABLE disponibilidade_ambientes (
    id SERIAL NOT NULL, 
    ambiente_id INTEGER NOT NULL, 
    dia_semana INTEGER NOT NULL, 
    hora_inicio TIME WITHOUT TIME ZONE NOT NULL, 
    hora_fim TIME WITHOUT TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    CHECK (dia_semana between 0 and 6), 
    CHECK (hora_fim > hora_inicio), 
    FOREIGN KEY(ambiente_id) REFERENCES ambientes (id) ON DELETE CASCADE
);

CREATE INDEX ix_disponibilidade_ambientes_ambiente_id ON disponibilidade_ambientes (ambiente_id);

CREATE TABLE execucoes_otimizacao (
    id SERIAL NOT NULL, 
    cenario_id INTEGER NOT NULL, 
    escopo JSONB NOT NULL, 
    parametros JSONB NOT NULL, 
    status VARCHAR(20) NOT NULL, 
    status_solver VARCHAR(30), 
    motivo_termino TEXT, 
    objetivo FLOAT, 
    limite_inferior FLOAT, 
    tempo_s FLOAT, 
    diagnosticos JSONB, 
    resultado JSONB, 
    criado_por_id INTEGER, 
    criado_em TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
    iniciado_em TIMESTAMP WITHOUT TIME ZONE, 
    finalizado_em TIMESTAMP WITHOUT TIME ZONE, 
    PRIMARY KEY (id), 
    CHECK (status in ('pendente','executando','concluida','falha','cancelada')), 
    FOREIGN KEY(cenario_id) REFERENCES cenarios_planejamento (id) ON DELETE CASCADE, 
    FOREIGN KEY(criado_por_id) REFERENCES usuarios (id)
);

CREATE INDEX ix_execucoes_otimizacao_cenario_id ON execucoes_otimizacao (cenario_id);

CREATE TABLE importacoes (
    id SERIAL NOT NULL, 
    arquivo_nome VARCHAR(300) NOT NULL, 
    arquivo_hash VARCHAR(64) NOT NULL, 
    tipo VARCHAR(40) NOT NULL, 
    status VARCHAR(20) NOT NULL, 
    mapeamento JSONB, 
    previa JSONB, 
    relatorio JSONB, 
    cenario_id INTEGER, 
    criado_por_id INTEGER, 
    criado_em TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
    confirmado_em TIMESTAMP WITHOUT TIME ZONE, 
    PRIMARY KEY (id), 
    FOREIGN KEY(cenario_id) REFERENCES cenarios_planejamento (id) ON DELETE SET NULL, 
    FOREIGN KEY(criado_por_id) REFERENCES usuarios (id)
);

CREATE INDEX ix_importacoes_arquivo_hash ON importacoes (arquivo_hash);

CREATE TABLE instrutores (
    id SERIAL NOT NULL, 
    matricula VARCHAR(40) NOT NULL, 
    nome VARCHAR(200) NOT NULL, 
    email VARCHAR(200), 
    unidade_id INTEGER NOT NULL, 
    areas_competencia TEXT, 
    carga_horaria_contratual NUMERIC(5, 2) NOT NULL, 
    limite_ch_letiva NUMERIC(5, 2) NOT NULL, 
    max_horas_dia NUMERIC(4, 2) NOT NULL, 
    intervalo_minimo_h NUMERIC(4, 2) NOT NULL, 
    turno_preferencial_id INTEGER, 
    restricoes_deslocamento TEXT, 
    situacao VARCHAR(20) NOT NULL, 
    ativo BOOLEAN NOT NULL, 
    criado_em TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
    atualizado_em TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    CHECK (limite_ch_letiva <= carga_horaria_contratual), 
    FOREIGN KEY(turno_preferencial_id) REFERENCES turnos (id), 
    FOREIGN KEY(unidade_id) REFERENCES unidades (id), 
    UNIQUE (matricula)
);

CREATE INDEX ix_instrutores_unidade_id ON instrutores (unidade_id);

CREATE TABLE matrizes_curriculares (
    id SERIAL NOT NULL, 
    curso_id INTEGER NOT NULL, 
    versao VARCHAR(30) NOT NULL, 
    vigencia_inicio DATE, 
    situacao VARCHAR(20) NOT NULL, 
    matriz_origem_id INTEGER, 
    ativo BOOLEAN NOT NULL, 
    criado_em TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
    atualizado_em TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(curso_id) REFERENCES cursos (id), 
    FOREIGN KEY(matriz_origem_id) REFERENCES matrizes_curriculares (id), 
    UNIQUE (curso_id, versao)
);

CREATE INDEX ix_matrizes_curriculares_curso_id ON matrizes_curriculares (curso_id);

CREATE TABLE periodos_horarios (
    id SERIAL NOT NULL, 
    unidade_id INTEGER NOT NULL, 
    turno_id INTEGER NOT NULL, 
    ordem INTEGER NOT NULL, 
    hora_inicio TIME WITHOUT TIME ZONE NOT NULL, 
    hora_fim TIME WITHOUT TIME ZONE NOT NULL, 
    dias_semana INTEGER[] NOT NULL, 
    excepcional BOOLEAN NOT NULL, 
    ativo BOOLEAN NOT NULL, 
    criado_em TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
    atualizado_em TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    CHECK (hora_fim > hora_inicio), 
    FOREIGN KEY(turno_id) REFERENCES turnos (id), 
    FOREIGN KEY(unidade_id) REFERENCES unidades (id), 
    UNIQUE (turno_id, ordem)
);

CREATE INDEX ix_periodos_horarios_turno_id ON periodos_horarios (turno_id);

CREATE INDEX ix_periodos_horarios_unidade_id ON periodos_horarios (unidade_id);

CREATE TABLE recursos_ambientes (
    id SERIAL NOT NULL, 
    recurso_id INTEGER NOT NULL, 
    ambiente_id INTEGER NOT NULL, 
    quantidade INTEGER NOT NULL, 
    PRIMARY KEY (id), 
    CHECK (quantidade > 0), 
    FOREIGN KEY(ambiente_id) REFERENCES ambientes (id) ON DELETE CASCADE, 
    FOREIGN KEY(recurso_id) REFERENCES recursos (id) ON DELETE CASCADE, 
    UNIQUE (recurso_id, ambiente_id)
);

CREATE INDEX ix_recursos_ambientes_ambiente_id ON recursos_ambientes (ambiente_id);

CREATE INDEX ix_recursos_ambientes_recurso_id ON recursos_ambientes (recurso_id);

CREATE TABLE registros_decisao (
    id SERIAL NOT NULL, 
    tipo VARCHAR(30) NOT NULL, 
    cenario_id INTEGER, 
    alocacao_id INTEGER, 
    dados JSONB NOT NULL, 
    motivo TEXT, 
    incluir_treinamento BOOLEAN NOT NULL, 
    revisado BOOLEAN NOT NULL, 
    usuario_id INTEGER, 
    criado_em TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    CHECK (tipo in ('sugestao','selecao','rejeicao','alteracao_manual','aprovacao','reprovacao','preferencia','resultado_cenario')), 
    FOREIGN KEY(cenario_id) REFERENCES cenarios_planejamento (id) ON DELETE SET NULL, 
    FOREIGN KEY(usuario_id) REFERENCES usuarios (id)
);

CREATE INDEX ix_registros_decisao_tipo ON registros_decisao (tipo);

CREATE TABLE simulacoes_capacidade (
    id SERIAL NOT NULL, 
    nome VARCHAR(200) NOT NULL, 
    tipo VARCHAR(20) NOT NULL, 
    parametros JSONB NOT NULL, 
    cenario_base_id INTEGER, 
    cenario_simulado_id INTEGER, 
    status VARCHAR(20) NOT NULL, 
    resultado JSONB, 
    criado_por_id INTEGER, 
    criado_em TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(cenario_base_id) REFERENCES cenarios_planejamento (id) ON DELETE SET NULL, 
    FOREIGN KEY(cenario_simulado_id) REFERENCES cenarios_planejamento (id) ON DELETE SET NULL, 
    FOREIGN KEY(criado_por_id) REFERENCES usuarios (id)
);

CREATE TABLE validacoes (
    id SERIAL NOT NULL, 
    cenario_id INTEGER NOT NULL, 
    total_bloqueios INTEGER NOT NULL, 
    total_alertas INTEGER NOT NULL, 
    total_preferencias INTEGER NOT NULL, 
    total_recomendacoes INTEGER NOT NULL, 
    executado_por_id INTEGER, 
    executado_em TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(cenario_id) REFERENCES cenarios_planejamento (id) ON DELETE CASCADE, 
    FOREIGN KEY(executado_por_id) REFERENCES usuarios (id)
);

CREATE INDEX ix_validacoes_cenario_id ON validacoes (cenario_id);

CREATE TABLE versoes_planejamento (
    id SERIAL NOT NULL, 
    cenario_id INTEGER NOT NULL, 
    numero INTEGER NOT NULL, 
    estado VARCHAR(30) NOT NULL, 
    motivo TEXT, 
    snapshot JSONB NOT NULL, 
    indicadores JSONB, 
    autor_id INTEGER, 
    criado_em TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(autor_id) REFERENCES usuarios (id), 
    FOREIGN KEY(cenario_id) REFERENCES cenarios_planejamento (id) ON DELETE CASCADE, 
    UNIQUE (cenario_id, numero)
);

CREATE INDEX ix_versoes_planejamento_cenario_id ON versoes_planejamento (cenario_id);

CREATE TABLE disponibilidade_instrutores (
    id SERIAL NOT NULL, 
    instrutor_id INTEGER NOT NULL, 
    dia_semana INTEGER NOT NULL, 
    hora_inicio TIME WITHOUT TIME ZONE NOT NULL, 
    hora_fim TIME WITHOUT TIME ZONE NOT NULL, 
    unidade_id INTEGER, 
    PRIMARY KEY (id), 
    CHECK (dia_semana between 0 and 6), 
    CHECK (hora_fim > hora_inicio), 
    FOREIGN KEY(instrutor_id) REFERENCES instrutores (id) ON DELETE CASCADE, 
    FOREIGN KEY(unidade_id) REFERENCES unidades (id)
);

CREATE INDEX ix_disponibilidade_instrutores_instrutor_id ON disponibilidade_instrutores (instrutor_id);

CREATE TABLE habilitacoes_instrutores (
    id SERIAL NOT NULL, 
    instrutor_id INTEGER NOT NULL, 
    nome VARCHAR(200) NOT NULL, 
    valido_ate DATE, 
    ativo BOOLEAN NOT NULL, 
    criado_em TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
    atualizado_em TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(instrutor_id) REFERENCES instrutores (id) ON DELETE CASCADE, 
    UNIQUE (instrutor_id, nome)
);

CREATE INDEX ix_habilitacoes_instrutores_instrutor_id ON habilitacoes_instrutores (instrutor_id);

CREATE TABLE instrutor_unidades (
    instrutor_id INTEGER NOT NULL, 
    unidade_id INTEGER NOT NULL, 
    PRIMARY KEY (instrutor_id, unidade_id), 
    FOREIGN KEY(instrutor_id) REFERENCES instrutores (id) ON DELETE CASCADE, 
    FOREIGN KEY(unidade_id) REFERENCES unidades (id)
);

CREATE TABLE ocorrencias_validacao (
    id SERIAL NOT NULL, 
    validacao_id INTEGER NOT NULL, 
    severidade VARCHAR(20) NOT NULL, 
    regra VARCHAR(60) NOT NULL, 
    descricao TEXT NOT NULL, 
    recurso_tipo VARCHAR(20), 
    recurso_id INTEGER, 
    data DATE, 
    inicio TIMESTAMP WITHOUT TIME ZONE, 
    fim TIMESTAMP WITHOUT TIME ZONE, 
    turma_id INTEGER, 
    uc_id INTEGER, 
    instrutor_id INTEGER, 
    ambiente_id INTEGER, 
    alocacao_id INTEGER, 
    origem VARCHAR(30), 
    PRIMARY KEY (id), 
    CHECK (severidade in ('bloqueio','alerta','preferencia','recomendacao')), 
    FOREIGN KEY(validacao_id) REFERENCES validacoes (id) ON DELETE CASCADE
);

CREATE INDEX ix_ocorrencias_validacao_validacao_id ON ocorrencias_validacao (validacao_id);

CREATE TABLE resultados_otimizacao (
    id SERIAL NOT NULL, 
    execucao_id INTEGER NOT NULL, 
    criterio VARCHAR(60) NOT NULL, 
    valor_bruto FLOAT NOT NULL, 
    peso FLOAT NOT NULL, 
    pontos FLOAT NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(execucao_id) REFERENCES execucoes_otimizacao (id) ON DELETE CASCADE
);

CREATE INDEX ix_resultados_otimizacao_execucao_id ON resultados_otimizacao (execucao_id);

CREATE TABLE turmas (
    id SERIAL NOT NULL, 
    codigo VARCHAR(40) NOT NULL, 
    nome VARCHAR(200) NOT NULL, 
    curso_id INTEGER NOT NULL, 
    matriz_id INTEGER NOT NULL, 
    unidade_id INTEGER NOT NULL, 
    calendario_id INTEGER, 
    turno_id INTEGER, 
    qtd_alunos INTEGER NOT NULL, 
    capacidade_prevista INTEGER, 
    data_inicio DATE NOT NULL, 
    data_fim DATE NOT NULL, 
    dias_possiveis INTEGER[] NOT NULL, 
    num_grupos INTEGER NOT NULL, 
    prioridade INTEGER NOT NULL, 
    necessidades_acessibilidade BOOLEAN NOT NULL, 
    restricoes TEXT, 
    situacao VARCHAR(20) NOT NULL, 
    simulacao_id INTEGER, 
    ativo BOOLEAN NOT NULL, 
    criado_em TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
    atualizado_em TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    CHECK (data_fim >= data_inicio), 
    CHECK (num_grupos between 1 and 16), 
    CHECK (qtd_alunos >= 0), 
    FOREIGN KEY(calendario_id) REFERENCES calendarios (id), 
    FOREIGN KEY(curso_id) REFERENCES cursos (id), 
    FOREIGN KEY(matriz_id) REFERENCES matrizes_curriculares (id), 
    FOREIGN KEY(simulacao_id) REFERENCES simulacoes_capacidade (id) ON DELETE CASCADE, 
    FOREIGN KEY(turno_id) REFERENCES turnos (id), 
    FOREIGN KEY(unidade_id) REFERENCES unidades (id), 
    UNIQUE (codigo)
);

CREATE INDEX ix_turmas_curso_id ON turmas (curso_id);

CREATE INDEX ix_turmas_matriz_id ON turmas (matriz_id);

CREATE INDEX ix_turmas_simulacao_id ON turmas (simulacao_id);

CREATE INDEX ix_turmas_unidade_id ON turmas (unidade_id);

CREATE TABLE unidades_curriculares (
    id SERIAL NOT NULL, 
    matriz_id INTEGER NOT NULL, 
    codigo VARCHAR(30) NOT NULL, 
    nome VARCHAR(200) NOT NULL, 
    carga_horaria_total INTEGER NOT NULL, 
    ch_teorica INTEGER, 
    ch_pratica INTEGER, 
    ch_semanal_desejada NUMERIC(6, 2), 
    duracao_bloco_periodos INTEGER NOT NULL, 
    encontros_semanais INTEGER NOT NULL, 
    sequencia INTEGER NOT NULL, 
    modulo VARCHAR(60), 
    competencias TEXT, 
    certificacao_exigida VARCHAR(200), 
    capacidade_min INTEGER, 
    capacidade_max INTEGER, 
    divide_grupos BOOLEAN NOT NULL, 
    aulas_consecutivas BOOLEAN NOT NULL, 
    restricoes_pedagogicas TEXT, 
    prioridade INTEGER NOT NULL, 
    ativo BOOLEAN NOT NULL, 
    criado_em TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
    atualizado_em TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    CHECK (carga_horaria_total > 0), 
    CHECK (duracao_bloco_periodos >= 1), 
    CHECK (encontros_semanais >= 1), 
    FOREIGN KEY(matriz_id) REFERENCES matrizes_curriculares (id), 
    UNIQUE (matriz_id, codigo)
);

CREATE INDEX ix_unidades_curriculares_matriz_id ON unidades_curriculares (matriz_id);

CREATE TABLE competencias_instrutores (
    id SERIAL NOT NULL, 
    instrutor_id INTEGER NOT NULL, 
    uc_id INTEGER NOT NULL, 
    nivel VARCHAR(20) NOT NULL, 
    condicoes TEXT, 
    valido_ate DATE, 
    ativo BOOLEAN NOT NULL, 
    criado_em TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
    atualizado_em TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    CHECK (nivel in ('pleno','supervisionado','em_formacao')), 
    FOREIGN KEY(instrutor_id) REFERENCES instrutores (id) ON DELETE CASCADE, 
    FOREIGN KEY(uc_id) REFERENCES unidades_curriculares (id), 
    UNIQUE (instrutor_id, uc_id)
);

CREATE INDEX ix_competencias_instrutores_instrutor_id ON competencias_instrutores (instrutor_id);

CREATE INDEX ix_competencias_instrutores_uc_id ON competencias_instrutores (uc_id);

CREATE TABLE turma_uc (
    id SERIAL NOT NULL, 
    turma_id INTEGER NOT NULL, 
    uc_id INTEGER NOT NULL, 
    situacao VARCHAR(20) NOT NULL, 
    data_inicio DATE, 
    data_limite DATE, 
    ch_realizada NUMERIC(7, 2) NOT NULL, 
    instrutor_preferido_id INTEGER, 
    ativo BOOLEAN NOT NULL, 
    criado_em TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
    atualizado_em TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    CHECK (situacao in ('prevista','ofertada','em_execucao','concluida','pendente','cancelada')), 
    CHECK (ch_realizada >= 0), 
    FOREIGN KEY(instrutor_preferido_id) REFERENCES instrutores (id), 
    FOREIGN KEY(turma_id) REFERENCES turmas (id) ON DELETE CASCADE, 
    FOREIGN KEY(uc_id) REFERENCES unidades_curriculares (id), 
    UNIQUE (turma_id, uc_id)
);

CREATE INDEX ix_turma_uc_turma_id ON turma_uc (turma_id);

CREATE INDEX ix_turma_uc_uc_id ON turma_uc (uc_id);

CREATE TABLE uc_prerequisitos (
    uc_id INTEGER NOT NULL, 
    prerequisito_id INTEGER NOT NULL, 
    PRIMARY KEY (uc_id, prerequisito_id), 
    CHECK (uc_id <> prerequisito_id), 
    FOREIGN KEY(prerequisito_id) REFERENCES unidades_curriculares (id), 
    FOREIGN KEY(uc_id) REFERENCES unidades_curriculares (id) ON DELETE CASCADE
);

CREATE TABLE uc_recursos (
    uc_id INTEGER NOT NULL, 
    recurso_tipo VARCHAR(60) NOT NULL, 
    quantidade INTEGER NOT NULL, 
    PRIMARY KEY (uc_id, recurso_tipo), 
    CHECK (quantidade > 0), 
    FOREIGN KEY(uc_id) REFERENCES unidades_curriculares (id) ON DELETE CASCADE
);

CREATE TABLE uc_tipos_ambiente (
    uc_id INTEGER NOT NULL, 
    tipo_ambiente_id INTEGER NOT NULL, 
    PRIMARY KEY (uc_id, tipo_ambiente_id), 
    FOREIGN KEY(tipo_ambiente_id) REFERENCES tipos_ambiente (id), 
    FOREIGN KEY(uc_id) REFERENCES unidades_curriculares (id) ON DELETE CASCADE
);

CREATE TABLE atividades (
    id SERIAL NOT NULL, 
    cenario_id INTEGER NOT NULL, 
    turma_uc_id INTEGER NOT NULL, 
    grupo INTEGER, 
    instrutor_id INTEGER, 
    ambiente_id INTEGER, 
    dia_semana INTEGER NOT NULL, 
    periodo_inicio_id INTEGER NOT NULL, 
    num_periodos INTEGER NOT NULL, 
    data_inicio DATE NOT NULL, 
    data_fim DATE NOT NULL, 
    fixa BOOLEAN NOT NULL, 
    origem VARCHAR(20) NOT NULL, 
    execucao_id INTEGER, 
    criado_em TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    CHECK (dia_semana between 0 and 6), 
    CHECK (num_periodos >= 1), 
    FOREIGN KEY(ambiente_id) REFERENCES ambientes (id), 
    FOREIGN KEY(cenario_id) REFERENCES cenarios_planejamento (id) ON DELETE CASCADE, 
    FOREIGN KEY(execucao_id) REFERENCES execucoes_otimizacao (id) ON DELETE SET NULL, 
    FOREIGN KEY(instrutor_id) REFERENCES instrutores (id), 
    FOREIGN KEY(periodo_inicio_id) REFERENCES periodos_horarios (id), 
    FOREIGN KEY(turma_uc_id) REFERENCES turma_uc (id) ON DELETE CASCADE
);

CREATE INDEX ix_atividades_cenario_id ON atividades (cenario_id);

CREATE INDEX ix_atividades_turma_uc_id ON atividades (turma_uc_id);

CREATE TABLE alocacoes (
    id SERIAL NOT NULL, 
    cenario_id INTEGER NOT NULL, 
    atividade_id INTEGER, 
    turma_uc_id INTEGER NOT NULL, 
    turma_id INTEGER NOT NULL, 
    uc_id INTEGER NOT NULL, 
    grupo INTEGER, 
    grupos INTEGER[] NOT NULL, 
    instrutor_id INTEGER, 
    ambiente_id INTEGER, 
    data DATE NOT NULL, 
    inicio TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
    fim TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
    fim_ambiente TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
    minutos_aula INTEGER NOT NULL, 
    intervalo TSRANGE GENERATED ALWAYS AS (tsrange(inicio, fim, '[)')) STORED, 
    intervalo_ambiente TSRANGE GENERATED ALWAYS AS (tsrange(inicio, fim_ambiente, '[)')) STORED, 
    status VARCHAR(20) NOT NULL, 
    fixa BOOLEAN NOT NULL, 
    origem VARCHAR(20) NOT NULL, 
    observacao TEXT, 
    excecao_id INTEGER, 
    versao INTEGER NOT NULL, 
    criado_por_id INTEGER, 
    criado_em TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
    atualizado_em TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    CONSTRAINT excl_alocacao_ambiente EXCLUDE USING gist (cenario_id WITH =, ambiente_id WITH =, intervalo_ambiente WITH &&) WHERE (status <> 'cancelada' AND ambiente_id IS NOT NULL), 
    CONSTRAINT excl_alocacao_instrutor EXCLUDE USING gist (cenario_id WITH =, instrutor_id WITH =, intervalo WITH &&) WHERE (status <> 'cancelada' AND instrutor_id IS NOT NULL), 
    CONSTRAINT excl_alocacao_turma_grupos EXCLUDE USING gist (cenario_id WITH =, turma_id WITH =, grupos gist__int_ops WITH &&, intervalo WITH &&) WHERE (status <> 'cancelada'), 
    CHECK (status in ('programada','realizada','cancelada')), 
    CHECK (fim > inicio), 
    CHECK (fim_ambiente >= fim), 
    CHECK (minutos_aula > 0), 
    FOREIGN KEY(ambiente_id) REFERENCES ambientes (id), 
    FOREIGN KEY(atividade_id) REFERENCES atividades (id) ON DELETE SET NULL, 
    FOREIGN KEY(cenario_id) REFERENCES cenarios_planejamento (id) ON DELETE CASCADE, 
    FOREIGN KEY(criado_por_id) REFERENCES usuarios (id), 
    FOREIGN KEY(excecao_id) REFERENCES excecoes_autorizadas (id), 
    FOREIGN KEY(instrutor_id) REFERENCES instrutores (id), 
    FOREIGN KEY(turma_id) REFERENCES turmas (id) ON DELETE CASCADE, 
    FOREIGN KEY(turma_uc_id) REFERENCES turma_uc (id) ON DELETE CASCADE, 
    FOREIGN KEY(uc_id) REFERENCES unidades_curriculares (id)
);

CREATE INDEX ix_alocacoes_ambiente_id ON alocacoes (ambiente_id);

CREATE INDEX ix_alocacoes_atividade_id ON alocacoes (atividade_id);

CREATE INDEX ix_alocacoes_cenario_data ON alocacoes (cenario_id, data);

CREATE INDEX ix_alocacoes_cenario_id ON alocacoes (cenario_id);

CREATE INDEX ix_alocacoes_instrutor_id ON alocacoes (instrutor_id);

CREATE INDEX ix_alocacoes_turma_id ON alocacoes (turma_id);

CREATE INDEX ix_alocacoes_turma_uc_id ON alocacoes (turma_uc_id);

CREATE INDEX ix_alocacoes_uc_id ON alocacoes (uc_id);

CREATE TABLE alocacao_recursos (
    alocacao_id INTEGER NOT NULL, 
    recurso_id INTEGER NOT NULL, 
    quantidade INTEGER NOT NULL, 
    PRIMARY KEY (alocacao_id, recurso_id), 
    CHECK (quantidade > 0), 
    FOREIGN KEY(alocacao_id) REFERENCES alocacoes (id) ON DELETE CASCADE, 
    FOREIGN KEY(recurso_id) REFERENCES recursos (id)
);

INSERT INTO alembic_version (version_num) VALUES ('0001') RETURNING alembic_version.version_num;

-- Running upgrade 0001 -> 0002

ALTER TABLE usuarios ADD COLUMN auth_user_id VARCHAR(36);

ALTER TABLE usuarios ADD CONSTRAINT uq_usuarios_auth_user_id UNIQUE (auth_user_id);

ALTER TABLE importacoes ADD COLUMN conteudo BYTEA;

ALTER TABLE execucoes_otimizacao ADD COLUMN worker VARCHAR(120);

ALTER TABLE execucoes_otimizacao ADD COLUMN heartbeat_em TIMESTAMP WITHOUT TIME ZONE;

ALTER TABLE simulacoes_capacidade ADD COLUMN worker VARCHAR(120);

ALTER TABLE simulacoes_capacidade ADD COLUMN heartbeat_em TIMESTAMP WITHOUT TIME ZONE;

ALTER TABLE simulacoes_capacidade ADD COLUMN iniciado_em TIMESTAMP WITHOUT TIME ZONE;

ALTER TABLE simulacoes_capacidade ADD COLUMN finalizado_em TIMESTAMP WITHOUT TIME ZONE;

CREATE INDEX ix_execucoes_fila ON execucoes_otimizacao (id) WHERE status IN ('pendente','executando');

CREATE INDEX ix_simulacoes_fila ON simulacoes_capacidade (id) WHERE status IN ('pendente','executando');

DO $$
DECLARE t record;
BEGIN
  FOR t IN SELECT tablename FROM pg_tables WHERE schemaname = 'public' LOOP
    EXECUTE 'ALTER TABLE public.' || quote_ident(t.tablename) || ' ENABLE ROW LEVEL SECURITY';
  END LOOP;
  -- Papéis da Data API do Supabase (inexistentes em PostgreSQL comum).
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
    EXECUTE 'REVOKE ALL ON ALL TABLES IN SCHEMA public FROM anon';
    EXECUTE 'REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM anon';
    EXECUTE 'REVOKE ALL ON ALL FUNCTIONS IN SCHEMA public FROM anon';
    EXECUTE 'ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON TABLES FROM anon';
    EXECUTE 'ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON SEQUENCES FROM anon';
  END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
    EXECUTE 'REVOKE ALL ON ALL TABLES IN SCHEMA public FROM authenticated';
    EXECUTE 'REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM authenticated';
    EXECUTE 'REVOKE ALL ON ALL FUNCTIONS IN SCHEMA public FROM authenticated';
    EXECUTE 'ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON TABLES FROM authenticated';
    EXECUTE 'ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON SEQUENCES FROM authenticated';
  END IF;
END $$;;

UPDATE alembic_version SET version_num='0002' WHERE alembic_version.version_num = '0001';

-- Running upgrade 0002 -> 0003

CREATE TABLE areas (
    id SERIAL NOT NULL, 
    unidade_id INTEGER NOT NULL, 
    codigo VARCHAR(40) NOT NULL, 
    nome VARCHAR(100) NOT NULL, 
    ativo BOOLEAN NOT NULL, 
    criado_em TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
    atualizado_em TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(unidade_id) REFERENCES unidades (id), 
    UNIQUE (codigo)
);

CREATE INDEX ix_areas_unidade_id ON areas (unidade_id);

ALTER TABLE cursos ADD COLUMN area_id INTEGER;

ALTER TABLE cursos ADD FOREIGN KEY(area_id) REFERENCES areas (id);

CREATE INDEX ix_cursos_area_id ON cursos (area_id);

ALTER TABLE turmas ADD COLUMN area_id INTEGER;

ALTER TABLE turmas ADD FOREIGN KEY(area_id) REFERENCES areas (id);

CREATE INDEX ix_turmas_area_id ON turmas (area_id);

ALTER TABLE instrutores ADD COLUMN area_id INTEGER;

ALTER TABLE instrutores ADD FOREIGN KEY(area_id) REFERENCES areas (id);

CREATE INDEX ix_instrutores_area_id ON instrutores (area_id);

ALTER TABLE ambientes ADD COLUMN area_id INTEGER;

ALTER TABLE ambientes ADD FOREIGN KEY(area_id) REFERENCES areas (id);

CREATE INDEX ix_ambientes_area_id ON ambientes (area_id);

INSERT INTO unidades (codigo, nome, situacao, ativo) VALUES
  ('BEIRA-MAR', 'Unidade Beira Mar', 'ativa', true),
  ('PORTO', 'Unidade Porto', 'ativa', true)
ON CONFLICT (codigo) DO NOTHING;

INSERT INTO areas (unidade_id, codigo, nome, ativo)
SELECT u.id, a.codigo, a.nome, true
FROM (VALUES
  ('AUTOMACAO', 'AUTOMAÇÃO', 'BEIRA-MAR'), ('ENERGIAS', 'ENERGIAS', 'BEIRA-MAR'), ('AUTOMOTIVA', 'AUTOMOTIVA', 'BEIRA-MAR'),
  ('MECATRONICA', 'MECATRÔNICA', 'BEIRA-MAR'), ('MECANICA', 'MECÂNICA', 'BEIRA-MAR'), ('INSTRUMENTACAO', 'INSTRUMENTAÇÃO', 'BEIRA-MAR'),
  ('LOGISTICA', 'LOGÍSTICA', 'PORTO'), ('PORTOS', 'PORTOS', 'PORTO'), ('DDS-TI', 'DDS/TI', 'PORTO'),
  ('ECONOMIA-CRIATIVA', 'ECONOMIA CRIATIVA', 'PORTO'), ('GESTAO', 'GESTÃO', 'PORTO')
) AS a(codigo, nome, unidade)
JOIN unidades u ON u.codigo = a.unidade
ON CONFLICT (codigo) DO NOTHING;

-- Turnos oficiais (4 aulas; manhã/tarde 55 min, noite 50 min) nas unidades que ainda não têm turnos
INSERT INTO turnos (unidade_id, codigo, nome, hora_inicio, hora_fim, ordem, ativo)
SELECT u.id, t.codigo, t.nome, t.ini::time, t.fim::time, t.ordem, true
FROM unidades u
CROSS JOIN (VALUES ('M', 'Manhã', '07:30', '11:30', 1), ('T', 'Tarde', '13:30', '17:30', 2), ('N', 'Noite', '18:20', '21:50', 3))
  AS t(codigo, nome, ini, fim, ordem)
WHERE u.codigo IN ('BEIRA-MAR', 'PORTO')
  AND NOT EXISTS (SELECT 1 FROM turnos x WHERE x.unidade_id = u.id);

INSERT INTO periodos_horarios (unidade_id, turno_id, ordem, hora_inicio, hora_fim, dias_semana, excepcional, ativo)
SELECT t.unidade_id, t.id, p.ordem, p.ini::time, p.fim::time, '{0,1,2,3,4}', false, true
FROM turnos t
JOIN unidades u ON u.id = t.unidade_id AND u.codigo IN ('BEIRA-MAR', 'PORTO')
JOIN (VALUES
  ('M', 1, '07:30', '08:25'), ('M', 2, '08:25', '09:20'), ('M', 3, '09:40', '10:35'), ('M', 4, '10:35', '11:30'),
  ('T', 1, '13:30', '14:25'), ('T', 2, '14:25', '15:20'), ('T', 3, '15:40', '16:35'), ('T', 4, '16:35', '17:30'),
  ('N', 1, '18:20', '19:10'), ('N', 2, '19:10', '20:00'), ('N', 3, '20:10', '21:00'), ('N', 4, '21:00', '21:50')
) AS p(turno, ordem, ini, fim) ON p.turno = t.codigo
WHERE NOT EXISTS (SELECT 1 FROM periodos_horarios x WHERE x.turno_id = t.id);

-- Regras de composição das aulas (padrão da instituição), se ainda não registradas
INSERT INTO configuracoes (chave, valor, descricao) VALUES ('regras_aula', '{"turno_inteiro": true, "contagem": "hora_aula"}'::jsonb,
  'Composição das aulas: com ''turno inteiro'', cada UC ocupa todas as aulas do turno no dia; aula parcial só no fechamento da carga horária (dividindo o turno com outra UC que também esteja fechando). ''hora_aula'': cada aula conta 1 h de carga horária.')
ON CONFLICT (chave) DO NOTHING;

-- Segurança: mesma política das demais tabelas (RLS e sem acesso pela Data API pública)
ALTER TABLE public.areas ENABLE ROW LEVEL SECURITY;
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
    EXECUTE 'REVOKE ALL ON public.areas FROM anon';
  END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
    EXECUTE 'REVOKE ALL ON public.areas FROM authenticated';
  END IF;
END $$;

UPDATE alembic_version SET version_num='0003' WHERE alembic_version.version_num = '0002';

-- Running upgrade 0003 -> 0004

ALTER TABLE instrutores ADD COLUMN todas_areas BOOLEAN DEFAULT false NOT NULL;

ALTER TABLE ambientes ADD COLUMN todas_areas BOOLEAN DEFAULT false NOT NULL;

CREATE TABLE instrutor_areas (
    instrutor_id INTEGER NOT NULL, 
    area_id INTEGER NOT NULL, 
    PRIMARY KEY (instrutor_id, area_id), 
    FOREIGN KEY(instrutor_id) REFERENCES instrutores (id) ON DELETE CASCADE, 
    FOREIGN KEY(area_id) REFERENCES areas (id)
);

CREATE TABLE ambiente_areas (
    ambiente_id INTEGER NOT NULL, 
    area_id INTEGER NOT NULL, 
    PRIMARY KEY (ambiente_id, area_id), 
    FOREIGN KEY(ambiente_id) REFERENCES ambientes (id) ON DELETE CASCADE, 
    FOREIGN KEY(area_id) REFERENCES areas (id)
);

ALTER TABLE public.instrutor_areas ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.ambiente_areas ENABLE ROW LEVEL SECURITY;
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
    EXECUTE 'REVOKE ALL ON public.instrutor_areas, public.ambiente_areas FROM anon';
  END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
    EXECUTE 'REVOKE ALL ON public.instrutor_areas, public.ambiente_areas FROM authenticated';
  END IF;
END $$;

ALTER TABLE excecoes_autorizadas DROP CONSTRAINT IF EXISTS excecoes_autorizadas_tipo_check;

ALTER TABLE excecoes_autorizadas ADD CONSTRAINT excecoes_autorizadas_tipo_check CHECK (tipo IN ('feriado_bloqueio', 'carga_horaria', 'regra_academica'));

UPDATE alembic_version SET version_num='0004' WHERE alembic_version.version_num = '0003';

-- Running upgrade 0004 -> 0005

ALTER TABLE usuarios DROP CONSTRAINT IF EXISTS usuarios_perfil_check;

ALTER TABLE usuarios ADD CONSTRAINT usuarios_perfil_check CHECK (perfil in ('administrador','planejador','coordenador','gestor','consulta','instrutor'));

ALTER TABLE usuarios ADD COLUMN instrutor_id INTEGER;

ALTER TABLE usuarios ADD FOREIGN KEY(instrutor_id) REFERENCES instrutores (id) ON DELETE SET NULL;

ALTER TABLE usuarios ADD CONSTRAINT usuarios_instrutor_id_key UNIQUE (instrutor_id);

ALTER TABLE instrutores ADD COLUMN atualizado_pelo_instrutor_em TIMESTAMP WITHOUT TIME ZONE;

CREATE TABLE observacoes_instrutor (
    id SERIAL NOT NULL, 
    instrutor_id INTEGER NOT NULL, 
    turma_uc_id INTEGER, 
    tipo VARCHAR(30) NOT NULL, 
    texto TEXT NOT NULL, 
    status VARCHAR(20) DEFAULT 'nova' NOT NULL, 
    resposta TEXT, 
    respondido_por_id INTEGER, 
    respondido_em TIMESTAMP WITHOUT TIME ZONE, 
    criado_em TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    CONSTRAINT observacoes_instrutor_status_check CHECK (status in ('nova','lida','resolvida')), 
    FOREIGN KEY(instrutor_id) REFERENCES instrutores (id) ON DELETE CASCADE, 
    FOREIGN KEY(turma_uc_id) REFERENCES turma_uc (id) ON DELETE CASCADE, 
    FOREIGN KEY(respondido_por_id) REFERENCES usuarios (id) ON DELETE SET NULL
);

CREATE INDEX ix_observacoes_instrutor_instrutor_id ON observacoes_instrutor (instrutor_id);

CREATE INDEX ix_observacoes_instrutor_turma_uc_id ON observacoes_instrutor (turma_uc_id);

CREATE TABLE notificacoes (
    id SERIAL NOT NULL, 
    instrutor_id INTEGER NOT NULL, 
    tipo VARCHAR(30) NOT NULL, 
    titulo VARCHAR(200) NOT NULL, 
    texto TEXT, 
    aba VARCHAR(20), 
    lida BOOLEAN DEFAULT false NOT NULL, 
    criado_em TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(instrutor_id) REFERENCES instrutores (id) ON DELETE CASCADE
);

CREATE INDEX ix_notificacoes_instrutor_id ON notificacoes (instrutor_id);

ALTER TABLE alocacoes ADD COLUMN instrutor_titular_id INTEGER;

ALTER TABLE alocacoes ADD FOREIGN KEY(instrutor_titular_id) REFERENCES instrutores (id) ON DELETE SET NULL;

ALTER TABLE public.observacoes_instrutor ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.notificacoes ENABLE ROW LEVEL SECURITY;
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
    EXECUTE 'REVOKE ALL ON public.observacoes_instrutor, public.notificacoes FROM anon';
  END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
    EXECUTE 'REVOKE ALL ON public.observacoes_instrutor, public.notificacoes FROM authenticated';
  END IF;
END $$;

INSERT INTO permissoes_perfil (perfil, acao) VALUES ('instrutor', 'portal.instrutor') ON CONFLICT DO NOTHING;

INSERT INTO permissoes_perfil (perfil, acao) VALUES ('administrador', 'observacoes.gerenciar') ON CONFLICT DO NOTHING;

INSERT INTO permissoes_perfil (perfil, acao) VALUES ('planejador', 'observacoes.gerenciar') ON CONFLICT DO NOTHING;

INSERT INTO permissoes_perfil (perfil, acao) VALUES ('coordenador', 'observacoes.gerenciar') ON CONFLICT DO NOTHING;

UPDATE alembic_version SET version_num='0005' WHERE alembic_version.version_num = '0004';

-- Running upgrade 0005 -> 0006

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM turnos WHERE codigo = 'N' AND hora_inicio = '18:20' AND hora_fim = '21:50') THEN
    UPDATE alocacoes a SET inicio = a.inicio + interval '100 years', fim = a.fim + interval '100 years',
                           fim_ambiente = a.fim_ambiente + interval '100 years'
      FROM turmas t JOIN turnos tn ON tn.id = t.turno_id
     WHERE a.turma_id = t.id AND tn.codigo = 'N' AND tn.hora_inicio = '18:20'
       AND a.inicio::time >= '18:20' AND a.fim::time <= '21:50';
    UPDATE alocacoes SET inicio = inicio - interval '100 years' + interval '10 minutes',
                         fim = fim - interval '100 years' + interval '10 minutes',
                         fim_ambiente = fim_ambiente - interval '100 years' + interval '10 minutes'
     WHERE inicio > timestamp '2100-01-01';
    UPDATE periodos_horarios p SET hora_inicio = p.hora_inicio + interval '10 minutes', hora_fim = p.hora_fim + interval '10 minutes'
      FROM turnos t WHERE p.turno_id = t.id AND t.codigo = 'N' AND t.hora_inicio = '18:20';
    UPDATE turnos SET hora_inicio = '18:30', hora_fim = '22:00' WHERE codigo = 'N' AND hora_inicio = '18:20' AND hora_fim = '21:50';
    UPDATE disponibilidade_instrutores SET hora_inicio = '18:30' WHERE hora_inicio = '18:20';
    UPDATE disponibilidade_instrutores SET hora_fim = '22:00' WHERE hora_fim = '21:50';
    UPDATE disponibilidade_ambientes SET hora_inicio = '18:30' WHERE hora_inicio = '18:20';
    UPDATE disponibilidade_ambientes SET hora_fim = '22:00' WHERE hora_fim = '21:50';
    UPDATE horarios_funcionamento SET hora_fim = '22:00' WHERE hora_fim = '21:50';
    UPDATE bloqueios SET inicio = inicio + interval '10 minutes', fim = fim + interval '10 minutes'
     WHERE alvo_tipo = 'instrutor' AND inicio::time = '18:20' AND fim::time = '21:50';
  END IF;
END $$;

UPDATE alembic_version SET version_num='0006' WHERE alembic_version.version_num = '0005';

-- Running upgrade 0006 -> 0007

ALTER TABLE instrutores ADD COLUMN modalidade VARCHAR(12) DEFAULT 'mensalista' NOT NULL;

ALTER TABLE instrutores ADD CONSTRAINT instrutores_modalidade_check CHECK (modalidade in ('mensalista','horista'));

UPDATE alembic_version SET version_num='0007' WHERE alembic_version.version_num = '0006';

-- Running upgrade 0007 -> 0008

ALTER TABLE usuarios DROP CONSTRAINT IF EXISTS usuarios_perfil_check;

UPDATE usuarios SET perfil = 'planejador' WHERE perfil = 'coordenador';

UPDATE usuarios SET perfil = 'observador' WHERE perfil IN ('gestor', 'consulta');

ALTER TABLE usuarios ADD CONSTRAINT usuarios_perfil_check CHECK (perfil in ('administrador','planejador','instrutor','observador'));

DELETE FROM permissoes_perfil WHERE perfil IN ('coordenador', 'gestor', 'consulta');

INSERT INTO permissoes_perfil (perfil, acao) VALUES ('observador', 'cadastros.ler') ON CONFLICT DO NOTHING;

INSERT INTO permissoes_perfil (perfil, acao) VALUES ('observador', 'alocacoes.ler') ON CONFLICT DO NOTHING;

INSERT INTO permissoes_perfil (perfil, acao) VALUES ('observador', 'indicadores.ler') ON CONFLICT DO NOTHING;

INSERT INTO permissoes_perfil (perfil, acao) VALUES ('observador', 'exportacao.executar') ON CONFLICT DO NOTHING;

UPDATE alembic_version SET version_num='0008' WHERE alembic_version.version_num = '0007';

-- Running upgrade 0008 -> 0009

ALTER TABLE instrutores ADD COLUMN nivel VARCHAR(10) DEFAULT 'tecnico' NOT NULL;

ALTER TABLE instrutores ADD CONSTRAINT instrutores_nivel_check CHECK (nivel in ('basico','tecnico'));

ALTER TABLE turmas ADD COLUMN dias_ead INTEGER[] DEFAULT '{}' NOT NULL;

UPDATE alembic_version SET version_num='0009' WHERE alembic_version.version_num = '0008';

-- Running upgrade 0009 -> 0010

ALTER TABLE usuarios DROP CONSTRAINT IF EXISTS usuarios_perfil_check;

ALTER TABLE usuarios ADD CONSTRAINT usuarios_perfil_check CHECK (perfil in ('administrador','planejador','coordenador','instrutor','observador'));

INSERT INTO permissoes_perfil (perfil, acao) VALUES ('coordenador', 'cadastros.ler') ON CONFLICT DO NOTHING;

INSERT INTO permissoes_perfil (perfil, acao) VALUES ('coordenador', 'cadastros.editar') ON CONFLICT DO NOTHING;

INSERT INTO permissoes_perfil (perfil, acao) VALUES ('coordenador', 'alocacoes.ler') ON CONFLICT DO NOTHING;

INSERT INTO permissoes_perfil (perfil, acao) VALUES ('coordenador', 'alocacoes.editar') ON CONFLICT DO NOTHING;

INSERT INTO permissoes_perfil (perfil, acao) VALUES ('coordenador', 'cenarios.criar') ON CONFLICT DO NOTHING;

INSERT INTO permissoes_perfil (perfil, acao) VALUES ('coordenador', 'cenarios.editar') ON CONFLICT DO NOTHING;

INSERT INTO permissoes_perfil (perfil, acao) VALUES ('coordenador', 'otimizacao.executar') ON CONFLICT DO NOTHING;

INSERT INTO permissoes_perfil (perfil, acao) VALUES ('coordenador', 'simulacao.executar') ON CONFLICT DO NOTHING;

INSERT INTO permissoes_perfil (perfil, acao) VALUES ('coordenador', 'indicadores.ler') ON CONFLICT DO NOTHING;

INSERT INTO permissoes_perfil (perfil, acao) VALUES ('coordenador', 'importacao.executar') ON CONFLICT DO NOTHING;

INSERT INTO permissoes_perfil (perfil, acao) VALUES ('coordenador', 'exportacao.executar') ON CONFLICT DO NOTHING;

INSERT INTO permissoes_perfil (perfil, acao) VALUES ('coordenador', 'dados_pessoais.ler') ON CONFLICT DO NOTHING;

INSERT INTO permissoes_perfil (perfil, acao) VALUES ('coordenador', 'observacoes.gerenciar') ON CONFLICT DO NOTHING;

INSERT INTO permissoes_perfil (perfil, acao) VALUES ('coordenador', 'solicitacoes.aprovar') ON CONFLICT DO NOTHING;

INSERT INTO permissoes_perfil (perfil, acao) VALUES ('administrador', 'solicitacoes.aprovar') ON CONFLICT DO NOTHING;

CREATE TABLE solicitacoes_instrutor (
    id SERIAL NOT NULL, 
    instrutor_id INTEGER NOT NULL, 
    tipo VARCHAR(20) NOT NULL, 
    data_inicio DATE NOT NULL, 
    data_fim DATE NOT NULL, 
    turnos INTEGER[] DEFAULT '{}' NOT NULL, 
    justificativa TEXT NOT NULL, 
    status VARCHAR(20) DEFAULT 'pendente' NOT NULL, 
    resposta TEXT, 
    decidido_por_id INTEGER, 
    decidido_em TIMESTAMP WITHOUT TIME ZONE, 
    efeitos JSONB, 
    criado_em TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    CONSTRAINT solicitacoes_tipo_check CHECK (tipo in ('folga','substituicao')), 
    CONSTRAINT solicitacoes_status_check CHECK (status in ('pendente','aprovada','recusada','cancelada')), 
    CONSTRAINT solicitacoes_datas_check CHECK (data_fim >= data_inicio), 
    FOREIGN KEY(instrutor_id) REFERENCES instrutores (id) ON DELETE CASCADE, 
    FOREIGN KEY(decidido_por_id) REFERENCES usuarios (id) ON DELETE SET NULL
);

CREATE INDEX ix_solicitacoes_instrutor_instrutor_id ON solicitacoes_instrutor (instrutor_id);

ALTER TABLE public.solicitacoes_instrutor ENABLE ROW LEVEL SECURITY;
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
    EXECUTE 'REVOKE ALL ON public.solicitacoes_instrutor FROM anon';
  END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
    EXECUTE 'REVOKE ALL ON public.solicitacoes_instrutor FROM authenticated';
  END IF;
END $$;

ALTER TABLE unidades_curriculares ADD COLUMN categoria VARCHAR(12) DEFAULT 'tecnica' NOT NULL;

ALTER TABLE unidades_curriculares ADD CONSTRAINT ucs_categoria_check CHECK (categoria in ('tecnica','transversal'));

ALTER TABLE competencias_instrutores DROP CONSTRAINT IF EXISTS competencias_instrutores_nivel_check;

ALTER TABLE competencias_instrutores DROP CONSTRAINT IF EXISTS ck_competencias_instrutores_nivel;

DO $$ DECLARE r record; BEGIN
      FOR r IN SELECT conname FROM pg_constraint WHERE conrelid = 'competencias_instrutores'::regclass AND contype = 'c'
               AND strpos(pg_get_constraintdef(oid), 'supervisionado') > 0 LOOP
        EXECUTE 'ALTER TABLE competencias_instrutores DROP CONSTRAINT ' || quote_ident(r.conname);
      END LOOP; END $$;

UPDATE competencias_instrutores SET nivel = 'parcial' WHERE nivel = 'supervisionado';

ALTER TABLE competencias_instrutores ADD CONSTRAINT competencias_instrutores_nivel_check CHECK (nivel in ('pleno','parcial','em_formacao'));

DO $$ DECLARE u record; t_id int; BEGIN
      FOR u IN SELECT id FROM unidades LOOP
        IF NOT EXISTS (SELECT 1 FROM turnos WHERE unidade_id = u.id AND codigo = 'S') THEN
          INSERT INTO turnos (unidade_id, codigo, nome, hora_inicio, hora_fim, ordem, ativo, criado_em, atualizado_em)
          VALUES (u.id, 'S', 'Sábado', '09:00', '13:00', 4, true, now(), now()) RETURNING id INTO t_id;
          INSERT INTO periodos_horarios (unidade_id, turno_id, ordem, hora_inicio, hora_fim, dias_semana, excepcional, ativo, criado_em, atualizado_em)
          SELECT u.id, t_id, v.ordem, v.ini::time, v.fim::time, '{5}', false, true, now(), now() FROM (VALUES (1, '09:00', '09:55'), (2, '09:55', '10:50'), (3, '11:10', '12:05'), (4, '12:05', '13:00')) AS v(ordem, ini, fim);
        END IF;
        IF EXISTS (SELECT 1 FROM horarios_funcionamento WHERE unidade_id = u.id)
           AND NOT EXISTS (SELECT 1 FROM horarios_funcionamento WHERE unidade_id = u.id AND dia_semana = 5) THEN
          INSERT INTO horarios_funcionamento (unidade_id, dia_semana, hora_inicio, hora_fim, ativo) VALUES (u.id, 5, '09:00', '13:00', true);
        END IF;
      END LOOP;
      UPDATE calendarios SET dias_letivos = array_append(dias_letivos, 5) WHERE NOT (5 = ANY(dias_letivos));
    END $$;

UPDATE alembic_version SET version_num='0010' WHERE alembic_version.version_num = '0009';

-- Running upgrade 0010 -> 0011

DO $$ DECLARE u record; t_id int; BEGIN
      FOR u IN SELECT id FROM unidades LOOP
        IF NOT EXISTS (SELECT 1 FROM turnos WHERE unidade_id = u.id AND codigo = 'I') THEN
          INSERT INTO turnos (unidade_id, codigo, nome, hora_inicio, hora_fim, ordem, ativo, criado_em, atualizado_em)
          VALUES (u.id, 'I', 'Integral (PFP)', '08:00', '17:00', 5, true, now(), now()) RETURNING id INTO t_id;
          INSERT INTO periodos_horarios (unidade_id, turno_id, ordem, hora_inicio, hora_fim, dias_semana, excepcional, ativo, criado_em, atualizado_em)
          SELECT u.id, t_id, v.ordem, v.ini::time, v.fim::time, '{0,1,2,3,4}', false, true, now(), now() FROM (VALUES (1, '08:00', '09:00'), (2, '09:00', '10:00'), (3, '10:00', '11:00'), (4, '11:00', '12:00'), (5, '13:00', '14:00'), (6, '14:00', '15:00'), (7, '15:00', '16:00'), (8, '16:00', '17:00')) AS v(ordem, ini, fim);
        END IF;
      END LOOP;
      -- quem tem manhã e tarde no mesmo dia pode dar aula de dia inteiro (08:00–17:00)
      INSERT INTO disponibilidade_instrutores (instrutor_id, dia_semana, hora_inicio, hora_fim, unidade_id)
      SELECT DISTINCT m.instrutor_id, m.dia_semana, time '08:00', time '17:00', m.unidade_id
        FROM disponibilidade_instrutores m
        JOIN instrutores i ON i.id = m.instrutor_id
        JOIN turnos tm ON tm.unidade_id = i.unidade_id AND tm.codigo = 'M'
        JOIN turnos tt ON tt.unidade_id = i.unidade_id AND tt.codigo = 'T'
        JOIN disponibilidade_instrutores t ON t.instrutor_id = m.instrutor_id AND t.dia_semana = m.dia_semana
       WHERE m.dia_semana < 5 AND m.hora_inicio <= tm.hora_inicio AND m.hora_fim >= tm.hora_fim
         AND t.hora_inicio <= tt.hora_inicio AND t.hora_fim >= tt.hora_fim
         AND NOT EXISTS (SELECT 1 FROM disponibilidade_instrutores x WHERE x.instrutor_id = m.instrutor_id AND x.dia_semana = m.dia_semana
                          AND x.hora_inicio <= time '08:00' AND x.hora_fim >= time '17:00');
    END $$;

UPDATE alembic_version SET version_num='0011' WHERE alembic_version.version_num = '0010';

-- Running upgrade 0011 -> 0012

ALTER TABLE matrizes_curriculares ADD COLUMN tipo_oferta VARCHAR(10);

UPDATE turnos SET nome = 'Manhã e tarde (PFP)' WHERE codigo = 'I' AND nome = 'Integral (PFP)';

DO $$ BEGIN
      DELETE FROM disponibilidade_instrutores WHERE hora_inicio = time '08:00' AND hora_fim = time '17:00';
      INSERT INTO disponibilidade_instrutores (instrutor_id, dia_semana, hora_inicio, hora_fim, unidade_id)
      SELECT DISTINCT d.instrutor_id, d.dia_semana, x.ini, x.fim, d.unidade_id
        FROM disponibilidade_instrutores d
        JOIN instrutores i ON i.id = d.instrutor_id
        JOIN turnos t ON t.unidade_id = i.unidade_id AND t.codigo IN ('M', 'T')
        JOIN (VALUES ('M', time '08:00', time '12:00'), ('T', time '13:00', time '17:00')) AS x(cod, ini, fim) ON x.cod = t.codigo
       WHERE d.dia_semana < 5 AND d.hora_inicio <= t.hora_inicio AND d.hora_fim >= t.hora_fim
         AND NOT EXISTS (SELECT 1 FROM disponibilidade_instrutores y WHERE y.instrutor_id = d.instrutor_id AND y.dia_semana = d.dia_semana
                          AND y.hora_inicio <= x.ini AND y.hora_fim >= x.fim);
    END $$;

UPDATE configuracoes SET valor = jsonb_set(valor, '{contagem}', '"relogio"') WHERE chave = 'regras_aula' AND valor->>'contagem' = 'hora_aula';

UPDATE alembic_version SET version_num='0012' WHERE alembic_version.version_num = '0011';

-- Running upgrade 0012 -> 0013

CREATE TABLE epis_curso (
    id SERIAL NOT NULL, 
    curso_id INTEGER NOT NULL, 
    nome VARCHAR(150) NOT NULL, 
    quantidade_por_aluno INTEGER DEFAULT 1 NOT NULL, 
    antecedencia_dias INTEGER DEFAULT 15 NOT NULL, 
    observacao TEXT, 
    ativo BOOLEAN DEFAULT true NOT NULL, 
    criado_em TIMESTAMP WITHOUT TIME ZONE DEFAULT now(), 
    atualizado_em TIMESTAMP WITHOUT TIME ZONE DEFAULT now(), 
    PRIMARY KEY (id), 
    FOREIGN KEY(curso_id) REFERENCES cursos (id) ON DELETE CASCADE
);

CREATE INDEX ix_epis_curso_curso_id ON epis_curso (curso_id);

CREATE TABLE epis_turma (
    id SERIAL NOT NULL, 
    turma_id INTEGER NOT NULL, 
    epi_curso_id INTEGER, 
    nome VARCHAR(150) NOT NULL, 
    quantidade INTEGER DEFAULT 0 NOT NULL, 
    prazo DATE, 
    providenciado BOOLEAN DEFAULT false NOT NULL, 
    providenciado_em TIMESTAMP WITHOUT TIME ZONE, 
    entregue BOOLEAN DEFAULT false NOT NULL, 
    entregue_em TIMESTAMP WITHOUT TIME ZONE, 
    atualizado_por_id INTEGER, 
    observacao TEXT, 
    criado_em TIMESTAMP WITHOUT TIME ZONE DEFAULT now(), 
    atualizado_em TIMESTAMP WITHOUT TIME ZONE DEFAULT now(), 
    PRIMARY KEY (id), 
    UNIQUE (turma_id, epi_curso_id), 
    FOREIGN KEY(turma_id) REFERENCES turmas (id) ON DELETE CASCADE, 
    FOREIGN KEY(epi_curso_id) REFERENCES epis_curso (id) ON DELETE SET NULL
);

CREATE INDEX ix_epis_turma_turma_id ON epis_turma (turma_id);

ALTER TABLE public.epis_curso ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.epis_turma ENABLE ROW LEVEL SECURITY;
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
    EXECUTE 'REVOKE ALL ON public.epis_curso, public.epis_turma FROM anon';
  END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
    EXECUTE 'REVOKE ALL ON public.epis_curso, public.epis_turma FROM authenticated';
  END IF;
END $$;

UPDATE alembic_version SET version_num='0013' WHERE alembic_version.version_num = '0012';

-- Running upgrade 0013 -> 0014

ALTER TABLE cursos ADD COLUMN dispensa_epi BOOLEAN DEFAULT false NOT NULL;

UPDATE alembic_version SET version_num='0014' WHERE alembic_version.version_num = '0013';

-- Running upgrade 0014 -> 0015

ALTER TABLE turmas ADD COLUMN modulos INTEGER;

ALTER TABLE turmas ADD COLUMN modulo_atual INTEGER;

ALTER TABLE excecoes_autorizadas DROP CONSTRAINT excecoes_autorizadas_tipo_check;

ALTER TABLE excecoes_autorizadas ADD CONSTRAINT excecoes_autorizadas_tipo_check CHECK (tipo in ('feriado_bloqueio','carga_horaria','regra_academica','reposicao'));

UPDATE alembic_version SET version_num='0015' WHERE alembic_version.version_num = '0014';

-- Running upgrade 0015 -> 0016

CREATE TABLE pdi_itens (
    id SERIAL NOT NULL, 
    instrutor_id INTEGER NOT NULL, 
    curso_id INTEGER, 
    uc_codigo VARCHAR(30) NOT NULL, 
    uc_nome VARCHAR(200) NOT NULL, 
    tipo VARCHAR(20) DEFAULT 'uc' NOT NULL, 
    certificacao VARCHAR(200), 
    prioridade VARCHAR(10), 
    prazo DATE, 
    situacao VARCHAR(20) DEFAULT 'planejado' NOT NULL, 
    observacao TEXT, 
    concluido_em DATE, 
    criado_por_id INTEGER, 
    criado_em TIMESTAMP WITHOUT TIME ZONE DEFAULT now(), 
    atualizado_em TIMESTAMP WITHOUT TIME ZONE DEFAULT now(), 
    PRIMARY KEY (id), 
    CONSTRAINT pdi_itens_tipo_check CHECK (tipo in ('uc','completar','certificacao')), 
    CONSTRAINT pdi_itens_situacao_check CHECK (situacao in ('planejado','em_andamento','concluido','cancelado')), 
    FOREIGN KEY(instrutor_id) REFERENCES instrutores (id) ON DELETE CASCADE, 
    FOREIGN KEY(curso_id) REFERENCES cursos (id) ON DELETE SET NULL, 
    FOREIGN KEY(criado_por_id) REFERENCES usuarios (id) ON DELETE SET NULL
);

CREATE INDEX ix_pdi_itens_instrutor_id ON pdi_itens (instrutor_id);

ALTER TABLE public.pdi_itens ENABLE ROW LEVEL SECURITY;
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
    EXECUTE 'REVOKE ALL ON public.pdi_itens FROM anon';
  END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
    EXECUTE 'REVOKE ALL ON public.pdi_itens FROM authenticated';
  END IF;
END $$;

UPDATE alembic_version SET version_num='0016' WHERE alembic_version.version_num = '0015';

-- Running upgrade 0016 -> 0017

CREATE TABLE termos_horas (
    id SERIAL NOT NULL, 
    instrutor_id INTEGER NOT NULL, 
    mes DATE NOT NULL, 
    horas_aula NUMERIC(6, 2) DEFAULT 0 NOT NULL, 
    horas_outras NUMERIC(6, 2) DEFAULT 0 NOT NULL, 
    observacao TEXT, 
    atualizado_por_id INTEGER, 
    criado_em TIMESTAMP WITHOUT TIME ZONE DEFAULT now(), 
    atualizado_em TIMESTAMP WITHOUT TIME ZONE DEFAULT now(), 
    PRIMARY KEY (id), 
    UNIQUE (instrutor_id, mes), 
    CHECK (horas_aula >= 0), 
    CHECK (horas_outras >= 0), 
    FOREIGN KEY(instrutor_id) REFERENCES instrutores (id) ON DELETE CASCADE, 
    FOREIGN KEY(atualizado_por_id) REFERENCES usuarios (id) ON DELETE SET NULL
);

CREATE INDEX ix_termos_horas_instrutor_id ON termos_horas (instrutor_id);

ALTER TABLE public.termos_horas ENABLE ROW LEVEL SECURITY;
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
    EXECUTE 'REVOKE ALL ON public.termos_horas FROM anon';
  END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
    EXECUTE 'REVOKE ALL ON public.termos_horas FROM authenticated';
  END IF;
END $$;

UPDATE alembic_version SET version_num='0017' WHERE alembic_version.version_num = '0016';

-- Running upgrade 0017 -> 0018

ALTER TABLE termos_horas ADD COLUMN dias_semana INTEGER[];

UPDATE alembic_version SET version_num='0018' WHERE alembic_version.version_num = '0017';

-- Running upgrade 0018 -> 0019

ALTER TABLE cursos ADD COLUMN preve_ead BOOLEAN DEFAULT false NOT NULL;

ALTER TABLE unidades_curriculares ADD COLUMN modalidade VARCHAR(12) DEFAULT 'presencial' NOT NULL;

ALTER TABLE unidades_curriculares ADD CONSTRAINT ucs_modalidade_check CHECK (modalidade in ('presencial','ead'));

UPDATE alembic_version SET version_num='0019' WHERE alembic_version.version_num = '0018';

-- Running upgrade 0019 -> 0020

ALTER TABLE termos_horas ADD COLUMN agenda JSONB;

UPDATE alembic_version SET version_num='0020' WHERE alembic_version.version_num = '0019';

COMMIT;

