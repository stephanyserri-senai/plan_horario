import { useState } from "react";
import { api, dataBR, iso, qs } from "../api";
import { Abas, Pagina, Tabela, useCarregar } from "../components/ui";
import { BarraOcupacao, Faixa, GraficoSerie } from "../components/Ocupacao";
import { useApp } from "../contexto";

const ESTADO: Record<string, [string, string, string]> = {  // classe, rótulo, explicação
  livre: ["ag-livre", "Livre", "na jornada e sem aula: pode assumir"],
  aula: ["ag-aula", "Em aula", "com aula marcada"],
  PL: ["ag-PL", "PL", "planejamento: está na escola, pode substituir"],
  PJ: ["ag-PJ", "PJ", "projeto: está na escola, pode substituir"],
  TR: ["ag-TR", "TR", "treinamento: liberado das aulas, não substitui"],
  bloqueado: ["ag-bloq", "Indisponível", "licença, folga, manutenção…"],
  nao_letivo: ["ag-fora", "Não letivo", "feriado ou recesso"],
  fora_jornada: ["ag-fora", "Fora da jornada", "não trabalha neste turno"],
};
const FILTROS = { instrutores: ["livre", "aula", "PL", "PJ", "TR", "bloqueado"], salas: ["livre", "aula", "bloqueado"] } as const;
const NOMES_DIA = ["Domingo", "Segunda-feira", "Terça-feira", "Quarta-feira", "Quinta-feira", "Sexta-feira", "Sábado"];
const somaDias = (s: string, n: number) => { const d = new Date(s + "T12:00:00"); d.setDate(d.getDate() + n); return iso(d); };

/** Situação de cada instrutor e sala num dia, turno a turno. */
function QuemEstaOnde() {
  const { cenario } = useApp();
  const [dia, setDia] = useState(iso(new Date()));
  const [turno, setTurno] = useState("");
  const [ver, setVer] = useState<"instrutores" | "salas">("instrutores");
  const [estado, setEstado] = useState("");
  const [busca, setBusca] = useState("");
  const r = useCarregar<any>(() => cenario && dia ? api.get(`/api/consultas/situacao${qs({ cenario_id: cenario.id, data: dia, turno })}`) : Promise.resolve(null),
    [cenario?.id, dia, turno]);
  const d = r.dados;
  const turnos = (d?.turnos || []).filter((t: any) => t.no_dia);  // só os turnos que acontecem neste dia da semana
  const fora = (d?.turnos || []).filter((t: any) => !t.no_dia);
  const todas = d?.[ver] || [];
  const conta = (e: string) => todas.reduce((n: number, l: any) => n + turnos.filter((t: any) => l.turnos[t.codigo]?.estado === e).length, 0);
  const linhas = todas.filter((l: any) => (!busca || `${l.nome} ${l.codigo || ""}`.toLowerCase().includes(busca.toLowerCase()))
    && (!estado || turnos.some((t: any) => l.turnos[t.codigo]?.estado === estado)));
  const hoje = iso(new Date());
  const celula = (c: any) => {
    if (!c || c.estado === "sem_turno") return <span className="mudo">—</span>;
    if (c.estado === "fora_jornada") return <span className="cel-fora">fora da jornada</span>;
    const [cls, txt, expl] = ESTADO[c.estado] || ["", c.estado, ""];
    return <div className={`cel-sit ${cls} ${estado && c.estado !== estado ? "apagada" : ""}`} title={expl}>
      <b>{c.estado === "aula" ? c.turma : txt}</b>
      {c.estado === "aula" && <small>{c.uc.split(" – ")[0]} · {ver === "instrutores" ? (c.sala || "sem sala") : (c.instrutor || "sem instrutor")} · {c.horario}</small>}
      {c.estado !== "aula" && (c.detalhe || ["PL", "PJ", "TR"].includes(c.estado)) && <small>{c.detalhe || expl}</small>}</div>;
  };
  return (
    <>
      <div className="onde-barra">
        <div className="seletor-dia" role="group" aria-label="Dia">
          <button className="btn" aria-label="Dia anterior" onClick={() => setDia(somaDias(dia, -1))}>◀</button>
          <input type="date" aria-label="Dia" value={dia} onChange={(e) => e.target.value && setDia(e.target.value)} />
          <button className="btn" aria-label="Próximo dia" onClick={() => setDia(somaDias(dia, 1))}>▶</button>
          {dia !== hoje && <button className="btn-link" onClick={() => setDia(hoje)}>hoje</button>}
        </div>
        <div className="segmentado" role="tablist" aria-label="Ver">
          {(["instrutores", "salas"] as const).map((v) => <button key={v} role="tab" aria-selected={ver === v} className={ver === v ? "ativo" : ""}
            onClick={() => { setVer(v); setEstado(""); }}>{v === "instrutores" ? "👤 Instrutores" : "🏫 Salas e laboratórios"}</button>)}
        </div>
        <select aria-label="Turno" value={turno} onChange={(e) => setTurno(e.target.value)}>
          <option value="">Todos os turnos</option><option value="M">Manhã</option><option value="T">Tarde</option><option value="N">Noite</option><option value="S">Sábado</option></select>
        <input type="search" placeholder={ver === "instrutores" ? "Buscar instrutor…" : "Buscar sala…"} aria-label="Buscar" value={busca} onChange={(e) => setBusca(e.target.value)} />
      </div>
      {d && <>
        <h3 className="onde-dia">{NOMES_DIA[new Date(d.data + "T12:00:00").getDay()]}, {dataBR(d.data)}
          {Object.keys(d.nao_letivo).length > 0 && <small className="aviso-nl"> · não letivo: {Object.values(d.nao_letivo).join("; ")}</small>}</h3>
        <div className="filtro-estados" role="group" aria-label="Filtrar por situação">
          <span className="sub">Mostrar:</span>
          <button className={`chip-estado sem-ponto ${!estado ? "ativo" : ""}`} onClick={() => setEstado("")}>Todos</button>
          {FILTROS[ver].map((e) => <button key={e} title={ESTADO[e][2]} className={`chip-estado ${ESTADO[e][0]} ${estado === e ? "ativo" : ""}`}
            onClick={() => setEstado(estado === e ? "" : e)}>{e === "bloqueado" ? "Indisponível" : ESTADO[e][1]} <b>{conta(e)}</b></button>)}
          <small className="mudo">números = {ver === "instrutores" ? "instrutor" : "sala"} × turno</small>
        </div>
        {turnos.length === 0 ? <p className="sub">Nenhum turno com aula neste dia{turno ? " (no turno escolhido)" : ""}.</p> :
          <Tabela colunas={[
            { chave: "nome", rotulo: ver === "instrutores" ? "Instrutor" : "Sala", render: (l: any) => <div className="onde-nome"><b>{ver === "salas" ? l.codigo : l.nome}</b>
              <small className="mudo">{ver === "salas" ? l.nome : l.modalidade}</small></div> },
            ...turnos.map((t: any) => ({ chave: t.codigo, rotulo: t.nome, render: (l: any) => celula(l.turnos[t.codigo]) })),
          ]} linhas={linhas} chave={(l: any) => l.id} vazio={estado ? `Ninguém “${ESTADO[estado][1].toLowerCase()}” neste dia.` : "Nada encontrado."} />}
        {fora.length > 0 && <p className="sub">{fora.map((t: any) => t.nome).join(", ")}: sem aula {fora.some((t: any) => t.codigo === "S") ? "de segunda a sexta" : "aos sábados"} — escolha {fora.some((t: any) => t.codigo === "S") ? "um sábado" : "um dia útil"} para ver.</p>}
      </>}
      {r.carregando && !d && <p role="status">Consultando…</p>}
      {r.erro && <div className="erro-box">{r.erro}</div>}
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
      {[["Semestre inteiro", "", ""], ["Últimas 4 semanas", dias(-28), hoje], ["Próximas 4 semanas", hoje, dias(28)],
        ...(cenario?.periodo_fim ? [["Daqui até o fim", hoje, cenario.periodo_fim]] : [])].map(([rot, a, b]) => (
        <button key={rot} className={`chip-estado sem-ponto ${inicio === a && fim === b ? "ativo" : ""}`} onClick={() => atalho(a!, b!)}>{rot}</button>))}
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
      <div className="segmentado" role="tablist" aria-label="Ordem">
        {[["mais", "▲ Mais ocupados"], ["menos", "▼ Com mais folga"]].map(([v, rot]) => <button key={v} role="tab" aria-selected={ordem === v}
          className={ordem === v ? "ativo" : ""} onClick={() => setOrdem(v)}>{rot}</button>)}
      </div>
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
              { chave: "horas_ocupadas", rotulo: "Horas ocupadas", alinhar: "dir", render: (l: any) => `${Math.round(l.horas_ocupadas)} h` }]}
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
    <Pagina titulo="Consultas" descricao="Quem está livre, em aula ou fora num dia; quem está mais (e menos) ocupado; e como a ocupação evolui semana a semana. Segue o semestre e a unidade escolhidos no topo.">
      <Abas abas={[{ id: "onde", rotulo: "📍 Quem está onde" }, { id: "ranking", rotulo: "🏆 Ranking de ocupação" }, { id: "tempo", rotulo: "📈 Ocupação no tempo" }]}
        ativa={aba} mudar={setAba} />
      {aba === "onde" && <QuemEstaOnde />}
      {aba === "ranking" && <Ranking />}
      {aba === "tempo" && <NoTempo />}
    </Pagina>
  );
}
