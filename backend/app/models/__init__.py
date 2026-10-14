from app.models.cadastros import *  # noqa: F401,F403
from app.models.planejamento import *  # noqa: F401,F403
from app.models.cadastros import (  # noqa: F401
    Ambiente, AmbienteArea, Area, Bloqueio, Calendario, CalendarioExcecao, CompetenciaInstrutor, Configuracao, Curso,
    DeslocamentoUnidade, DisponibilidadeAmbiente, DisponibilidadeInstrutor, HabilitacaoInstrutor,
    HorarioFuncionamento, Instrutor, InstrutorArea, InstrutorUnidade, MatrizCurricular, PeriodoHorario, Recurso,
    RecursoAmbiente, Setor, TipoAmbiente, Turma, TurmaUC, Turno, UCPrerequisito, UCRecurso,
    UCTipoAmbiente, Unidade, UnidadeCurricular,
)
from app.models.planejamento import (  # noqa: F401
    Alocacao, AlocacaoRecurso, Atividade, CenarioPlanejamento, ExcecaoAutorizada, ExecucaoOtimizacao,
    HistoricoAuditoria, Importacao, ObservacaoInstrutor, OcorrenciaValidacao, ParametrosOtimizacao, PermissaoEscopo,
    PermissaoPerfil, RegistroDecisao, ResultadoOtimizacao, SimulacaoCapacidade, Usuario, Validacao,
    VersaoPlanejamento, TODOS_GRUPOS, ESTADOS_CENARIO,
)
