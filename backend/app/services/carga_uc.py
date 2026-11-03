"""Carga horária da unidade curricular: TOTAL (do aluno) = EaD + PRESENCIAL.

- A modalidade da UC (presencial, ead ou semipresencial) é diferente da modalidade do curso: um curso presencial pode ter
  UCs totalmente EaD ou com parte EaD. Nada é propagado do curso para as UCs.
- Só a carga PRESENCIAL vira aulas, encontros, reservas de sala/laboratório, conflitos e agenda do instrutor.
  As horas EaD assíncronas não ocupam ninguém; tutoria ou encontro remoto síncrono é uma atividade própria do
  instrutor (bloqueio tipo "tutoria_ead", com horário e duração), que conta na carga docente.
- A conversão de horas em aulas (55 min de dia, 50 à noite) acontece uma vez só, na geração das aulas, sobre as horas
  presenciais (minutos = horas × 60); os valores aqui são sempre HORAS.
"""
from __future__ import annotations

MODALIDADES_UC = ("presencial", "ead", "semipresencial")
ROTULO_MODALIDADE = {"presencial": "Presencial", "ead": "EaD", "semipresencial": "Semipresencial"}


class ErroCarga(ValueError):
    pass


def ch_presencial(uc) -> float:
    """Horas presenciais da UC (o que vira aula). Registro sem a divisão: EAD = 0; senão, a carga total."""
    p = getattr(uc, "carga_horaria_presencial", None)
    if p is not None:
        return float(p)
    return 0.0 if getattr(uc, "modalidade", "presencial") == "ead" else float(uc.carga_horaria_total or 0)


def ch_ead(uc) -> float:
    e = getattr(uc, "carga_horaria_ead", None)
    if e is not None:
        return float(e)
    return float(uc.carga_horaria_total or 0) if getattr(uc, "modalidade", "presencial") == "ead" else 0.0


def so_ead(uc) -> bool:
    """UC sem nenhuma hora presencial: não gera encontro nem reserva de ambiente."""
    return ch_presencial(uc) <= 0


def modalidade_das_cargas(ead: float, presencial: float) -> str:
    if presencial <= 0:
        return "ead"
    return "presencial" if ead <= 0 else "semipresencial"


def normalizar_modalidade(txt) -> str | None:
    import unicodedata
    t = "".join(c for c in unicodedata.normalize("NFD", str(txt or "")).lower() if unicodedata.category(c) != "Mn").strip()
    t = t.replace("-", "").replace(" ", "")
    if not t:
        return None
    if t in ("presencial", "p"):
        return "presencial"
    if t in ("ead", "ead100", "distancia", "adistancia", "online", "totalmenteead", "100ead"):
        return "ead"
    if t.startswith("semi") or t in ("hibrida", "hibrido", "misto", "mista"):
        return "semipresencial"
    raise ErroCarga(f"modalidade da UC '{txt}' inválida: use presencial, EAD ou semipresencial")


def horas(v, rotulo: str) -> float | None:
    """Converte a célula em horas: vazio = None (diferente de zero); aceita 24, 24,0, '24 h'; recusa negativo."""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        n = float(v)
    else:
        s = str(v).strip().lower().replace("horas", "").replace("hrs", "").replace("h", "").strip()
        if s == "":
            return None
        if "," in s and "." in s:
            s = s.replace(".", "")
        try:
            n = float(s.replace(",", "."))
        except ValueError:
            raise ErroCarga(f"{rotulo} '{v}' não é um número")
    if n < 0:
        raise ErroCarga(f"{rotulo} não pode ser negativa ({n:g})")
    if abs(n - round(n)) > 1e-6:
        raise ErroCarga(f"{rotulo} {n:g} h: use horas inteiras")
    return float(round(n))


def resolver(total, ead, presencial, modalidade) -> dict:
    """Combina total, EaD, presencial e modalidade da UC; calcula a parcela que falta por diferença e confere.
    Devolve {"carga_horaria_total", "carga_horaria_ead", "carga_horaria_presencial", "modalidade", "divisao_confirmada"};
    sem nenhuma informação de divisão devolve "pendente": True (a importação pede a distribuição antes de gravar).
    Levanta ErroCarga em conflito."""
    total = horas(total, "carga horária total")
    ead = horas(ead, "carga horária EaD")
    presencial = horas(presencial, "carga horária presencial")
    mod = normalizar_modalidade(modalidade) if not (modalidade in MODALIDADES_UC) else modalidade
    if total is None:
        if ead is not None and presencial is not None:
            total = ead + presencial
        else:
            raise ErroCarga("informe a carga horária total da UC")
    if total <= 0:
        raise ErroCarga("a carga horária total da UC deve ser maior que zero")
    if ead is None and presencial is None:
        if mod == "ead":
            ead, presencial = total, 0.0
        elif mod == "presencial":
            ead, presencial = 0.0, total
        elif mod == "semipresencial":
            raise ErroCarga(f"UC semipresencial de {total:g} h: informe a carga EaD ou a presencial")
        else:
            return {"carga_horaria_total": int(total), "pendente": True}
    elif ead is None:
        ead = total - presencial
        if ead < 0:
            raise ErroCarga(f"carga presencial ({presencial:g} h) maior que a total ({total:g} h)")
    elif presencial is None:
        presencial = total - ead
        if presencial < 0:
            raise ErroCarga(f"carga EaD ({ead:g} h) maior que a total ({total:g} h)")
    if abs(ead + presencial - total) > 1e-6:
        raise ErroCarga(f"EaD ({ead:g} h) + presencial ({presencial:g} h) = {ead + presencial:g} h, diferente da total ({total:g} h)")
    pelas_cargas = modalidade_das_cargas(ead, presencial)
    if mod and mod != pelas_cargas:
        raise ErroCarga(f"modalidade '{ROTULO_MODALIDADE[mod]}' não combina com as cargas (EaD {ead:g} h, presencial {presencial:g} h "
                        f"= {ROTULO_MODALIDADE[pelas_cargas]})")
    return {"carga_horaria_total": int(total), "carga_horaria_ead": int(ead), "carga_horaria_presencial": int(presencial),
            "modalidade": pelas_cargas, "divisao_confirmada": True}


def distribuir(total: int, regra: dict | None) -> dict:
    """Distribuição escolhida na prévia para planilha antiga (sem as colunas): {"tipo": "presencial"|"ead"|"percentual_ead", "valor": %}."""
    tipo = (regra or {}).get("tipo")
    if tipo == "presencial":
        return resolver(total, 0, None, None)
    if tipo == "ead":
        return resolver(total, None, 0, None)
    if tipo == "percentual_ead":
        pct = float((regra or {}).get("valor") or 0)
        if not 0 <= pct <= 100:
            raise ErroCarga("percentual EaD entre 0 e 100")
        ead = round(total * pct / 100)
        return resolver(total, ead, None, None)
    raise ErroCarga("defina a distribuição das horas (tudo presencial, tudo EaD ou percentual EaD)")


def completar_registro(uc) -> None:
    """Mantém o registro consistente ao gravar (cadastros antigos, cópias de versão, demo): sem a divisão, deriva da
    modalidade — EAD = tudo EaD; senão tudo presencial — e deixa `divisao_confirmada` falso para conferência.
    Mudou a total sem mexer nas parcelas: ajusta a parcela da modalidade."""
    total = int(uc.carga_horaria_total or 0)
    e, p = uc.carga_horaria_ead, uc.carga_horaria_presencial
    if e is None and p is None:
        e, p = (total, 0) if uc.modalidade == "ead" else (0, total)
    elif p is None:
        p = max(0, total - int(e))
    elif e is None:
        e = max(0, total - int(p))
    if int(e) + int(p) != total:
        if uc.modalidade == "ead" or int(p) == 0:
            e, p = total, 0
        else:
            e = min(int(e), total)
            p = total - e
    uc.carga_horaria_ead, uc.carga_horaria_presencial = int(e), int(p)
    if uc.modalidade not in MODALIDADES_UC or (uc.modalidade != modalidade_das_cargas(e, p)):
        uc.modalidade = modalidade_das_cargas(e, p)
