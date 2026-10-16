"""API genérica de cadastros: consulta paginada com pesquisa e filtros,
inclusão, edição, inativação/reativação, histórico e opções para seleção."""
from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal

from fastapi import APIRouter, Body, Depends, Query, Request
from sqlalchemy import String, cast, delete, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.registro import ENTIDADES, SOMENTE_LEITURA, campos
from app.core.db import get_db
from app.core.deps import Contexto, get_contexto
from app.core.errors import ConflitoConcorrencia, ConflitoValidacao, EntradaInvalida, NaoEncontrado
from app.models import (
    Curso, HistoricoAuditoria, MatrizCurricular, Turma, TurmaUC, UCPrerequisito, UCRecurso, UCTipoAmbiente, Unidade, UnidadeCurricular,
    CompetenciaInstrutor,
)
from app.services import auditoria
from app.services.regras_aula import horas_dia_pela_carga, jornada_dos_codigos, normalizar_jornada, turnos_por_dia, validar_jornada

router = APIRouter(prefix="/api", tags=["cadastros"])


def _cfg(ent: str) -> dict:
    if ent not in ENTIDADES:
        raise NaoEncontrado(f"Cadastro '{ent}' inexistente.")
    return ENTIDADES[ent]


def serializar(obj, ent: str, ctx: Contexto | None = None) -> dict:
    cfg = ENTIDADES[ent]
    d = auditoria.snapshot(obj)
    for k in cfg.get("ocultar", []):
        d.pop(k, None)
    if ctx is not None and not ctx.pode("dados_pessoais.ler"):
        for k in cfg.get("pessoais", []):
            if k in d:
                d[k] = None
    if ent == "ucs":
        d["tipos_ambiente_ids"] = [t.id for t in obj.tipos_ambiente]
    if ent in ("instrutores", "ambientes") and getattr(obj, "id", None):
        from sqlalchemy.orm import object_session
        from app.models import AmbienteArea, InstrutorArea
        M, col = (InstrutorArea, InstrutorArea.instrutor_id) if ent == "instrutores" else (AmbienteArea, AmbienteArea.ambiente_id)
        sess = object_session(obj)
        d["areas_ids"] = sorted(sess.scalars(select(M.area_id).where(col == obj.id)).all()) if sess else []
    if ent == "instrutores" and getattr(obj, "id", None):
        from sqlalchemy.orm import object_session
        from app.api.portal import acesso_do_instrutor
        sess = object_session(obj)
        d.update(_dados_instrutor(sess, obj))
        d["_acesso_portal"] = acesso_do_instrutor(sess, obj.id) if sess else None
    if ent in ("turnos", "areas") and getattr(obj, "unidade_id", None):
        from sqlalchemy.orm import object_session
        sess = object_session(obj)
        un = sess.get(Unidade, obj.unidade_id) if sess else None
        d["_unidade"] = un.nome.removeprefix("Unidade ") if un else ""
    if ent == "turmas" and getattr(obj, "curso_id", None):
        from sqlalchemy.orm import object_session
        sess = object_session(obj)
        curso = sess.get(Curso, obj.curso_id) if sess else None
        d["_numero"], d["_tipo_oferta"] = _partes_codigo(curso.codigo if curso else "", obj.codigo or "")
    try:
        d["_rotulo"] = cfg["label"].format(**{k: ("" if v is None else v) for k, v in d.items()})
    except (KeyError, IndexError):
        d["_rotulo"] = str(d.get("id"))
    return d


def converter(ent: str, dados: dict, parcial: bool) -> dict:
    model = ENTIDADES[ent]["model"]
    cols = {c.key: c for c in model.__table__.columns}
    res, erros = {}, []
    for k, v in dados.items():
        if k not in cols or k in SOMENTE_LEITURA or k.startswith("_"):
            continue
        col = cols[k]
        try:
            if v in ("", None):
                v = None
            elif isinstance(col.type, (String,)) or col.type.__class__.__name__ == "Text":
                v = str(v).strip()
            else:
                pt = col.type.python_type
                if pt is bool:
                    v = v if isinstance(v, bool) else str(v).lower() in ("1", "true", "sim", "on")
                elif pt is int:
                    v = int(v)
                elif pt in (float, Decimal):
                    v = float(v)
                elif pt is date:
                    v = date.fromisoformat(str(v)[:10])
                elif pt is datetime:
                    v = datetime.fromisoformat(str(v))
                elif pt is time:
                    v = time.fromisoformat(str(v))
                elif pt is list:
                    v = [int(x) for x in v]
        except (ValueError, TypeError, NotImplementedError):
            erros.append(f"{k}: valor inválido")
            continue
        if v is None and not col.nullable and col.default is None:
            erros.append(f"{k}: obrigatório")
            continue
        res[k] = v
    if not parcial:
        for f in campos(ent):
            # a área é conferida em _regras_especificas (a turma pode herdá-la do curso)
            if f["obrigatorio"] and f["nome"] not in res and f["tipo"] != "multiref" and f["nome"] != "area_id":
                erros.append(f"{f['nome']}: obrigatório")
    if erros:
        raise EntradaInvalida("Dados inválidos: " + "; ".join(erros), detalhes={"erros": erros})
    return res


def _pk(ent: str, id_: str):
    cfg = ENTIDADES[ent]
    if "pk" in cfg:
        partes = id_.split(":")
        model = cfg["model"]
        conv = []
        for nome, p in zip(cfg["pk"], partes):
            conv.append(int(p) if model.__table__.c[nome].type.python_type is int else p)
        return tuple(conv)
    return int(id_)


def _verificar_escopo(ctx: Contexto, ent: str, obj):
    col = ENTIDADES[ent].get("unidade_col")
    if col:
        ctx.exigir_unidade(getattr(obj, col))
    if ent == "turmas" and not ctx.acessa_turma(obj):
        from app.core.errors import AcessoNegado
        raise AcessoNegado("Turma fora do seu escopo de acesso.")


FIXA_MSG = ("As unidades (Beira Mar e Porto) e as áreas tecnológicas são fixas da instituição: não podem ser incluídas, "
            "excluídas, inativadas nem renomeadas pelo sistema.")


def _regras_especificas(db: Session, ent: str, obj, dados: dict, novo: bool):
    """Regras de integridade de negócio dos cadastros."""
    cfg = ENTIDADES[ent]
    if cfg.get("fixa") and novo:
        raise ConflitoValidacao(FIXA_MSG, codigo="ESTRUTURA_FIXA")
    if not novo:
        mudou = [k for k in cfg.get("travados", []) if k in dados and getattr(obj, k) != dados[k]]
        if mudou:
            raise ConflitoValidacao(FIXA_MSG, codigo="ESTRUTURA_FIXA")
    if "area_id" in {c.key for c in cfg["model"].__table__.columns}:
        from app.models import Area
        if ent == "turmas" and novo and not dados.get("area_id"):
            curso = db.get(Curso, dados.get("curso_id") or obj.curso_id) if (dados.get("curso_id") or obj.curso_id) else None
            if curso and curso.area_id:
                obj.area_id = dados["area_id"] = curso.area_id  # turma herda a área do curso
        area_id = dados.get("area_id", obj.area_id)
        if novo and "area_id" in cfg.get("obrigatorios", []) and not area_id and not dados.get("todas_areas"):
            raise EntradaInvalida("Informe a área tecnológica (ex.: AUTOMAÇÃO, LOGÍSTICA) ou marque que atende todas as áreas.")
        if area_id:
            area = db.get(Area, int(area_id))
            if area is None:
                raise EntradaInvalida("Área inexistente.")
            unidade_id = dados.get("unidade_id", obj.unidade_id)
            if ent == "cursos" and not unidade_id:
                obj.unidade_id = dados["unidade_id"] = area.unidade_id  # curso assume a unidade da área
            elif unidade_id and int(unidade_id) != area.unidade_id:
                un = db.get(Unidade, area.unidade_id)
                raise ConflitoValidacao(f"A área {area.nome} pertence à {un.nome if un else 'outra unidade'}; escolha uma área da mesma unidade do cadastro.")
    if ent == "ucs" and not novo:
        em_uso = db.scalar(select(func.count()).select_from(Turma).where(Turma.matriz_id == obj.matriz_id, Turma.simulacao_id.is_(None)))
        estruturais = {"carga_horaria_total", "codigo", "matriz_id", "duracao_bloco_periodos", "ch_teorica", "ch_pratica"}
        if em_uso and estruturais & set(dados) and any(getattr(obj, k) != v for k, v in dados.items() if k in estruturais):
            raise ConflitoValidacao("Esta versão da matriz já é utilizada por turmas. Crie uma nova versão da matriz para alterar a estrutura da UC "
                                    "(alterações retroativas não são permitidas).", codigo="MATRIZ_EM_USO")
    if ent == "turma_ucs" and dados.get("uc_id"):
        turma = db.get(Turma, dados.get("turma_id") or obj.turma_id)
        uc = db.get(UnidadeCurricular, dados["uc_id"])
        if uc and turma and uc.matriz_id != turma.matriz_id:
            raise ConflitoValidacao("A UC não pertence à matriz curricular da turma.")
    if ent == "turmas" and ("matriz_id" in dados or "curso_id" in dados):
        m = db.get(MatrizCurricular, dados.get("matriz_id") or obj.matriz_id)
        if m and m.curso_id != (dados.get("curso_id") or obj.curso_id):
            raise ConflitoValidacao("A matriz curricular informada não pertence ao curso da turma.")
    if ent == "turmas" and (dados.get("turno_id") or "unidade_id" in dados):
        from app.models import Turno
        tid, uid = dados.get("turno_id", obj.turno_id), dados.get("unidade_id", obj.unidade_id)
        t = db.get(Turno, int(tid)) if tid else None
        if t is not None and uid and t.unidade_id != int(uid):
            raise ConflitoValidacao("O turno escolhido é de outra unidade: use o turno (manhã, tarde ou noite) da unidade do curso.")
    if ent == "instrutores":
        c = dados.get("carga_horaria_contratual", getattr(obj, "carga_horaria_contratual", None))
        l = dados.get("limite_ch_letiva", getattr(obj, "limite_ch_letiva", None))
        if c is not None and l is not None and float(l) > float(c):
            raise ConflitoValidacao("O limite de carga letiva não pode exceder a carga contratual.")
        from app.services.regras_aula import teto_letivo
        if c is not None and l is not None and teto_letivo(c) > 0 and float(l) > teto_letivo(c) + 1e-6:
            t = teto_letivo(c)
            raise ConflitoValidacao(f"Com {float(c):g} h semanais, o instrutor pode ter no máximo {t:g} h de aula por semana "
                                    f"({int(t // 4)} de {int(float(c) // 4)} turnos = 90% da jornada; o restante fica para planejamento).")


def _traduzir_integridade(e: IntegrityError):
    msg = str(e.orig)
    if "unique" in msg.lower() or "duplicate key" in msg.lower():
        raise ConflitoValidacao("Já existe um registro com estes identificadores (duplicidade).", detalhes={"banco": msg.split("DETAIL:")[-1].strip()[:300]})
    if "foreign key" in msg.lower():
        raise ConflitoValidacao("Referência inválida ou registro em uso por outros cadastros.", detalhes={"banco": msg.split("DETAIL:")[-1].strip()[:300]})
    if "check constraint" in msg.lower():
        raise ConflitoValidacao("Valores violam uma regra de integridade do cadastro.", detalhes={"banco": msg[:300]})
    raise e


# ============================================================================ preenchimento automático
def _partes_codigo(sigla: str, codigo: str) -> tuple[str | None, str | None]:
    """HTC-ELT-12 -> ('12', 'HTC'); ELT-12 (sem tipo) -> ('12', None); códigos fora do padrão -> (None, None)."""
    S, C = (sigla or "").upper(), (codigo or "").upper()
    if not S:
        return None, None
    i = C.find("-" + S + "-")
    if i > 0:
        return codigo[i + len(S) + 2:] or None, codigo[:i]
    if C.startswith(S + "-"):
        return codigo[len(S) + 1:] or None, None
    return None, None


def codigo_turma(sigla: str, numero, tipo) -> str:
    """Tipo de oferta + sigla do curso + número: HTC-ELT-12."""
    return "-".join(str(x).strip().upper() for x in (tipo, sigla, numero) if x not in (None, ""))


def _matriz_padrao(db: Session, curso_id: int, tipo_oferta: str | None = None) -> MatrizCurricular | None:
    """Versão da matriz para a turma: a vigente do tipo de oferta (ex.: HTC), senão a vigente geral, senão a mais recente."""
    ms = db.scalars(select(MatrizCurricular).where(MatrizCurricular.curso_id == curso_id, MatrizCurricular.ativo.is_(True))
                    .order_by(MatrizCurricular.id.desc())).all()
    tipo = (tipo_oferta or "").strip().upper() or None
    return (next((m for m in ms if m.situacao == "vigente" and tipo and m.tipo_oferta == tipo), None)
            or next((m for m in ms if m.situacao == "vigente" and not m.tipo_oferta), None)
            or next((m for m in ms if m.situacao == "vigente"), None) or (ms[0] if ms else None))


def _derivar(db: Session, ent: str, dados: dict, obj=None) -> dict:
    """Completa campos que vêm de outro cadastro, para o usuário não digitar a mesma coisa duas vezes."""
    from app.models import Area, Calendario, Turno
    d = dict(dados)
    vazio = lambda k: d.get(k) in (None, "")
    if ent == "cursos" and not vazio("area_id"):
        area = db.get(Area, int(d["area_id"]))
        if area:
            d["unidade_id"] = area.unidade_id  # a unidade do curso é sempre a da área
    if ent in ("instrutores", "ambientes") and not vazio("area_id") and not d.get("todas_areas"):
        area = db.get(Area, int(d["area_id"]))
        if area:
            d["unidade_id"] = area.unidade_id  # a unidade é sempre a da área principal
    if ent == "instrutores" and vazio("max_horas_dia") and not vazio("carga_horaria_contratual"):
        d["max_horas_dia"] = horas_dia_pela_carga(d["carga_horaria_contratual"])
    if ent == "instrutores" and obj is None and vazio("limite_ch_letiva") and not vazio("carga_horaria_contratual"):
        from app.services.regras_aula import teto_letivo
        d["limite_ch_letiva"] = teto_letivo(d["carga_horaria_contratual"]) or float(d["carga_horaria_contratual"])  # 90% da jornada
    if ent == "ambientes" and obj is None and vazio("capacidade_operacional") and not vazio("capacidade_fisica"):
        d["capacidade_operacional"] = d["capacidade_fisica"]
    if ent == "ucs" and obj is None and vazio("duracao_bloco_periodos"):
        d["duracao_bloco_periodos"] = 4  # turno inteiro (a regra do turno prevalece de qualquer forma)
    if ent == "turmas":
        curso_id = d.get("curso_id") or (obj.curso_id if obj else None)
        curso = db.get(Curso, int(curso_id)) if curso_id else None
        if curso:
            trocou_curso = obj is None or ("curso_id" in d and int(d["curso_id"]) != obj.curso_id)
            if vazio("matriz_id") and trocou_curso:
                m = _matriz_padrao(db, curso.id, d.get("_tipo_oferta"))
                if m is None:
                    raise ConflitoValidacao(f"O curso {curso.codigo} ainda não tem matriz curricular. Cadastre a matriz e as UCs antes da turma.")
                d["matriz_id"] = m.id
            if trocou_curso:
                d["area_id"] = curso.area_id
                area = db.get(Area, curso.area_id) if curso.area_id else None
                d["unidade_id"] = area.unidade_id if area else curso.unidade_id
            num = d.get("_numero")
            if num not in (None, ""):
                tipo = (d.get("_tipo_oferta") or "").strip().upper() or None
                novo = codigo_turma(curso.codigo, num, tipo)
                if obj is None or novo != obj.codigo:
                    d["codigo"] = novo
                    if vazio("nome") or (obj is not None and d.get("nome") == obj.nome):
                        from app.api.registro import TIPOS_OFERTA
                        rot = next((t["rotulo"].split(" – ", 1)[1] for t in TIPOS_OFERTA if t["valor"] == tipo), tipo)
                        turno = db.get(Turno, int(d.get("turno_id") or (obj.turno_id if obj else 0) or 0)) if (d.get("turno_id") or (obj and obj.turno_id)) else None
                        if tipo == "PFP":  # turma de manhã e tarde (08–12 e 13–17)
                            rot, turno = "PFP (manhã e tarde)", None
                        d["nome"] = f"{curso.nome} {num}" + (f" – {rot}" if rot else "") + (f" ({turno.nome})" if turno else "")
        if "dias_ead" in d or "dias_possiveis" in d:
            from app.services.planejamento import dias_com_ead
            ead = d["dias_ead"] if "dias_ead" in d else (obj.dias_ead if obj else [])
            d["dias_ead"] = sorted({int(x) for x in (ead or [])})
            d["dias_possiveis"] = dias_com_ead(d["dias_possiveis"] if "dias_possiveis" in d else (obj.dias_possiveis if obj else [0, 1, 2, 3, 4]),
                                               d["dias_ead"], obj.dias_ead if obj and "dias_ead" in d else None)
        # padrão de dias (regras institucionais): 5 presenciais | 4 + 1 EAD | só sábado; aperfeiçoamento/empresa pode ter menos
        if obj is None or any(k in d for k in ("dias_possiveis", "dias_ead", "turno_id", "curso_id", "_tipo_oferta", "codigo", "_numero")):
            from app.services.regras_institucionais import TURNO_SABADO, erro_padrao_dias, oferta_flexivel
            from app.services.regras_institucionais import TURNO_PFP, eh_pfp, erro_turno_pfp
            pfp = eh_pfp(d.get("codigo") or (obj.codigo if obj else None), d.get("_tipo_oferta"))
            un_t = d.get("unidade_id") or (obj.unidade_id if obj else None)
            if pfp and un_t:  # turma PFP: manhã 08–12 e tarde 13–17
                integral = db.scalar(select(Turno).where(Turno.unidade_id == int(un_t), Turno.codigo == TURNO_PFP))
                if integral is None:
                    raise EntradaInvalida("A unidade ainda não tem o horário das turmas PFP (aplique as atualizações 0011 e 0012).")
                d["turno_id"] = integral.id
            tid = d.get("turno_id") if "turno_id" in d else (obj.turno_id if obj else None)
            turno = db.get(Turno, int(tid)) if tid not in (None, "") else None
            erro_pfp = erro_turno_pfp(pfp, turno.codigo if turno else None)
            if erro_pfp:
                raise EntradaInvalida(erro_pfp)
            if turno is not None and turno.codigo == TURNO_SABADO:
                d["dias_possiveis"], d["dias_ead"] = [5], []  # turma de sábado: só o sábado é presencial
            dias = d["dias_possiveis"] if "dias_possiveis" in d else (obj.dias_possiveis if obj else [0, 1, 2, 3, 4])
            ead = d["dias_ead"] if "dias_ead" in d else (obj.dias_ead if obj else [])
            cid = d.get("curso_id") or (obj.curso_id if obj else None)
            erro = erro_padrao_dias([int(x) for x in dias or []], [int(x) for x in ead or []], turno.codigo if turno else None,
                                    oferta_flexivel(db, d.get("codigo") or (obj.codigo if obj else None) or
                                                    (f"{(d.get('_tipo_oferta') or '').upper()}-" if d.get("_tipo_oferta") else ""), int(cid) if cid else None))
            if erro:
                raise EntradaInvalida(erro)
        if obj is None and vazio("codigo") and vazio("_numero"):
            raise EntradaInvalida("Informe o número da turma (o código é montado com a sigla do curso e o tipo de oferta).")
        un = d.get("unidade_id") or (obj.unidade_id if obj else None)
        if un and obj is None and (vazio("data_inicio") or vazio("data_fim") or vazio("calendario_id")):
            from datetime import date as _date
            cals = db.scalars(select(Calendario).where(Calendario.unidade_id == int(un), Calendario.ativo.is_(True))
                              .order_by(Calendario.data_inicio)).all()
            ini = _date.fromisoformat(str(d["data_inicio"])[:10]) if not vazio("data_inicio") else None
            cal = next((c for c in cals if ini and c.data_inicio <= ini <= c.data_fim), None) or \
                next((c for c in cals if c.data_fim >= _date.today()), cals[-1] if cals else None)
            if cal:
                if vazio("calendario_id"):
                    d["calendario_id"] = cal.id
                if vazio("data_inicio"):
                    d["data_inicio"] = cal.data_inicio.isoformat()
                if vazio("data_fim"):
                    d["data_fim"] = cal.data_fim.isoformat()
    return d


# ============================================================================ instrutor: UCs e disponibilidade no próprio cadastro
def _dados_instrutor(db: Session | None, inst) -> dict:
    from app.models import DisponibilidadeInstrutor, Turno
    if db is None:
        return {}
    comps = db.scalars(select(CompetenciaInstrutor).where(CompetenciaInstrutor.instrutor_id == inst.id, CompetenciaInstrutor.ativo.is_(True))).all()
    disp = db.scalars(select(DisponibilidadeInstrutor).where(DisponibilidadeInstrutor.instrutor_id == inst.id)).all()
    # jornada = turnos de segunda a sexta (M, V, N); o sábado (turno S, 09:00–13:00) é marcado à parte pelo dia
    from app.services.regras_aula import TURNOS_ESPECIAIS
    turnos = [t for t in db.scalars(select(Turno).where(Turno.unidade_id == inst.unidade_id, Turno.ativo.is_(True))) if t.codigo not in TURNOS_ESPECIAIS]
    t_ids = [t.id for t in turnos if any(x.dia_semana < 5 and x.hora_inicio <= t.hora_inicio and x.hora_fim >= t.hora_fim for x in disp)]
    janelas = {(t.hora_inicio, t.hora_fim) for t in turnos}
    from datetime import time as _t
    from app.services.regras_aula import BLOCOS_PFP
    integral = {(_t.fromisoformat(a), _t.fromisoformat(b)) for a, b, _c in BLOCOS_PFP} | {(_t(8), _t(17))}  # janelas das turmas PFP
    cod = {t.id: t.codigo for t in turnos}
    return {"ucs_competencia": [{"uc_id": c.uc_id, "nivel": c.nivel} for c in comps],
            "jornada": jornada_dos_codigos(cod[i] for i in t_ids) if t_ids else None,
            "disp_turnos": t_ids, "disp_dias": sorted({x.dia_semana for x in disp}),
            "disp_personalizada": any((x.hora_inicio, x.hora_fim) not in janelas | integral for x in disp if x.dia_semana < 5)}


def _gravar_instrutor(db: Session, inst, dados: dict):
    from app.models import DisponibilidadeInstrutor, Turno
    if dados.get("ucs_competencia") is not None:
        quer = {int(x["uc_id"]): (x.get("nivel") or "pleno") for x in dados["ucs_competencia"] if x.get("uc_id")}
        atuais = {c.uc_id: c for c in db.scalars(select(CompetenciaInstrutor).where(CompetenciaInstrutor.instrutor_id == inst.id))}
        for uc_id, c in atuais.items():
            if uc_id not in quer:
                c.ativo = False
        for uc_id, nivel in quer.items():
            if uc_id in atuais:
                atuais[uc_id].ativo, atuais[uc_id].nivel = True, nivel
            else:
                if db.get(UnidadeCurricular, uc_id) is None:
                    raise EntradaInvalida("UC inexistente.")
                db.add(CompetenciaInstrutor(instrutor_id=inst.id, uc_id=uc_id, nivel=nivel, ativo=True))
    turnos_un = {t.codigo: t for t in db.scalars(select(Turno).where(Turno.unidade_id == inst.unidade_id, Turno.ativo.is_(True)))}
    if dados.get("jornada") not in (None, ""):
        # turnos de trabalho (M, V, N, MV ou VN) → turnos da unidade do instrutor
        from app.services.regras_aula import JORNADAS
        j = normalizar_jornada(str(dados["jornada"]))
        if j is None:
            raise EntradaInvalida("Turnos de trabalho inválidos: use M, V, N, MV ou VN.")
        faltando = [c for c in JORNADAS[j] if c not in turnos_un]
        if faltando:
            raise EntradaInvalida("A unidade do instrutor não tem os turnos desta jornada cadastrados.")
        dados = {**dados, "disp_turnos": [turnos_un[c].id for c in JORNADAS[j]]}
    if dados.get("disp_turnos") is not None:
        ids = [int(x) for x in dict.fromkeys(dados["disp_turnos"])]
        por_id = {t.id: t for t in turnos_un.values()}
        if any(i not in por_id for i in ids):
            raise EntradaInvalida("Turno inválido para a unidade do instrutor.")
        erro = validar_jornada(jornada_dos_codigos(por_id[i].codigo for i in ids), inst.max_horas_dia)
        if erro:
            raise ConflitoValidacao(erro)
        inst.turno_preferencial_id = ids[0] if ids else None
        dias = [int(x) for x in (dados.get("disp_dias") if dados.get("disp_dias") is not None else [0, 1, 2, 3, 4])]
        db.execute(delete(DisponibilidadeInstrutor).where(DisponibilidadeInstrutor.instrutor_id == inst.id))
        for tid in dados["disp_turnos"]:
            t = db.get(Turno, int(tid))
            if t is None or t.unidade_id != inst.unidade_id:
                raise EntradaInvalida("Turno inválido para a unidade do instrutor.")
            for dia in dias:
                if dia == 5 and "S" in turnos_un:
                    continue  # sábado: turno próprio (abaixo)
                db.add(DisponibilidadeInstrutor(instrutor_id=inst.id, dia_semana=dia, hora_inicio=t.hora_inicio, hora_fim=t.hora_fim))
        cods = {db.get(Turno, int(x)).codigo for x in dados["disp_turnos"]}
        if "I" in turnos_un:  # turmas PFP: quem é da manhã dá 08–12; quem é da tarde, 13–17
            from datetime import time as _t
            from app.services.regras_aula import janelas_pfp
            for a, b in janelas_pfp(cods):
                for dia in [x for x in dias if x < 5]:
                    db.add(DisponibilidadeInstrutor(instrutor_id=inst.id, dia_semana=dia, hora_inicio=_t.fromisoformat(a), hora_fim=_t.fromisoformat(b)))
        if 5 in dias and "S" in turnos_un:  # dá aula aos sábados: 09:00–13:00
            sab = turnos_un["S"]
            db.add(DisponibilidadeInstrutor(instrutor_id=inst.id, dia_semana=5, hora_inicio=sab.hora_inicio, hora_fim=sab.hora_fim))
    elif inst.id and ("max_horas_dia" in dados or "carga_horaria_contratual" in dados):
        # mudou a carga sem mexer nos turnos: os turnos atuais precisam continuar valendo (40 h = MV ou VN)
        db.flush()
        atual = _dados_instrutor(db, inst)
        if atual["jornada"] and not atual["disp_personalizada"]:
            erro = validar_jornada(atual["jornada"], inst.max_horas_dia)
            if erro:
                raise ConflitoValidacao(erro + " Ajuste os turnos de trabalho junto com a carga.")
    db.flush()


@router.get("/cadastros-apoio/ucs-por-area")
def ucs_por_area(areas: str = "", unidade_id: int | None = None, todas: bool = False, db: Session = Depends(get_db), ctx: Contexto = Depends(get_contexto)):
    """UCs dos cursos das áreas escolhidas (para marcar o que o instrutor ministra)."""
    ctx.exigir("cadastros.ler")
    return listar_ucs_por_area(db, [int(x) for x in areas.split(",") if x.strip()], unidade_id, todas)


def listar_ucs_por_area(db: Session, ids: list[int], unidade_id: int | None = None, todas: bool = False) -> list[dict]:
    from app.models import Area
    q = select(Curso).where(Curso.ativo.is_(True))
    if todas and unidade_id:
        q = q.where(Curso.area_id.in_(select(Area.id).where(Area.unidade_id == unidade_id)))
    elif not todas:
        q = q.where(Curso.area_id.in_(ids or [-1]))
    nomes_area = {a.id: a.nome for a in db.scalars(select(Area))}
    res = []
    for c in db.scalars(q.order_by(Curso.nome)):
        ms = db.scalars(select(MatrizCurricular).where(MatrizCurricular.curso_id == c.id, MatrizCurricular.ativo.is_(True)).order_by(MatrizCurricular.id)).all()
        for m in ms:
            ucs = db.scalars(select(UnidadeCurricular).where(UnidadeCurricular.matriz_id == m.id, UnidadeCurricular.ativo.is_(True))
                             .order_by(UnidadeCurricular.sequencia, UnidadeCurricular.codigo)).all()
            if ucs:
                res.append({"curso_id": c.id, "curso": f"{c.codigo} – {c.nome}" + (f" (matriz {m.versao})" if len(ms) > 1 else ""),
                            "area": nomes_area.get(c.area_id), "ucs": [{"id": u.id, "codigo": u.codigo, "nome": u.nome, "ch": u.carga_horaria_total,
                                                                        "certificacao": u.certificacao_exigida, "categoria": u.categoria} for u in ucs]})
    return res


@router.get("/cadastros-apoio/codigo-turma")
def previa_codigo_turma(curso_id: int, numero: str = "", tipo: str = "", db: Session = Depends(get_db), ctx: Contexto = Depends(get_contexto)):
    ctx.exigir("cadastros.ler")
    curso = db.get(Curso, curso_id)
    if curso is None:
        raise NaoEncontrado("Curso não encontrado.")
    cod = codigo_turma(curso.codigo, numero, tipo) if numero else None
    existe = bool(cod and db.scalar(select(func.count()).select_from(Turma).where(Turma.codigo == cod)))
    m = _matriz_padrao(db, curso.id)
    return {"codigo": cod, "existe": existe, "sigla": curso.codigo, "matriz": m.versao if m else None}


@router.get("/meta/entidades")
def meta(ctx: Contexto = Depends(get_contexto)):
    return [{"chave": k, "rotulo": c["rotulo"], "grupo": c["grupo"], "campos": campos(k), "busca": c["busca"],
             "inativavel": hasattr(c["model"], "ativo") and not c.get("fixa"), "fixa": bool(c.get("fixa")), "pk": c.get("pk", ["id"])}
            for k, c in ENTIDADES.items()]


def _condicoes_unidade(ent: str, M, ctx: Contexto) -> list:
    """Filtro de unidade dos cadastros: coluna de unidade (escopo do usuário) e, quando a unidade foi escolhida na
    tela, também os cadastros ligados a ela por relação (UCs pelo curso, competências pelo instrutor etc.)."""
    from app.models import Ambiente, Calendario, Instrutor
    cfg = _cfg(ent)
    col_un = cfg.get("unidade_col")
    filtro = ctx.extra.get("filtro_unidade")
    un = ctx.unidades
    if ent == "unidades":
        un = ctx.extra.get("unidades_escopo", ctx.unidades)  # a lista de unidades mostra todas as do escopo (para trocar o filtro)
    if un is None:
        return []
    if col_un:
        return [or_(getattr(M, col_un).in_(un), getattr(M, col_un).is_(None))]
    if filtro is None:
        return []
    cursos = select(Curso.id).where(Curso.unidade_id.in_(un))
    rel = {
        "matrizes": lambda: M.curso_id.in_(cursos),
        "ucs": lambda: M.matriz_id.in_(select(MatrizCurricular.id).where(MatrizCurricular.curso_id.in_(cursos))),
        "turma_ucs": lambda: M.turma_id.in_(select(Turma.id).where(Turma.unidade_id.in_(un))),
        "competencias": lambda: M.instrutor_id.in_(select(Instrutor.id).where(Instrutor.unidade_id.in_(un))),
        "habilitacoes": lambda: M.instrutor_id.in_(select(Instrutor.id).where(Instrutor.unidade_id.in_(un))),
        "disponibilidade_instrutores": lambda: M.instrutor_id.in_(select(Instrutor.id).where(Instrutor.unidade_id.in_(un))),
        "disponibilidade_ambientes": lambda: M.ambiente_id.in_(select(Ambiente.id).where(Ambiente.unidade_id.in_(un))),
        "recursos_ambientes": lambda: M.ambiente_id.in_(select(Ambiente.id).where(Ambiente.unidade_id.in_(un))),
        "calendario_excecoes": lambda: M.calendario_id.in_(select(Calendario.id).where(Calendario.unidade_id.in_(un))),
    }
    return [rel[ent]()] if ent in rel else []


@router.get("/cadastros/{ent}")
def listar(ent: str, request: Request, q: str | None = None, pagina: int = 1, por_pagina: int = Query(25, le=500), ativo: bool | None = None,
           ordenar: str | None = None, db: Session = Depends(get_db), ctx: Contexto = Depends(get_contexto)):
    ctx.exigir("cadastros.ler")
    cfg = _cfg(ent)
    M = cfg["model"]
    stmt = select(M)
    if hasattr(M, "simulacao_id"):
        stmt = stmt.where(M.simulacao_id.is_(None))
    if ativo is not None and hasattr(M, "ativo"):
        stmt = stmt.where(M.ativo.is_(ativo))
    for cond in _condicoes_unidade(ent, M, ctx):
        stmt = stmt.where(cond)
    if ent == "turmas":
        if ctx.cursos is not None:
            stmt = stmt.where(M.curso_id.in_(ctx.cursos))
        if ctx.turmas is not None:
            stmt = stmt.where(M.id.in_(ctx.turmas))
    if q and cfg["busca"]:
        stmt = stmt.where(or_(*[cast(getattr(M, c), String).ilike(f"%{q}%") for c in cfg["busca"]]))
    # filtros combináveis: ?campo=valor (igualdade) para qualquer coluna
    cols = {c.key: c for c in M.__table__.columns}
    for k, v in request.query_params.items():
        if k in cols and v != "":
            col = cols[k]
            try:
                pt = col.type.python_type
                if pt is bool:
                    stmt = stmt.where(col == (v.lower() in ("1", "true", "sim")))
                elif pt is list:
                    stmt = stmt.where(col.any(int(v)))
                else:
                    stmt = stmt.where(col == (pt(v) if pt in (int, float) else (date.fromisoformat(v) if pt is date else v)))
            except (ValueError, NotImplementedError):
                raise EntradaInvalida(f"Filtro inválido: {k}={v}")
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    if ordenar:
        desc = ordenar.startswith("-")
        nome = ordenar.lstrip("-")
        if nome in cols:
            stmt = stmt.order_by(cols[nome].desc() if desc else cols[nome])
    else:
        pkcols = list(M.__table__.primary_key.columns)
        stmt = stmt.order_by(*pkcols)
    itens = db.scalars(stmt.offset((pagina - 1) * por_pagina).limit(por_pagina)).all()
    return {"total": total, "pagina": pagina, "por_pagina": por_pagina, "itens": [serializar(o, ent, ctx) for o in itens]}


@router.get("/cadastros/{ent}/opcoes")
def opcoes(ent: str, q: str | None = None, limite: int = 500, db: Session = Depends(get_db), ctx: Contexto = Depends(get_contexto)):
    ctx.exigir("cadastros.ler")
    cfg = _cfg(ent)
    M = cfg["model"]
    stmt = select(M)
    if hasattr(M, "ativo"):
        stmt = stmt.where(M.ativo.is_(True))
    if hasattr(M, "simulacao_id"):
        stmt = stmt.where(M.simulacao_id.is_(None))
    if q and cfg["busca"]:
        stmt = stmt.where(or_(*[cast(getattr(M, c), String).ilike(f"%{q}%") for c in cfg["busca"]]))
    if "filtro_unidade" in ctx.extra:  # listas suspensas seguem a unidade escolhida na tela
        for cond in _condicoes_unidade(ent, M, ctx):
            stmt = stmt.where(cond)
    res = []
    filtrada = "filtro_unidade" in ctx.extra
    for o in db.scalars(stmt.limit(limite)):
        s = serializar(o, ent, ctx)
        rotulo = s["_rotulo"]
        if filtrada and s.get("_unidade") and rotulo.endswith(f" – {s['_unidade']}"):
            rotulo = rotulo[: -len(f" – {s['_unidade']}")]  # com uma unidade só na tela, o sufixo "– Porto" é redundante
        item = {"id": s.get("id"), "rotulo": rotulo}
        if "unidade_id" in s:
            item["unidade_id"] = s["unidade_id"]
        if "area_id" in s:
            item["area_id"] = s["area_id"]
        if ent == "turmas":  # a grade usa para marcar os dias EAD (turmas 80-20) no turno da turma
            item.update({"turno_id": o.turno_id, "curso_id": o.curso_id, "dias_ead": list(o.dias_ead or []), "data_inicio": o.data_inicio.isoformat(),
                         "data_fim": o.data_fim.isoformat()})
        res.append(item)
    return res


@router.get("/cadastros/{ent}/{id_}")
def obter(ent: str, id_: str, db: Session = Depends(get_db), ctx: Contexto = Depends(get_contexto)):
    ctx.exigir("cadastros.ler")
    obj = db.get(_cfg(ent)["model"], _pk(ent, id_))
    if obj is None:
        raise NaoEncontrado("Registro não encontrado.")
    _verificar_escopo(ctx, ent, obj)
    return serializar(obj, ent, ctx)


def _aplicar_extras(db: Session, ent: str, obj, dados: dict):
    if ent in ("instrutores", "ambientes") and dados.get("areas_ids") is not None:
        gravar_outras_areas(db, ent, obj, dados["areas_ids"])
    if ent == "instrutores":
        _gravar_instrutor(db, obj, dados)
    if ent == "ucs" and "tipos_ambiente_ids" in dados and dados["tipos_ambiente_ids"] is not None:
        db.execute(delete(UCTipoAmbiente).where(UCTipoAmbiente.uc_id == obj.id))
        for tid in dados["tipos_ambiente_ids"]:
            db.add(UCTipoAmbiente(uc_id=obj.id, tipo_ambiente_id=int(tid)))
        db.flush()
        db.refresh(obj)


def _norm(v):
    """Compara listas sem depender da ordem (inclusive listas de dicionários)."""
    if isinstance(v, list):
        return sorted(repr(sorted(x.items()) if isinstance(x, dict) else x) for x in v)
    return v


def _avisar_instrutor(db: Session, ctx, ent: str, obj, campos: list[str] | None = None, acao: str = "alterou"):
    """Notifica o instrutor quando a coordenação mexe no cadastro dele (ou em algo ligado a ele)."""
    from app.services.notificacoes import CADASTROS_DO_INSTRUTOR, avisar_alteracao_cadastro, notificar
    if ent == "instrutores" and campos:
        avisar_alteracao_cadastro(db, ctx, obj.id, campos, acao)
    elif ent in CADASTROS_DO_INSTRUTOR and getattr(obj, "instrutor_id", None):
        rotulo, aba = CADASTROS_DO_INSTRUTOR[ent]
        quem = getattr(getattr(ctx, "usuario", None), "nome", None) or "A coordenação"
        notificar(db, obj.instrutor_id, "cadastro", "Seu cadastro foi atualizado", f"{quem} {acao}: {rotulo}.", aba, ctx)


def gravar_outras_areas(db: Session, ent: str, obj, areas_ids):
    """Áreas adicionais (além da principal), sempre da mesma unidade."""
    from app.models import AmbienteArea, Area, InstrutorArea
    M, col, chave = (InstrutorArea, InstrutorArea.instrutor_id, "instrutor_id") if ent == "instrutores" else (AmbienteArea, AmbienteArea.ambiente_id, "ambiente_id")
    db.execute(delete(M).where(col == obj.id))
    for aid in {int(x) for x in areas_ids if x} - {obj.area_id}:
        area = db.get(Area, aid)
        if area is None:
            raise EntradaInvalida("Área inexistente.")
        if area.unidade_id != obj.unidade_id:
            raise ConflitoValidacao(f"A área {area.nome} é de outra unidade.")
        db.add(M(**{chave: obj.id, "area_id": aid}))
    db.flush()


@router.post("/cadastros/{ent}")
def criar(ent: str, dados: dict = Body(...), db: Session = Depends(get_db), ctx: Contexto = Depends(get_contexto)):
    ctx.exigir("cadastros.editar")
    cfg = _cfg(ent)
    dados = _derivar(db, ent, dados)
    vals = converter(ent, dados, parcial=False)
    obj = cfg["model"](**vals)
    _verificar_escopo(ctx, ent, obj)
    _regras_especificas(db, ent, obj, vals, novo=True)
    try:
        db.add(obj)
        db.flush()
        _aplicar_extras(db, ent, obj, dados)
        if ent != "instrutores":
            _avisar_instrutor(db, ctx, ent, obj, acao="incluiu")
        if ent == "turmas" and dados.get("criar_ofertas", True):
            for uc in db.scalars(select(UnidadeCurricular).where(UnidadeCurricular.matriz_id == obj.matriz_id, UnidadeCurricular.ativo.is_(True))):
                db.add(TurmaUC(turma_id=obj.id, uc_id=uc.id, situacao="prevista"))
            db.flush()
        auditoria.registrar(db, ctx, "cadastro.criar", cfg["model"].__tablename__, getattr(obj, "id", None), depois=auditoria.snapshot(obj))
        db.commit()
    except IntegrityError as e:
        db.rollback()
        _traduzir_integridade(e)
    return serializar(obj, ent, ctx)


@router.put("/cadastros/{ent}/{id_}")
def atualizar(ent: str, id_: str, dados: dict = Body(...), db: Session = Depends(get_db), ctx: Contexto = Depends(get_contexto)):
    ctx.exigir("cadastros.editar")
    cfg = _cfg(ent)
    obj = db.get(cfg["model"], _pk(ent, id_), with_for_update=True)
    if obj is None:
        raise NaoEncontrado("Registro não encontrado.")
    _verificar_escopo(ctx, ent, obj)
    # controle otimista: se o cliente enviar atualizado_em, ele deve coincidir
    if dados.get("atualizado_em") and hasattr(obj, "atualizado_em") and obj.atualizado_em and \
            str(obj.atualizado_em.isoformat())[:19] != str(dados["atualizado_em"])[:19]:
        raise ConflitoConcorrencia("Este registro foi alterado por outro usuário. Recarregue antes de salvar.")
    dados = _derivar(db, ent, dados, obj)
    vals = converter(ent, dados, parcial=True)
    _regras_especificas(db, ent, obj, vals, novo=False)
    antes = auditoria.snapshot(obj)
    extras_antes = {**_dados_instrutor(db, obj), "areas_ids": serializar(obj, ent).get("areas_ids")} if ent == "instrutores" else {}
    for k, v in vals.items():
        setattr(obj, k, v)
    _verificar_escopo(ctx, ent, obj)
    try:
        db.flush()
        _aplicar_extras(db, ent, obj, dados)
        if ent == "instrutores":
            depois_ = auditoria.snapshot(obj)
            extras_depois = {**_dados_instrutor(db, obj), "areas_ids": serializar(obj, ent).get("areas_ids")}
            mudou = [k for k in vals if str(antes.get(k)) != str(depois_.get(k))]
            mudou += [k for k in ("areas_ids", "ucs_competencia", "disp_turnos", "disp_dias")
                      if dados.get(k) is not None and _norm(extras_antes.get(k)) != _norm(extras_depois.get(k))]
            _avisar_instrutor(db, ctx, ent, obj, mudou)
        else:
            _avisar_instrutor(db, ctx, ent, obj)
        auditoria.registrar(db, ctx, "cadastro.alterar", cfg["model"].__tablename__, getattr(obj, "id", id_), antes=antes,
                            depois=auditoria.snapshot(obj), motivo=dados.get("_motivo"))
        db.commit()
    except IntegrityError as e:
        db.rollback()
        _traduzir_integridade(e)
    return serializar(obj, ent, ctx)


@router.post("/cadastros/{ent}/{id_}/inativar")
def inativar(ent: str, id_: str, dados: dict = Body(default={}), db: Session = Depends(get_db), ctx: Contexto = Depends(get_contexto)):
    return _ativo(ent, id_, False, dados.get("motivo"), db, ctx)


@router.post("/cadastros/{ent}/{id_}/reativar")
def reativar(ent: str, id_: str, dados: dict = Body(default={}), db: Session = Depends(get_db), ctx: Contexto = Depends(get_contexto)):
    return _ativo(ent, id_, True, dados.get("motivo"), db, ctx)


def _ativo(ent, id_, valor, motivo, db, ctx):
    ctx.exigir("cadastros.editar")
    cfg = _cfg(ent)
    if cfg.get("fixa"):
        raise ConflitoValidacao(FIXA_MSG, codigo="ESTRUTURA_FIXA")
    obj = db.get(cfg["model"], _pk(ent, id_))
    if obj is None or not hasattr(obj, "ativo"):
        raise NaoEncontrado("Registro não encontrado ou não inativável.")
    _verificar_escopo(ctx, ent, obj)
    obj.ativo = valor
    _avisar_instrutor(db, ctx, ent, obj, ["ativo"] if ent == "instrutores" else None, "reativou" if valor else "inativou")
    auditoria.registrar(db, ctx, "cadastro.reativar" if valor else "cadastro.inativar", cfg["model"].__tablename__, getattr(obj, "id", id_),
                        depois={"ativo": valor}, motivo=motivo)
    db.commit()
    return serializar(obj, ent, ctx)


@router.delete("/cadastros/{ent}/{id_}")
def excluir(ent: str, id_: str, db: Session = Depends(get_db), ctx: Contexto = Depends(get_contexto)):
    """Exclusão física apenas para vínculos e registros sem histórico próprio
    (cadastros principais são inativados)."""
    ctx.exigir("cadastros.editar")
    cfg = _cfg(ent)
    M = cfg["model"]
    if cfg.get("fixa"):
        raise ConflitoValidacao(FIXA_MSG, codigo="ESTRUTURA_FIXA")
    if hasattr(M, "ativo") and ent not in ("disponibilidade_ambientes", "disponibilidade_instrutores", "calendario_excecoes", "bloqueios",
                                          "competencias", "habilitacoes", "periodos", "horarios_funcionamento", "deslocamentos"):
        raise ConflitoValidacao("Cadastros principais não são excluídos: utilize a inativação para preservar o histórico.")
    obj = db.get(M, _pk(ent, id_))
    if obj is None:
        raise NaoEncontrado("Registro não encontrado.")
    _verificar_escopo(ctx, ent, obj)
    antes = auditoria.snapshot(obj)
    try:
        db.delete(obj)
        db.flush()
        from types import SimpleNamespace
        _avisar_instrutor(db, ctx, ent, SimpleNamespace(**antes), acao="removeu")
        auditoria.registrar(db, ctx, "cadastro.excluir", M.__tablename__, id_, antes=antes)
        db.commit()
    except IntegrityError as e:
        db.rollback()
        _traduzir_integridade(e)
    return {"ok": True}


@router.get("/cadastros/{ent}/{id_}/historico")
def historico(ent: str, id_: str, db: Session = Depends(get_db), ctx: Contexto = Depends(get_contexto)):
    ctx.exigir("cadastros.ler")
    M = _cfg(ent)["model"]
    linhas = db.scalars(select(HistoricoAuditoria).where(HistoricoAuditoria.entidade == M.__tablename__, HistoricoAuditoria.entidade_id == str(id_))
                        .order_by(HistoricoAuditoria.em.desc()).limit(200)).all()
    return [{"id": h.id, "em": h.em.isoformat(), "usuario": h.usuario_nome, "acao": h.acao, "antes": h.antes, "depois": h.depois, "motivo": h.motivo,
             "origem": h.origem} for h in linhas]


@router.post("/cadastros/turmas/{id_}/duplicar")
def duplicar_turma(id_: int, dados: dict = Body(...), db: Session = Depends(get_db), ctx: Contexto = Depends(get_contexto)):
    ctx.exigir("cadastros.editar")
    t = db.get(Turma, id_)
    if t is None:
        raise NaoEncontrado("Turma não encontrada.")
    _verificar_escopo(ctx, "turmas", t)
    base = {k: v for k, v in auditoria.snapshot(t).items() if k not in ("id", "criado_em", "atualizado_em", "simulacao_id")}
    base.update({"codigo": dados["codigo"], "nome": dados.get("nome") or f"{t.nome} (cópia)", "situacao": "planejada"})
    vals = converter("turmas", {**base, **{k: v for k, v in dados.items() if k not in ("codigo", "nome")}}, parcial=False)
    nova = Turma(**vals)
    try:
        db.add(nova)
        db.flush()
        for tuc in db.scalars(select(TurmaUC).where(TurmaUC.turma_id == t.id)):
            db.add(TurmaUC(turma_id=nova.id, uc_id=tuc.uc_id, situacao="prevista"))
        auditoria.registrar(db, ctx, "cadastro.duplicar", "turmas", nova.id, depois={"origem": t.id, **auditoria.snapshot(nova)})
        db.commit()
    except IntegrityError as e:
        db.rollback()
        _traduzir_integridade(e)
    return serializar(nova, "turmas", ctx)


# ============================================================================ estrutura curricular (área → curso → versão → UCs)
@router.get("/estrutura-curricular")
def estrutura_curricular(area_id: int | None = None, db: Session = Depends(get_db), ctx: Contexto = Depends(get_contexto)):
    """Áreas com os cursos e as versões da matriz de cada curso (para navegar sem listas soltas)."""
    from app.models import Area, Turma
    ctx.exigir("cadastros.ler")
    q = select(Area).where(Area.ativo.is_(True)).order_by(Area.nome)
    if ctx.unidades is not None:
        q = q.where(Area.unidade_id.in_(ctx.unidades))
    areas = db.scalars(q).all()
    cursos = db.scalars(select(Curso).where(Curso.ativo.is_(True)).order_by(Curso.nome)).all()
    matrizes = db.scalars(select(MatrizCurricular).where(MatrizCurricular.ativo.is_(True)).order_by(MatrizCurricular.id)).all()
    ucs = db.execute(select(UnidadeCurricular.matriz_id, func.count(), func.sum(UnidadeCurricular.carga_horaria_total))
                     .where(UnidadeCurricular.ativo.is_(True)).group_by(UnidadeCurricular.matriz_id)).all()
    por_matriz = {m: (n, int(ch or 0)) for m, n, ch in ucs}
    turmas = dict(db.execute(select(Turma.matriz_id, func.count()).where(Turma.ativo.is_(True), Turma.simulacao_id.is_(None))
                             .group_by(Turma.matriz_id)).all())
    res = []
    for a in areas:
        if area_id and a.id != area_id:
            continue
        cs = []
        for c in [c for c in cursos if c.area_id == a.id]:
            vs = [{"id": m.id, "versao": m.versao, "tipo_oferta": m.tipo_oferta, "situacao": m.situacao,
                   "vigencia_inicio": m.vigencia_inicio.isoformat() if m.vigencia_inicio else None,
                   "ucs": por_matriz.get(m.id, (0, 0))[0], "ch_total": por_matriz.get(m.id, (0, 0))[1], "turmas": turmas.get(m.id, 0)}
                  for m in matrizes if m.curso_id == c.id]
            cs.append({"id": c.id, "codigo": c.codigo, "nome": c.nome, "tipo": c.tipo, "modalidade": c.modalidade,
                       "carga_horaria_total": c.carga_horaria_total, "versoes": vs})
        res.append({"id": a.id, "codigo": a.codigo, "nome": a.nome, "unidade_id": a.unidade_id, "cursos": cs})
    return res


@router.get("/estrutura-curricular/versoes/{mid}")
def ucs_da_versao(mid: int, db: Session = Depends(get_db), ctx: Contexto = Depends(get_contexto)):
    """UCs de uma versão da matriz, com classificação, carga horária, dias de aula, salas e certificação."""
    from app.models import Turma
    ctx.exigir("cadastros.ler")
    m = db.get(MatrizCurricular, mid)
    if m is None:
        raise NaoEncontrado("Versão da matriz não encontrada.")
    ucs = db.scalars(select(UnidadeCurricular).where(UnidadeCurricular.matriz_id == mid, UnidadeCurricular.ativo.is_(True))
                     .order_by(UnidadeCurricular.sequencia, UnidadeCurricular.codigo)).all()
    em_uso = db.scalar(select(func.count()).select_from(Turma).where(Turma.matriz_id == mid, Turma.simulacao_id.is_(None)))
    return {"versao": serializar(m, "matrizes", ctx), "em_uso_por_turmas": em_uso,
            "ucs": [{"id": u.id, "codigo": u.codigo, "nome": u.nome, "categoria": u.categoria, "carga_horaria_total": u.carga_horaria_total,
                     "encontros_semanais": u.encontros_semanais, "sequencia": u.sequencia, "certificacao_exigida": u.certificacao_exigida,
                     "tipos_ambiente_ids": [t.id for t in u.tipos_ambiente], "tipos_ambiente": [t.nome for t in u.tipos_ambiente]} for u in ucs]}


@router.post("/cadastros/matrizes/{id_}/nova_versao")
def nova_versao_matriz(id_: int, dados: dict = Body(...), db: Session = Depends(get_db), ctx: Contexto = Depends(get_contexto)):
    """Cria nova versão copiando UCs, tipos de ambiente, equipamentos,
    pré-requisitos e competências. A versão antiga permanece intacta."""
    ctx.exigir("cadastros.editar")
    m = db.get(MatrizCurricular, id_)
    if m is None:
        raise NaoEncontrado("Matriz não encontrada.")
    tipo = (dados.get("tipo_oferta", m.tipo_oferta) or "").strip().upper() or None
    nova = MatrizCurricular(curso_id=m.curso_id, versao=dados["versao"], vigencia_inicio=dados.get("vigencia_inicio"), situacao="rascunho",
                            tipo_oferta=tipo, matriz_origem_id=m.id)
    try:
        db.add(nova)
        db.flush()
        mapa = {}
        for uc in db.scalars(select(UnidadeCurricular).where(UnidadeCurricular.matriz_id == m.id)):
            snap = {k: v for k, v in auditoria.snapshot(uc).items() if k not in ("id", "criado_em", "atualizado_em")}
            snap["matriz_id"] = nova.id
            nu = UnidadeCurricular(**{k: v for k, v in snap.items() if k in UnidadeCurricular.__table__.c})
            db.add(nu)
            db.flush()
            mapa[uc.id] = nu.id
            for t in uc.tipos_ambiente:
                db.add(UCTipoAmbiente(uc_id=nu.id, tipo_ambiente_id=t.id))
            for r in db.scalars(select(UCRecurso).where(UCRecurso.uc_id == uc.id)):
                db.add(UCRecurso(uc_id=nu.id, recurso_tipo=r.recurso_tipo, quantidade=r.quantidade))
            for c in db.scalars(select(CompetenciaInstrutor).where(CompetenciaInstrutor.uc_id == uc.id)):
                db.add(CompetenciaInstrutor(instrutor_id=c.instrutor_id, uc_id=nu.id, nivel=c.nivel, condicoes=c.condicoes, valido_ate=c.valido_ate))
        for p in db.scalars(select(UCPrerequisito).where(UCPrerequisito.uc_id.in_(list(mapa)))):
            db.add(UCPrerequisito(uc_id=mapa[p.uc_id], prerequisito_id=mapa.get(p.prerequisito_id, p.prerequisito_id)))
        auditoria.registrar(db, ctx, "matriz.nova_versao", "matrizes_curriculares", nova.id, depois={"origem": m.id, "versao": nova.versao, "ucs": len(mapa)})
        db.commit()
    except IntegrityError as e:
        db.rollback()
        _traduzir_integridade(e)
    return serializar(nova, "matrizes", ctx)


@router.post("/unidades/{uid}/turnos-padrao")
def criar_turnos_padrao(uid: int, ctx: Contexto = Depends(get_contexto), db: Session = Depends(get_db)):
    """Cria os turnos da instituição (manhã, tarde e noite, 4 aulas cada) numa unidade que ainda não tem turnos.
    Não altera nem apaga turnos existentes."""
    from app.models import PeriodoHorario, Turno, Unidade
    from app.services.regras_aula import TURNOS_PADRAO
    ctx.exigir("cadastros.editar")
    un = db.get(Unidade, uid)
    if un is None:
        raise NaoEncontrado("Unidade inexistente.")
    if ctx.unidades is not None and uid not in ctx.unidades:
        raise EntradaInvalida("Unidade fora do seu escopo de acesso.")
    if db.scalar(select(func.count()).select_from(Turno).where(Turno.unidade_id == uid)):
        raise EntradaInvalida("Esta unidade já possui turnos cadastrados; ajuste-os em Cadastros → Turnos e horários.")
    hm = lambda m: time(m // 60, m % 60)  # noqa: E731
    criados = []
    for ordem, (cod, nome, aulas) in enumerate(TURNOS_PADRAO, 1):
        t = Turno(unidade_id=uid, codigo=cod, nome=nome, hora_inicio=hm(aulas[0][0]), hora_fim=hm(aulas[-1][0] + aulas[-1][1]), ordem=ordem)
        db.add(t)
        db.flush()
        for i, (ini, dur) in enumerate(aulas, 1):
            db.add(PeriodoHorario(unidade_id=uid, turno_id=t.id, ordem=i, hora_inicio=hm(ini), hora_fim=hm(ini + dur), dias_semana=[0, 1, 2, 3, 4]))
        criados.append(nome)
        auditoria.registrar(db, ctx, "turno.criar_padrao", "turnos", t.id, depois=auditoria.snapshot(t))
    db.commit()
    return {"criados": criados, "mensagem": "Turnos criados: manhã (07:30–11:30), tarde (13:30–17:30) e noite (18:30–22:00), com 4 aulas cada e intervalo no meio."}
