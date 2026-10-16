"""EPIs: o que cada curso exige por aluno e o controle, por turma, do que comprar/separar e entregar.

- O curso lista os EPIs (quantidade por aluno e quantos dias antes do início da turma eles devem estar prontos).
- Cada turma do curso recebe a sua lista: quantidade = alunos × quantidade por aluno; prazo = início − antecedência.
- O controle tem duas marcações: "comprado/separado" e "entregue à turma". Prazo vencido ou próximo vira aviso
  (Início, Riscos e a página de EPIs), para ninguém esquecer da entrega.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import EntradaInvalida, NaoEncontrado
from app.models import Curso, EpiCurso, EpiTurma, Turma
from app.services import auditoria

DIAS_AVISO = 7  # prazo a até 7 dias: "vence em breve"
SITUACOES = {"entregue": "Entregue", "atrasado": "Prazo vencido", "proximo": "Vence em breve", "providenciado": "Separado, falta entregar",
             "pendente": "A providenciar"}


def situacao(e: EpiTurma, hoje: date | None = None) -> str:
    hoje = hoje or date.today()
    if e.entregue:
        return "entregue"
    if e.prazo and e.prazo < hoje:
        return "atrasado"
    if e.prazo and e.prazo <= hoje + timedelta(days=DIAS_AVISO):
        return "proximo"
    return "providenciado" if e.providenciado else "pendente"


def _ativa(t: Turma, hoje: date) -> bool:
    return t.simulacao_id is None and t.ativo and t.situacao not in ("concluida", "cancelada") and (t.data_fim is None or t.data_fim >= hoje)


def sincronizar_turma(db: Session, turma: Turma) -> int:
    """Cria na turma os EPIs do curso que ainda não estão lá e acerta quantidade/prazo dos que ainda não foram
    providenciados (ex.: mudou o número de alunos ou a data de início). Não mexe no que já foi separado ou entregue."""
    if turma.simulacao_id is not None or not turma.curso_id:
        return 0
    epis = db.scalars(select(EpiCurso).where(EpiCurso.curso_id == turma.curso_id, EpiCurso.ativo.is_(True))).all()
    atuais = {e.epi_curso_id: e for e in db.scalars(select(EpiTurma).where(EpiTurma.turma_id == turma.id))}
    novos = 0
    for ec in epis:
        qtd = (turma.qtd_alunos or 0) * (ec.quantidade_por_aluno or 1)
        prazo = turma.data_inicio - timedelta(days=ec.antecedencia_dias or 0) if turma.data_inicio else None
        e = atuais.get(ec.id)
        if e is None:
            db.add(EpiTurma(turma_id=turma.id, epi_curso_id=ec.id, nome=ec.nome, quantidade=qtd, prazo=prazo))
            novos += 1
        elif not e.providenciado and not e.entregue:
            e.nome, e.quantidade, e.prazo = ec.nome, qtd, prazo
    db.flush()
    return novos


def sincronizar_curso(db: Session, curso_id: int, hoje: date | None = None) -> int:
    """Leva os EPIs do curso às turmas ainda em andamento ou futuras."""
    hoje = hoje or date.today()
    return sum(sincronizar_turma(db, t) for t in db.scalars(select(Turma).where(Turma.curso_id == curso_id)) if _ativa(t, hoje))


# ----------------------------------------------------------------------------- EPIs do curso
def ser_curso(e: EpiCurso) -> dict:
    return {"id": e.id, "curso_id": e.curso_id, "nome": e.nome, "quantidade_por_aluno": e.quantidade_por_aluno,
            "antecedencia_dias": e.antecedencia_dias, "observacao": e.observacao, "ativo": e.ativo}


def _validar(dados: dict) -> dict:
    nome = (dados.get("nome") or "").strip()
    if not nome:
        raise EntradaInvalida("Informe o EPI (ex.: luva isolante, óculos de proteção).")
    try:
        qtd = int(dados.get("quantidade_por_aluno") or 1)
        ant = int(dados.get("antecedencia_dias") if dados.get("antecedencia_dias") not in (None, "") else 15)
    except (TypeError, ValueError):
        raise EntradaInvalida("Quantidade e antecedência devem ser números inteiros.")
    if qtd < 1 or not 0 <= ant <= 180:
        raise EntradaInvalida("Quantidade por aluno a partir de 1; antecedência entre 0 e 180 dias.")
    return {"nome": nome[:150], "quantidade_por_aluno": qtd, "antecedencia_dias": ant, "observacao": (dados.get("observacao") or "").strip() or None}


def criar_epi_curso(db: Session, ctx, curso_id: int, dados: dict) -> EpiCurso:
    if db.get(Curso, curso_id) is None:
        raise NaoEncontrado("Curso não encontrado.")
    e = EpiCurso(curso_id=curso_id, **_validar(dados))
    db.add(e)
    db.flush()
    sincronizar_curso(db, curso_id)
    auditoria.registrar(db, ctx, "epi.curso.criar", "epis_curso", e.id, depois=ser_curso(e))
    return e


def alterar_epi_curso(db: Session, ctx, eid: int, dados: dict) -> EpiCurso:
    e = db.get(EpiCurso, eid)
    if e is None:
        raise NaoEncontrado("EPI não encontrado.")
    antes = ser_curso(e)
    if "ativo" in dados and len(dados) == 1:
        e.ativo = bool(dados["ativo"])
    else:
        for k, v in _validar({**antes, **dados}).items():
            setattr(e, k, v)
    db.flush()
    if e.ativo:
        sincronizar_curso(db, e.curso_id)
    else:  # retirado do curso: sai das turmas onde ainda não foi providenciado
        for t in db.scalars(select(EpiTurma).where(EpiTurma.epi_curso_id == e.id, EpiTurma.providenciado.is_(False), EpiTurma.entregue.is_(False))):
            db.delete(t)
    auditoria.registrar(db, ctx, "epi.curso.alterar", "epis_curso", e.id, antes=antes, depois=ser_curso(e))
    return e


# ----------------------------------------------------------------------------- controle por turma
def listar(db: Session, unidades=None, turma_id: int | None = None, curso_id: int | None = None, situacao_filtro: str | None = None,
           hoje: date | None = None) -> dict:
    hoje = hoje or date.today()
    q = select(EpiTurma, Turma).join(Turma, Turma.id == EpiTurma.turma_id).where(Turma.simulacao_id.is_(None))
    if unidades is not None:
        q = q.where(Turma.unidade_id.in_(unidades))
    if turma_id:
        q = q.where(Turma.id == turma_id)
    if curso_id:
        q = q.where(Turma.curso_id == curso_id)
    cursos = {c.id: c for c in db.scalars(select(Curso))}
    itens, resumo = [], {k: 0 for k in SITUACOES}
    for e, t in db.execute(q.order_by(EpiTurma.prazo.nulls_last(), Turma.codigo, EpiTurma.nome)).all():
        if not turma_id and not _ativa(t, hoje) and e.entregue:
            continue  # turmas encerradas com tudo entregue saem da lista geral
        s = situacao(e, hoje)
        resumo[s] += 1
        if situacao_filtro and s != situacao_filtro and not (situacao_filtro == "abertos" and s != "entregue"):
            continue
        c = cursos.get(t.curso_id)
        itens.append({"id": e.id, "turma_id": t.id, "turma": t.codigo, "turma_nome": t.nome, "inicio_turma": t.data_inicio.isoformat() if t.data_inicio else None,
                      "alunos": t.qtd_alunos, "curso": f"{c.codigo} – {c.nome}" if c else None, "nome": e.nome, "quantidade": e.quantidade,
                      "prazo": e.prazo.isoformat() if e.prazo else None, "dias_para_prazo": (e.prazo - hoje).days if e.prazo else None,
                      "providenciado": e.providenciado, "providenciado_em": e.providenciado_em.isoformat() if e.providenciado_em else None,
                      "entregue": e.entregue, "entregue_em": e.entregue_em.isoformat() if e.entregue_em else None,
                      "observacao": e.observacao, "situacao": s, "situacao_rotulo": SITUACOES[s]})
    return {"itens": itens, "resumo": resumo, "hoje": hoje.isoformat(), "dias_aviso": DIAS_AVISO}


def marcar(db: Session, ctx, eid: int, dados: dict) -> EpiTurma:
    """Marca/desmarca "comprado/separado" e "entregue"; ajusta prazo, quantidade ou observação. Entregue implica separado."""
    e = db.get(EpiTurma, eid)
    if e is None:
        raise NaoEncontrado("EPI da turma não encontrado.")
    antes = {k: getattr(e, k) for k in ("providenciado", "entregue", "prazo", "quantidade", "observacao")}
    agora = datetime.now()
    if "providenciado" in dados:
        e.providenciado = bool(dados["providenciado"])
        e.providenciado_em = agora if e.providenciado else None
        if not e.providenciado:
            e.entregue, e.entregue_em = False, None
    if "entregue" in dados:
        e.entregue = bool(dados["entregue"])
        e.entregue_em = agora if e.entregue else None
        if e.entregue and not e.providenciado:
            e.providenciado, e.providenciado_em = True, agora
    if "prazo" in dados:
        try:
            e.prazo = date.fromisoformat(str(dados["prazo"])) if dados["prazo"] else None
        except ValueError:
            raise EntradaInvalida("Prazo inválido.")
    if "quantidade" in dados:
        try:
            e.quantidade = max(0, int(dados["quantidade"]))
        except (TypeError, ValueError):
            raise EntradaInvalida("Quantidade inválida.")
    if "observacao" in dados:
        e.observacao = (dados["observacao"] or "").strip()[:1000] or None
    e.atualizado_por_id = getattr(ctx, "id", None)
    db.flush()
    auditoria.registrar(db, ctx, "epi.turma.marcar", "epis_turma", e.id, antes={k: str(v) for k, v in antes.items()},
                        depois={k: str(getattr(e, k)) for k in antes})
    return e


def avisos(db: Session, unidades=None, hoje: date | None = None) -> dict:
    """Quantos EPIs estão com prazo vencido ou vencendo (para os avisos do Início e de Riscos)."""
    r = listar(db, unidades, hoje=hoje)
    return {"atrasados": r["resumo"]["atrasado"], "proximos": r["resumo"]["proximo"],
            "itens": [i for i in r["itens"] if i["situacao"] in ("atrasado", "proximo")]}
