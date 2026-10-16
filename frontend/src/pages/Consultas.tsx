import { useState } from "react";
import { api, dataBR, iso, qs } from "../api";
import { Abas, Pagina, Tabela, useCarregar } from "../components/ui";
import { BarraOcupacao, Faixa, GraficoSerie } from "../components/Ocupacao";
import { useApp } from "../contexto";

const ESTADO: Record<string, [string, string]> = {
  aula: ["ag-aula", "em aula"], PL: ["ag-PL", "PL · planejamento"], PJ: ["ag-PJ", "PJ · projeto"], TR: ["ag-TR", "TR · treinamento"], livre: ["ag-livre", "livre"],
  bloqueado: ["ag-bloq", "bloqueado"], fora_jornada: ["ag-fora", "fora da jornada"], nao_letivo: ["ag-fora", "não letivo"],
};

/** Situação de cada instrutor e sala num dia (e turno). */
function QuemEstaOnde() {
  const { cenario } = useApp();
  const [dia, setDia] = useState(iso(new Date()));
  const [turno, setTurno] = useState("");
  const [ver, setVer] = useState("instrutores");
  const [estado, setEstado] = useState("");
  const [busca, setBusca] = useState("");
  const r = useCarregar<any>(() => cenario && dia ? api.get(`/api/consultas/situacao${qs({ cenario_id: cenario.id, data: dia, turno })}`) : Promise.resolve(null),
    [cenario?.id, dia, turno]);
  const d = r.dados;
  const linhas = (d?.[ver] || []).filter((l: any) => (!busca || (l.nome + " " + (l.codigo || "")).toLowerCase().includes(busca.toLowerCase()))
    && (!estado || Object.values(l.turnos).some((c: any) => c.estado === estado)));
  const celula = (c: any) => {
    if (!c) return <span className="mudo">—</span>;
    const [cls, txt] = ESTADO[c.estado] || ["", c.estado];
    return <div className={`cel-sit ${cls}`}><b>{txt}</b>
      {c.estado === "aula" && <small>{c.turma} · {c.uc.split(" – ")[0]}{ver === "instrutores" ? ` · ${c.sala || "sem sala"}` : ` · ${c.instrutor || "sem instrutor"}`}</small>}
      {c.detalhe && <small>{c.detalhe}</small>}</div>;
  };
  return (
    <>
      <div className="filtros">
        <label>Dia <input type="date" value={dia} onChange={(e) => setDia(e.target.value)} /></label>
        <select aria-label="Turno" value={turno} onChange={(e) => setTurno(e.target.value)}>
          <option value="">Todos os turnos</option><option value="M">Manhã</option><option value="T">Tarde</option><option value="N">Noite</option></select>
        <select aria-label="Ver" value={ver} onChange={(e) => setVer(e.target.value)}><option value="instrutores">Instrutores</option><option value="salas">Salas e laboratórios</option></select>
        <select aria-label="Situação" value={estado} onChange={(e) => setEstado(e.target.value)}>
          <option value="">Qualquer situação</option>
          {(ver === "instrutores" ? ["livre", "aula", "PL", "PJ", "TR", "bloqueado", "fora_jornada"] : ["livre", "aula", "bloqueado"]).map((e) => <option key={e} value={e}>{ESTADO[e][1]}</option>)}
        </select>
        <input type="search" placeholder="Buscar nome…" aria-label="Buscar" value={busca} onChange={(e) => setBusca(e.target.value)} />
      </div>
      {d && <>
        <p className="sub">{d.dia_semana}, {dataBR(d.data)}{Object.keys(d.nao_letivo).length ? ` · dia não letivo: ${Object.values(d.nao_letivo).join("; ")}` : ""}</p>
        <div className="kpis">
          {ver === "instrutores" ? <>
            <div className="kpi kpi-ok"><span>Instrutores livres (turnos)</span><b>{d.resumo.instrutores_livres}</b><small>na jornada e sem aula</small></div>
            <div className="kpi"><span>Em aula</span><b>{d.resumo.instrutores_em_aula}</b></div>
            <div className="kpi"><span>Em PL / PJ</span><b>{d.resumo.instrutores_pl_pj}</b><small>estão na escola: podem substituir</small></div>
            <div className="kpi"><span>Em treinamento (TR)</span><b>{d.resumo.instrutores_tr ?? 0}</b><small>liberados das aulas: não substituem</small></div>
            <div className={`kpi ${d.resumo.instrutores_bloqueados ? "kpi-alerta" : ""}`}><span>Bloqueados</span><b>{d.resumo.instrutores_bloqueados}</b><small>licença, afastamento…</small></div>
          </> : <>
            <div className="kpi kpi-ok"><span>Salas livres (turnos)</span><b>{d.resumo.salas_livres}</b></div>
            <div className="kpi"><span>Ocupadas</span><b>{d.resumo.salas_ocupadas}</b></div>
            <div className={`kpi ${d.resumo.salas_bloqueadas ? "kpi-alerta" : ""}`}><span>Bloqueadas</span><b>{d.resumo.salas_bloqueadas}</b><small>manutenção…</small></div>
          </>}
        </div>
        <Tabela colunas={[
          { chave: "nome", rotulo: ver === "instrutores" ? "Instrutor" : "Sala", render: (l: any) => <><b>{ver === "salas" ? l.codigo : l.nome}</b>{ver === "salas" && <small className="mudo"> {l.nome}</small>}
            {l.modalidade && <small className="mudo"> · {l.modalidade}</small>}</> },
          ...d.turnos.map((t: any) => ({ chave: t.codigo, rotulo: t.nome, render: (l: any) => celula(l.turnos[t.codigo]) })),
        ]} linhas={linhas} chave={(l: any) => l.id} vazio="Ninguém nesta situação." />
      </>}
      {r.carregando && !d && <p role="status">Consultando…</p>}
    </>
  );
}

function Periodo({ inicio, fim, setInicio, setFim }: { inicio: string; fim: string; setInicio: (v: string) => void; setFim: (v: string) => void }) {
  const { cenario } = useApp();
  const hoje = iso(new Date());
  const atalho = (a: string, b: string) => { setInicio(a); setFim(b); };
  const dias = (n: number) => { const d = new Date(); d.setDate(d.getDate() + n); return iso(d); };
  return (
    <div className="filtros">
      <label>De <input type="date" value={inicio} onChange={(e) => setInicio(e.target.value)} /></label>
      <label>Até <input type="date" value={fim} onChange={(e) => setFim(e.target.value)} /></label>
      <button className="btn-link" onClick={() => atalho("", "")}>semestre inteiro</button>
      <button className="btn-link" onClick={() => atalho(dias(-28), hoje)}>últimas 4 semanas</button>
      <button className="btn-link" onClick={() => atalho(hoje, dias(28))}>próximas 4 semanas</button>
      {cenario?.periodo_fim && <button className="btn-link" onClick={() => atalho(hoje, cenario.periodo_fim!)}>daqui até o fim</button>}
    </div>
  );
}

/** Rankings de ocupação no período: instrutores (da jornada), salas, áreas e turnos. */
function Ranking() {
  const { cenario } = useApp();
  const [inicio, setInicio] = useState("");
  const [fim, setFim] = useState("");
  const [ordem, setOrdem] = useState("mais");
  const r = useCarregar<any>(() => cenario ? api.get(`/api/consultas/ranking${qs({ cenario_id: cenario.id, inicio, fim })}`) : Promise.resolve(null), [cenario?.id, inicio, fim]);
  const d = r.dados;
  return (
    <>
      <Periodo inicio={inicio} fim={fim} setInicio={setInicio} setFim={setFim} />
      <div className="filtros"><select aria-label="Ordem" value={ordem} onChange={(e) => setOrdem(e.target.value)}>
        <option value="mais">Maiores ocupações</option><option value="menos">Menores ocupações (folga)</option></select></div>
      {d && <>
        <p className="sub">{dataBR(d.periodo.inicio)} a {dataBR(d.periodo.fim)} · {d.periodo.semanas} semana(s) · ocupação do instrutor = horas de aula por semana ÷ carga contratual
          (ideal até {d.referencias.ideal_pct}%, teto {d.referencias.teto_pct}%).</p>
        <div className="dist-faixas" aria-label="Instrutores por faixa de ocupação">
          {["acima_teto", "atencao", "ideal", "baixa", "ociosa"].map((f) => <div key={f}><Faixa f={f} /> <b>{d.distribuicao_instrutores[f] || 0}</b></div>)}
        </div>
        <div className="grid-2">
          <section className="card"><h2>Instrutores</h2>
            <Tabela colunas={[{ chave: "pos", rotulo: "#", alinhar: "dir" },
              { chave: "nome", rotulo: "Instrutor", render: (l: any) => <><b>{l.nome}</b><small className="mudo"> {l.area} · {l.modalidade} · {l.carga_h} h</small></> },
              { chave: "ocupacao_pct", rotulo: "Ocupação média", render: (l: any) => <BarraOcupacao pct={l.ocupacao_pct} /> },
              { chave: "pico_pct", rotulo: "Semana mais cheia", alinhar: "dir", render: (l: any) => `${l.pico_pct}%` }]}
              linhas={(ordem === "mais" ? d.instrutores_mais : d.instrutores_menos).map((l: any, i: number) => ({ ...l, pos: i + 1 }))} chave={(l: any) => l.id} />
          </section>
          <section className="card"><h2>Salas e laboratórios</h2>
            <Tabela colunas={[{ chave: "codigo", rotulo: "Sala", render: (l: any) => <><b>{l.codigo}</b><small className="mudo"> {l.tipo}</small></> },
              { chave: "ocupacao_pct", rotulo: "Ocupação", render: (l: any) => <BarraOcupacao pct={l.ocupacao_pct} /> },
              { chave: "horas_ocupadas", rotulo: "Horas ocupadas", alinhar: "dir" }]}
              linhas={ordem === "mais" ? d.salas_mais : d.salas_menos} chave={(l: any) => l.id} />
          </section>
          <section className="card"><h2>Áreas (instrutores)</h2>
            <Tabela colunas={[{ chave: "area", rotulo: "Área" }, { chave: "instrutores", rotulo: "Instrutores", alinhar: "dir" },
              { chave: "ocupacao_pct", rotulo: "Ocupação média", render: (l: any) => <BarraOcupacao pct={l.ocupacao_pct} /> }]} linhas={d.areas} chave={(l: any) => l.area} />
          </section>
          <section className="card"><h2>Turnos (salas)</h2>
            <Tabela colunas={[{ chave: "turno", rotulo: "Turno" }, { chave: "ocupacao_pct", rotulo: "Ocupação", render: (l: any) => <BarraOcupacao pct={l.ocupacao_pct} /> }]}
              linhas={d.turnos} chave={(l: any) => l.turno} />
          </section>
        </div>
      </>}
      {r.carregando && !d && <p role="status">Calculando…</p>}
    </>
  );
}

/** Ocupação semana a semana em um intervalo (o que já passou e a previsão pela grade gerada). */
function NoTempo() {
  const { cenario } = useApp();
  const [inicio, setInicio] = useState("");
  const [fim, setFim] = useState("");
  const r = useCarregar<any>(() => cenario ? api.get(`/api/consultas/serie${qs({ cenario_id: cenario.id, inicio, fim })}`) : Promise.resolve(null), [cenario?.id, inicio, fim]);
  const d = r.dados;
  return (
    <>
      <Periodo inicio={inicio} fim={fim} setInicio={setInicio} setFim={setFim} />
      {d && <>
        <div className="kpis">
          <div className="kpi"><span>Instrutores · média até hoje</span><b>{d.media_realizada.instrutores_pct ?? "—"}%</b><small>da jornada</small></div>
          <div className="kpi"><span>Instrutores · previsão</span><b>{d.media_prevista.instrutores_pct ?? "—"}%</b><small>semanas futuras, pela grade</small></div>
          <div className="kpi"><span>Salas · média até hoje</span><b>{d.media_realizada.salas_pct ?? "—"}%</b></div>
          <div className="kpi"><span>Salas · previsão</span><b>{d.media_prevista.salas_pct ?? "—"}%</b></div>
          {d.pico && <div className="kpi"><span>Semana mais cheia (instrutores)</span><b>{d.pico.instrutores_pct}%</b><small>semana de {d.pico.rotulo}</small></div>}
        </div>
        <section className="card"><h2>Ocupação por semana</h2><GraficoSerie dados={d} altura={300} /></section>
      </>}
      {r.carregando && !d && <p role="status">Calculando…</p>}
    </>
  );
}

export default function Consultas() {
  const { cenario } = useApp();
  const [aba, setAba] = useState("onde");
  if (!cenario) return <Pagina titulo="Consultas"><p>Selecione um semestre no topo da página.</p></Pagina>;
  return (
    <Pagina titulo="Consultas" descricao="Situação de instrutores e salas num dia, rankings de ocupação e a ocupação ao longo do tempo (com previsão pela grade gerada). Seguem o semestre e a unidade escolhidos no topo.">
      <Abas abas={[{ id: "onde", rotulo: "Quem está onde (dia e turno)" }, { id: "ranking", rotulo: "Ranking de ocupação" }, { id: "tempo", rotulo: "Ocupação no tempo" }]}
        ativa={aba} mudar={setAba} />
      {aba === "onde" && <QuemEstaOnde />}
      {aba === "ranking" && <Ranking />}
      {aba === "tempo" && <NoTempo />}
    </Pagina>
  );
}
