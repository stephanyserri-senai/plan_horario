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


def sincronizar_turma(db: Session, turma: Turma, hoje: date | None = None) -> int:
    """Cria na turma os EPIs do curso que ainda não estão lá e acerta quantidade/prazo dos que ainda não foram
    providenciados (ex.: mudou o número de alunos ou a data de início). Não mexe no que já foi separado ou entregue."""
    if turma.simulacao_id is not None or not turma.curso_id:
        return 0
    hoje = hoje or date.today()
    epis = db.scalars(select(EpiCurso).where(EpiCurso.curso_id == turma.curso_id, EpiCurso.ativo.is_(True))).all()
    atuais = {e.epi_curso_id: e for e in db.scalars(select(EpiTurma).where(EpiTurma.turma_id == turma.id))}
    novos = 0
    for ec in epis:
        qtd = (turma.qtd_alunos or 0) * (ec.quantidade_por_aluno or 1)
        prazo = turma.data_inicio - timedelta(days=ec.antecedencia_dias or 0) if turma.data_inicio else None
        iniciada = turma.data_inicio is not None and turma.data_inicio <= hoje
        e = atuais.get(ec.id)
        if e is None:
            if iniciada and prazo is not None and prazo < hoje:
                prazo = hoje + timedelta(days=DIAS_AVISO)  # EPI novo numa turma já em aula: uma semana para providenciar
            db.add(EpiTurma(turma_id=turma.id, epi_curso_id=ec.id, nome=ec.nome, quantidade=qtd, prazo=prazo))
            novos += 1
        elif not e.providenciado and not e.entregue:
            e.nome, e.quantidade = ec.nome, qtd
            if not iniciada:  # depois do início, o prazo combinado não muda sozinho
                e.prazo = prazo
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


SEM_EPI = "Este curso está marcado como \"não precisa de EPI\". Desmarque a opção para montar a lista."


def definir_dispensa(db: Session, ctx, curso_id: int, dispensa: bool) -> Curso:
    """Marca (ou desmarca) que o curso não precisa de EPI. Só dá para marcar com a lista vazia."""
    c = db.get(Curso, curso_id)
    if c is None:
        raise NaoEncontrado("Curso não encontrado.")
    if dispensa and db.scalar(select(EpiCurso.id).where(EpiCurso.curso_id == curso_id, EpiCurso.ativo.is_(True)).limit(1)):
        raise EntradaInvalida("O curso tem EPIs na lista: retire-os antes de marcar que ele não precisa de EPI.")
    antes = c.dispensa_epi
    c.dispensa_epi = bool(dispensa)
    db.flush()
    auditoria.registrar(db, ctx, "epi.curso.dispensa", "cursos", c.id, antes={"dispensa_epi": antes}, depois={"dispensa_epi": c.dispensa_epi})
    return c


def criar_epi_curso(db: Session, ctx, curso_id: int, dados: dict) -> EpiCurso:
    c = db.get(Curso, curso_id)
    if c is None:
        raise NaoEncontrado("Curso não encontrado.")
    if c.dispensa_epi:
        raise EntradaInvalida(SEM_EPI)
    e = EpiCurso(curso_id=curso_id, **_validar(dados))
    db.add(e)
    db.flush()
    sincronizar_curso(db, curso_id)
    auditoria.registrar(db, ctx, "epi.curso.criar", "epis_curso", e.id, depois=ser_curso(e))
    return e


def importar_lista(db: Session, ctx, curso_id: int, texto: str, antecedencia_padrao: int = 15) -> dict:
    """Lista colada (um EPI por linha; opcional "nome; quantidade por aluno; dias de antecedência"). Repetidos
    (mesmo nome já ativo no curso) são ignorados. As turmas do curso em andamento ou futuras recebem tudo de uma vez."""
    c = db.get(Curso, curso_id)
    if c is None:
        raise NaoEncontrado("Curso não encontrado.")
    if c.dispensa_epi:
        raise EntradaInvalida(SEM_EPI)
    existentes = {e.nome.strip().lower() for e in db.scalars(select(EpiCurso).where(EpiCurso.curso_id == curso_id, EpiCurso.ativo.is_(True)))}
    criados, repetidos = [], []
    for n, linha in enumerate((texto or "").splitlines(), 1):
        partes = [p.strip() for p in linha.replace("\t", ";").split(";")]
        if not partes or not partes[0]:
            continue
        dados = {"nome": partes[0], "quantidade_por_aluno": partes[1] if len(partes) > 1 and partes[1] else 1,
                 "antecedencia_dias": partes[2] if len(partes) > 2 and partes[2] else antecedencia_padrao}
        try:
            v = _validar(dados)
        except EntradaInvalida as e:
            raise EntradaInvalida(f"Linha {n} ({partes[0]}): {e}")
        if v["nome"].lower() in existentes:
            repetidos.append(v["nome"])
            continue
        e = EpiCurso(curso_id=curso_id, **v)
        db.add(e)
        existentes.add(v["nome"].lower())
        criados.append(e)
    if not criados and not repetidos:
        raise EntradaInvalida("Cole ao menos um EPI (um por linha).")
    db.flush()
    turmas = sincronizar_curso(db, curso_id)
    for e in criados:
        auditoria.registrar(db, ctx, "epi.curso.criar", "epis_curso", e.id, depois=ser_curso(e), origem="lista")
    return {"criados": [ser_curso(e) for e in criados], "repetidos": repetidos, "itens_nas_turmas": turmas}


def resumo_cursos(db: Session, unidades=None, hoje: date | None = None) -> list[dict]:
    """Por curso: quantos EPIs tem a lista e quantas turmas ativas estão no controle."""
    from app.models import Area
    hoje = hoje or date.today()
    areas = {a.id: a for a in db.scalars(select(Area))}
    n_epis: dict[int, int] = {}
    for e in db.scalars(select(EpiCurso).where(EpiCurso.ativo.is_(True))):
        n_epis[e.curso_id] = n_epis.get(e.curso_id, 0) + 1
    turmas: dict[int, int] = {}
    for t in db.scalars(select(Turma).where(Turma.simulacao_id.is_(None))):
        if _ativa(t, hoje):
            turmas[t.curso_id] = turmas.get(t.curso_id, 0) + 1
    res = []
    for c in db.scalars(select(Curso).where(Curso.ativo.is_(True)).order_by(Curso.nome)):
        if unidades is not None and c.unidade_id is not None and c.unidade_id not in unidades:
            continue
        a = areas.get(c.area_id)
        res.append({"id": c.id, "codigo": c.codigo, "nome": c.nome, "area_id": c.area_id, "area": a.nome if a else "Sem área",
                    "epis": n_epis.get(c.id, 0), "turmas_ativas": turmas.get(c.id, 0), "dispensa_epi": c.dispensa_epi})
    return res


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
                      "observacao": e.observacao, "situacao": s, "situacao_rotulo": SITUACOES[s], "avulso": e.epi_curso_id is None})
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


def incluir_avulso(db: Session, ctx, turma: Turma, dados: dict) -> EpiTurma:
    """EPI incluído à mão numa turma (fora da lista do curso): ex.: necessidade específica de uma turma."""
    nome = (dados.get("nome") or "").strip()
    if not nome:
        raise EntradaInvalida("Informe o EPI.")
    try:
        qtd = int(dados.get("quantidade") if dados.get("quantidade") not in (None, "") else (turma.qtd_alunos or 0))
        prazo = date.fromisoformat(str(dados["prazo"])) if dados.get("prazo") else (turma.data_inicio - timedelta(days=15) if turma.data_inicio else None)
    except (TypeError, ValueError):
        raise EntradaInvalida("Quantidade ou prazo inválido.")
    if qtd < 0:
        raise EntradaInvalida("A quantidade não pode ser negativa.")
    e = EpiTurma(turma_id=turma.id, epi_curso_id=None, nome=nome[:150], quantidade=qtd, prazo=prazo,
                 observacao=(dados.get("observacao") or "").strip()[:1000] or None, atualizado_por_id=getattr(ctx, "id", None))
    db.add(e)
    db.flush()
    auditoria.registrar(db, ctx, "epi.turma.incluir", "epis_turma", e.id, depois={"turma": turma.codigo, "nome": e.nome, "quantidade": qtd, "prazo": str(prazo)})
    return e


def excluir(db: Session, ctx, eid: int) -> None:
    """Exclui um EPI da turma. Os que vêm da lista do curso voltariam na próxima atualização da turma:
    para esses, retire o EPI do curso (ou mantenha e marque)."""
    e = db.get(EpiTurma, eid)
    if e is None:
        raise NaoEncontrado("EPI da turma não encontrado.")
    if e.epi_curso_id is not None:
        raise EntradaInvalida("Este EPI vem da lista do curso: para tirá-lo, retire-o do curso (Cursos, matrizes e UCs).")
    auditoria.registrar(db, ctx, "epi.turma.excluir", "epis_turma", e.id, antes={"nome": e.nome, "quantidade": e.quantidade})
    db.delete(e)
    db.flush()


def avisos(db: Session, unidades=None, hoje: date | None = None) -> dict:
    """Quantos EPIs estão com prazo vencido ou vencendo (para os avisos do Início e de Riscos)."""
    r = listar(db, unidades, hoje=hoje)
    return {"atrasados": r["resumo"]["atrasado"], "proximos": r["resumo"]["proximo"],
            "itens": [i for i in r["itens"] if i["situacao"] in ("atrasado", "proximo")]}
