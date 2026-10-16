import { useState } from "react";
import { api, dataBR, DIAS_CURTOS, iso, qs, segundaDe } from "../api";
import { Abas, Pagina, Tabela, useCarregar } from "../components/ui";
import { BarraOcupacao, Faixa } from "../components/Ocupacao";
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
const CURTO: Record<string, string> = { livre: "livre", PL: "PL", PJ: "PJ", TR: "TR", bloqueado: "indisp.", nao_letivo: "não letivo" };
const SIGLA_TURNO: Record<string, string> = { M: "M", T: "V", N: "N", S: "S" };

/** Situação de cada instrutor e sala num dia (turno a turno) ou na semana inteira (dia a dia). */
function QuemEstaOnde() {
  const { cenario } = useApp();
  const [modo, setModo] = useState<"dia" | "semana">("dia");
  const [dia, setDia] = useState(iso(new Date()));
  const [turno, setTurno] = useState("");
  const [ver, setVer] = useState<"instrutores" | "salas">("instrutores");
  const [estado, setEstado] = useState("");
  const [busca, setBusca] = useState("");
  const seg = iso(segundaDe(new Date(dia + "T12:00:00")));
  const datas = modo === "dia" ? [dia] : [0, 1, 2, 3, 4, 5].map((n) => somaDias(seg, n));
  const r = useCarregar<any[]>(() => cenario ? Promise.all(datas.map((data) => api.get(`/api/consultas/situacao${qs({ cenario_id: cenario.id, data, turno })}`)))
    : Promise.resolve([]), [cenario?.id, datas.join(","), turno]);
  const dias = r.dados || [];
  const d = dias[0];
  const turnosDe = (x: any) => (x?.turnos || []).filter((t: any) => t.no_dia);  // só os turnos que acontecem naquele dia da semana
  const turnos = turnosDe(d);
  const fora = (d?.turnos || []).filter((t: any) => !t.no_dia);
  const todas = d?.[ver] || [];
  const porDia = dias.map((x: any) => Object.fromEntries((x[ver] || []).map((l: any) => [l.id, l])));
  const celulas = (id: any) => dias.flatMap((x: any, k: number) => turnosDe(x).map((t: any) => porDia[k][id]?.turnos[t.codigo]));
  const conta = (e: string) => todas.reduce((n: number, l: any) => n + celulas(l.id).filter((c: any) => c?.estado === e).length, 0);
  const linhas = todas.filter((l: any) => (!busca || `${l.nome} ${l.codigo || ""}`.toLowerCase().includes(busca.toLowerCase()))
    && (!estado || celulas(l.id).some((c: any) => c?.estado === estado)));
  const hoje = iso(new Date());
  const passo = modo === "dia" ? 1 : 7;
  const celula = (c: any) => {
    if (!c || c.estado === "sem_turno") return <span className="mudo">—</span>;
    if (c.estado === "fora_jornada") return <span className="cel-fora">fora da jornada</span>;
    const [cls, txt, expl] = ESTADO[c.estado] || ["", c.estado, ""];
    return <div className={`cel-sit ${cls} ${estado && c.estado !== estado ? "apagada" : ""}`} title={expl}>
      <b>{c.estado === "aula" ? c.turma : txt}</b>
      {c.estado === "aula" && <small>{c.uc.split(" – ")[0]} · {ver === "instrutores" ? (c.sala || "sem sala") : (c.instrutor || "sem instrutor")} · {c.horario}</small>}
      {c.estado !== "aula" && (c.detalhe || ["PL", "PJ", "TR"].includes(c.estado)) && <small>{c.detalhe || expl}</small>}</div>;
  };
  // semana: em cada dia, uma linha curta por turno (M, V, N ou S)
  const celulaDia = (x: any, k: number, id: any) => {
    const ts = turnosDe(x);
    if (!ts.length) return <span className="mudo">—</span>;
    return <div className="mini-turnos">{ts.map((t: any) => {
      const c = porDia[k][id]?.turnos[t.codigo];
      if (!c || c.estado === "sem_turno") return null;
      const [cls, , expl] = ESTADO[c.estado] || ["", c.estado, ""];
      const titulo = c.estado === "aula" ? `${t.nome}: ${c.turma} · ${c.uc} · ${ver === "instrutores" ? (c.sala || "sem sala") : (c.instrutor || "sem instrutor")} · ${c.horario}`
        : `${t.nome}: ${c.detalhe || expl || "fora da jornada"}`;
      return <div key={t.codigo} title={titulo} className={`mini-sit ${c.estado === "fora_jornada" ? "mini-fora" : `cel-sit ${cls}`} ${estado && c.estado !== estado ? "apagada" : ""}`}>
        <i>{SIGLA_TURNO[t.codigo] || t.codigo}</i> {c.estado === "aula" ? c.turma : c.estado === "fora_jornada" ? "—" : CURTO[c.estado] || c.estado}</div>;
    })}</div>;
  };
  const coluna = { chave: "nome", rotulo: ver === "instrutores" ? "Instrutor" : "Sala", render: (l: any) => <div className="onde-nome"><b>{ver === "salas" ? l.codigo : l.nome}</b>
    <small className="mudo">{ver === "salas" ? l.nome : l.modalidade}</small></div> };
  return (
    <>
      <div className="onde-barra">
        <div className="segmentado" role="tablist" aria-label="Período">
          {(["dia", "semana"] as const).map((m) => <button key={m} role="tab" aria-selected={modo === m} className={modo === m ? "ativo" : ""}
            onClick={() => setModo(m)}>{m === "dia" ? "Um dia" : "Semana"}</button>)}
        </div>
        <div className="seletor-dia" role="group" aria-label={modo === "dia" ? "Dia" : "Semana"}>
          <button className="btn" aria-label={modo === "dia" ? "Dia anterior" : "Semana anterior"} onClick={() => setDia(somaDias(dia, -passo))}>◀</button>
          <input type="date" aria-label="Dia" value={dia} onChange={(e) => e.target.value && setDia(e.target.value)} />
          <button className="btn" aria-label={modo === "dia" ? "Próximo dia" : "Próxima semana"} onClick={() => setDia(somaDias(dia, passo))}>▶</button>
          {dia !== hoje && <button className="btn-link" onClick={() => setDia(hoje)}>hoje</button>}
        </div>
        <div className="segmentado" role="tablist" aria-label="Ver">
          {(["instrutores", "salas"] as const).map((v) => <button key={v} role="tab" aria-selected={ver === v} className={ver === v ? "ativo" : ""}
            onClick={() => { setVer(v); setEstado(""); }}>{v === "instrutores" ? "👤 Instrutores" : "🏫 Salas e laboratórios"}</button>)}
        </div>
        <select aria-label="Turno" value={turno} onChange={(e) => setTurno(e.target.value)}>
          <option value="">Todos os turnos</option><option value="M">Manhã</option><option value="T">Tarde</option><option value="N">Noite</option><option value="S">Sábado</option></select>
        <input type="search" className="busca-larga" placeholder={ver === "instrutores" ? "Buscar instrutor pelo nome…" : "Buscar sala pelo código ou nome…"} aria-label="Buscar"
          value={busca} onChange={(e) => setBusca(e.target.value)} />
      </div>
      {d && <>
        <h3 className="onde-dia">{modo === "dia" ? <>{NOMES_DIA[new Date(d.data + "T12:00:00").getDay()]}, {dataBR(d.data)}</>
          : <>Semana de {dataBR(datas[0])} a {dataBR(datas[datas.length - 1])}</>}
          {dias.some((x: any) => Object.keys(x.nao_letivo).length > 0) && <small className="aviso-nl"> · não letivo: {dias.filter((x: any) => Object.keys(x.nao_letivo).length)
            .map((x: any) => `${dataBR(x.data).slice(0, 5)} (${Object.values(x.nao_letivo).join("; ")})`).join(", ")}</small>}</h3>
        <div className="filtro-estados" role="group" aria-label="Filtrar por situação">
          <span className="sub">Mostrar:</span>
          <button className={`chip-estado sem-ponto ${!estado ? "ativo" : ""}`} onClick={() => setEstado("")}>Todos</button>
          {FILTROS[ver].map((e) => <button key={e} title={ESTADO[e][2]} className={`chip-estado ${ESTADO[e][0]} ${estado === e ? "ativo" : ""}`}
            onClick={() => setEstado(estado === e ? "" : e)}>{e === "bloqueado" ? "Indisponível" : ESTADO[e][1]} <b>{conta(e)}</b></button>)}
          <small className="mudo">números = {ver === "instrutores" ? "instrutor" : "sala"} × turno{modo === "semana" ? " × dia" : ""}</small>
        </div>
        {modo === "semana" ? <>
          <Tabela colunas={[coluna, ...dias.map((x: any, k: number) => ({ chave: x.data, rotulo: `${DIAS_CURTOS[(k) % 7]} ${dataBR(x.data).slice(0, 5)}`,
            render: (l: any) => celulaDia(x, k, l.id) }))]} linhas={linhas} chave={(l: any) => l.id}
            vazio={estado ? `Ninguém “${ESTADO[estado][1].toLowerCase()}” nesta semana.` : "Nada encontrado."} />
          <p className="sub">M = manhã, V = vespertino (tarde), N = noite, S = sábado. Passe o mouse sobre um turno para ver UC, sala e horário.</p>
        </> : turnos.length === 0 ? <p className="sub">Nenhum turno com aula neste dia{turno ? " (no turno escolhido)" : ""}.</p> :
          <Tabela colunas={[coluna, ...turnos.map((t: any) => ({ chave: t.codigo, rotulo: t.nome, render: (l: any) => celula(l.turnos[t.codigo]) }))]}
            linhas={linhas} chave={(l: any) => l.id} vazio={estado ? `Ninguém “${ESTADO[estado][1].toLowerCase()}” neste dia.` : "Nada encontrado."} />}
        {modo === "dia" && fora.length > 0 && <p className="sub">{fora.map((t: any) => t.nome).join(", ")}: sem aula {fora.some((t: any) => t.codigo === "S") ? "de segunda a sexta" : "aos sábados"} — escolha {fora.some((t: any) => t.codigo === "S") ? "um sábado" : "um dia útil"} para ver.</p>}
      </>}
      {r.carregando && !d && <p role="status">Consultando…</p>}
      {r.erro && <div className="erro-box">{r.erro}</div>}
    </>
  );
}

export function Periodo({ inicio, fim, setInicio, setFim }: { inicio: string; fim: string; setInicio: (v: string) => void; setFim: (v: string) => void }) {
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

export default function Consultas() {
  const { cenario } = useApp();
  const [aba, setAba] = useState("onde");
  if (!cenario) return <Pagina titulo="Consultas"><p>Selecione um semestre no topo da página.</p></Pagina>;
  return (
    <Pagina titulo="Consultas" descricao="Quem está livre, em aula ou fora num dia ou na semana, e quem está mais (e menos) ocupado. A ocupação semana a semana fica em Ocupação e andamento. Segue o semestre e a unidade escolhidos no topo.">
      <Abas abas={[{ id: "onde", rotulo: "📍 Quem está onde" }, { id: "ranking", rotulo: "🏆 Ranking de ocupação" }]}
        ativa={aba} mudar={setAba} />
      {aba === "onde" && <QuemEstaOnde />}
      {aba === "ranking" && <Ranking />}
    </Pagina>
  );
}
