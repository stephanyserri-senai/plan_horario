"""Distribuição dos instrutores: mensalistas são ocupados primeiro; o horista só completa o que eles não cobrem."""
from app.solver.contrato import AmbienteS, AtividadeS, EntradaSolver, InstrutorS, Janela, Slot
from app.solver.cpsat import resolver


def _entrada(insts, encontros, n=2):
    slots = [Slot(i + 1, 1, 1, i, [0, 1, 2, 3, 4], 420 + 55 * i, 475 + 55 * i) for i in range(4)]
    ambs = [AmbienteS(r, 1, 40, 40, False, []) for r in (1, 2, 3)]
    ats = [AtividadeS(f"a{k}", turma_id=k, turma_uc_id=k, uc_id=k, grupo=None, grupos=[k], unidade_id=1, turno_id=1,
                      dias_permitidos=[0, 1, 2, 3, 4], num_periodos=4, encontros=encontros, instrutores=[i.id for i in insts],
                      ambientes=[1, 2, 3], tamanho=30, data_ini=1, data_fim=100) for k in range(1, n + 1)]
    return EntradaSolver(slots, insts, ambs, ats, limite_tempo_s=10, threads=1)


def test_mensalista_ocupado_antes_do_horista():
    disp = [Janela(d, 0, 1440) for d in range(5)]
    # o horista vem primeiro na lista e tem o mesmo limite: mesmo assim as aulas vão para os mensalistas
    insts = [InstrutorS(1, [1], disp, 40 * 60, 10 * 60, horista=True), InstrutorS(2, [1], disp, 40 * 60, 10 * 60),
             InstrutorS(3, [1], disp, 40 * 60, 10 * 60)]
    saida = resolver(_entrada(insts, 2))
    assert saida.status in ("OTIMA", "VIAVEL")
    assert {a.instrutor_id for a in saida.atribuicoes} <= {2, 3}
    assert saida.termos["prioridade_mensalista"] == 0


def test_horista_completa_o_que_o_mensalista_nao_cobre():
    disp = [Janela(d, 0, 1440) for d in range(5)]
    # o mensalista só tem 2 dias (8 aulas de 55 min ≈ 7,3 h) livres na semana: o restante vai para o horista
    insts = [InstrutorS(1, [1], disp, 40 * 60, 10 * 60, horista=True), InstrutorS(2, [1], disp, 8 * 55, 10 * 60)]
    saida = resolver(_entrada(insts, 2))
    assert saida.status in ("OTIMA", "VIAVEL")
    por = {}
    for a in saida.atribuicoes:
        por[a.instrutor_id] = por.get(a.instrutor_id, 0) + 1
    assert por == {2: 2, 1: 2}


def test_todos_ocupados_o_que_sobra_e_repartido_entre_os_horistas():
    disp = [Janela(d, 0, 1440) for d in range(5)]
    # 3 UCs; o mensalista cobre uma (limite) e as outras duas vão uma para cada horista, sem concentrar num só
    insts = [InstrutorS(1, [1], disp, 40 * 60, 10 * 60, horista=True), InstrutorS(2, [1], disp, 40 * 60, 10 * 60, horista=True),
             InstrutorS(3, [1], disp, 8 * 55, 10 * 60)]
    saida = resolver(_entrada(insts, 2, n=3))
    assert saida.status in ("OTIMA", "VIAVEL")
    por = {}
    for a in saida.atribuicoes:
        por.setdefault(a.instrutor_id, set()).add(a.chave)
    assert {i: len(c) for i, c in por.items()} == {1: 1, 2: 1, 3: 1}


def test_listas_de_instrutores_mostram_mensalista_primeiro():
    from app.services.planejamento import mensalistas_primeiro
    lista = [{"nome": "Ana", "modalidade": "horista", "nivel": "pleno"}, {"nome": "Bruno", "modalidade": "mensalista", "nivel": "parcial"},
             {"nome": "Carla", "modalidade": "mensalista", "nivel": "pleno"}]
    assert [x["nome"] for x in mensalistas_primeiro(lista)] == ["Carla", "Bruno", "Ana"]
