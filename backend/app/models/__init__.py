from app.models.cadastros import *  # noqa: F401,F403
from app.models.planejamento import *  # noqa: F401,F403
from app.models.cadastros import (  # noqa: F401
    Ambiente, AmbienteArea, Area, Bloqueio, Calendario, CalendarioExcecao, CompetenciaInstrutor, Configuracao, Curso, EpiCurso, EpiTurma,
    DeslocamentoUnidade, DisponibilidadeAmbiente, DisponibilidadeInstrutor, HabilitacaoInstrutor,
    HorarioFuncionamento, Instrutor, InstrutorArea, InstrutorUnidade, MatrizCurricular, PdiItem, PeriodoHorario, Recurso,
    RecursoAmbiente, Setor, TermoHoras, TipoAmbiente, Turma, TurmaUC, Turno, UCPrerequisito, UCRecurso,
    UCTipoAmbiente, Unidade, UnidadeCurricular,
)
from app.models.planejamento import (  # noqa: F401
    Alocacao, AlocacaoRecurso, Atividade, CenarioPlanejamento, ExcecaoAutorizada, ExecucaoOtimizacao,
    HistoricoAuditoria, Importacao, Notificacao, ObservacaoInstrutor, OcorrenciaValidacao, ParametrosOtimizacao, PermissaoEscopo,
    PermissaoPerfil, RegistroDecisao, ResultadoOtimizacao, SimulacaoCapacidade, SolicitacaoImpressao, SolicitacaoInstrutor, Usuario, Validacao,
    VersaoPlanejamento, TODOS_GRUPOS, ESTADOS_CENARIO,
)
