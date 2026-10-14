import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, dataBR, qs } from "../api";
import { Badge, Kpi, Modal, Pagina, Tabela, useCarregar } from "../components/ui";
import { useApp } from "../contexto";
import { useOpcoes } from "../hooks";
import { semestreDe } from "../semestre";
import { Recomendacao } from "./Planejamento";

type Item = {
  id: string; tipo: "area" | "curso" | "turma" | "uc"; pai: string | null; codigo: string; nome: string; inicio: string; fim: string;
  limite?: string | null; ultima_aula?: string | null; total_h: number; realizada_h: number; programada_h: number; restante_h: number;
  folga_dias?: number; critico?: boolean; atrasado?: boolean; sem_horario?: boolean; caminho_critico?: boolean; instrutores?: string[];
  ucs?: number; ucs_criticas?: number; turma_id?: number; turma_uc_id?: number; turma_codigo?: string; curso_nome?: string;
  depende_de?: string[]; dependencia_violada?: string[]; uc_ref?: string;
};

/** Visão por instrutor: Instrutor › (turma · UC), a partir das UCs. */
function porInstrutor(itens: Item[]): Item[] {
  const grupos: Record<string, Item> = {};
  const res: Item[] = [];
  itens.filter((i) => i.tipo === "uc").forEach((u) => {
    (u.instrutores?.length ? u.instrutores : ["Sem instrutor definido"]).forEach((nome) => {
      const gid = `i:${nome}`;
      const g = grupos[gid] ||= { id: gid, tipo: "area", pai: null, codigo: "", nome, inicio: u.inicio, fim: u.fim, total_h: 0, realizada_h: 0,
        programada_h: 0, restante_h: 0, ucs: 0, ucs_criticas: 0 };
      g.inicio = u.inicio < g.inicio ? u.inicio : g.inicio;
      g.fim = u.fim > g.fim ? u.fim : g.fim;
      g.ucs = (g.ucs || 0) + 1;
      g.ucs_criticas = (g.ucs_criticas || 0) + (u.critico ? 1 : 0);
      (["total_h", "realizada_h", "programada_h", "restante_h"] as const).forEach((k) => { g[k] += u[k]; });
      res.push({ ...u, id: `${u.id}@${nome}`, uc_ref: u.id, pai: gid });
    });
  });
  return [...Object.values(grupos).sort((a, b) => a.nome.localeCompare(b.nome)), ...res];
}

const DIA = 86400000;
const dt = (s: string) => new Date(s + "T12:00");
const n1 = (v: number) => (Number(v) || 0).toLocaleString("pt-BR", { maximumFractionDigits: 1 });
const MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"];
const NIVEL: Record<string, number> = { area: 0, curso: 1, turma: 2, uc: 3 };
const ROTULO_TIPO: Record<string, string> = { area: "Área", curso: "Curso", turma: "Turma", uc: "UC" };

export default function Cronograma() {
  const { cenario } = useApp();
  const [unidade, setUnidade] = useState("");
  const [area, setArea] = useState("");
  const [curso, setCurso] = useState("");
  const [zoom, setZoom] = useState<"semanas" | "meses">("semanas");
  const [soCriticos, setSoCriticos] = useState(false);
  const [tabela, setTabela] = useState(false);
  const [fechados, setFechados] = useState<Set<string>>(new Set());
  const [dica, setDica] = useState<{ it: Item; x: number; y: number } | null>(null);
  const [agrupar, setAgrupar] = useState<"area" | "instrutor">("area");
  const [sel, setSel] = useState<Item | null>(null);
  const nav = useNavigate();
  const unidades = useOpcoes("unidades");
  const areas = useOpcoes("areas").filter((a: any) => !unidade || String(a.unidade_id) === unidade);
  const cursos = useOpcoes("cursos").filter((c: any) => (!unidade || String(c.unidade_id) === unidade) && (!area || String(c.area_id) === area));
  const d = useCarregar<any>(() => cenario ? api.get(`/api/cronograma${qs({ cenario_id: cenario.id, unidade_id: unidade, area_id: area, curso_id: curso })}`) : Promise.resolve(null),
    [cenario?.id, unidade, area, curso]);

  const brutos: Item[] = d.dados?.itens || [];
  const itens: Item[] = useMemo(() => agrupar === "instrutor" ? porInstrutor(brutos) : brutos, [brutos, agrupar]);
  const nivel = (i: Item) => agrupar === "instrutor" ? (i.tipo === "uc" ? 1 : 0) : NIVEL[i.tipo];
  const filhos = useMemo(() => {
    const m: Record<string, Item[]> = {};
    itens.forEach((i) => { const k = i.pai || "raiz"; (m[k] = m[k] || []).push(i); });
    return m;
  }, [itens]);
  // com "só o que é crítico": UCs críticas ou do caminho crítico e seus ascendentes
  const visiveisCriticos = useMemo(() => {
    const ids = new Set<string>();
    const porId = Object.fromEntries(itens.map((i) => [i.id, i]));
    itens.filter((i) => i.tipo === "uc" && (i.critico || i.caminho_critico)).forEach((i) => {
      let x: Item | undefined = i;
      while (x) { ids.add(x.id); x = x.pai ? porId[x.pai] : undefined; }
    });
    return ids;
  }, [itens]);
  const linhas: Item[] = [];
  const percorrer = (pai: string) => (filhos[pai] || []).forEach((i) => {
    if (soCriticos && !visiveisCriticos.has(i.id)) return;
    linhas.push(i);
    if (!fechados.has(i.id)) percorrer(i.id);
  });
  percorrer("raiz");

  if (!cenario) return <Pagina titulo="Cronograma"><p>Escolha o semestre no topo da página.</p></Pagina>;
  const r = d.dados?.resumo;
  // escala de tempo
  const datas = itens.flatMap((i) => [i.inicio, i.fim, i.limite].filter(Boolean) as string[]);
  const ini = datas.length ? new Date(Math.min(...datas.map((s) => dt(s).getTime())) - 3 * DIA) : new Date();
  const fimEscala = datas.length ? new Date(Math.max(...datas.map((s) => dt(s).getTime())) + 10 * DIA) : new Date();
  const px = zoom === "semanas" ? 14 : 4;
  const dias = Math.ceil((fimEscala.getTime() - ini.getTime()) / DIA);
  const largura = dias * px;
  const x = (s: string) => ((dt(s).getTime() - ini.getTime()) / DIA) * px;
  const hoje = d.dados?.hoje;
  const meses: { x: number; w: number; rotulo: string }[] = [];
  for (let m = new Date(ini.getFullYear(), ini.getMonth(), 1); m < fimEscala; m = new Date(m.getFullYear(), m.getMonth() + 1, 1)) {
    const a = Math.max(0, ((m.getTime() - ini.getTime()) / DIA) * px);
    const prox = new Date(m.getFullYear(), m.getMonth() + 1, 1);
    const b = Math.min(largura, ((prox.getTime() - ini.getTime()) / DIA) * px);
    if (b - a >= 48) meses.push({ x: a, w: b - a, rotulo: `${MESES[m.getMonth()]}/${m.getFullYear()}` });
  }
  const semanas: { x: number; rotulo: string }[] = [];
  const seg = new Date(ini); seg.setDate(seg.getDate() + ((8 - seg.getDay()) % 7));
  for (let s = seg; s < fimEscala; s = new Date(s.getTime() + 7 * DIA)) {
    semanas.push({ x: ((s.getTime() - ini.getTime()) / DIA) * px, rotulo: `${String(s.getDate()).padStart(2, "0")}/${String(s.getMonth() + 1).padStart(2, "0")}` });
  }
  const alternar = (id: string) => setFechados((f) => { const n = new Set(f); n.has(id) ? n.delete(id) : n.add(id); return n; });
  const recolherAte = (tipo: string) => setFechados(new Set(itens.filter((i) => NIVEL[i.tipo] >= NIVEL[tipo] && i.tipo !== "uc").map((i) => i.id)));

  return (
    <Pagina titulo={`Cronograma (Gantt) — ${semestreDe(cenario)}`} descricao="Andamento de cada unidade curricular no tempo, por área, curso e turma (ou por instrutor), com prazos, folgas e o caminho crítico de cada turma. Clique numa barra para ver detalhes e ações.">
      {r && <div className="kpis">
        <Kpi rotulo="Turmas" valor={r.turmas} detalhe={r.inicio ? `${dataBR(r.inicio)} a ${dataBR(r.fim)}` : undefined} />
        <Kpi rotulo="Turmas atrasadas" valor={r.turmas_atrasadas} tom={r.turmas_atrasadas ? "erro" : "ok"} detalhe="terminam depois do prazo" />
        <Kpi rotulo="Turmas em risco" valor={r.turmas_em_risco} tom={r.turmas_em_risco ? "alerta" : "ok"} detalhe={`folga de até ${d.dados.limiar_folga_dias} dias`} />
        <Kpi rotulo="UCs críticas" valor={r.ucs_criticas} tom={r.ucs_criticas ? "alerta" : "ok"} detalhe={`de ${r.ucs} UCs`} onClick={() => setSoCriticos(true)} />
        <Kpi rotulo="UCs com carga sem horário" valor={r.ucs_sem_horario} tom={r.ucs_sem_horario ? "alerta" : "ok"} detalhe="fim projetado (tracejado)" />
      </div>}
      <div className="filtros">
        <select aria-label="Unidade" value={unidade} onChange={(e) => { setUnidade(e.target.value); setArea(""); setCurso(""); }}>
          <option value="">Todas as unidades</option>{unidades.map((u) => <option key={u.id} value={u.id}>{u.rotulo}</option>)}</select>
        <select aria-label="Área" value={area} onChange={(e) => { setArea(e.target.value); setCurso(""); }}>
          <option value="">Todas as áreas</option>{areas.map((a) => <option key={a.id} value={a.id}>{a.rotulo}</option>)}</select>
        <select aria-label="Curso" value={curso} onChange={(e) => setCurso(e.target.value)}>
          <option value="">Todos os cursos</option>{cursos.map((c) => <option key={c.id} value={c.id}>{c.rotulo}</option>)}</select>
        <select aria-label="Agrupar" value={agrupar} onChange={(e) => { setAgrupar(e.target.value as any); setFechados(new Set()); }}>
          <option value="area">Agrupar: área › curso › turma</option><option value="instrutor">Agrupar: instrutor</option></select>
        <select aria-label="Escala" value={zoom} onChange={(e) => setZoom(e.target.value as any)}><option value="semanas">Escala: semanas</option><option value="meses">Escala: meses</option></select>
        <label><input type="checkbox" checked={soCriticos} onChange={(e) => setSoCriticos(e.target.checked)} /> Só o que é crítico</label>
        <button className="btn" onClick={() => setFechados(new Set())}>Expandir tudo</button>
        <button className="btn" onClick={() => agrupar === "instrutor" ? setFechados(new Set(itens.filter((i) => i.tipo !== "uc").map((i) => i.id))) : recolherAte("turma")}>
          {agrupar === "instrutor" ? "Recolher instrutores" : "Recolher turmas"}</button>
        <button className="btn" onClick={() => setTabela(!tabela)}>{tabela ? "Ver gráfico" : "Ver como tabela"}</button>
        <button className="btn" onClick={() => baixarCSV(brutos)}>Baixar CSV</button>
      </div>
      <div className="legenda gantt-legenda" aria-hidden="true">
        <span><i className="realizada" /> Realizada</span><span><i className="programada" /> Com horário</span><span><i className="falta" /> Projeção (sem horário)</span>
        <span><b className="leg-prazo">▼</b> Prazo</span><span><b className="leg-hoje">│</b> Hoje</span>
        <span><b className="faixa-erro">⚠</b> Crítica (atrasada ou folga ≤ {d.dados?.limiar_folga_dias ?? 7} dias)</span><span><b>◆</b> Caminho crítico da turma</span><span><b className="faixa-erro">→</b> Pré-requisito</span>
      </div>
      {d.carregando && !d.dados && <p role="status">Montando o cronograma…</p>}
      {d.erro && <div className="erro-box">{d.erro}</div>}
      {d.dados && !itens.length && <p className="mudo">Nenhuma turma encontrada com os filtros escolhidos.</p>}

      {itens.length > 0 && tabela && <Tabela colunas={[
        { chave: "turma", rotulo: "Turma", render: (i: Item) => itens.find((t) => t.id === i.pai)?.codigo },
        { chave: "uc", rotulo: "Unidade curricular", render: (i: Item) => <>{i.caminho_critico && "◆ "}<b>{i.codigo}</b> {i.nome}</> },
        { chave: "inicio", rotulo: "Início", render: (i: Item) => dataBR(i.inicio) },
        { chave: "fim", rotulo: "Término", render: (i: Item) => <>{dataBR(i.fim)}{i.sem_horario && <small className="mudo"> (projetado)</small>}</> },
        { chave: "limite", rotulo: "Prazo", render: (i: Item) => dataBR(i.limite) },
        { chave: "folga_dias", rotulo: "Folga (dias)", alinhar: "dir" },
        { chave: "sit", rotulo: "Situação", render: (i: Item) => i.atrasado ? <Badge tipo="bloqueio">atrasada</Badge> : i.critico ? <Badge tipo="alerta">crítica</Badge> : <Badge tipo="ok">no prazo</Badge> },
      ]} linhas={linhas.filter((i) => i.tipo === "uc")} chave={(i) => i.id} />}

      {itens.length > 0 && !tabela && <div className="gantt" onMouseLeave={() => setDica(null)}>
        <div className="gantt-inner" style={{ width: 320 + largura }}>
          <div className="gantt-cab">
            <div className="gantt-rot gantt-rot-cab">Área › Curso › Turma › UC</div>
            <div className="gantt-escala" style={{ width: largura }}>
              {meses.map((m) => <div key={m.rotulo} className="gantt-mes" style={{ left: m.x, width: m.w }}>{m.rotulo}</div>)}
              {zoom === "semanas" && semanas.map((s) => <div key={s.x} className="gantt-sem" style={{ left: s.x }}>{s.rotulo}</div>)}
            </div>
          </div>
          <div className="gantt-corpo">
            {hoje && <div className="gantt-hoje" style={{ left: 320 + x(hoje) }} title={`Hoje: ${dataBR(hoje)}`} />}
            <Dependencias linhas={linhas} x={x} px={px} largura={largura} />
            {linhas.map((i) => {
              const grupo = i.tipo !== "uc";
              const x0 = x(i.inicio), x1 = x(i.fim) + px;
              const xUlt = i.ultima_aula ? x(i.ultima_aula) + px : x0;
              const xLim = i.limite ? x(i.limite) + px : null;
              const sol = grupo ? x1 - x0 : Math.max(0, (i.sem_horario ? xUlt : x1) - x0);
              const pctReal = i.total_h ? i.realizada_h / i.total_h : 0;
              const tem = (filhos[i.id] || []).length > 0;
              return (
                <div key={i.id} className={`gantt-linha nivel-${i.tipo}`}>
                  <div className="gantt-rot" style={{ paddingLeft: 8 + nivel(i) * 16 }}>
                    {tem ? <button className="gantt-caret" aria-label={fechados.has(i.id) ? "Expandir" : "Recolher"} aria-expanded={!fechados.has(i.id)} onClick={() => alternar(i.id)}>{fechados.has(i.id) ? "▸" : "▾"}</button> : <span className="gantt-caret" />}
                    <span className="gantt-nome" title={`${ROTULO_TIPO[i.tipo]}: ${i.codigo} ${i.nome}`}>
                      {i.caminho_critico && <b title="Caminho crítico da turma">◆ </b>}
                      {agrupar === "instrutor" && i.tipo === "uc" ? <small className="mudo">{i.turma_codigo} · </small> : null}
                      {i.tipo === "uc" ? <span className="gantt-link" role="button" tabIndex={0} onClick={() => setSel(i)}
                          onKeyDown={(e) => e.key === "Enter" && setSel(i)}><b>{i.codigo}</b> {i.nome}</span>
                        : <>{i.tipo === "turma" ? <b>{i.codigo}</b> : null} {i.tipo === "turma" ? "" : i.nome}</>}
                      {i.dependencia_violada?.length ? <span className="faixa-erro" title={`Começa antes de terminar: ${i.dependencia_violada.join(", ")}`}> ⚠ pré-req.</span> : null}
                    </span>
                    {i.atrasado ? <span className="gantt-st faixa-erro">⚠ atrasada</span> : i.critico ? <span className="gantt-st faixa-erro">⚠ {i.folga_dias ?? ""}{i.folga_dias != null ? " d" : " crítica"}</span>
                      : grupo && i.ucs_criticas ? <span className="gantt-st faixa-alerta">{i.ucs_criticas} crít.</span> : null}
                  </div>
                  <div className="gantt-trilha" style={{ width: largura }}>
                    {zoom === "semanas" && semanas.map((s) => <span key={s.x} className="gantt-grade" style={{ left: s.x }} />)}
                    <div className={`gantt-barra ${grupo ? "grupo" : "uc"} ${!grupo && i.critico ? "critico" : ""} ${grupo && i.atrasado ? "atrasado" : ""} ${i.caminho_critico ? "cam" : ""}`}
                      style={{ left: x0, width: Math.max(x1 - x0, 3) }}
                      onMouseMove={(e) => setDica({ it: i, x: e.clientX, y: e.clientY })} onMouseLeave={() => setDica(null)}
                      onClick={() => i.tipo === "uc" && setSel(i)}
                      role="img" aria-label={`${i.codigo} ${i.nome}: ${dataBR(i.inicio)} a ${dataBR(i.fim)}${i.limite ? `, prazo ${dataBR(i.limite)}` : ""}${i.critico ? ", crítica" : ""}`}>
                      {!grupo && <>
                        <span className="seg programada" style={{ width: sol }} />
                        {pctReal > 0 && <span className="seg realizada" style={{ width: sol * Math.min(i.realizada_h / Math.max(i.realizada_h + i.programada_h, 0.01), 1) }} />}
                        {i.sem_horario && <span className="seg falta" style={{ left: sol, width: Math.max(x1 - x0 - sol, 0) }} />}
                      </>}
                      {xLim != null && i.atrasado && <span className="gantt-atraso" style={{ left: xLim - x0, width: Math.max(x1 - xLim, 0) }} />}
                    </div>
                    {xLim != null && <span className="gantt-prazo" style={{ left: xLim - 5 }} title={`Prazo: ${dataBR(i.limite)}`}>▼</span>}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>}
      {dica && <div className="gantt-dica" style={{ left: Math.min(dica.x + 14, window.innerWidth - 300), top: dica.y + 14 }}>
        <b>{ROTULO_TIPO[dica.it.tipo]}: {dica.it.codigo} {dica.it.tipo !== "turma" ? dica.it.nome : ""}</b>
        <div>{dataBR(dica.it.inicio)} → {dataBR(dica.it.fim)}{dica.it.sem_horario ? " (término projetado)" : ""}</div>
        {dica.it.limite && <div>Prazo: {dataBR(dica.it.limite)} · folga {dica.it.folga_dias} dia(s)</div>}
        <div>Carga: {n1(dica.it.realizada_h)} h realizadas · {n1(dica.it.programada_h)} h com horário · {n1(dica.it.restante_h)} h sem horário (total {n1(dica.it.total_h)} h)</div>
        {dica.it.instrutores?.length ? <div>Instrutores: {dica.it.instrutores.join(", ")}</div> : null}
        {dica.it.caminho_critico && <div>◆ Define o término da turma (caminho crítico)</div>}
        {dica.it.atrasado ? <div className="faixa-erro">⚠ Termina depois do prazo</div> : dica.it.critico ? <div className="faixa-erro">⚠ Folga pequena até o prazo</div> : null}
      </div>}
      {d.dados && <p className="sub">{d.dados.explicacao}</p>}
      <Modal titulo={sel ? `${sel.turma_codigo} · ${sel.codigo} ${sel.nome}` : ""} aberto={!!sel} fechar={() => setSel(null)} largo>
        {sel && <DetalheUC it={sel} cenarioId={cenario.id} irGrade={() => nav(`/grade?turma=${sel.turma_id}`)} irGerar={() => nav("/geracao")} />}
      </Modal>
    </Pagina>
  );
}

/** Setas de pré-requisito (do fim do pré-requisito ao início da UC). Vermelha quando a UC começa antes de ele terminar. */
function Dependencias({ linhas, x, px, largura }: { linhas: Item[]; x: (s: string) => number; px: number; largura: number }) {
  const idx: Record<string, number> = {};
  linhas.forEach((l, i) => { idx[l.uc_ref || l.id] = i; });
  const setas: { d: string; ruim: boolean }[] = [];
  linhas.forEach((l, i) => (l.depende_de || []).forEach((dep) => {
    const j = idx[dep];
    if (j === undefined) return;
    const pre = linhas[j];
    const x1 = x(pre.fim) + px, y1 = j * 30 + 15, x2 = x(l.inicio), y2 = i * 30 + 15;
    const meio = Math.max(x1 + 6, Math.min(x2 - 6, x1 + 12));
    setas.push({ d: `M${x1},${y1} H${meio} V${y2} H${x2}`, ruim: (l.dependencia_violada || []).includes(pre.codigo) });
  }));
  if (!setas.length) return null;
  return (
    <svg className="gantt-deps" width={largura} height={linhas.length * 30} style={{ left: 320 }} aria-hidden="true">
      <defs><marker id="seta" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto"><path d="M0,0 L6,3 L0,6 z" fill="currentColor" /></marker></defs>
      {setas.map((s, k) => <path key={k} d={s.d} className={s.ruim ? "ruim" : ""} markerEnd="url(#seta)" />)}
    </svg>
  );
}

function DetalheUC({ it, cenarioId, irGrade, irGerar }: { it: Item; cenarioId: number; irGrade: () => void; irGerar: () => void }) {
  const [rec, setRec] = useState<any | null>(null);
  const [carregando, setCarregando] = useState(false);
  return (
    <div className="explicacao">
      <p>
        {it.atrasado ? <Badge tipo="bloqueio">atrasada</Badge> : it.critico ? <Badge tipo="alerta">crítica</Badge> : <Badge tipo="ok">no prazo</Badge>}{" "}
        {it.caminho_critico && <Badge tipo="info">◆ define o término da turma</Badge>}
      </p>
      <Tabela colunas={[{ chave: "k", rotulo: "" }, { chave: "v", rotulo: "", alinhar: "dir" }]} chave={(l) => l.k} linhas={[
        { k: "Curso / turma", v: `${it.curso_nome || ""} · ${it.turma_codigo}` },
        { k: "Período", v: `${dataBR(it.inicio)} → ${dataBR(it.fim)}${it.sem_horario ? " (término projetado)" : ""}` },
        { k: "Prazo", v: `${dataBR(it.limite)} · folga ${it.folga_dias} dia(s)` },
        { k: "Carga horária", v: `${n1(it.realizada_h)} h realizadas · ${n1(it.programada_h)} h com horário · ${n1(it.restante_h)} h sem horário (de ${n1(it.total_h)} h)` },
        { k: "Instrutores", v: it.instrutores?.join(", ") || "—" },
        ...(it.dependencia_violada?.length ? [{ k: "Pré-requisito", v: `⚠ começa antes de terminar ${it.dependencia_violada.join(", ")}` }] : []),
      ]} />
      <div className="acoes">
        <button className="btn" onClick={irGrade}>Ver na grade</button>
        {it.restante_h > 0.01 && <button className="btn" disabled={carregando} onClick={async () => {
          setCarregando(true);
          try { setRec(await api.get(`/api/recomendacoes/nao_alocacao${qs({ cenario_id: cenarioId, turma_uc_id: it.turma_uc_id })}`)); } finally { setCarregando(false); }
        }}>{carregando ? "Analisando…" : "Por que está sem horário?"}</button>}
        {it.restante_h > 0.01 && <button className="btn btn-primario" onClick={irGerar}>Gerar horários</button>}
      </div>
      {rec && <Recomendacao r={rec} />}
    </div>
  );
}

function baixarCSV(itens: Item[]) {
  const cab = ["Turma", "Curso", "UC", "Nome", "Início", "Término", "Projetado", "Prazo", "Folga (dias)", "Situação", "Caminho crítico", "Total (h)", "Sem horário (h)", "Instrutores"];
  const esc = (v: any) => `"${String(v ?? "").replace(/"/g, '""')}"`;
  const linhas = itens.filter((i) => i.tipo === "uc").map((i) => [i.turma_codigo, i.curso_nome, i.codigo, i.nome, i.inicio, i.fim, i.sem_horario ? "sim" : "não",
    i.limite, i.folga_dias, i.atrasado ? "atrasada" : i.critico ? "crítica" : "no prazo", i.caminho_critico ? "sim" : "não", i.total_h, i.restante_h,
    (i.instrutores || []).join(", ")].map(esc).join(";"));
  const blob = new Blob(["\ufeff" + [cab.map(esc).join(";"), ...linhas].join("\n")], { type: "text/csv;charset=utf-8" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = "cronograma.csv";
  a.click();
  URL.revokeObjectURL(a.href);
}
