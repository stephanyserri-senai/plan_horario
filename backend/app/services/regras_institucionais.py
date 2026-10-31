"""Regras institucionais: a "memória" do algoritmo de planejamento.

Tudo o que a instituição definiu sobre turmas, aulas, instrutores, substituições e quadro fica catalogado
aqui, num lugar só, com o código que aplica cada regra. O gerador de horários, a validação, os cadastros,
as importações e as análises consultam estas regras; a página "Regras do sistema" e o arquivo
docs/REGRAS_DE_NEGOCIO.md são gerados a partir deste catálogo (ver scripts/gerar_regras_md.py).

O "treinamento" do sistema não é um modelo estatístico: são estas regras (obrigatórias, de preferência
e avisos) mais o registro das decisões humanas (registros_decisao) — cada sugestão aceita ou recusada
fica registrada e pode ser revisada pelo administrador para calibrar pesos e preferências.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

DIAS = ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"]
SEMANA = [0, 1, 2, 3, 4]
SABADO = 5
TURNO_SABADO = "S"
# ofertas que podem ter menos dias por semana: aperfeiçoamento e atendimentos específicos para empresas
OFERTAS_FLEXIVEIS = {"APE", "EMP"}
# turmas PFP: aula o dia todo (08:00–12:00 e 13:00–17:00), no turno integral
OFERTA_PFP, TURNO_PFP = "PFP", "I"


def eh_pfp(codigo: str | None, tipo_oferta: str | None = None) -> bool:
    return (tipo_oferta or "").strip().upper() == OFERTA_PFP or (codigo or "").split("-")[0].strip().upper() == OFERTA_PFP


def erro_turno_pfp(pfp: bool, turno_codigo: str | None) -> str | None:
    if turno_codigo == TURNO_PFP and not pfp:
        return "O horário 'manhã e tarde (PFP)' é só das turmas PFP: escolha o tipo de oferta PFP ou outro turno."
    return None


# ----------------------------------------------------------------------------- padrão de dias da turma
def oferta_flexivel(db: Session, codigo: str | None, curso_id: int | None) -> bool:
    """Aperfeiçoamento e turmas para empresas podem ter menos dias (o treinamento costuma ser curto)."""
    from app.models import Curso
    from app.services.planejamento import _sem_acento
    pref = (codigo or "").split("-")[0].strip().upper()
    if pref in OFERTAS_FLEXIVEIS:
        return True
    curso = db.get(Curso, curso_id) if curso_id else None
    return "aperfeicoamento" in _sem_acento(curso.tipo if curso else "")


def erro_padrao_dias(dias_possiveis, dias_ead, turno_codigo: str | None, flexivel: bool) -> str | None:
    """Padrões aceitos: 5 dias presenciais (seg a sex) | 4 presenciais + 1 EAD (seg a sex) | só sábado (turno de sábado).
    Turmas de aperfeiçoamento/para empresas podem ter menos dias. Devolve a mensagem de erro ou None."""
    dias = sorted(set(dias_possiveis or []))
    ead = sorted(set(dias_ead or []))
    if turno_codigo == TURNO_SABADO:
        if dias != [SABADO]:
            return "Turma do turno de sábado tem aula presencial só no sábado (09:00–13:00)."
        return None
    if SABADO in dias or SABADO in ead or 6 in dias:
        return "Aula no sábado só em turma do turno de sábado (09:00–13:00), e então só no sábado."
    if flexivel:
        return None if dias else "Informe ao menos um dia de aula."
    if dias == SEMANA and not ead:
        return None
    if len(dias) == 4 and len(ead) == 1 and sorted(dias + ead) == SEMANA:
        return None
    return ("Os dias da turma devem ser 5 dias presenciais (seg a sex) ou 4 presenciais + 1 dia EAD (turma 80-20). "
            "Só turmas de aperfeiçoamento ou para empresas podem ter menos dias.")


def conformidade(db: Session, unidades=None) -> list[dict]:
    """Turmas ativas fora do padrão de dias (para corrigir no cadastro)."""
    from app.models import Turma, Turno
    turnos = {t.id: t.codigo for t in db.scalars(select(Turno))}
    q = select(Turma).where(Turma.ativo.is_(True), Turma.simulacao_id.is_(None), Turma.situacao.notin_(["concluida", "cancelada"]))
    if unidades is not None:
        q = q.where(Turma.unidade_id.in_(unidades))
    res = []
    for t in db.scalars(q.order_by(Turma.codigo)):
        erro = erro_padrao_dias(t.dias_possiveis, t.dias_ead, turnos.get(t.turno_id), oferta_flexivel(db, t.codigo, t.curso_id))
        if erro:
            res.append({"turma_id": t.id, "turma": t.codigo, "dias": ", ".join(DIAS[d] for d in sorted(t.dias_possiveis or [])),
                        "ead": ", ".join(DIAS[d] for d in sorted(t.dias_ead or [])), "problema": erro})
    return res


# ----------------------------------------------------------------------------- catálogo
def catalogo() -> list[dict]:
    """Todas as regras que o sistema aplica, com o tipo (obrigatória, preferência, aviso) e onde valem."""
    from app.services.analise_ocupacao import INSTRUTORES_POR_TURMA, OCUPACAO_IDEAL
    from app.services.planejamento import OFERTAS_BASICAS, OFERTAS_TECNICAS
    from app.services.regras_aula import HORAS_POR_TURNO, OCUPACAO_MAXIMA, TURNO_SABADO as TS, TURNOS_PADRAO
    from app.services.substituicao import ANTECEDENCIA_DIAS

    def h(m):
        return f"{m // 60:02d}:{m % 60:02d}"
    turnos = "; ".join(f"{nome} {h(a[0][0])}–{h(a[-1][0] + a[-1][1])}" for _c, nome, a in [*TURNOS_PADRAO, TS])
    R = []

    def regra(codigo, grupo, tipo, titulo, descricao, onde, parametros=None):
        R.append({"codigo": codigo, "grupo": grupo, "tipo": tipo, "titulo": titulo, "descricao": descricao, "onde": onde,
                  "parametros": parametros or {}})

    # turmas e dias
    regra("TURMA_DIAS", "Turmas e dias", "obrigatoria", "Dias da turma",
          "Toda turma tem 5 dias presenciais (segunda a sexta) ou 4 dias presenciais + 1 dia de EAD (turma 80-20).",
          ["cadastro de turmas", "importação", "conformidade"])
    regra("TURMA_SABADO", "Turmas e dias", "obrigatoria", "Turma de sábado",
          "Turma do turno de sábado tem aula presencial só no sábado, das 09:00 às 13:00 (4 aulas). Sábado não é usado por turmas da semana.",
          ["cadastro de turmas", "gerador", "validação"], {"turno": "S", "horario": "09:00–13:00"})
    regra("TURMA_FLEXIVEL", "Turmas e dias", "obrigatoria", "Exceção: aperfeiçoamento e empresas",
          "Só atendimentos específicos de aperfeiçoamento e turmas para empresas podem ter menos dias por semana (o treinamento costuma ser curto).",
          ["cadastro de turmas", "importação"], {"tipos_de_oferta": sorted(OFERTAS_FLEXIVEIS)})
    regra("TURMA_PFP", "Turmas e dias", "obrigatoria", "Turma PFP (manhã e tarde)",
          "Turma PFP tem aula de manhã e de tarde: 08:00–12:00 e 13:00–17:00 (almoço 12:00–13:00). Cada metade é um turno inteiro: "
          "a manhã e a tarde podem ter UCs e instrutores diferentes. Na grade, as aulas aparecem nas linhas da manhã e da tarde "
          "(o limiar de horário aceita o início às 08:00 e às 13:00). Quem é da manhã dá o bloco 08–12; quem é da tarde, o 13–17.",
          ["cadastro de turmas", "importação", "gerador", "validação", "grade"], {"manha": "08:00–12:00", "tarde": "13:00–17:00"})
    regra("TURMA_EAD", "Turmas e dias", "obrigatoria", "Dia EAD (turma 80-20)",
          "O dia EAD (normalmente a sexta) não tem aula presencial: sai dos dias de aula, aparece na grade com a etiqueta EAD e a validação bloqueia aula nele.",
          ["cadastro", "gerador", "validação", "grade", "exportações"])
    # matriz curricular
    regra("VERSAO_CADASTRADA", "Matriz curricular", "obrigatoria", "Lista de UCs fixa na versão cadastrada",
          "Cada versão da matriz tem a sua própria lista de UCs (nome, carga horária e se é presencial ou EAD). Enquanto a versão está "
          "em rascunho, as UCs podem ser incluídas, alteradas ou retiradas; depois de cadastrada (vigente ou encerrada), a lista fica fixa "
          "e não volta a rascunho. Para mudar, cria-se uma nova versão, que copia as UCs. Salas, certificação, dias por semana e ordem "
          "continuam ajustáveis.", ["cadastro de UCs", "versões da matriz"])
    regra("UC_EAD", "Matriz curricular", "obrigatoria", "UC presencial ou EAD",
          "Toda UC é presencial ou EAD. A opção EAD só existe nos cursos marcados como “prevê UCs EAD” (no cadastro do curso). "
          "A UC EAD é cursada a distância: não entra na geração da grade nem na demanda de instrutores e salas, e aparece no "
          "acompanhamento como “EAD (fora da grade)”.", ["cadastro de UCs", "gerador", "riscos", "acompanhamento"])
    # aulas
    regra("TURNOS", "Aulas e turnos", "obrigatoria", "Turnos oficiais", f"Turnos: {turnos}.", ["estrutura fixa"])
    regra("TURNO_INTEIRO", "Aulas e turnos", "obrigatoria", "Turno inteiro",
          f"Cada UC ocupa o turno inteiro do dia ({HORAS_POR_TURNO} aulas). Aula parcial só no fechamento da carga horária.",
          ["gerador", "validação"], {"aulas_por_turno": HORAS_POR_TURNO})
    regra("CONTAGEM_MINUTOS", "Aulas e turnos", "obrigatoria", "Carga horária em minutos reais",
          "Cada aula vale o tempo que dura: 55 min de dia, 50 min à noite (60 min nas turmas PFP). O que falta para a carga da UC vira outra aula: "
          "uma UC de 20 h no matutino tem 22 aulas (1200 min ÷ 55); no noturno, 24 aulas (1200 ÷ 50).",
          ["carga horária", "relatórios"])
    regra("DIVISAO_3_2", "Aulas e turnos", "preferencia", "Divisão 3 + 2",
          "Na semana, a turma pode ter duas UCs: uma com 3 dias e outra com 2, conforme a carga a cumprir, as horas da UC e o instrutor disponível. É uma opção, não obrigação.",
          ["análise do quadro (encaixe de turma nova)"])
    # instrutores
    regra("TETO_90", "Instrutores", "obrigatoria", "Teto de 90% da jornada com aula",
          f"Aula em no máximo {OCUPACAO_MAXIMA:.0%} dos turnos da jornada: 40 h → 9 de 10 turnos (36 h); 20 h → 4 de 5 (16 h). O turno restante é planejamento (PL), projeto (PJ) ou reserva.",
          ["cadastro", "importação", "gerador", "validação"], {"teto": OCUPACAO_MAXIMA})
    regra("OCUPACAO_IDEAL", "Instrutores", "preferencia", "Ocupação ideal de 80%",
          f"O ideal é até {OCUPACAO_IDEAL:.0%} da jornada com aula; entre 80% e 90% é atenção.", ["acompanhamento", "quadro de instrutores"],
          {"ideal": OCUPACAO_IDEAL})
    regra("JORNADA", "Instrutores", "obrigatoria", "Turnos de trabalho",
          "40 h semanais = dois turnos por dia (MV ou VN); 20 h = um turno (M, V ou N). Sábado (09:00–13:00) é marcado à parte, por dia.",
          ["cadastro", "portal", "gerador"])
    regra("MODALIDADE", "Instrutores", "obrigatoria", "Mensalista e horista",
          "Mensalista tem as horas garantidas (aula, PL, PJ ou TR); horista não (turno sem aula pode ser dispensa). A modalidade não depende do turno.",
          ["cadastro", "agenda do instrutor"])
    regra("TERMO_HORAS", "Instrutores", "aviso", "Termo de horas do horista (ajustável)",
          "Mensalista tem jornada semanal fixa (ex.: 40 h), com aulas até 90% dela. Horista recebe todo mês um termo de horas: as horas de "
          "aula do mês (e outras ocupações) e, se for o caso, os dias da semana. O termo é adaptável: numa urgência (alguém num dia ou num "
          "total de horas fora do termo) ele é ajustado, desde que o instrutor concorde — o ajuste fica registrado com o motivo. Por isso aula "
          "fora do termo é alerta; o que impede, para horista e mensalista, é já estar ocupado e a carga máxima do contrato. A geração do "
          "semestre procura manter o horista dentro do termo; a simulação e a previsão de turmas não olham o termo.",
          ["disponibilidade e termos", "validação", "gerador", "simulador", "riscos", "substituição"])
    regra("LIMITE_44H", "Instrutores", "obrigatoria", "No máximo 44 h de trabalho por semana",
          "Ninguém trabalha mais de 44 h por semana — mensalista ou horista, somando aula, planejamento (PL), projeto (PJ), treinamento, "
          "ajuste de urgência e outras atividades. A carga contratual vai até 44 h; o termo de horas não aceita semana acima de 44 h; "
          "a validação bloqueia a aula que passaria do limite (aulas + PL/PJ da semana) e o gerador desconta o PL/PJ fixo da semana.",
          ["cadastro", "importação", "termo de horas", "validação", "gerador", "substituição"], {"max_horas_semana": 44})
    regra("MENSALISTA_PRIMEIRO", "Instrutores", "preferencia", "Mensalistas ocupados primeiro",
          "Todos os instrutores devem ser ocupados, mas na distribuição das aulas o mensalista (jornada garantida) tem prioridade: recebe "
          "primeiro, e o horista fica com o que os mensalistas habilitados não conseguem cobrir (ocupados, no teto de 90% ou sem a UC). "
          "O gerador de horários conta cada hora dada por horista como custo (critério prioridade_mensalista) e equilibra a carga dentro "
          "de cada grupo — entre os mensalistas e, no que sobra, entre os horistas, para não concentrar em poucos. As listas de instrutores "
          "possíveis, as sugestões de substituto e as correções de riscos mostram o mensalista antes do horista.",
          ["gerador", "alocação manual", "substituição", "solicitações", "riscos", "simulador"], {"peso_padrao": 30.0})
    regra("NIVEL", "Instrutores", "obrigatoria", "Nível básico ou técnico",
          f"Instrutor BÁSICO só dá aula em aprendizagem industrial básica e qualificações ({', '.join(sorted(OFERTAS_BASICAS))}); TÉCNICO, em todas as modalidades "
          f"(inclusive {', '.join(sorted(OFERTAS_TECNICAS))}). Sem exceção.", ["gerador", "validação", "substituição", "quadro"])
    regra("UC_TRANSVERSAL", "Instrutores", "obrigatoria", "UC transversal",
          "UC transversal: qualquer instrutor da unidade pode dar (sem precisar marcar no perfil; vale só a certificação exigida, se houver).",
          ["cadastro de UCs", "gerador", "validação"])
    regra("UC_TECNICA", "Instrutores", "obrigatoria", "UC técnica: sim ou em partes",
          "UC técnica: só quem marcou a UC no próprio perfil — 'Sim' (dá a UC) ou 'Em partes' (dá com alerta).", ["portal", "cadastro", "gerador", "validação"])
    regra("AREA", "Instrutores", "obrigatoria", "Área do instrutor",
          "O instrutor dá aula nas turmas da área principal e das outras áreas em que atua; fora disso só com exceção justificada.",
          ["gerador", "validação"])
    regra("CERTIFICACAO", "Instrutores", "obrigatoria", "Certificação exigida", "UC que exige certificação (ex.: NR-10) só com instrutor certificado e dentro da validade.",
          ["gerador", "validação"])
    # substituição e solicitações
    regra("PL_PJ_TR", "Instrutores", "obrigatoria", "PL, PJ e TR na agenda",
          "Turno sem aula do instrutor pode ser PL (planejamento), PJ (projeto/outra atividade) ou TR (treinamento: liberado das aulas). "
          "O gerador não coloca aula nesses turnos; em PL/PJ o instrutor está na escola e pode substituir, em TR não.",
          ["agenda do instrutor", "gerador", "validação", "substituição"])
    regra("SUBST_PRESENCA", "Substituições e solicitações", "obrigatoria", "Quem pode substituir",
          f"Instrutor em PL ou PJ pode assumir no mesmo dia (já está na escola); com turno vazio, só se a substituição for planejada com pelo menos {ANTECEDENCIA_DIAS} dia de antecedência.",
          ["substituição"], {"antecedencia_dias": ANTECEDENCIA_DIAS})
    regra("UM_INSTRUTOR_POR_UC", "Substituições e solicitações", "obrigatoria", "Um instrutor por UC",
          "Cada UC de uma turma (por grupo, quando a UC divide a turma) tem um só instrutor do começo ao fim. Outro instrutor só entra "
          "por substituição (o titular continua sendo o da UC) ou por exceção justificada; passar a UC de vez a outro instrutor "
          "(remanejamento) troca o instrutor de todas as aulas futuras. O gerador completa a UC com quem já dá as aulas dela.",
          ["validação", "gerador", "substituição", "riscos"])
    regra("TERMO_MES_SEGUINTE", "Instrutores", "obrigatoria", "Termo de horas: feito no fim do mês para o mês seguinte",
          "O termo de horas do horista é o tempo PAGO para ele estar disponível — não só aula: aula, planejamento (PL), projeto (PJ) ou "
          "ajuste de urgência, cada um com a sua cor na grade do mês e o total de horas pagas. A grade vai por semana, dia e turno (manhã, "
          "tarde, noite e o turno de sábado). Aula e urgência são turnos em que ele pode estar em sala; urgência neste mês vira aula prevista "
          "no termo seguinte. Ex.: sábado pago "
          "para planejamento de quem não tem disponibilidade na semana; pode ser só um turno no dia. Cada turno marcado leva o horário de "
          "entrada e saída daquele dia, que depende do turno de entrada do instrutor e do curso (manhã 07:30–11:30 ou 08:00–12:00; tarde "
          "13:30–17:30, 13:00–17:30 ou 13:00–17:00; noite 18:30–22:00 ou 18:00–22:00; ou outro), e as horas do termo são contadas por esse "
          "horário. Aula fora de um turno com aula no termo, ou fora do horário daquele dia, é alerta. "
          "É feito no fim de cada mês para o mês seguinte. Se foi preciso contar com o instrutor num dia que não estava previsto no termo, "
          "esse dia deve entrar no termo do mês seguinte (numa urgência, o termo do mês é ajustado com a concordância dele). O perfil do "
          "instrutor tem a aba Termo de horas (consulta e alteração), com o prazo e a sugestão do próximo termo; no portal o instrutor "
          "consulta o próprio termo e as horas já lançadas.", ["perfil do instrutor", "portal", "validação", "substituição"])
    regra("SUBST_HORISTA_TERMO", "Substituições e solicitações", "obrigatoria", "Horista fora do termo como substituto",
          "Mesmo sem horas ou sem o dia no termo do mês (ou fora da disponibilidade cadastrada), o horista aparece como opção de substituto. "
          "Só assume com a aprovação da supervisão e a concordância (e disponibilidade) dele; o termo do mês é ajustado junto e tudo fica "
          "registrado com o motivo.", ["substituição", "termos de horas"])
    regra("SUBST_PAINEL", "Substituições e solicitações", "aviso", "Painel de substituições",
          "Menu Substituições: busca-se o instrutor, vê-se o que ele estaria fazendo no período (aula a aula) e marcam-se as aulas; o sistema "
          "indica quem pode assumir pela disponibilidade no dia e no horário — livres da área, de outra área/sem a UC (exceção), horistas "
          "fora do termo (com aprovação), livres em parte — com o mensalista antes do horista.", ["substituição"])
    regra("IMPRESSAO_PRAZO", "Substituições e solicitações", "obrigatoria", "Pedido de impressão até a quinta da semana anterior",
          "O instrutor pede a impressão do material pelo portal (o que imprimir, dia de uso, turma, cópias, páginas, frente e verso, "
          "colorido e o PDF do material — até 4 MB — ou o link do arquivo) até a quinta-feira da semana anterior ao uso — para usar de segunda a sábado da semana S, até a "
          "quinta da semana S-1; depois disso o portal não aceita para aquela data. A coordenação dá o retorno (em produção, pronta para "
          "retirar, entregue ou recusada com o motivo) e o instrutor é avisado no portal.", ["portal", "coordenação"], {"dia_limite": "quinta-feira"})
    regra("SOLICITACOES", "Substituições e solicitações", "obrigatoria", "Solicitações do instrutor",
          "Pelo portal o instrutor pede folga ou substituição, com justificativa; o coordenador aprova ou recusa. Folga aprovada vira bloqueio na agenda e as aulas afetadas recebem sugestão de substituto.",
          ["portal", "coordenação"])
    regra("EPI_TURMA", "Turmas", "aviso", "EPIs do curso em cada turma",
          "O curso lista os EPIs exigidos por aluno. Cada turma recebe a lista com quantidade = alunos × por aluno e prazo = início da turma − antecedência; "
          "o controle marca comprado/separado e entregue. Prazo vencido sem entrega, ou a menos de 7 dias, vira aviso no Início e em Riscos.",
          ["cadastro de cursos", "cadastro de turmas", "controle de EPIs", "riscos"], {"dias_aviso": 7})
    regra("TURMA_MODULAR", "Turmas", "obrigatoria", "Turma modular: código sobe a cada semestre",
          "No cadastro da turma diz-se se ela é modular (quantos módulos) e o módulo em curso. Modular: o código leva o módulo "
          "(HTC-AIT-2-34 = turma 34 no 2º módulo); não modular: código no padrão de sempre (HTC-AIT-34). Um módulo por semestre: "
          "ao criar o semestre seguinte, a turma passa ao próximo módulo (código, módulo e fim), até o último — 3 módulos a partir de 2026/2 vão até 2027/2.",
          ["cadastro de turmas", "novo semestre"])
    regra("UC_FORA_DO_PRAZO", "Turmas", "obrigatoria", "UC que não termina no prazo",
          "Turma modular: o módulo precisa fechar no semestre, então a sugestão é reposição aos sábados (turno de sábado, com o instrutor da UC "
          "ou um habilitado), por exceção registrada e pela validação central. Turma não modular: as aulas que faltam passam para o próximo "
          "semestre (o prazo da UC vai para o fim dele).",
          ["riscos", "sugestões", "validação"])
    regra("REMANEJAMENTO", "Substituições e solicitações", "preferencia", "Remanejar o único habilitado",
          "UC que depende de um só instrutor: além de habilitar outro, o sistema sugere liberar o habilitado de outra UC dele, "
          "passando-a a quem está livre e pode assumi-la naquela turma (área, nível e certificação).",
          ["riscos", "sugestões", "substituição"])
    regra("ADERENCIA_INSTRUTOR", "Instrutores", "aviso", "Índice de aderência e PDI",
          "Aderência a um curso = parte da carga horária das UCs técnicas que o instrutor pode ministrar ('sim' vale a UC inteira, "
          "'em partes' metade; sem a certificação exigida a UC ainda não conta; UCs transversais ficam de fora; instrutor básico entra só nos cursos básicos). A aderência à área soma "
          "os cursos da área e a geral soma todas as áreas do instrutor. O que falta vira proposta de PDI (aprender, completar ou certificar), "
          "com prioridade pela demanda das turmas, por quantos outros instrutores já dão a UC e pelo ganho no curso; concluir um item "
          "pode marcar a UC como 'sim' no perfil. O instrutor acompanha o índice (por área e geral), a ocupação e o PDI no portal e registra "
          "as formações que concluir: as UCs indicadas são habilitadas na hora e a coordenação recebe uma observação para conferir. "
          "A equipe tem também o índice por área (média dos instrutores que atuam nela).",
          ["perfil do instrutor", "portal do instrutor", "PDI"])
    # quadro e decisões
    regra("PROPORCAO_5_4", "Quadro e decisões", "aviso", "5 instrutores para 4 turmas",
          f"Referência de {INSTRUTORES_POR_TURMA:g} instrutor por turma. É um aviso, que pesa quando a folga dos instrutores não comporta uma turma nova.",
          ["quadro de instrutores"], {"instrutores_por_turma": INSTRUTORES_POR_TURMA})
    regra("CAPACIDADE_AREA", "Quadro e decisões", "obrigatoria", "Capacidade da área",
          "Na capacidade de uma área contam os instrutores da área principal; um de outra área só entra se já dá aula em turma desta, com a fração da jornada que dedica a ela.",
          ["quadro de instrutores"])
    regra("SUGESTOES", "Quadro e decisões", "preferencia", "Sugestões e aprendizado",
          "Toda sugestão do sistema (substituto, sala, horário, habilitação, adiamento) pode ser aceita com um clique e é aplicada automaticamente, pela mesma validação. "
          "Aceites e recusas ficam registrados como decisões para revisar e calibrar o sistema.",
          ["grade", "substituição", "geração", "diagnósticos"])
    # salas
    regra("SALA_AREA", "Salas", "obrigatoria", "Laboratório especializado", "Laboratório especializado só recebe turmas da(s) área(s) dele; sala comum atende todas.",
          ["gerador", "validação"])
    regra("SALA_CAPACIDADE", "Salas", "obrigatoria", "Capacidade e acessibilidade", "A sala precisa comportar a turma (ou o grupo) e ser acessível quando a turma exige.",
          ["gerador", "validação"])
    return R


def para_markdown() -> str:
    """docs/REGRAS_DE_NEGOCIO.md: a memória das regras em texto, gerada do catálogo."""
    tipos = {"obrigatoria": "obrigatória", "preferencia": "preferência", "aviso": "aviso"}
    linhas = ["# Regras de negócio do planejamento (memória do algoritmo)", "",
              "Gerado por `scripts/gerar_regras_md.py` a partir de `backend/app/services/regras_institucionais.py`. "
              "Não edite à mão: altere o catálogo e gere de novo.", ""]
    grupo = None
    for r in catalogo():
        if r["grupo"] != grupo:
            linhas += ([""] if grupo else []) + [f"## {r['grupo']}", ""]
            grupo = r["grupo"]
        linhas.append(f"- **{r['titulo']}** (`{r['codigo']}`, {tipos[r['tipo']]}): {r['descricao']} _Onde: {', '.join(r['onde'])}._")
    return "\n".join(linhas) + "\n"
