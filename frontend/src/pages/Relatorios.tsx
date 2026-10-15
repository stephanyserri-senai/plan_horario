import { useState } from "react";
import { baixar, qs } from "../api";
import { Pagina } from "../components/ui";
import { useApp } from "../contexto";
import { useOpcoes } from "../hooks";

type Filtro = { campo: string; ent: string; todos: string };
type Item = { id: string; ic: string; titulo: string; desc: string; url: string; nome: string; filtro?: Filtro; periodo?: boolean; formatos?: string[] };

const HORARIOS: Item[] = [
  { id: "turmas", ic: "👥", titulo: "Horário das turmas", desc: "Uma aba por turma: semana a semana (UC, instrutor e sala de cada dia) e quanto falta de cada UC.",
    url: "/api/exportar/horario_turmas", nome: "horario_turmas", filtro: { campo: "turma_id", ent: "turmas", todos: "Todas as turmas" } },
  { id: "instrutores", ic: "👩‍🏫", titulo: "Agenda dos instrutores", desc: "Ocupação de cada instrutor (horas por semana, folga, % ocupado) e a agenda dele.",
    url: "/api/exportar/agenda_instrutores", nome: "agenda_instrutores", filtro: { campo: "instrutor_id", ent: "instrutores", todos: "Todos os instrutores" }, periodo: true },
  { id: "salas", ic: "🏫", titulo: "Uso das salas e laboratórios", desc: "Horas livres e ocupadas de cada ambiente e o quadro semanal de uso.",
    url: "/api/exportar/uso_ambientes", nome: "salas_e_laboratorios", filtro: { campo: "ambiente_id", ent: "ambientes", todos: "Todas as salas" }, periodo: true },
];
const INDICADORES: Item[] = [
  { id: "carga", ic: "📊", titulo: "Carga horária por turma e UC", desc: "Carga total, realizada, programada, o que falta, prazo e risco de atraso.",
    url: "/api/exportar/indicadores/turmas", nome: "carga_horaria_turmas_ucs", periodo: true },
  { id: "ocup_salas", ic: "📈", titulo: "Ocupação das salas", desc: "Taxa de ocupação por sala, por turno e por dia da semana.",
    url: "/api/exportar/indicadores/ambientes", nome: "ocupacao_salas", periodo: true },
  { id: "ocup_inst", ic: "⏱️", titulo: "Ocupação dos instrutores", desc: "Carga contratual, limite de aulas (teto de 90%), média semanal e folga.",
    url: "/api/exportar/indicadores/instrutores", nome: "ocupacao_instrutores", periodo: true },
  { id: "gargalos", ic: "⚠️", titulo: "Gargalos de capacidade", desc: "Onde falta sala, laboratório ou instrutor e o que fazer.",
    url: "/api/exportar/indicadores/gargalos", nome: "gargalos", periodo: true },
];
const TIPOS_GRADE = [["", "Todas as aulas"], ["turma", "Uma turma"], ["instrutor", "Um instrutor"], ["ambiente", "Uma sala"], ["turno", "Um turno"]];
const ENT: Record<string, string> = { turma: "turmas", instrutor: "instrutores", ambiente: "ambientes", turno: "turnos" };

function Botoes({ gerar, desabilitado, formatos = ["xlsx", "pdf"] }: { gerar: (f: string) => Promise<void>; desabilitado?: boolean; formatos?: string[] }) {
  const [baixando, setBaixando] = useState("");
  const ir = async (f: string) => { setBaixando(f); try { await gerar(f); } finally { setBaixando(""); } };
  return (
    <div className="rel-botoes">
      {formatos.map((f) => (
        <button key={f} className={`btn ${f === "xlsx" ? "btn-primario" : ""}`} disabled={desabilitado || !!baixando} onClick={() => ir(f)}>
          {baixando === f ? "Gerando…" : f === "xlsx" ? "⬇ Excel" : "⬇ PDF"}
        </button>))}
    </div>
  );
}

function Cartao({ it, base }: { it: Item; base: Record<string, any> }) {
  const [fid, setFid] = useState("");
  const ops = useOpcoes(it.filtro?.ent);
  const gerar = (f: string) => {
    const p: Record<string, any> = { ...base, formato: f };
    if (!it.periodo) { delete p.inicio; delete p.fim; }
    if (it.filtro && fid) p[it.filtro.campo] = fid;
    const sufixo = fid ? `_${(ops.find((o) => String(o.id) === fid)?.rotulo || fid).split(" ")[0]}` : "";
    return baixar(`${it.url}${qs(p)}`, `${it.nome}${sufixo}.${f}`);
  };
  return (
    <div className="exp-cartao">
      <div className="exp-ico" aria-hidden="true">{it.ic}</div>
      <div className="exp-corpo">
        <b>{it.titulo}</b>
        <p>{it.desc}</p>
        <div className="exp-acoes">
          {it.filtro && <select aria-label={`Filtrar ${it.titulo}`} value={fid} onChange={(e) => setFid(e.target.value)}>
            <option value="">{it.filtro.todos}</option>{ops.map((o) => <option key={o.id} value={o.id}>{o.rotulo}</option>)}</select>}
          <Botoes gerar={gerar} />
        </div>
      </div>
    </div>
  );
}

/** Lista de aulas e grade de uma semana: escolhe o recorte (turma, instrutor, sala, turno). */
function CartaoGrade({ base, semanaInicial }: { base: Record<string, any>; semanaInicial: string }) {
  const [tipo, setTipo] = useState("");
  const [fid, setFid] = useState("");
  const [semana, setSemana] = useState(semanaInicial);
  const ops = useOpcoes(ENT[tipo]);
  const filtro = tipo && fid ? { filtro: tipo, filtro_id: fid } : {};
  return (
    <>
      <div className="exp-cartao">
        <div className="exp-ico" aria-hidden="true">📋</div>
        <div className="exp-corpo">
          <b>Lista de aulas</b>
          <p>Todas as aulas do período, uma por linha: data, horário, turma, UC, instrutor e sala.</p>
          <div className="exp-acoes">
            <select aria-label="Recorte da lista" value={tipo} onChange={(e) => { setTipo(e.target.value); setFid(""); }}>
              {TIPOS_GRADE.map(([v, r]) => <option key={v} value={v}>{r}</option>)}</select>
            {tipo && <select aria-label="Escolha" value={fid} onChange={(e) => setFid(e.target.value)}>
              <option value="">— escolha —</option>{ops.map((o) => <option key={o.id} value={o.id}>{o.rotulo}</option>)}</select>}
            <Botoes desabilitado={!!tipo && !fid} gerar={(f) => baixar(`/api/exportar/grade${qs({ ...base, ...filtro, formato: f })}`, `aulas.${f}`)} />
          </div>
        </div>
      </div>
      <div className="exp-cartao">
        <div className="exp-ico" aria-hidden="true">🗓️</div>
        <div className="exp-corpo">
          <b>Grade de uma semana</b>
          <p>Quadro horário × dia. No Excel, uma aba com todas as turmas e uma aba para cada turma; o PDF traz o quadro geral.</p>
          <div className="exp-acoes">
            <label className="rel-semana">Semana de <input type="date" value={semana} onChange={(e) => setSemana(e.target.value)} /></label>
            <Botoes desabilitado={!semana || (!!tipo && !fid)}
              gerar={(f) => baixar(`/api/exportar/grade${qs({ cenario_id: base.cenario_id, ...filtro, semana, formato: f })}`, `grade_semana.${f}`)} />
          </div>
          {tipo && <p className="mudo">Usa o mesmo recorte da lista de aulas ({TIPOS_GRADE.find((t) => t[0] === tipo)?.[1].toLowerCase()}).</p>}
        </div>
      </div>
    </>
  );
}

export default function Relatorios() {
  const { cenario, cenarios } = useApp();
  const [inicio, setInicio] = useState("");
  const [fim, setFim] = useState("");
  const [pacote, setPacote] = useState("xlsx");
  const [gerandoPacote, setGerandoPacote] = useState(false);
  const [sel, setSel] = useState<number[]>([]);
  if (!cenario) return <Pagina titulo="Relatórios"><p>Selecione ou crie um semestre no topo da tela.</p></Pagina>;
  const base: Record<string, any> = { cenario_id: cenario.id, inicio: inicio || undefined, fim: fim || undefined };
  const hoje = new Date();
  const seg = new Date(hoje); seg.setDate(hoje.getDate() - ((hoje.getDay() + 6) % 7));
  const semanaInicial = seg.toISOString().slice(0, 10);
  const doSemestre = cenarios.filter((c) => c.tipo !== "simulacao");
  return (
    <Pagina titulo="Relatórios" descricao="Relatórios prontos do semestre e da versão selecionados no topo, em Excel ou PDF. Respeitam o seu perfil e escopo de unidades e ficam registrados na auditoria.">
      <section className="card rel-topo">
        <div>
          <h2>{cenario.nome}</h2>
          <p className="sub">Período (opcional): sem datas, vale o semestre inteiro.</p>
          <div className="filtros">
            <label>De <input type="date" value={inicio} onChange={(e) => setInicio(e.target.value)} /></label>
            <label>Até <input type="date" value={fim} min={inicio || undefined} onChange={(e) => setFim(e.target.value)} /></label>
            {(inicio || fim) && <button className="btn-link" onClick={() => { setInicio(""); setFim(""); }}>limpar período</button>}
          </div>
        </div>
        <div className="rel-pacote">
          <b>📦 Todos os relatórios</b>
          <p className="sub">Um arquivo .zip com os 8 relatórios do semestre.</p>
          <div className="exp-acoes">
            <select aria-label="Formato do pacote" value={pacote} onChange={(e) => setPacote(e.target.value)}>
              <option value="xlsx">Excel</option><option value="pdf">PDF</option><option value="ambos">Excel e PDF</option></select>
            <button className="btn btn-primario" disabled={gerandoPacote} onClick={async () => {
              setGerandoPacote(true);
              try { await baixar(`/api/exportar/pacote${qs({ ...base, formato: pacote })}`, "relatorios.zip"); } finally { setGerandoPacote(false); }
            }}>{gerandoPacote ? "Gerando… (até 30 s)" : "⬇ Baixar todos"}</button>
          </div>
        </div>
      </section>
      <section className="card">
        <h2>Horários</h2>
        <div className="exp-grid">
          {HORARIOS.map((it) => <Cartao key={it.id} it={it} base={base} />)}
          <CartaoGrade base={base} semanaInicial={semanaInicial} />
        </div>
      </section>
      <section className="card">
        <h2>Indicadores</h2>
        <div className="exp-grid">{INDICADORES.map((it) => <Cartao key={it.id} it={it} base={base} />)}</div>
      </section>
      <section className="card">
        <h2>Comparar versões</h2>
        <p className="sub">Pontuação, aulas, carga pendente, ocupação e conflitos de cada versão, com os mesmos pesos.</p>
        <div className="exp-grid">
          <div className="exp-cartao">
            <div className="exp-ico" aria-hidden="true">⚖️</div>
            <div className="exp-corpo">
              <b>Comparativo de versões</b>
              <div className="checks">{doSemestre.map((c) => <label key={c.id}><input type="checkbox" checked={sel.includes(c.id)}
                onChange={(e) => setSel(e.target.checked ? [...sel, c.id] : sel.filter((x) => x !== c.id))} /> {c.nome}</label>)}</div>
              <div className="exp-acoes">
                {sel.length < 2 && <span className="mudo">Marque ao menos duas versões.</span>}
                <Botoes desabilitado={sel.length < 2} gerar={(f) => baixar(`/api/exportar/comparativo${qs({ cenarios_ids: sel.join(","), formato: f })}`, `comparativo_versoes.${f}`)} />
              </div>
            </div>
          </div>
        </div>
      </section>
    </Pagina>
  );
}
