"""Pedidos de impressão dos instrutores (material de aula).

O instrutor pede pelo portal; a coordenação atende e dá o retorno. Regra: o pedido é feito até a QUINTA-FEIRA da
semana anterior ao uso (material de segunda a sábado da semana S → pedido até a quinta da semana S-1).
Situações: pendente → em produção → pronta (para retirar) → entregue; ou recusada; o instrutor pode cancelar enquanto pendente.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ConflitoValidacao, EntradaInvalida, NaoEncontrado
from app.models import Instrutor, SolicitacaoImpressao, Turma
from app.services import auditoria
from app.services.notificacoes import notificar

STATUS = {"pendente": "Aguardando a coordenação", "em_producao": "Em produção", "pronta": "Pronta para retirar",
          "entregue": "Entregue", "recusada": "Recusada", "cancelada": "Cancelada"}
# a coordenação muda a situação nesta ordem (e pode recusar enquanto não estiver pronta)
PROXIMOS = {"pendente": ["em_producao", "pronta", "recusada"], "em_producao": ["pronta", "recusada"], "pronta": ["entregue"],
            "entregue": [], "recusada": [], "cancelada": []}
DIA_LIMITE = 3  # quinta-feira
MAX_PDF = 4 * 1024 * 1024  # 4 MB (limite de envio da hospedagem); maior que isso, mande o link do arquivo


def hoje() -> date:
    return date.today()


def prazo_para(data_uso: date) -> date:
    """Quinta-feira da semana anterior à semana de uso."""
    segunda_uso = data_uso - timedelta(days=data_uso.weekday())
    return segunda_uso - timedelta(days=7) + timedelta(days=DIA_LIMITE)


def serializar(db: Session, s: SolicitacaoImpressao) -> dict:
    inst = db.get(Instrutor, s.instrutor_id)
    t = db.get(Turma, s.turma_id) if s.turma_id else None
    return {"id": s.id, "instrutor_id": s.instrutor_id, "instrutor": inst.nome if inst else None, "turma_id": s.turma_id,
            "turma": t.codigo if t else None, "titulo": s.titulo, "descricao": s.descricao, "arquivo_url": s.arquivo_url,
            "arquivo_nome": s.arquivo_nome, "arquivo_tamanho": s.arquivo_tamanho, "tem_pdf": bool(s.arquivo_nome),
            "copias": s.copias, "paginas": s.paginas, "frente_verso": s.frente_verso, "colorido": s.colorido,
            "folhas": s.copias * (-(-(s.paginas or 1) // 2) if s.frente_verso else (s.paginas or 1)),
            "data_uso": s.data_uso.isoformat(), "prazo": s.prazo.isoformat(), "status": s.status, "status_rotulo": STATUS[s.status],
            "proximos": PROXIMOS.get(s.status, []), "resposta": s.resposta,
            "atendido_em": s.atendido_em.isoformat() if s.atendido_em else None, "criado_em": s.criado_em.isoformat() if s.criado_em else None}


def criar(db: Session, ctx, inst: Instrutor, d: dict) -> SolicitacaoImpressao:
    titulo = (d.get("titulo") or "").strip()
    if len(titulo) < 3:
        raise EntradaInvalida("Diga o que vai ser impresso (ex.: apostila de comandos elétricos, prova da UC ELT-INS).")
    try:
        data_uso = date.fromisoformat(str(d.get("data_uso"))[:10])
    except ValueError:
        raise EntradaInvalida("Informe o dia em que o material será usado.")
    try:
        copias = int(d.get("copias") or 0)
        paginas = int(d["paginas"]) if d.get("paginas") not in (None, "") else None
    except (TypeError, ValueError):
        raise EntradaInvalida("Cópias e páginas devem ser números inteiros.")
    if copias < 1 or copias > 2000:
        raise EntradaInvalida("Informe o número de cópias (de 1 a 2000).")
    if paginas is not None and (paginas < 1 or paginas > 1000):
        raise EntradaInvalida("Número de páginas inválido (de 1 a 1000).")
    prazo = prazo_para(data_uso)
    if hoje() > prazo:
        raise ConflitoValidacao(f"Fora do prazo: para usar em {data_uso:%d/%m}, a impressão deveria ter sido pedida até a quinta-feira "
                                f"{prazo:%d/%m} (semana anterior). Escolha outra data de uso ou fale com a coordenação.",
                                codigo="IMPRESSAO_FORA_DO_PRAZO")
    turma_id = int(d["turma_id"]) if d.get("turma_id") else None
    url = (d.get("arquivo_url") or "").strip() or None
    if url and not (url.startswith("http://") or url.startswith("https://")):
        raise EntradaInvalida("O link do arquivo deve começar com https:// (ex.: link do Drive ou do OneDrive).")
    s = SolicitacaoImpressao(instrutor_id=inst.id, turma_id=turma_id, titulo=titulo[:200], descricao=(d.get("descricao") or "").strip() or None,
                             arquivo_url=url, copias=copias, paginas=paginas, frente_verso=bool(d.get("frente_verso")),
                             colorido=bool(d.get("colorido")), data_uso=data_uso, prazo=prazo, status="pendente")
    db.add(s)
    db.flush()
    auditoria.registrar(db, ctx, "impressao.solicitar", "solicitacoes_impressao", s.id, depois=auditoria.snapshot(s))
    return s


def anexar_pdf(db: Session, ctx, inst: Instrutor, sid: int, nome: str, conteudo: bytes) -> SolicitacaoImpressao:
    """PDF para imprimir, enviado com o pedido (enquanto ele ainda não foi atendido)."""
    s = db.get(SolicitacaoImpressao, sid)
    if s is None or s.instrutor_id != inst.id:
        raise NaoEncontrado("Pedido de impressão não encontrado.")
    if s.status != "pendente":
        raise ConflitoValidacao("O pedido já está com a coordenação: para trocar o arquivo, fale com ela.")
    if not conteudo:
        raise EntradaInvalida("O arquivo está vazio.")
    if len(conteudo) > MAX_PDF:
        raise EntradaInvalida(f"O PDF tem {len(conteudo) / 1048576:.1f} MB; o limite é 4 MB. Para arquivo maior, mande o link (Drive, OneDrive…).")
    if not conteudo.startswith(b"%PDF"):
        raise EntradaInvalida("Envie o material em PDF.")
    nome = (nome or "material.pdf").replace("/", "_").replace("\\", "_")[:200]
    s.arquivo_nome, s.arquivo_tamanho, s.arquivo_pdf = nome if nome.lower().endswith(".pdf") else nome + ".pdf", len(conteudo), conteudo
    db.flush()
    auditoria.registrar(db, ctx, "impressao.anexar_pdf", "solicitacoes_impressao", s.id, depois={"arquivo_nome": s.arquivo_nome, "tamanho": len(conteudo)})
    return s


def pdf(db: Session, sid: int) -> tuple[SolicitacaoImpressao, bytes]:
    s = db.get(SolicitacaoImpressao, sid)
    if s is None or not s.arquivo_nome:
        raise NaoEncontrado("Este pedido não tem PDF.")
    return s, s.arquivo_pdf or b""


def cancelar(db: Session, ctx, inst: Instrutor, sid: int) -> SolicitacaoImpressao:
    s = db.get(SolicitacaoImpressao, sid)
    if s is None or s.instrutor_id != inst.id:
        raise NaoEncontrado("Pedido de impressão não encontrado.")
    if s.status != "pendente":
        raise ConflitoValidacao("Só dá para cancelar um pedido que ainda não foi atendido.")
    s.status = "cancelada"
    db.flush()
    auditoria.registrar(db, ctx, "impressao.cancelar", "solicitacoes_impressao", s.id)
    return s


def atender(db: Session, ctx, sid: int, status: str, resposta: str | None = None) -> SolicitacaoImpressao:
    """Retorno da coordenação: em produção, pronta (para retirar), entregue ou recusada — o instrutor é avisado no portal."""
    s = db.get(SolicitacaoImpressao, sid)
    if s is None:
        raise NaoEncontrado("Pedido de impressão não encontrado.")
    if status not in PROXIMOS.get(s.status, []):
        raise ConflitoValidacao(f"O pedido está '{STATUS[s.status].lower()}': não dá para passar para '{STATUS.get(status, status).lower()}'.")
    resposta = (resposta or "").strip() or None
    if status == "recusada" and not resposta:
        raise EntradaInvalida("Diga o motivo da recusa (o instrutor recebe o retorno).")
    antes = auditoria.snapshot(s)
    s.status, s.atendido_por_id, s.atendido_em = status, getattr(ctx, "id", None), datetime.now()
    if resposta:
        s.resposta = resposta
    db.flush()
    auditoria.registrar(db, ctx, "impressao.atender", "solicitacoes_impressao", s.id, antes=antes, depois=auditoria.snapshot(s))
    titulo = {"em_producao": f"Impressão em produção: {s.titulo}", "pronta": f"✅ Impressão pronta: {s.titulo}",
              "entregue": f"Impressão entregue: {s.titulo}", "recusada": f"Impressão recusada: {s.titulo}"}[status]
    notificar(db, s.instrutor_id, "impressao", titulo, (resposta or STATUS[status]) + f" (uso em {s.data_uso:%d/%m}).", "impressoes", ctx)
    return s


def listar(db: Session, instrutor_id: int | None = None, status: str | None = None, unidades=None) -> list[dict]:
    q = select(SolicitacaoImpressao).join(Instrutor, Instrutor.id == SolicitacaoImpressao.instrutor_id)
    if instrutor_id:
        q = q.where(SolicitacaoImpressao.instrutor_id == instrutor_id)
    if status:
        q = q.where(SolicitacaoImpressao.status == status)
    if unidades is not None:
        q = q.where(Instrutor.unidade_id.in_(unidades or [-1]))
    ordem = {"pendente": 0, "em_producao": 1, "pronta": 2, "recusada": 3, "entregue": 4, "cancelada": 5}
    lista = [serializar(db, s) for s in db.scalars(q.order_by(SolicitacaoImpressao.data_uso, SolicitacaoImpressao.id).limit(500))]
    return sorted(lista, key=lambda x: (ordem.get(x["status"], 9), x["data_uso"]))
