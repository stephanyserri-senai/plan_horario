"""Contrato de comunicação com o solver.

O solver não acessa o banco de dados: recebe uma `EntradaSolver` (dados
puros, serializáveis em JSON) e devolve uma `SaidaSolver`. Isso permite
executá-lo em processo separado, em outro serviço ou em testes isolados.

Modelo temporal: o solver decide um padrão SEMANAL (dia da semana, período
inicial, instrutor e ambiente para cada encontro). Cada atividade tem uma
janela de datas; as restrições de recurso só se aplicam entre atividades cujas
janelas se sobrepõem. O padrão é depois expandido em aulas datadas pelo
serviço de aplicação, que passa cada aula pela validação central.

Unidades: tempo em minutos desde 00:00; datas em ordinal (date.toordinal()).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass
class Slot:
    """Período elementar de aula (bloco da grade de uma unidade/turno)."""
    id: int
    unidade_id: int
    turno_id: int
    ordem: int
    dias: list[int]
    ini: int
    fim: int
    excepcional: bool = False


@dataclass
class Janela:
    dia: int
    ini: int
    fim: int


@dataclass
class InstrutorS:
    id: int
    unidades: list[int]
    disponibilidade: list[Janela]
    limite_semanal_min: int
    max_dia_min: int
    descanso_min: int = 0
    turno_preferencial_id: int | None = None


@dataclass
class AmbienteS:
    id: int
    unidade_id: int
    capacidade_operacional: int
    capacidade_fisica: int
    especializado: bool
    disponibilidade: list[Janela]  # vazia = sem restrição além da grade
    preparacao_min: int = 0


@dataclass
class OpcaoAnterior:
    dia: int
    slot_inicio_id: int
    instrutor_id: int | None
    ambiente_id: int | None


@dataclass
class AtividadeS:
    """Demanda semanal: `encontros` blocos de `num_periodos` períodos."""
    chave: str
    turma_id: int
    turma_uc_id: int
    uc_id: int
    grupo: int | None
    grupos: list[int]
    unidade_id: int
    turno_id: int | None
    dias_permitidos: list[int]
    num_periodos: int
    encontros: int
    instrutores: list[int]
    ambientes: list[int]
    tamanho: int
    data_ini: int
    data_fim: int
    prioridade: int = 3
    urgencia: float = 0.0  # 0..1 (1 = prazo mais apertado)
    aceita_convencional: bool = True
    recursos_moveis: dict[str, dict[str, int]] = field(default_factory=dict)  # ambiente_id(str) -> {tipo: qtd}
    anteriores: list[OpcaoAnterior] = field(default_factory=list)  # padrão vigente (minimizar mudanças)
    preservar: list[OpcaoAnterior] = field(default_factory=list)  # padrão aprovado no próprio cenário
    descricao: str = ""


@dataclass
class OcupacaoFixa:
    """Ocupação que o solver não pode alterar (aulas fixas / fora do escopo)."""
    recurso: str  # instrutor | ambiente | turma | recurso_movel
    recurso_id: str  # id (ou "unidade:tipo" para recurso móvel)
    dia: int
    ini: int
    fim: int
    data_ini: int
    data_fim: int
    grupos: list[int] = field(default_factory=list)
    quantidade: int = 1
    unidade_id: int | None = None
    minutos: int = 0


@dataclass
class EntradaSolver:
    slots: list[Slot]
    instrutores: list[InstrutorS]
    ambientes: list[AmbienteS]
    atividades: list[AtividadeS]
    fixas: list[OcupacaoFixa] = field(default_factory=list)
    acervo_movel: dict[str, int] = field(default_factory=dict)  # "unidade:tipo" -> quantidade
    deslocamentos: dict[str, int] = field(default_factory=dict)  # "u1:u2" -> minutos
    pesos: dict[str, float] = field(default_factory=dict)
    modo: str = "completo"  # completo: toda demanda é obrigatória | parcial: maximiza o atendimento
    limite_tempo_s: float = 30.0
    threads: int = 4
    semente: int = 0

    def to_dict(self):
        return asdict(self)


@dataclass
class Atribuicao:
    chave: str
    encontro: int
    dia: int
    slot_inicio_id: int
    slot_ids: list[int]
    num_periodos: int
    ini: int
    fim: int
    minutos: int
    instrutor_id: int | None
    ambiente_id: int | None


@dataclass
class SaidaSolver:
    status: str  # OTIMA | VIAVEL | SEM_SOLUCAO_NO_LIMITE | INVIAVEL | MODELO_INVALIDO | SEM_DEMANDA
    motivo: str
    tempo_s: float
    objetivo: float | None = None
    limite_inferior: float | None = None
    atribuicoes: list[Atribuicao] = field(default_factory=list)
    nao_alocados: list[dict] = field(default_factory=list)
    termos: dict[str, float] = field(default_factory=dict)
    diagnosticos: list[str] = field(default_factory=list)
    estatisticas: dict = field(default_factory=dict)

    def to_dict(self):
        return asdict(self)
