"""Serviço central de validação.

Obrigatório para qualquer inclusão, alteração, importação, otimização ou
publicação. As mesmas funções de regra são usadas para validar uma aula
proposta (modo individual, consultas pontuais ao banco) e para validar um
cenário inteiro (modo em lote, dados pré-carregados).

Severidades:
- bloqueio      restrição obrigatória: impede a gravação/publicação
- alerta        situação operacional que merece atenção
- preferencia   preferência não atendida
- recomendacao  sugestão de melhoria
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.services.regras_aula import limite_letivo_efetivo
from app.models import (
    Alocacao,
    Area,
    Curso,
    AlocacaoRecurso,
    Ambiente,
    Bloqueio,
    CompetenciaInstrutor,
    DeslocamentoUnidade,
    DisponibilidadeAmbiente,
    DisponibilidadeInstrutor,
    ExcecaoAutorizada,
    HabilitacaoInstrutor,
    HorarioFuncionamento,
    Instrutor,
    InstrutorUnidade,
    Recurso,
    RecursoAmbiente,
    TipoAmbiente,
    Turma,
    TurmaUC,
    Turno,
    UCRecurso,
    UnidadeCurricular,
)
from app.models.planejamento import TODOS_GRUPOS
from app.services.calendario import Calendarios, combinar, minutos, sobrepoe, segunda_da_semana

BLOQUEIO, ALERTA, PREFERENCIA, RECOMENDACAO = "bloqueio", "alerta", "preferencia", "recomendacao"


@dataclass
class Ocorrencia:
    severidade: str
    regra: str
    descricao: str
    recurso_tipo: str | None = None
    recurso_id: int | None = None
    data: date | None = None
    inicio: datetime | None = None
    fim: datetime | None = None
    turma_id: int | None = None
    uc_id: int | None = None
    instrutor_id: int | None = None
    ambiente_id: int | None = None
    alocacao_id: int | None = None
    relacionados: list[int] = field(default_factory=list)
    origem: str | None = None

    def to_dict(self):
        d = asdict(self)
        for k in ("data", "inicio", "fim"):
            if d[k] is not None:
                d[k] = d[k].isoformat()
        return d


@dataclass
class AulaProposta:
    """Uma aula datada a validar (nova ou alteração de existente)."""
    turma_uc_id: int
    inicio: datetime
    fim: datetime
    minutos_aula: int
    grupo: int | None = None
    instrutor_id: int | None = None
    ambiente_id: int | None = None
    recursos: list[tuple[int, int]] = field(default_factory=list)  # (recurso_id, quantidade)
    excecao_id: int | None = None
    alocacao_id: int | None = None  # quando é alteração de uma aula existente
    origem: str = "manual"

    @property
    def data(self) -> date:
        return self.inicio.date()


@dataclass
class SessaoExistente:
    id: int
    turma_id: int
    turma_uc_id: int
    uc_id: int
    grupos: list[int]
    instrutor_id: int | None
    ambiente_id: int | None
    data: date
    inicio: datetime
    fim: datetime
    fim_ambiente: datetime
    minutos_aula: int
    status: str
    unidade_id: int | None = None
    recursos: dict[int, int] = field(default_factory=dict)


def grupos_da_aula(grupo: int | None) -> list[int]:
    return list(TODOS_GRUPOS) if grupo is None else [grupo]


def _desc_hora(ini: datetime, fim: datetime) -> str:
    return f"{ini:%d/%m/%Y} {ini:%H:%M}–{fim:%H:%M}"


class BaseDados:
    """Acesso aos dados necessários às regras, com cache por instância.

    Em modo lote (`precarregar`), as sessões do cenário ficam em memória,
    indexadas por recurso e data; em modo individual, são consultadas no banco
    (dentro da mesma transação que fará a gravação)."""

    def __init__(self, db: Session, cenario_id: int):
        self.db = db
        self.cenario_id = cenario_id
        self.cal = Calendarios(db)
        self._cache: dict = {}
        self._lote = False
        self._por_chave: dict[tuple, list[SessaoExistente]] = defaultdict(list)
        self._sessoes: dict[int, SessaoExistente] = {}

    # ----------------------------------------------------------------- entidades
    def get(self, model, id_):
        if id_ is None:
            return None
        k = (model.__name__, id_)
        if k not in self._cache:
            self._cache[k] = self.db.get(model, id_)
        return self._cache[k]

    def _memo(self, chave, fn):
        if chave not in self._cache:
            self._cache[chave] = fn()
        return self._cache[chave]

    def regras(self) -> dict:
        from app.services.regras_aula import regras_aula
        return self._memo(("regras_aula",), lambda: regras_aula(self.db))

    def periodos_turno(self, turno_id, dia_semana):
        from app.services.regras_aula import periodos_do_turno
        return self._memo(("per_turno", turno_id, dia_semana), lambda: periodos_do_turno(self.db, turno_id, dia_semana))

    def areas_recurso(self, obj):
        from app.services.areas import areas_do_recurso
        return self._memo(("areas", type(obj).__name__, obj.id), lambda: areas_do_recurso(self.db, obj))

    def disponibilidade_instrutor(self, instrutor_id):
        return self._memo(("disp_i", instrutor_id), lambda: self.db.scalars(
            select(DisponibilidadeInstrutor).where(DisponibilidadeInstrutor.instrutor_id == instrutor_id)).all())

    def disponibilidade_ambiente(self, ambiente_id):
        return self._memo(("disp_a", ambiente_id), lambda: self.db.scalars(
            select(DisponibilidadeAmbiente).where(DisponibilidadeAmbiente.ambiente_id == ambiente_id)).all())

    def funcionamento(self, unidade_id):
        return self._memo(("func", unidade_id), lambda: self.db.scalars(
            select(HorarioFuncionamento).where(HorarioFuncionamento.unidade_id == unidade_id, HorarioFuncionamento.ativo.is_(True))).all())

    def competencia(self, instrutor_id, uc_id):
        return self._memo(("comp", instrutor_id, uc_id), lambda: self.db.scalars(
            select(CompetenciaInstrutor).where(CompetenciaInstrutor.instrutor_id == instrutor_id,
                                               CompetenciaInstrutor.uc_id == uc_id, CompetenciaInstrutor.ativo.is_(True))).first())

    def habilitacoes(self, instrutor_id):
        return self._memo(("hab", instrutor_id), lambda: self.db.scalars(
            select(HabilitacaoInstrutor).where(HabilitacaoInstrutor.instrutor_id == instrutor_id, HabilitacaoInstrutor.ativo.is_(True))).all())

    def unidades_instrutor(self, instrutor: Instrutor) -> set[int]:
        def f():
            s = {instrutor.unidade_id}
            s.update(self.db.scalars(select(InstrutorUnidade.unidade_id).where(InstrutorUnidade.instrutor_id == instrutor.id)))
            return s
        return self._memo(("uni_i", instrutor.id), f)

    def tipos_uc(self, uc: UnidadeCurricular) -> set[int]:
        return self._memo(("tipos_uc", uc.id), lambda: {t.id for t in uc.tipos_ambiente})

    def recursos_uc(self, uc_id) -> list[UCRecurso]:
        return self._memo(("rec_uc", uc_id), lambda: self.db.scalars(select(UCRecurso).where(UCRecurso.uc_id == uc_id)).all())

    def recursos_fixos_ambiente(self, ambiente_id) -> dict[str, int]:
        def f():
            res: dict[str, int] = defaultdict(int)
            rows = self.db.execute(
                select(Recurso.tipo, RecursoAmbiente.quantidade)
                .join(RecursoAmbiente, RecursoAmbiente.recurso_id == Recurso.id)
                .where(RecursoAmbiente.ambiente_id == ambiente_id, Recurso.ativo.is_(True), Recurso.situacao == "disponivel")
            )
            for tipo, q in rows:
                res[tipo] += q
            return dict(res)
        return self._memo(("rec_fixo", ambiente_id), f)

    def recursos_moveis(self, unidade_id, tipo) -> list[Recurso]:
        return self._memo(("rec_mov", unidade_id, tipo), lambda: self.db.scalars(
            select(Recurso).where(Recurso.unidade_id == unidade_id, Recurso.tipo == tipo, Recurso.movel.is_(True),
                                  Recurso.ativo.is_(True), Recurso.situacao == "disponivel")).all())

    def deslocamento(self, u1, u2) -> int:
        if u1 is None or u2 is None or u1 == u2:
            return 0
        def f():
            v = self.db.scalar(select(DeslocamentoUnidade.minutos).where(
                ((DeslocamentoUnidade.origem_id == u1) & (DeslocamentoUnidade.destino_id == u2))
                | ((DeslocamentoUnidade.origem_id == u2) & (DeslocamentoUnidade.destino_id == u1))))
            return 60 if v is None else v  # sem cadastro: 60 min por segurança (alerta de cadastro)
        return self._memo(("desl", min(u1, u2), max(u1, u2)), f)

    def bloqueios(self, alvo_tipo, alvo_id, ini, fim) -> list[Bloqueio]:
        chave = ("bloq", alvo_tipo, alvo_id)
        if self._lote:
            todos = self._memo(chave, lambda: self.db.scalars(select(Bloqueio).where(
                Bloqueio.alvo_tipo == alvo_tipo, Bloqueio.alvo_id == alvo_id, Bloqueio.ativo.is_(True))).all())
            return [b for b in todos if sobrepoe(b.inicio, b.fim, ini, fim)]
        return self.db.scalars(select(Bloqueio).where(
            Bloqueio.alvo_tipo == alvo_tipo, Bloqueio.alvo_id == alvo_id, Bloqueio.ativo.is_(True),
            Bloqueio.inicio < fim, Bloqueio.fim > ini)).all()

    # ----------------------------------------------------------------- sessões
    def _linha_para_sessao(self, a: Alocacao) -> SessaoExistente:
        amb = self.get(Ambiente, a.ambiente_id)
        turma = self.get(Turma, a.turma_id)
        return SessaoExistente(
            id=a.id, turma_id=a.turma_id, turma_uc_id=a.turma_uc_id, uc_id=a.uc_id, grupos=list(a.grupos),
            instrutor_id=a.instrutor_id, ambiente_id=a.ambiente_id, data=a.data, inicio=a.inicio, fim=a.fim,
            fim_ambiente=a.fim_ambiente, minutos_aula=a.minutos_aula, status=a.status,
            unidade_id=amb.unidade_id if amb else (turma.unidade_id if turma else None),
        )

    def precarregar(self):
        """Modo lote: carrega todas as aulas ativas do cenário."""
        self._lote = True
        linhas = self.db.scalars(select(Alocacao).where(Alocacao.cenario_id == self.cenario_id, Alocacao.status != "cancelada")).all()
        recs = defaultdict(dict)
        if linhas:
            for ar in self.db.scalars(select(AlocacaoRecurso).join(Alocacao).where(Alocacao.cenario_id == self.cenario_id)):
                recs[ar.alocacao_id][ar.recurso_id] = ar.quantidade
        for a in linhas:
            s = self._linha_para_sessao(a)
            s.recursos = recs.get(a.id, {})
            self._indexar(s)
        return self

    def _indexar(self, s: SessaoExistente):
        self._sessoes[s.id] = s
        semana = segunda_da_semana(s.data)
        self._por_chave[("turma", s.turma_id, s.data)].append(s)
        self._por_chave[("tuc", s.turma_uc_id)].append(s)
        self._por_chave[("data", s.data)].append(s)
        if s.instrutor_id:
            self._por_chave[("instrutor", s.instrutor_id, s.data)].append(s)
            self._por_chave[("instrutor_sem", s.instrutor_id, semana)].append(s)
        if s.ambiente_id:
            self._por_chave[("ambiente", s.ambiente_id, s.data)].append(s)

    def adicionar_virtual(self, s: SessaoExistente):
        """Usado pelo otimizador/importador para validar várias aulas novas em
        conjunto (cada nova aula passa a ser considerada pelas seguintes)."""
        self._indexar(s)

    def _consulta(self, *conds) -> list[SessaoExistente]:
        linhas = self.db.scalars(select(Alocacao).where(Alocacao.cenario_id == self.cenario_id, Alocacao.status != "cancelada", *conds)).all()
        return [self._linha_para_sessao(a) for a in linhas]

    def sessoes_instrutor(self, instrutor_id, d: date):
        if self._lote:
            return self._por_chave.get(("instrutor", instrutor_id, d), [])
        return self._consulta(Alocacao.instrutor_id == instrutor_id, Alocacao.data == d)

    def sessoes_instrutor_periodo(self, instrutor_id, d0: date, d1: date):
        if self._lote:
            res = []
            d = d0
            while d <= d1:
                res.extend(self._por_chave.get(("instrutor", instrutor_id, d), []))
                d += timedelta(days=1)
            return res
        return self._consulta(Alocacao.instrutor_id == instrutor_id, Alocacao.data >= d0, Alocacao.data <= d1)

    def sessoes_ambiente(self, ambiente_id, d: date):
        if self._lote:
            return self._por_chave.get(("ambiente", ambiente_id, d), [])
        return self._consulta(Alocacao.ambiente_id == ambiente_id, Alocacao.data == d)

    def sessoes_turma(self, turma_id, d: date):
        if self._lote:
            return self._por_chave.get(("turma", turma_id, d), [])
        return self._consulta(Alocacao.turma_id == turma_id, Alocacao.data == d)

    def sessoes_turma_uc(self, turma_uc_id):
        if self._lote:
            return self._por_chave.get(("tuc", turma_uc_id), [])
        return self._consulta(Alocacao.turma_uc_id == turma_uc_id)

    def uso_recurso(self, recurso_id, d: date) -> list[tuple[SessaoExistente, int]]:
        if self._lote:
            return [(s, s.recursos[recurso_id]) for s in self._por_chave.get(("data", d), []) if recurso_id in s.recursos]
        linhas = self.db.execute(
            select(Alocacao, AlocacaoRecurso.quantidade).join(AlocacaoRecurso, AlocacaoRecurso.alocacao_id == Alocacao.id)
            .where(Alocacao.cenario_id == self.cenario_id, Alocacao.status != "cancelada", Alocacao.data == d,
                   AlocacaoRecurso.recurso_id == recurso_id)).all()
        return [(self._linha_para_sessao(a), q) for a, q in linhas]


# =============================================================================
# Regras
# =============================================================================
def _janela_contem(janelas, dia, ini: datetime, fim: datetime) -> bool:
    mi, mf = ini.hour * 60 + ini.minute, fim.hour * 60 + fim.minute
    if fim.date() != ini.date():
        return False
    return any(j.dia_semana == dia and minutos(j.hora_inicio) <= mi and mf <= minutos(j.hora_fim) for j in janelas)


def carga_horaria_minutos(b: BaseDados, tuc: TurmaUC, grupo: int | None, ignorar: set[int]) -> tuple[int, int]:
    """(minutos realizados, minutos programados) da turma×UC para o grupo
    indicado. Aulas da turma inteira contam para todos os grupos."""
    realizados = int(float(tuc.ch_realizada or 0) * 60)
    programados = 0
    for s in b.sessoes_turma_uc(tuc.id):
        if s.id in ignorar:
            continue
        if grupo is not None and grupo not in s.grupos:
            continue
        if s.status == "realizada":
            realizados += s.minutos_aula
        else:
            programados += s.minutos_aula
    return realizados, programados


def validar_aula(b: BaseDados, a: AulaProposta, ignorar: set[int] | None = None) -> list[Ocorrencia]:
    """Aplica todas as regras a uma aula proposta. `ignorar` contém ids de
    aulas existentes que não devem ser consideradas (a própria aula em edição,
    aulas que serão substituídas na mesma operação etc.)."""
    ignorar = set(ignorar or set())
    if a.alocacao_id:
        ignorar.add(a.alocacao_id)
    oc: list[Ocorrencia] = []

    tuc = b.get(TurmaUC, a.turma_uc_id)
    if tuc is None:
        return [Ocorrencia(BLOQUEIO, "REFERENCIA_INVALIDA", "Turma×UC inexistente.")]
    turma = b.get(Turma, tuc.turma_id)
    uc = b.get(UnidadeCurricular, tuc.uc_id)
    instrutor = b.get(Instrutor, a.instrutor_id)
    ambiente = b.get(Ambiente, a.ambiente_id)
    d = a.data
    dia = d.weekday()
    grupos = grupos_da_aula(a.grupo)
    base = dict(data=d, inicio=a.inicio, fim=a.fim, turma_id=turma.id, uc_id=uc.id,
                instrutor_id=a.instrutor_id, ambiente_id=a.ambiente_id, alocacao_id=a.alocacao_id, origem=a.origem)

    def add(sev, regra, desc, recurso_tipo=None, recurso_id=None, relacionados=None):
        oc.append(Ocorrencia(sev, regra, desc, recurso_tipo, recurso_id, relacionados=relacionados or [], **base))

    excecao = b.get(ExcecaoAutorizada, a.excecao_id)
    excecao_tipo = excecao.tipo if excecao else None
    hora = _desc_hora(a.inicio, a.fim)

    # --- integridade básica
    if a.fim <= a.inicio or a.fim.date() != a.inicio.date():
        add(BLOQUEIO, "INTERVALO_INVALIDO", "O término deve ser posterior ao início, no mesmo dia.")
        return oc
    if not turma.ativo or turma.situacao in ("cancelada", "concluida"):
        add(BLOQUEIO, "TURMA_INATIVA", f"A turma {turma.codigo} está {turma.situacao if turma.ativo else 'inativa'}.", "turma", turma.id)
    if not tuc.ativo or tuc.situacao in ("concluida", "cancelada"):
        add(BLOQUEIO, "UC_ENCERRADA", f"A UC {uc.codigo} está '{tuc.situacao}' para a turma {turma.codigo}.")
    if a.grupo is not None and (a.grupo < 1 or a.grupo > turma.num_grupos):
        add(BLOQUEIO, "GRUPO_INVALIDO", f"A turma {turma.codigo} possui {turma.num_grupos} grupo(s); grupo {a.grupo} inválido.")
    elif a.grupo is not None and not uc.divide_grupos:
        add(BLOQUEIO, "GRUPO_NAO_PREVISTO", f"A UC {uc.codigo} não prevê divisão da turma em grupos.")

    # --- (12) período de execução da turma e da UC
    if d < turma.data_inicio or d > turma.data_fim:
        add(BLOQUEIO, "FORA_PERIODO_TURMA", f"{d:%d/%m/%Y} está fora do período da turma {turma.codigo} ({turma.data_inicio:%d/%m/%Y}–{turma.data_fim:%d/%m/%Y}).")
    if tuc.data_inicio and d < tuc.data_inicio:
        add(BLOQUEIO, "FORA_PERIODO_UC", f"A UC {uc.codigo} só pode iniciar em {tuc.data_inicio:%d/%m/%Y}.")
    if tuc.data_limite and d > tuc.data_limite:
        add(BLOQUEIO, "FORA_PERIODO_UC", f"A UC {uc.codigo} deve ser concluída até {tuc.data_limite:%d/%m/%Y}.")

    # --- (6) feriados, recessos, dias não letivos e bloqueios
    letivo, motivo = b.cal.dia_letivo(turma, d)
    if not letivo:
        if excecao_tipo == "feriado_bloqueio":
            add(ALERTA, "EXCECAO_CALENDARIO", f"Aula em dia não letivo ({motivo}) autorizada pela exceção #{excecao.id}: {excecao.justificativa}")
        else:
            add(BLOQUEIO, "DIA_NAO_LETIVO", f"{d:%d/%m/%Y} não é dia letivo: {motivo}.")
    if dia in (turma.dias_ead or []):
        add(BLOQUEIO, "TURMA_DIA_EAD", f"{('Segunda', 'Terça', 'Quarta', 'Quinta', 'Sexta', 'Sábado', 'Domingo')[dia]} é dia de EAD da turma {turma.codigo} (turma 80-20): sem aula presencial.")
    elif dia not in (turma.dias_possiveis or []):
        add(BLOQUEIO, "TURMA_FORA_DIAS", f"A turma {turma.codigo} não tem aulas previstas neste dia da semana.")
    turno = b.get(Turno, turma.turno_id)
    if turno and (a.inicio.time() < turno.hora_inicio or a.fim.time() > turno.hora_fim):
        add(BLOQUEIO, "TURMA_FORA_TURNO", f"Horário {a.inicio:%H:%M}–{a.fim:%H:%M} fora do turno {turno.nome} da turma ({turno.hora_inicio:%H:%M}–{turno.hora_fim:%H:%M}).")

    # --- turno inteiro: a UC ocupa todas as aulas do turno no dia, salvo no fechamento da carga horária
    regras = b.regras()
    per_turno = b.periodos_turno(turma.turno_id, dia) if regras.get("turno_inteiro") else []
    if per_turno:
        from app.services.regras_aula import credito_bloco, periodos_para_fechar
        ini_t, fim_t = combinar(d, per_turno[0].hora_inicio), combinar(d, per_turno[-1].hora_fim)
        if a.inicio > ini_t or a.fim < fim_t:
            credito_turno = credito_bloco(regras, per_turno)
            gs = [a.grupo] if a.grupo is not None else ([None] if not (uc.divide_grupos and turma.num_grupos > 1) else list(range(1, turma.num_grupos + 1)))
            restantes = []
            for g in gs:
                r_, p_ = carga_horaria_minutos(b, tuc, g, ignorar)
                restantes.append(uc.carga_horaria_total * 60 - r_ - p_)
            restante = max(restantes) if restantes else 0
            if restante >= credito_turno:
                add(BLOQUEIO, "TURNO_INCOMPLETO",
                    f"Cada UC deve ocupar o turno inteiro ({len(per_turno)} aulas, {per_turno[0].hora_inicio:%H:%M}–{per_turno[-1].hora_fim:%H:%M}). "
                    f"Aula parcial só é permitida no fechamento da carga horária, e ainda faltam {restante / 60:.0f} h de {uc.codigo}.")
            elif a.minutos_aula > 0 and restante > 0:
                n = periodos_para_fechar(regras, restante, per_turno)
                add(RECOMENDACAO, "FECHAMENTO_CH",
                    f"Aula de fechamento de {uc.codigo}: faltam {restante / 60:.0f} h ({n} aula(s)); o restante do turno pode ser usado por outra UC que também esteja fechando.")

    alvos = [("turma", turma.id), ("unidade", turma.unidade_id)]
    if instrutor:
        alvos.append(("instrutor", instrutor.id))
    if ambiente:
        alvos.append(("ambiente", ambiente.id))
    for tipo, id_ in alvos:
        for bl in b.bloqueios(tipo, id_, a.inicio, a.fim):
            if tipo == "instrutor" and bl.tipo in ("planejamento", "projeto"):
                sigla = "PL" if bl.tipo == "planejamento" else "PJ"
                if a.origem == "substituicao":
                    # em PL/PJ o instrutor está na escola: pode assumir uma substituição (o turno vira aula)
                    add(ALERTA, "SUBSTITUTO_EM_PL_PJ", f"Está em {sigla} em {bl.inicio:%d/%m} ({bl.inicio:%H:%M}–{bl.fim:%H:%M}): "
                        f"está na escola e pode assumir; o {sigla} desse turno vira aula.", tipo, id_)
                    continue
                texto = (f"O instrutor tem {sigla} ({bl.motivo or bl.tipo}) em {bl.inicio:%d/%m} das {bl.inicio:%H:%M} às {bl.fim:%H:%M}. "
                         "Libere o turno na agenda do instrutor (grade por instrutor) ou escolha outro horário.")
            else:
                texto = f"Bloqueio de {tipo} ({bl.tipo}: {bl.motivo or 'sem motivo'}) entre {bl.inicio:%d/%m %H:%M} e {bl.fim:%d/%m %H:%M}."
            if excecao_tipo == "feriado_bloqueio" and tipo in ("turma", "unidade"):
                add(ALERTA, "EXCECAO_BLOQUEIO", texto + f" Autorizado pela exceção #{excecao.id}.", tipo, id_)
            else:
                add(BLOQUEIO, f"BLOQUEIO_{tipo.upper()}", texto, tipo, id_)

    # --- funcionamento da unidade
    unidade_aula = ambiente.unidade_id if ambiente else turma.unidade_id
    func_ = b.funcionamento(unidade_aula)
    if func_ and not _janela_contem(func_, dia, a.inicio, a.fim):
        add(BLOQUEIO, "FORA_FUNCIONAMENTO", f"{hora} está fora do horário de funcionamento da unidade.", "unidade", unidade_aula)

    # --- (2) turma (com grupos) em atividades simultâneas
    for s in b.sessoes_turma(turma.id, d):
        if s.id in ignorar:
            continue
        if set(s.grupos) & set(grupos) and sobrepoe(s.inicio, s.fim, a.inicio, a.fim):
            add(BLOQUEIO, "TURMA_SOBREPOSICAO",
                f"A turma {turma.codigo}{'' if a.grupo is None else f' (grupo {a.grupo})'} já tem aula em {_desc_hora(s.inicio, s.fim)} (aula #{s.id}).",
                "turma", turma.id, [s.id])

    # --- regras acadêmicas (área e competência): admitem exceção justificada do tipo "regra_academica"
    academica = excecao_tipo == "regra_academica"
    curso_turma = b.get(Curso, turma.curso_id)
    area_turma = turma.area_id or (curso_turma.area_id if curso_turma else None)

    from app.services.areas import atende_area

    def nome_area(aid):
        ar = b.get(Area, aid)
        return ar.nome if ar else "?"

    # --- instrutor
    if instrutor is None:
        add(ALERTA, "SEM_INSTRUTOR", "Aula sem instrutor definido: pendente de alocação.")
    else:
        if not instrutor.ativo or instrutor.situacao != "ativo":
            add(BLOQUEIO, "INSTRUTOR_INATIVO", f"O instrutor {instrutor.nome} não está ativo ({instrutor.situacao}).", "instrutor", instrutor.id)
        # (8) habilitação
        comp = b.competencia(instrutor.id, uc.id)
        if comp is None:
            if academica:
                add(ALERTA, "EXCECAO_REGRA_ACADEMICA", f"{instrutor.nome} sem competência cadastrada para {uc.codigo}, por exceção justificada #{excecao.id}: {excecao.justificativa}", "instrutor", instrutor.id)
            else:
                add(BLOQUEIO, "INSTRUTOR_NAO_HABILITADO", f"{instrutor.nome} não possui competência cadastrada para a UC {uc.codigo} – {uc.nome}.", "instrutor", instrutor.id)
        elif comp.valido_ate and comp.valido_ate < d:
            add(BLOQUEIO, "INSTRUTOR_NAO_HABILITADO", f"A habilitação de {instrutor.nome} para {uc.codigo} venceu em {comp.valido_ate:%d/%m/%Y}.", "instrutor", instrutor.id)
        elif comp.nivel == "em_formacao":
            add(BLOQUEIO, "INSTRUTOR_NAO_HABILITADO", f"{instrutor.nome} está 'em formação' para {uc.codigo} e não pode assumir a UC.", "instrutor", instrutor.id)
        elif comp.nivel == "supervisionado":
            add(ALERTA, "INSTRUTOR_SUPERVISIONADO", f"{instrutor.nome} atua em {uc.codigo} somente sob supervisão. {comp.condicoes or ''}".strip(), "instrutor", instrutor.id)
        if uc.certificacao_exigida:
            habs = [h for h in b.habilitacoes(instrutor.id) if h.nome.strip().lower() == uc.certificacao_exigida.strip().lower()]
            if not habs or all(h.valido_ate and h.valido_ate < d for h in habs):
                add(BLOQUEIO, "CERTIFICACAO_AUSENTE", f"A UC {uc.codigo} exige a certificação '{uc.certificacao_exigida}', ausente ou vencida para {instrutor.nome}.", "instrutor", instrutor.id)
        if not atende_area(*b.areas_recurso(instrutor), area_turma):
            if academica:
                add(ALERTA, "EXCECAO_REGRA_ACADEMICA", f"{instrutor.nome} ({nome_area(instrutor.area_id)}) em turma de {nome_area(area_turma)}, por exceção justificada #{excecao.id}: {excecao.justificativa}", "instrutor", instrutor.id)
            else:
                add(BLOQUEIO, "INSTRUTOR_OUTRA_AREA", f"{instrutor.nome} é da área {nome_area(instrutor.area_id)} e a turma {turma.codigo} é da área {nome_area(area_turma)}.", "instrutor", instrutor.id)
        from app.services.planejamento import nivel_atende, nivel_da_turma
        nivel_turma = b._memo(("nivel_turma", turma.id), lambda: nivel_da_turma(b.db, turma))
        if not nivel_atende(instrutor.nivel, nivel_turma):  # regra de habilitação: não admite exceção
            add(BLOQUEIO, "INSTRUTOR_NIVEL", f"{instrutor.nome} é instrutor básico (só AIB e qualificações) e a turma {turma.codigo} exige instrutor técnico.",
                "instrutor", instrutor.id)
        if unidade_aula not in b.unidades_instrutor(instrutor):
            add(BLOQUEIO, "INSTRUTOR_UNIDADE", f"{instrutor.nome} não está autorizado a atuar nesta unidade.", "instrutor", instrutor.id)
        # (5) disponibilidade
        disp = b.disponibilidade_instrutor(instrutor.id)
        if not disp:
            add(BLOQUEIO, "INSTRUTOR_SEM_DISPONIBILIDADE", f"{instrutor.nome} não possui disponibilidade cadastrada.", "instrutor", instrutor.id)
        elif not _janela_contem(disp, dia, a.inicio, a.fim):
            add(BLOQUEIO, "INSTRUTOR_FORA_DISPONIBILIDADE", f"{hora} está fora da disponibilidade cadastrada de {instrutor.nome}.", "instrutor", instrutor.id)
        # (1) sobreposição e (11) jornada / deslocamento
        do_dia = [s for s in b.sessoes_instrutor(instrutor.id, d) if s.id not in ignorar]
        for s in do_dia:
            if sobrepoe(s.inicio, s.fim, a.inicio, a.fim):
                add(BLOQUEIO, "INSTRUTOR_SOBREPOSICAO", f"{instrutor.nome} já leciona em {_desc_hora(s.inicio, s.fim)} (aula #{s.id}).", "instrutor", instrutor.id, [s.id])
            else:
                desl = b.deslocamento(s.unidade_id, unidade_aula)
                if desl:
                    folga = (a.inicio - s.fim) if s.fim <= a.inicio else (s.inicio - a.fim)
                    if folga < timedelta(minutes=desl):
                        add(BLOQUEIO, "DESLOCAMENTO_INSUFICIENTE",
                            f"{instrutor.nome} precisa de {desl} min para deslocamento entre unidades; intervalo disponível de {int(folga.total_seconds() // 60)} min (aula #{s.id}).",
                            "instrutor", instrutor.id, [s.id])
        min_dia = sum(s.minutos_aula for s in do_dia) + a.minutos_aula
        if min_dia > float(instrutor.max_horas_dia) * 60:
            add(BLOQUEIO, "JORNADA_DIARIA", f"{instrutor.nome} somaria {min_dia / 60:.1f} h no dia (limite {float(instrutor.max_horas_dia):.1f} h).", "instrutor", instrutor.id)
        seg = segunda_da_semana(d)
        da_semana = [s for s in b.sessoes_instrutor_periodo(instrutor.id, seg, seg + timedelta(days=6)) if s.id not in ignorar]
        min_sem = sum(s.minutos_aula for s in da_semana) + a.minutos_aula
        lim = limite_letivo_efetivo(instrutor)
        if min_sem > lim * 60:
            regra90 = " = 90% da jornada; o restante fica para planejamento" if lim < float(instrutor.limite_ch_letiva) - 1e-6 else ""
            add(BLOQUEIO, "LIMITE_SEMANAL", f"{instrutor.nome} somaria {min_sem / 60:.1f} h letivas na semana (limite {lim:.1f} h{regra90}).", "instrutor", instrutor.id)
        descanso = timedelta(hours=float(instrutor.intervalo_minimo_h or 0))
        if descanso:
            for s in b.sessoes_instrutor(instrutor.id, d - timedelta(days=1)):
                if s.id not in ignorar and a.inicio - s.fim < descanso:
                    add(BLOQUEIO, "INTERJORNADA", f"Descanso entre jornadas de {instrutor.nome} seria de {(a.inicio - s.fim).total_seconds() / 3600:.1f} h (mínimo {descanso.total_seconds() / 3600:.0f} h; aula #{s.id}).", "instrutor", instrutor.id, [s.id])
            for s in b.sessoes_instrutor(instrutor.id, d + timedelta(days=1)):
                if s.id not in ignorar and s.inicio - a.fim < descanso:
                    add(BLOQUEIO, "INTERJORNADA", f"Descanso entre jornadas de {instrutor.nome} seria de {(s.inicio - a.fim).total_seconds() / 3600:.1f} h (mínimo {descanso.total_seconds() / 3600:.0f} h; aula #{s.id}).", "instrutor", instrutor.id, [s.id])
        if instrutor.turno_preferencial_id and turma.turno_id and instrutor.turno_preferencial_id != turma.turno_id:
            add(PREFERENCIA, "PREFERENCIA_TURNO", f"{instrutor.nome} prefere outro turno.", "instrutor", instrutor.id)

    # --- ambiente
    tamanho = turma.qtd_alunos if a.grupo is None else -(-turma.qtd_alunos // max(turma.num_grupos, 1))
    if ambiente is None:
        add(ALERTA, "SEM_AMBIENTE", "Aula sem ambiente definido: pendente de alocação.")
    else:
        if not ambiente.ativo or ambiente.situacao != "operacional":
            add(BLOQUEIO, "AMBIENTE_INDISPONIVEL", f"O ambiente {ambiente.codigo} está '{ambiente.situacao}'.", "ambiente", ambiente.id)
        if ambiente.unidade_id != turma.unidade_id:
            add(ALERTA, "AMBIENTE_OUTRA_UNIDADE", f"O ambiente {ambiente.codigo} pertence a outra unidade.", "ambiente", ambiente.id)
        # (9) compatibilidade técnica
        tipos = b.tipos_uc(uc)
        tipo_amb = b.get(TipoAmbiente, ambiente.tipo_ambiente_id)
        if tipos and ambiente.tipo_ambiente_id not in tipos:
            add(BLOQUEIO, "AMBIENTE_INCOMPATIVEL", f"A UC {uc.codigo} exige {' ou '.join(sorted((b.get(TipoAmbiente, t).nome if b.get(TipoAmbiente, t) else str(t)) for t in tipos))}; {ambiente.codigo} é '{tipo_amb.nome if tipo_amb else '?'}'.", "ambiente", ambiente.id)
        elif tipo_amb and tipo_amb.especializado and tipos and any(not (b.get(TipoAmbiente, t).especializado) for t in tipos):
            add(RECOMENDACAO, "ESPECIALIZADO_DESNECESSARIO", f"{ambiente.codigo} é especializado, mas a UC {uc.codigo} aceita ambiente convencional.", "ambiente", ambiente.id)
        if tipo_amb and tipo_amb.especializado and not atende_area(*b.areas_recurso(ambiente), area_turma):
            if academica:
                add(ALERTA, "EXCECAO_REGRA_ACADEMICA", f"Laboratório {ambiente.codigo} ({nome_area(ambiente.area_id)}) usado por turma de {nome_area(area_turma)}, por exceção justificada #{excecao.id}.", "ambiente", ambiente.id)
            else:
                add(BLOQUEIO, "AMBIENTE_OUTRA_AREA", f"O laboratório {ambiente.codigo} é da área {nome_area(ambiente.area_id)} e a turma {turma.codigo} é da área {nome_area(area_turma)}.", "ambiente", ambiente.id)
        if turma.necessidades_acessibilidade and not ambiente.acessivel:
            add(BLOQUEIO, "ACESSIBILIDADE", f"A turma {turma.codigo} requer ambiente acessível; {ambiente.codigo} não é.", "ambiente", ambiente.id)
        # (7) capacidade
        if tamanho > ambiente.capacidade_fisica:
            add(BLOQUEIO, "CAPACIDADE_FISICA", f"{tamanho} alunos excedem a capacidade física de {ambiente.codigo} ({ambiente.capacidade_fisica}).", "ambiente", ambiente.id)
        elif tamanho > ambiente.capacidade_operacional:
            add(ALERTA, "CAPACIDADE_OPERACIONAL", f"{tamanho} alunos excedem a capacidade operacional recomendada de {ambiente.codigo} ({ambiente.capacidade_operacional}).", "ambiente", ambiente.id)
        # disponibilidade do ambiente
        disp_a = b.disponibilidade_ambiente(ambiente.id)
        if disp_a and not _janela_contem(disp_a, dia, a.inicio, a.fim):
            add(BLOQUEIO, "AMBIENTE_FORA_DISPONIBILIDADE", f"{hora} está fora da disponibilidade do ambiente {ambiente.codigo}.", "ambiente", ambiente.id)
        # (3) sobreposição (inclui tempo de preparação)
        prep = timedelta(minutes=ambiente.tempo_preparacao_min or 0)
        for s in b.sessoes_ambiente(ambiente.id, d):
            if s.id in ignorar:
                continue
            if sobrepoe(s.inicio, s.fim_ambiente, a.inicio, a.fim + prep):
                extra = f" (considerando {ambiente.tempo_preparacao_min} min de preparação)" if prep else ""
                add(BLOQUEIO, "AMBIENTE_SOBREPOSICAO", f"O ambiente {ambiente.codigo} já está ocupado em {_desc_hora(s.inicio, s.fim)}{extra} (aula #{s.id}).", "ambiente", ambiente.id, [s.id])

    if uc.capacidade_max and tamanho > uc.capacidade_max:
        add(ALERTA if uc.divide_grupos else BLOQUEIO, "CAPACIDADE_UC",
            f"{tamanho} alunos excedem o máximo de {uc.capacidade_max} por atividade da UC {uc.codigo}" + (" — utilize a divisão em grupos." if uc.divide_grupos else "."))

    # --- (10) equipamentos / recursos compartilhados
    fixos = b.recursos_fixos_ambiente(ambiente.id) if ambiente else {}
    reservados = defaultdict(int)
    for rid, q in a.recursos:
        r = b.get(Recurso, rid)
        if r:
            reservados[r.tipo] += q
    for req in b.recursos_uc(uc.id):
        disponivel = fixos.get(req.recurso_tipo, 0) + reservados.get(req.recurso_tipo, 0)
        if disponivel < req.quantidade:
            add(BLOQUEIO, "RECURSO_AUSENTE",
                f"A UC {uc.codigo} exige {req.quantidade} × '{req.recurso_tipo}'; disponível no ambiente/reserva: {disponivel}.")
    for rid, q in a.recursos:
        r = b.get(Recurso, rid)
        if r is None or not r.ativo or r.situacao != "disponivel":
            add(BLOQUEIO, "RECURSO_INDISPONIVEL", f"Recurso #{rid} inexistente ou indisponível.", "recurso", rid)
            continue
        for bl in b.bloqueios("recurso", rid, a.inicio, a.fim):
            add(BLOQUEIO, "BLOQUEIO_RECURSO", f"{r.nome} bloqueado ({bl.motivo or bl.tipo}).", "recurso", rid)
        em_uso = [(s, qq) for s, qq in b.uso_recurso(rid, d) if s.id not in ignorar and sobrepoe(s.inicio, s.fim, a.inicio, a.fim)]
        # pico de uso simultâneo dentro do intervalo
        pico = _pico_uso([(max(s.inicio, a.inicio), min(s.fim, a.fim), qq) for s, qq in em_uso])
        if pico + q > r.quantidade_total:
            add(BLOQUEIO, "RECURSO_CONFLITO",
                f"{r.nome}: {pico} unidade(s) já reservada(s) no horário; solicitadas {q}; total {r.quantidade_total}.",
                "recurso", rid, [s.id for s, _ in em_uso])

    # --- (13) carga horária restante
    total_min = uc.carga_horaria_total * 60
    grupos_ch = [a.grupo] if a.grupo is not None else ([None] if not (uc.divide_grupos and turma.num_grupos > 1) else list(range(1, turma.num_grupos + 1)))
    for g in grupos_ch:
        realizados, programados = carga_horaria_minutos(b, tuc, g, ignorar)
        if realizados + programados + a.minutos_aula > total_min:
            excedente = (realizados + programados + a.minutos_aula - total_min) / 60
            rotulo = f" (grupo {g})" if g else ""
            if excecao_tipo == "carga_horaria":
                add(ALERTA, "CH_EXCEDIDA_AUTORIZADA", f"Carga horária de {uc.codigo}{rotulo} excedida em {excedente:.1f} h, autorizada pela exceção #{excecao.id}.")
            else:
                add(BLOQUEIO, "CARGA_HORARIA_EXCEDIDA",
                    f"A UC {uc.codigo}{rotulo} tem {uc.carga_horaria_total} h; realizadas {realizados / 60:.1f} h, programadas {programados / 60:.1f} h. Esta aula excederia em {excedente:.1f} h.")
    return oc


def _pico_uso(intervalos: list[tuple[datetime, datetime, int]]) -> int:
    eventos = []
    for ini, fim, q in intervalos:
        if fim > ini:
            eventos.append((ini, 1, q))
            eventos.append((fim, 0, -q))
    eventos.sort()
    atual = pico = 0
    for _, _, delta in eventos:
        atual += delta
        pico = max(pico, atual)
    return pico


def possui_bloqueio(oc: list[Ocorrencia]) -> bool:
    return any(o.severidade == BLOQUEIO for o in oc)


def resumo(oc: list[Ocorrencia]) -> dict:
    cont = defaultdict(int)
    for o in oc:
        cont[o.severidade] += 1
    return {"bloqueios": cont[BLOQUEIO], "alertas": cont[ALERTA], "preferencias": cont[PREFERENCIA], "recomendacoes": cont[RECOMENDACAO]}


# =============================================================================
# Validação de cenário inteiro
# =============================================================================
def validar_cenario(db: Session, cenario_id: int) -> list[Ocorrencia]:
    b = BaseDados(db, cenario_id).precarregar()
    vistos: set[tuple] = set()
    resultado: list[Ocorrencia] = []
    for s in list(b._sessoes.values()):
        if s.status == "realizada":
            continue  # aulas já realizadas são fatos, não planejamento
        tuc = b.get(TurmaUC, s.turma_uc_id)
        grupo = None if len(s.grupos) == len(TODOS_GRUPOS) else s.grupos[0]
        a = AulaProposta(turma_uc_id=s.turma_uc_id, inicio=s.inicio, fim=s.fim, minutos_aula=s.minutos_aula,
                         grupo=grupo, instrutor_id=s.instrutor_id, ambiente_id=s.ambiente_id,
                         recursos=list(s.recursos.items()), alocacao_id=s.id, origem="validacao_cenario")
        al = db.get(Alocacao, s.id)
        a.excecao_id = al.excecao_id if al else None
        # Carga horária: avaliada uma única vez por turma×UC abaixo.
        for o in validar_aula(b, a):
            if o.regra in ("CARGA_HORARIA_EXCEDIDA", "CH_EXCEDIDA_AUTORIZADA"):
                continue
            chave = (o.regra, o.recurso_tipo, o.recurso_id, frozenset([s.id, *o.relacionados]))
            if o.relacionados and chave in vistos:
                continue
            vistos.add(chave)
            resultado.append(o)
        _ = tuc
    # carga horária por turma×UC
    tucs = {s.turma_uc_id for s in b._sessoes.values()}
    for tuc_id in tucs:
        tuc = b.get(TurmaUC, tuc_id)
        uc = b.get(UnidadeCurricular, tuc.uc_id)
        turma = b.get(Turma, tuc.turma_id)
        grupos_ch = [None] if not (uc.divide_grupos and turma.num_grupos > 1) else list(range(1, turma.num_grupos + 1))
        for g in grupos_ch:
            realizados, programados = carga_horaria_minutos(b, tuc, g, set())
            if realizados + programados > uc.carga_horaria_total * 60:
                autorizadas = db.scalar(select(func.count()).select_from(Alocacao).where(
                    Alocacao.cenario_id == cenario_id, Alocacao.turma_uc_id == tuc_id, Alocacao.excecao_id.isnot(None),
                    Alocacao.excecao_id.in_(select(ExcecaoAutorizada.id).where(ExcecaoAutorizada.tipo == "carga_horaria"))))
                sev = ALERTA if autorizadas else BLOQUEIO
                resultado.append(Ocorrencia(sev, "CARGA_HORARIA_EXCEDIDA",
                                            f"Turma {turma.codigo} – UC {uc.codigo}{f' (grupo {g})' if g else ''}: {(realizados + programados) / 60:.1f} h programadas/realizadas para {uc.carga_horaria_total} h.",
                                            turma_id=turma.id, uc_id=uc.id, origem="validacao_cenario"))
    return resultado


def ocorrencias_pendencias(db: Session, cenario_id: int, turma_ucs: list[TurmaUC]) -> list[Ocorrencia]:
    """Alertas de UCs sem programação suficiente (risco de não conclusão)."""
    from app.services.planejamento import situacao_carga_horaria  # import tardio (evita ciclo)
    res = []
    for tuc in turma_ucs:
        info = situacao_carga_horaria(db, cenario_id, tuc)
        if info["restante_h"] > 0.01 and tuc.situacao not in ("concluida", "cancelada"):
            res.append(Ocorrencia(ALERTA, "CH_PENDENTE",
                                  f"Turma {info['turma_codigo']} – UC {info['uc_codigo']}: {info['restante_h']:.1f} h ainda sem programação.",
                                  turma_id=tuc.turma_id, uc_id=tuc.uc_id, origem="validacao_cenario"))
    return res
