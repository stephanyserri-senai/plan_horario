import { useState } from "react";
import { baixar, qs } from "../api";
import { Card, Pagina } from "../components/ui";
import { useApp } from "../contexto";
import { useOpcoes } from "../hooks";

export default function Relatorios() {
  const { cenario, cenarios } = useApp();
  const [filtro, setFiltro] = useState("");
  const [fid, setFid] = useState("");
  const [inicio, setInicio] = useState("");
  const [fim, setFim] = useState("");
  const [sel, setSel] = useState<number[]>([]);
  const ENT: Record<string, string> = { turma: "turmas", instrutor: "instrutores", ambiente: "ambientes", turno: "turnos" };
  const ops = useOpcoes(ENT[filtro]);
  if (!cenario) return <Pagina titulo="Relatórios"><p>Selecione um cenário.</p></Pagina>;
  const b = (url: string, nome: string) => baixar(url, nome);
  const Formatos = ({ url, nome }: { url: (f: string) => string; nome: string }) => (
    <div className="acoes">{["xlsx", "csv", "pdf"].map((f) => <button key={f} className="btn" onClick={() => b(url(f), `${nome}.${f}`)}>{f.toUpperCase()}</button>)}</div>);
  return (
    <Pagina titulo="Relatórios e exportações" descricao="Exportações respeitam o perfil e o escopo de unidades do usuário e são registradas na auditoria.">
      <div className="grid-2">
        <Card titulo="Grade horária">
          <div className="filtros">
            <select aria-label="Grade por" value={filtro} onChange={(e) => { setFiltro(e.target.value); setFid(""); }}><option value="">Todas as aulas</option><option value="turma">Por turma</option><option value="instrutor">Por instrutor</option><option value="ambiente">Por ambiente</option><option value="turno">Por turno</option></select>
            {filtro && <select aria-label="Selecione" value={fid} onChange={(e) => setFid(e.target.value)}><option value="">—</option>{ops.map((o) => <option key={o.id} value={o.id}>{o.rotulo}</option>)}</select>}
            <label>De <input type="date" value={inicio} onChange={(e) => setInicio(e.target.value)} /></label><label>Até <input type="date" value={fim} onChange={(e) => setFim(e.target.value)} /></label>
          </div>
          <Formatos nome="grade" url={(f) => `/api/exportar/grade${qs({ cenario_id: cenario.id, formato: f, filtro: fid ? filtro : "", filtro_id: fid, inicio, fim })}`} />
        </Card>
        {[["ambientes", "Indicadores de ocupação dos ambientes"], ["instrutores", "Ocupação e carga horária dos instrutores"], ["turmas", "Turmas e UCs (carga horária e risco)"], ["gargalos", "Gargalos de capacidade"]].map(([t, r]) => (
          <Card key={t} titulo={r}><Formatos nome={`indicadores_${t}`} url={(f) => `/api/exportar/indicadores/${t}${qs({ cenario_id: cenario.id, formato: f, inicio, fim })}`} /></Card>))}
        <Card titulo="Comparativo de cenários">
          <div className="checks">{cenarios.map((c) => <label key={c.id}><input type="checkbox" checked={sel.includes(c.id)} onChange={(e) => setSel(e.target.checked ? [...sel, c.id] : sel.filter((x) => x !== c.id))} /> {c.nome}</label>)}</div>
          {sel.length >= 2 ? <Formatos nome="comparativo" url={(f) => `/api/exportar/comparativo?cenarios_ids=${sel.join(",")}&formato=${f}`} /> : <p className="mudo">Selecione ao menos dois cenários.</p>}
        </Card>
        <Card titulo="Resultados do simulador"><p>Disponíveis na lista de simulações (Simulador de capacidade).</p></Card>
      </div>
    </Pagina>
  );
}
