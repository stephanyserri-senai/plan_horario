import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api, dataBR, qs } from "../api";
import { Abas, Badge, Campo, Card, Kpi, AntesDepois, Erro, EstadoCenario, Modal, ResumoTabela, rotulo, OcorrenciasLista, Pagina, Tabela, useCarregar } from "../components/ui";
import { useApp } from "../contexto";
import { Sugestao } from "../components/Sugestao";
import { useOpcoes } from "../hooks";
import { semestreDe, semestres as listarSemestres } from "../semestre";

function opcoesSemestre(): string[] {
  const a = new Date().getFullYear();
  return [a - 1, a, a + 1].flatMap((x) => [`${x}/1`, `${x}/2`]);
}
function proximoSemestre(cenarios: any[]): string {
  const ex = new Set(listarSemestres(cenarios));
  return opcoesSemestre().find((sm) => !ex.has(sm) && sm >= `${new Date().getFullYear()}/${new Date().getMonth() < 6 ? 1 : 2}`) || opcoesSemestre()[3];
}
/** Datas sugeridas (editáveis): 1º semestre de fevereiro a junho; 2º de agosto a dezembro. */
function novoSemestre(sem: string) {
  const [a, n] = sem.split("/");
  return { _sem: sem, nome: `Planejamento ${sem}`, unidade_id: null,
    periodo_inicio: n === "1" ? `${a}-02-02` : `${a}-08-03`, periodo_fim: n === "1" ? `${a}-06-30` : `${a}-12-18` };
}
import { BarraCH, FluxoCenario, LegendaCH } from "../components/Visual";

const PROXIMOS: Record<string, { estado: string; rotulo: string; acao: string }[]> = {
  em_elaboracao: [{ estado: "em_validacao", rotulo: "Enviar para validação", acao: "cenarios.editar" }],
  em_validacao: [{ estado: "aguardando_aprovacao", rotulo: "Solicitar aprovação", acao: "cenarios.editar" }, { estado: "em_elaboracao", rotulo: "Voltar à elaboração", acao: "cenarios.editar" }],
  aguardando_aprovacao: [{ estado: "aprovado", rotulo: "Aprovar", acao: "cenarios.aprovar" }, { estado: "em_elaboracao", rotulo: "Reprovar (devolver)", acao: "cenarios.aprovar" }],
  aprovado: [{ estado: "publicado", rotulo: "Publicar", acao: "cenarios.publicar" }],
  publicado: [],
};

export default function Planejamento() {
  const [sp] = useSearchParams();
  const [aba, setAba] = useState(sp.get("aba") || "cenarios");
  const { cenario } = useApp();
  return (
    <Pagina titulo="Semestres e aprovação" descricao="Crie o semestre, acompanhe a aprovação e a publicação, confira conflitos e compare versões.">
      {cenario && <FluxoCenario estado={cenario.estado} />}
      <Abas abas={[{ id: "cenarios", rotulo: "Semestres e aprovação" }, { id: "oferta", rotulo: "Turma × UC (detalhe)" },
        { id: "validacao", rotulo: "Conferir conflitos" }, { id: "versoes", rotulo: "Histórico de versões" }, { id: "comparar", rotulo: "Comparar cenários" }]} ativa={aba} mudar={setAba} />
      {aba === "cenarios" && <Cenarios />}
      {aba === "oferta" && <Oferta />}
      {aba === "validacao" && <Validacao />}
      {aba === "versoes" && <Versoes />}
      {aba === "comparar" && <Comparar />}
    </Pagina>
  );
}

function Cenarios() {
  const { cenarios, recarregarCenarios, setCenarioId, pode, aviso, cenario } = useApp();
  const [novo, setNovo] = useState<any | null>(null);
  const [erro, setErro] = useState<any>(null);
  const [impacto, setImpacto] = useState<any | null>(null);
  const unidades = useOpcoes("unidades");
  const transicionar = async (c: any, estado: string) => {
    const motivo = estado === "em_elaboracao" || estado === "publicado" ? prompt("Motivo / observação:") ?? undefined : undefined;
    try {
      const r = await api.post(`/api/cenarios/${c.id}/transicao`, { estado, motivo, lock_version: c.lock_version });
      aviso(`Cenário agora está “${r.estado}” (versão ${r.versao}).`);
    } catch (e: any) { setErro(e); }
    recarregarCenarios();
  };
  return (
    <>
      <div className="filtros">
        {pode("cenarios.criar") && <button className="btn btn-primario" onClick={() => setNovo(novoSemestre(proximoSemestre(cenarios)))}>+ Novo semestre</button>}
        <span className="sub">Cada semestre tem uma versão em edição. Quando publicada, alterações viram uma "proposta de alteração" do mesmo semestre — você continua escolhendo só o semestre no topo.</span>
      </div>
      <Erro erro={erro} />
      <Tabela colunas={[
        { chave: "sem", rotulo: "Semestre", render: (c: any) => <b>{semestreDe(c)}</b> },
        { chave: "nome", rotulo: "Planejamento", render: (c: any) => <>{c.nome}{c.id === cenario?.id && <> <Badge tipo="ok">aberto</Badge></>}<br /><small>{c.descricao}</small></> },
        { chave: "tipo", rotulo: "Tipo", render: (c: any) => ({ base: "Planejamento", proposta: "Proposta de alteração", simulacao: "Simulação", copia: "Cópia" } as any)[c.tipo] || c.tipo }, { chave: "estado", rotulo: "Estado", render: (c: any) => <EstadoCenario estado={c.estado} /> },
        { chave: "versao", rotulo: "Versão", alinhar: "dir" }, { chave: "aulas", rotulo: "Aulas", alinhar: "dir" },
        { chave: "periodo", rotulo: "Período", render: (c: any) => `${dataBR(c.periodo_inicio)} – ${dataBR(c.periodo_fim)}` },
        { chave: "resultado_validacao", rotulo: "Validação", render: (c: any) => c.resultado_validacao ? <>{c.resultado_validacao.bloqueios ? <Badge tipo="bloqueio">{c.resultado_validacao.bloqueios}</Badge> : <Badge tipo="ok">0 bloqueios</Badge>} <Badge tipo="alerta">{c.resultado_validacao.alertas}</Badge></> : "—" },
        { chave: "acoes", rotulo: "Ações", render: (c: any) => (
          <div className="acoes-linha">
            <button className="btn-link" onClick={() => setCenarioId(c.id)}>Abrir</button>
            {pode("cenarios.criar") && <button className="btn-link" onClick={async () => { const nome = prompt("Nome da cópia:", `${c.nome} (cópia)`); if (!nome) return;
              try { const n = await api.post("/api/cenarios", { nome, copiar_de: c.id }); await recarregarCenarios(); setCenarioId(n.id); aviso("Cenário copiado."); } catch (e) { setErro(e); } }}>Copiar</button>}
            {c.tipo !== "simulacao" && (PROXIMOS[c.estado] || []).filter((p) => pode(p.acao)).map((p) => (
              <button key={p.estado} className="btn-link" onClick={() => transicionar(c, p.estado)}>{p.rotulo}</button>))}
            {["publicado", "aprovado"].includes(c.estado) && pode("cenarios.criar") && <button className="btn-link" onClick={async () => {
              const nome = prompt("Nome da proposta de alteração:", `Proposta – ${c.nome}`); if (!nome) return;
              try { const n = await api.post(`/api/cenarios/${c.id}/proposta`, { nome }); await recarregarCenarios(); setCenarioId(n.id); aviso("Proposta criada: edite-a na grade, valide e submeta à aprovação."); } catch (e) { setErro(e); } }}>Propor alteração</button>}
            {c.tipo === "proposta" && <button className="btn-link" onClick={async () => setImpacto(await api.get(`/api/cenarios/${c.id}/impacto`))}>Impacto</button>}
            {!["publicado", "aprovado"].includes(c.estado) && pode("cenarios.editar") && <button className="btn-link" onClick={async () => { if (!confirm("Arquivar cenário?")) return; await transicionar(c, "arquivado"); }}>Arquivar</button>}
          </div>) },
      ]} linhas={cenarios} />
      <Modal titulo="Novo semestre" aberto={!!novo} fechar={() => setNovo(null)}>
        {novo && <>
          <Campo rotulo="Ano" obrigatorio ajuda="Digite qualquer ano (ex.: 2027).">
            <input type="number" min={2000} max={2100} step={1} value={novo._sem.split("/")[0]}
              onChange={(e) => { const a = e.target.value.replace(/\D/g, "").slice(0, 4); setNovo({ ...novoSemestre(`${a}/${novo._sem.split("/")[1]}`), unidade_id: novo.unidade_id }); }} /></Campo>
          <Campo rotulo="Semestre" obrigatorio><select value={novo._sem.split("/")[1]}
            onChange={(e) => setNovo({ ...novoSemestre(`${novo._sem.split("/")[0]}/${e.target.value}`), unidade_id: novo.unidade_id })}>
            <option value="1">1º semestre</option><option value="2">2º semestre</option></select></Campo>
          <Campo rotulo="Nome"><input value={novo.nome} onChange={(e) => setNovo({ ...novo, nome: e.target.value })} /></Campo>
          <Campo rotulo="Unidade" ajuda="Vazio = as duas unidades no mesmo planejamento."><select value={novo.unidade_id ?? ""} onChange={(e) => setNovo({ ...novo, unidade_id: e.target.value || null })}>
            <option value="">Todas as unidades</option>{unidades.map((u) => <option key={u.id} value={u.id}>{u.rotulo}</option>)}</select></Campo>
          <Campo rotulo="Período letivo — início"><input type="date" value={novo.periodo_inicio} onChange={(e) => setNovo({ ...novo, periodo_inicio: e.target.value })} /></Campo>
          <Campo rotulo="Período letivo — fim"><input type="date" value={novo.periodo_fim} onChange={(e) => setNovo({ ...novo, periodo_fim: e.target.value })} /></Campo>
          <Campo rotulo="Descrição"><textarea value={novo.descricao ?? ""} onChange={(e) => setNovo({ ...novo, descricao: e.target.value })} /></Campo>
          {!/^(20|21)\d{2}$/.test(novo._sem.split("/")[0]) && <p className="aviso-inline">Informe o ano com 4 dígitos (ex.: 2027).</p>}
          {listarSemestres(cenarios).includes(novo._sem) && <p className="aviso-inline">Já existe o semestre {novo._sem}: será criada mais uma versão dele.</p>}
          <div className="rodape-modal"><button className="btn btn-primario" disabled={!/^(20|21)\d{2}$/.test(novo._sem.split("/")[0])} onClick={async () => {
            const { _sem, ...dados } = novo;
            try { const c = await api.post("/api/cenarios", dados); await recarregarCenarios(); setCenarioId(c.id); setNovo(null); aviso(`Semestre ${_sem} criado e aberto.`); } catch (e) { setErro(e); setNovo(null); }
          }}>Criar</button></div>
        </>}
      </Modal>
      <Modal titulo="Impacto da proposta em relação ao cenário publicado" aberto={!!impacto} fechar={() => setImpacto(null)} largo>
        {impacto && <>
          <p>{impacto.adicionadas} aula(s) adicionada(s), {impacto.removidas} removida(s), {impacto.alteradas} alterada(s).</p>
          <p><b>Turmas afetadas:</b> {impacto.recursos_afetados.turmas.join(", ") || "—"} · <b>Instrutores:</b> {impacto.recursos_afetados.instrutores.join(", ") || "—"} · <b>Ambientes:</b> {impacto.recursos_afetados.ambientes.join(", ") || "—"}</p>
          {impacto.detalhes.alteradas.length > 0 && <Tabela colunas={[{ chave: "data", rotulo: "Data", render: (x: any) => dataBR(x.data) }, { chave: "inicio", rotulo: "Horário" },
            { chave: "m", rotulo: "O que mudou", render: (x: any) => Object.keys(x.mudancas || {}).map((k) => rotulo(k)).join(", ") }]}
            linhas={impacto.detalhes.alteradas.slice(0, 50)} chave={(_x, i) => i} />}
        </>}
      </Modal>
    </>
  );
}

function Oferta() {
  const { cenario } = useApp();
  const [turma, setTurma] = useState("");
  const [explicacao, setExplicacao] = useState<any | null>(null);
  const turmas = useOpcoes("turmas");
  const d = useCarregar<any[]>(() => cenario ? api.get(`/api/planejamento/oferta${qs({ cenario_id: cenario.id, turma_id: turma })}`) : Promise.resolve([]), [cenario?.id, turma]);
  return (
    <>
      <div className="filtros"><LegendaCH /><select aria-label="Turma" value={turma} onChange={(e) => setTurma(e.target.value)}><option value="">Todas as turmas</option>{turmas.map((t) => <option key={t.id} value={t.id}>{t.rotulo}</option>)}</select></div>
      {d.carregando && <p role="status">Calculando…</p>}
      <Tabela colunas={[
        { chave: "turma_codigo", rotulo: "Turma" }, { chave: "uc", rotulo: "UC", render: (l: any) => <>{l.uc_codigo} – {l.uc_nome}</> },
        { chave: "estado_planejamento", rotulo: "Situação", render: (l: any) => <Badge tipo={l.estado_planejamento === "programada_integralmente" ? "ok" : l.estado_planejamento === "pendente_alocacao" ? "alerta" : "info"}>{l.estado_planejamento.replaceAll("_", " ")}</Badge> },
        { chave: "andamento", rotulo: "Andamento", render: (l: any) => <BarraCH total={l.total_h} realizada={l.realizada_h} programada={l.programada_h} /> },
        { chave: "total_h", rotulo: "Total (h)", alinhar: "dir" }, { chave: "encontros_necessarios", rotulo: "Aulas que faltam", alinhar: "dir" },
        { chave: "data_limite", rotulo: "Prazo", render: (l: any) => dataBR(l.data_limite) },
        { chave: "inst", rotulo: "Instrutores elegíveis", render: (l: any) => l.instrutores_elegiveis.length ? l.instrutores_elegiveis.map((i: any) => i.nome).join(", ") : <Badge tipo="bloqueio">nenhum</Badge> },
        { chave: "amb", rotulo: "Ambientes compatíveis", render: (l: any) => l.ambientes_compativeis.length ? l.ambientes_compativeis.map((a: any) => a.codigo).join(", ") : <Badge tipo="bloqueio">nenhum</Badge> },
        { chave: "por", rotulo: "", render: (l: any) => l.restante_h > 0 && <button className="btn" onClick={async () => setExplicacao(await api.get(`/api/recomendacoes/nao_alocacao${qs({ cenario_id: cenario!.id, turma_uc_id: l.turma_uc_id })}`))}>Por que está pendente?</button> },
      ]} linhas={d.dados || []} chave={(l) => l.turma_uc_id} />
      <Modal titulo="Recomendação explicável" aberto={!!explicacao} fechar={() => setExplicacao(null)} largo>{explicacao && <Recomendacao r={explicacao} />}</Modal>
    </>
  );
}

const LIMITANTE: Record<string, string> = {
  instrutor: "Falta de instrutor habilitado ou disponível", ambiente: "Falta de sala/laboratório compatível ou livre", turma: "A turma não tem horários livres",
  "combinação": "Poucos horários em que turma, instrutor e sala estão livres ao mesmo tempo", nenhum: "Competição com outras aulas pelos mesmos horários",
};

const ROT_ACAO: Record<string, string> = { habilitar_instrutor: "Aceitar e habilitar", passar_uc: "Aceitar e trocar", adiar_uc: "Aceitar e adiar", alocar_aula: "Alocar aqui" };

function Alternativa({ a }: { a: any }) {
  const { cenario } = useApp();
  const itens: any[] = Array.isArray(a.itens) ? a.itens : [];
  if (a.gargalo) return null; // tratado em tabela própria
  const aplicar = (acao: any) => async () => {
    const r = await api.post("/api/sugestoes/aplicar", { cenario_id: cenario!.id, acao });
    if (r.geracao?.aviso) alert(`${r.mensagem}\n\n${r.geracao.aviso}`);
    else if (r.geracao?.gerado) alert(`${r.mensagem}\n\nO gerador está refazendo a grade da turma (execução #${r.geracao.execucao_id}); acompanhe em Gerar horários.`);
    return r;
  };
  if (a.acao && cenario) return <li className="sem-marcador"><Sugestao texto={a.descricao} rotulo={ROT_ACAO[a.acao.tipo] || "Aceitar sugestão"} aplicar={aplicar(a.acao)}
    recusar={() => api.post("/api/sugestoes/recusar", { cenario_id: cenario.id, acao: a.acao, motivo: "não serve" })}
    detalhe={a.acao.tipo !== "alocar_aula" ? "Depois de aplicar, o gerador refaz os horários só desta turma (se o semestre estiver em edição)." : undefined} /></li>;
  return (
    <li>{a.descricao || rotulo(a.tipo || "")}
      {Array.isArray(a.itens) && itens.length === 0 && <div className="chips"><span className="mudo">nenhum</span></div>}
      {itens.length > 0 && typeof itens[0] === "string" && <div className="chips">{itens.map((x: string) => <span key={x} className="chip">{x}</span>)}</div>}
      {itens.length > 0 && typeof itens[0] === "object" && <Tabela colunas={[{ chave: "data", rotulo: "Dia", render: (it: any) => dataBR(it.data) }, { chave: "h", rotulo: "Horário", render: (it: any) => `${it.inicio}–${it.fim}` },
        { chave: "i", rotulo: "Instrutores livres", render: (it: any) => it.instrutores?.join(", ") }, { chave: "a", rotulo: "Salas livres", render: (it: any) => it.ambientes?.join(", ") },
        { chave: "ac", rotulo: "", render: (it: any) => it.acao && cenario ? <AlocarAqui aplicar={aplicar(it.acao)} rotulo={it.acao.rotulo} /> : null }]}
        linhas={itens.slice(0, 10)} chave={(_it, k) => k} />}
    </li>
  );
}

/** Quem poderia dar a aula e por que não pode (habilitação, teto de 90%, turnos livres). */
function AnaliseInstrutores({ a }: { a: any }) {
  const linhas = [...(a.habilitados || []).map((x: any) => ({ ...x, grupo: "Habilitado" })), ...(a.quase || []).map((x: any) => ({ ...x, grupo: "Não habilitado" }))];
  if (!linhas.length) return null;
  return (
    <>
      <h4>Quem poderia dar a aula e por que não pode</h4>
      <p className="sub">Semana típica a partir de {dataBR(a.semana_referencia)} · a turma precisa de {a.encontros_semanais} {String(a.turno || "").toLowerCase()}(s) por semana ·
        cada instrutor pode ter aula em no máximo 90% dos turnos da jornada (40 h: 9 de 10; 20 h: 4 de 5).</p>
      <Tabela colunas={[{ chave: "nome", rotulo: "Instrutor" }, { chave: "grupo", rotulo: "Situação na UC" },
        { chave: "oc", rotulo: "Turnos com aula", alinhar: "dir", render: (x: any) => <span className={x.turnos_com_aula >= x.teto_turnos ? "txt-alerta" : ""}>{x.turnos_com_aula} / {x.teto_turnos}</span> },
        { chave: "motivo", rotulo: "Por que não assume" }]} linhas={linhas} chave={(x: any) => x.id} />
    </>
  );
}

export function Recomendacao({ r }: { r: any }) {
  const alts: any[] = Array.isArray(r.alternativas) ? r.alternativas : [];
  const gargalos = alts.filter((a) => a.gargalo);
  const comDescricao = alts.filter((a) => !a.gargalo && (a.descricao || a.itens));
  const linhas = alts.filter((a) => !a.gargalo && !a.descricao && !a.itens);
  return (
    <div className="recomendacao">
      <h3>{r.pergunta}</h3>
      {r.problema && <p><b>O que aconteceu:</b> {r.problema}</p>}
      {r.recurso_limitante && <p><b>Principal causa:</b> {LIMITANTE[r.recurso_limitante] || r.recurso_limitante}</p>}
      {r.impacto && <p><b>Resultado:</b> {r.impacto}</p>}
      {r.analise_instrutores && <AnaliseInstrutores a={r.analise_instrutores} />}
      {(comDescricao.length > 0 || gargalos.length > 0 || linhas.length > 0) && <h4>O que você pode fazer</h4>}
      {comDescricao.length > 0 && <ul>{comDescricao.map((a, i) => <Alternativa key={i} a={a} />)}</ul>}
      {gargalos.length > 0 && <Tabela colunas={[{ chave: "gargalo", rotulo: "Onde falta capacidade" }, { chave: "deficit_h", rotulo: "Falta (h/semana)", alinhar: "dir" },
        { chave: "o", rotulo: "Salas compatíveis com horário sobrando", render: (g: any) => g.ambientes_compativeis_ociosos?.length ? g.ambientes_compativeis_ociosos.map((x: any) => `${x.codigo} (${x.horas_ociosas} h livres)`).join(", ") : "nenhuma" }]}
        linhas={gargalos} chave={(_g, i) => i} />}
      {linhas.length > 0 && <ResumoTabela dados={linhas} />}
      {r.depois ? <AntesDepois antes={r.antes} depois={r.depois} /> : null}
      {r.restricoes_atendidas && <p className="sub">✔ {r.restricoes_atendidas}</p>}
      {r.limitacoes && <p className="sub"><b>Observação:</b> {r.limitacoes}</p>}
    </div>
  );
}

function Validacao() {
  const { cenario, aviso } = useApp();
  const v = useCarregar<any>(() => cenario ? api.get(`/api/cenarios/${cenario.id}/validacoes`) : Promise.resolve(null), [cenario?.id]);
  const [sev, setSev] = useState("");
  const [rodando, setRodando] = useState(false);
  const oc = (v.dados?.ocorrencias || []).filter((o: any) => !sev || o.severidade === sev);
  return (
    <>
      <div className="filtros">
        <button className="btn btn-primario" disabled={rodando} onClick={async () => { setRodando(true); try { const r = await api.post(`/api/cenarios/${cenario!.id}/validar`); aviso(`Validação: ${r.resumo.bloqueios} bloqueio(s), ${r.resumo.alertas} alerta(s).`); v.recarregar(); } finally { setRodando(false); } }}>
          {rodando ? "Validando…" : "Validar cenário agora"}</button>
        <select aria-label="Severidade" value={sev} onChange={(e) => setSev(e.target.value)}><option value="">Todas as severidades</option>
          {["bloqueio", "alerta", "preferencia", "recomendacao"].map((s) => <option key={s}>{s}</option>)}</select>
      </div>
      {v.dados?.validacao && <div className="kpis">
        <Kpi rotulo="⛔ Bloqueios (conflitos)" valor={v.dados.validacao.total_bloqueios} tom={v.dados.validacao.total_bloqueios ? "erro" : "ok"} detalhe="precisam ser resolvidos" onClick={() => setSev("bloqueio")} />
        <Kpi rotulo="⚠ Alertas" valor={v.dados.validacao.total_alertas} tom={v.dados.validacao.total_alertas ? "alerta" : "ok"} detalhe="recomenda-se revisar" onClick={() => setSev("alerta")} />
        <Kpi rotulo="◐ Preferências não atendidas" valor={v.dados.validacao.total_preferencias} onClick={() => setSev("preferencia")} />
        <Kpi rotulo="💡 Recomendações" valor={v.dados.validacao.total_recomendacoes} onClick={() => setSev("recomendacao")} />
      </div>}
      {v.dados?.validacao && <p className="sub">Última validação em {new Date(v.dados.validacao.executado_em).toLocaleString("pt-BR")}: {v.dados.validacao.total_bloqueios} bloqueio(s),
        {" "}{v.dados.validacao.total_alertas} alerta(s), {v.dados.validacao.total_preferencias} preferência(s) não atendida(s), {v.dados.validacao.total_recomendacoes} recomendação(ões).</p>}
      <Tabela colunas={[{ chave: "severidade", rotulo: "Severidade", render: (o: any) => <Badge tipo={o.severidade} /> }, { chave: "regra", rotulo: "Regra" },
        { chave: "descricao", rotulo: "Descrição" }, { chave: "data", rotulo: "Data", render: (o: any) => dataBR(o.data) },
        { chave: "recurso", rotulo: "Recurso", render: (o: any) => o.recurso_tipo ? `${o.recurso_tipo} #${o.recurso_id}` : "" }, { chave: "alocacao_id", rotulo: "Aula" }]}
        linhas={oc.slice(0, 500)} vazio="Nenhuma ocorrência." />
    </>
  );
}

function Versoes() {
  const { cenario, pode, aviso, recarregarCenarios } = useApp();
  const vs = useCarregar<any[]>(() => cenario ? api.get(`/api/cenarios/${cenario.id}/versoes`) : Promise.resolve([]), [cenario?.id]);
  const [sel, setSel] = useState<number[]>([]);
  const [comp, setComp] = useState<any | null>(null);
  return (
    <>
      <div className="filtros">
        {pode("cenarios.editar") && <button className="btn" onClick={async () => { await api.post(`/api/cenarios/${cenario!.id}/versoes`, { motivo: prompt("Motivo:") || "registro manual" }); vs.recarregar(); }}>Registrar versão agora</button>}
        <button className="btn" disabled={sel.length !== 2} onClick={async () => setComp(await api.get(`/api/versoes/comparar?a=${sel[0]}&b=${sel[1]}`))}>Comparar 2 selecionadas</button>
      </div>
      <Tabela colunas={[{ chave: "sel", rotulo: "", render: (v: any) => <input type="checkbox" aria-label={`Selecionar versão ${v.numero}`} checked={sel.includes(v.id)} onChange={(e) => setSel(e.target.checked ? [...sel, v.id].slice(-2) : sel.filter((x) => x !== v.id))} /> },
        { chave: "numero", rotulo: "Versão" }, { chave: "estado", rotulo: "Estado", render: (v: any) => <EstadoCenario estado={v.estado} /> }, { chave: "motivo", rotulo: "Motivo" },
        { chave: "criado_em", rotulo: "Quando", render: (v: any) => new Date(v.criado_em).toLocaleString("pt-BR") }, { chave: "aulas", rotulo: "Aulas", alinhar: "dir" },
        { chave: "oc", rotulo: "Ocupação amb. %", render: (v: any) => v.indicadores?.taxa_ocupacao_ambientes_pct },
        { chave: "r", rotulo: "", render: (v: any) => pode("cenarios.restaurar") && <button className="btn-link" onClick={async () => {
          if (!confirm(`Restaurar a versão ${v.numero}? Em cenários publicados/aprovados é criado um novo cenário.`)) return;
          try { const r = await api.post(`/api/versoes/${v.id}/restaurar`, {}); aviso(`Restaurado: ${r.aulas} aulas; ${r.validacao.bloqueios} bloqueio(s) na revalidação.`); recarregarCenarios(); vs.recarregar(); } catch (e: any) { aviso(e.message, "erro"); }
        }}>Restaurar</button> }]} linhas={vs.dados || []} />
      <Modal titulo="Comparação entre versões" aberto={!!comp} fechar={() => setComp(null)} largo>
        {comp && <>
          <p>v{comp.versao_a.numero} → v{comp.versao_b.numero}: <b>{comp.adicionadas}</b> adicionada(s), <b>{comp.removidas}</b> removida(s), <b>{comp.alteradas}</b> alterada(s).</p>
          <AntesDepois antes={comp.versao_a.indicadores} depois={comp.versao_b.indicadores} rotuloA={`Versão ${comp.versao_a.numero}`} rotuloB={`Versão ${comp.versao_b.numero}`} />
          <ResumoTabela dados={Object.fromEntries(Object.entries(comp.recursos_afetados || {}).map(([k, v]: any) => [k, Array.isArray(v) ? v.length : v]))} />
          <p className="sub">Acima: quantidade de turmas, instrutores e salas afetados pela diferença entre as versões.</p>
        </>}
      </Modal>
    </>
  );
}

function Comparar() {
  const { cenarios } = useApp();
  const [sel, setSel] = useState<number[]>([]);
  const [r, setR] = useState<any | null>(null);
  const [erro, setErro] = useState<any>(null);
  return (
    <>
      <p className="sub">Todos os cenários são avaliados com o mesmo conjunto de pesos (escala documentada: pontos = peso × valor bruto por semana; menor é melhor).</p>
      <div className="checks">{cenarios.map((c) => <label key={c.id}><input type="checkbox" checked={sel.includes(c.id)} onChange={(e) => setSel(e.target.checked ? [...sel, c.id] : sel.filter((x) => x !== c.id))} /> {c.nome} (v{c.versao})</label>)}</div>
      <button className="btn btn-primario" disabled={sel.length < 2} onClick={async () => { setErro(null); try { setR(await api.post("/api/cenarios/comparar", { cenarios: sel })); } catch (e) { setErro(e); } }}>Comparar</button>
      <Erro erro={erro} />
      {r && <>
        <Card titulo="Classificação">
          <p>{r.criterio_ordenacao}</p>
          <ol>{r.ranking.map((id: number) => { const c = r.cenarios.find((x: any) => x.cenario.id === id); return <li key={id}><b>{c.cenario.nome}</b> — {c.avaliacao.pontuacao_total} pontos · pendente {c.carga_pendente_h} h · bloqueios {c.validacao?.bloqueios ?? "não validado"}</li>; })}</ol>
          <h3>Por que o 1º foi melhor que o 2º</h3>
          <Tabela colunas={[{ chave: "descricao", rotulo: "Critério" }, { chave: "melhor", rotulo: "1º", alinhar: "dir" }, { chave: "segundo", rotulo: "2º", alinhar: "dir" }, { chave: "unidade", rotulo: "Unidade" }, { chave: "diferenca_pontos", rotulo: "Diferença (pontos)", alinhar: "dir" }]}
            linhas={r.explicacao.por_criterio} vazio="Pontuações idênticas em todos os critérios." chave={(l) => l.criterio} />
          <p>Diferenças de grade entre 1º e 2º: {r.diferencas_melhor_vs_segundo.adicionadas} adicionadas, {r.diferencas_melhor_vs_segundo.removidas} removidas, {r.diferencas_melhor_vs_segundo.alteradas} alteradas.</p>
        </Card>
        <div className="tabela-wrap"><table className="tabela"><thead><tr><th>Indicador</th>{r.cenarios.map((c: any) => <th key={c.cenario.id}>{c.cenario.nome}</th>)}</tr></thead>
          <tbody>
            {[["Pontuação total", (c: any) => c.avaliacao.pontuacao_total], ["Aulas", (c: any) => c.indicadores.aulas], ["Horas programadas", (c: any) => c.indicadores.horas_programadas],
              ["Carga pendente (h)", (c: any) => c.carga_pendente_h], ["Ocupação ambientes %", (c: any) => c.indicadores.taxa_ocupacao_ambientes_pct],
              ["Ocupação instrutores %", (c: any) => c.indicadores.ocupacao_media_instrutores_pct], ["Janelas instrutores (h)", (c: any) => c.indicadores.janelas_instrutores_h],
              ["Deslocamentos", (c: any) => c.indicadores.deslocamentos], ["Bloqueios / alertas", (c: any) => c.validacao ? `${c.validacao.bloqueios} / ${c.validacao.alertas}` : "não validado"],
              ["Tempo da última otimização (s)", (c: any) => c.ultima_execucao?.tempo_s ?? "—"], ["Status do solver", (c: any) => c.ultima_execucao?.status_solver ?? "—"],
            ].map(([rot, f]: any) => <tr key={rot}><th>{rot}</th>{r.cenarios.map((c: any) => <td key={c.cenario.id}>{f(c)}</td>)}</tr>)}
            {r.cenarios[0].avaliacao.criterios.map((cr: any, k: number) => <tr key={cr.criterio}><th>{cr.descricao} <small>({cr.unidade}; peso {cr.peso})</small></th>
              {r.cenarios.map((c: any) => <td key={c.cenario.id}>{c.avaliacao.criterios[k].valor_bruto} <small>({c.avaliacao.criterios[k].pontos} pts)</small></td>)}</tr>)}
          </tbody></table></div>
        {r.cenarios.length > 0 && <p className="sub">Pesos utilizados: {Object.entries(r.pesos).map(([k, v]) => `${k}=${v}`).join(" · ")}</p>}
      </>}
    </>
  );
}

function AlocarAqui({ aplicar, rotulo }: { aplicar: () => Promise<any>; rotulo: string }) {
  const { aviso } = useApp();
  const [estado, setEstado] = useState<"" | "rodando" | "ok">("");
  if (estado === "ok") return <span className="sugestao-feito">✔ alocada</span>;
  return <button className="btn" title={`Aceitar a sugestão: criar a aula com ${rotulo}`} disabled={estado === "rodando"}
    onClick={async () => { setEstado("rodando"); try { await aplicar(); setEstado("ok"); aviso("Aula criada pela sugestão."); } catch (e: any) { setEstado(""); aviso(e?.message || String(e), "erro"); } }}>
    {estado === "rodando" ? "Alocando…" : "✔ Alocar aqui"}</button>;
}
