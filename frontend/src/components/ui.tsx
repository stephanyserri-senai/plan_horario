import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { ErroApi } from "../api";

export function useCarregar<T>(fn: () => Promise<T>, deps: any[]) {
  const [dados, setDados] = useState<T | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [carregando, setCarregando] = useState(false);
  const ref = useRef(0);
  const recarregar = useCallback(async () => {
    const n = ++ref.current;
    setCarregando(true);
    setErro(null);
    try {
      const r = await fn();
      if (n === ref.current) setDados(r);
    } catch (e: any) {
      if (n === ref.current) setErro(e.message || String(e));
    } finally {
      if (n === ref.current) setCarregando(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  useEffect(() => { recarregar(); }, [recarregar]);
  return { dados, erro, carregando, recarregar, setDados };
}

export function Pagina({ titulo, descricao, acoes, children }: { titulo: string; descricao?: string; acoes?: ReactNode; children: ReactNode }) {
  return (
    <section className="pagina">
      <header className="pagina-cab">
        <div>
          <h1>{titulo}</h1>
          {descricao && <p className="sub">{descricao}</p>}
        </div>
        {acoes && <div className="acoes">{acoes}</div>}
      </header>
      {children}
    </section>
  );
}

export function Card({ titulo, children, extra, className }: { titulo?: ReactNode; children: ReactNode; extra?: ReactNode; className?: string }) {
  return (
    <div className={`card ${className || ""}`}>
      {(titulo || extra) && <div className="card-cab"><h2>{titulo}</h2>{extra}</div>}
      {children}
    </div>
  );
}

export function Kpi({ rotulo, valor, detalhe, tom, onClick }: { rotulo: string; valor: ReactNode; detalhe?: ReactNode; tom?: "ok" | "alerta" | "erro"; onClick?: () => void }) {
  const C = onClick ? "button" : "div";
  return (
    <C className={`kpi ${tom ? `kpi-${tom}` : ""} ${onClick ? "clicavel" : ""}`} onClick={onClick} type={onClick ? "button" : undefined}>
      <span className="kpi-rotulo">{rotulo}</span>
      <span className="kpi-valor">{valor}</span>
      {detalhe && <span className="kpi-det">{detalhe}</span>}
    </C>
  );
}

const ICONES: Record<string, string> = { bloqueio: "⛔", alerta: "⚠", preferencia: "◐", recomendacao: "💡", ok: "✔", info: "ℹ" };
export function Badge({ tipo, children }: { tipo: string; children?: ReactNode }) {
  return <span className={`badge badge-${tipo}`}><span aria-hidden="true">{ICONES[tipo] || ""}</span> {children ?? tipo}</span>;
}

export function EstadoCenario({ estado }: { estado: string }) {
  const nomes: Record<string, string> = {
    em_elaboracao: "Em elaboração", em_otimizacao: "Em otimização", em_validacao: "Em validação", aguardando_aprovacao: "Aguardando aprovação",
    aprovado: "Aprovado", publicado: "Publicado", arquivado: "Arquivado",
  };
  return <span className={`estado estado-${estado}`}>{nomes[estado] || estado}</span>;
}

export function Modal({ titulo, aberto, fechar, children, largo }: { titulo: string; aberto: boolean; fechar: () => void; children: ReactNode; largo?: boolean }) {
  useEffect(() => {
    if (!aberto) return;
    const h = (e: KeyboardEvent) => e.key === "Escape" && fechar();
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [aberto, fechar]);
  if (!aberto) return null;
  return (
    <div className="modal-fundo" onMouseDown={(e) => e.target === e.currentTarget && fechar()}>
      <div className={`modal ${largo ? "modal-largo" : ""}`} role="dialog" aria-modal="true" aria-label={titulo}>
        <div className="modal-cab">
          <h2>{titulo}</h2>
          <button className="btn-icone" onClick={fechar} aria-label="Fechar">✕</button>
        </div>
        <div className="modal-corpo">{children}</div>
      </div>
    </div>
  );
}

export function Campo({ rotulo, children, ajuda, obrigatorio }: { rotulo: string; children: ReactNode; ajuda?: string; obrigatorio?: boolean }) {
  return (
    <label className="campo">
      <span className="campo-rotulo">{rotulo}{obrigatorio && <span className="obrig" aria-label="obrigatório"> *</span>}</span>
      {children}
      {ajuda && <span className="campo-ajuda">{ajuda}</span>}
    </label>
  );
}

export function Abas({ abas, ativa, mudar }: { abas: { id: string; rotulo: string }[]; ativa: string; mudar: (id: string) => void }) {
  return (
    <div className="abas" role="tablist">
      {abas.map((a) => (
        <button key={a.id} role="tab" aria-selected={a.id === ativa} className={a.id === ativa ? "ativa" : ""} onClick={() => mudar(a.id)}>{a.rotulo}</button>
      ))}
    </div>
  );
}

export type Coluna<T> = { chave: string; rotulo: string; render?: (l: T) => ReactNode; alinhar?: "dir" };
export function Tabela<T extends Record<string, any>>({ colunas, linhas, vazio, aoClicar, chave }: {
  colunas: Coluna<T>[]; linhas: T[]; vazio?: string; aoClicar?: (l: T) => void; chave?: (l: T, i: number) => string | number;
}) {
  return (
    <div className="tabela-wrap">
      <table className="tabela">
        <thead><tr>{colunas.map((c) => <th key={c.chave} className={c.alinhar === "dir" ? "dir" : ""}>{c.rotulo}</th>)}</tr></thead>
        <tbody>
          {linhas.length === 0 && <tr><td colSpan={colunas.length} className="vazio">{vazio || "Nenhum registro."}</td></tr>}
          {linhas.map((l, i) => (
            <tr key={chave ? chave(l, i) : (l.id ?? i)} onClick={aoClicar ? () => aoClicar(l) : undefined} className={aoClicar ? "clicavel" : ""}
                tabIndex={aoClicar ? 0 : undefined} onKeyDown={aoClicar ? (e) => e.key === "Enter" && aoClicar(l) : undefined}>
              {colunas.map((c) => <td key={c.chave} className={c.alinhar === "dir" ? "dir" : ""}>{c.render ? c.render(l) : fmt(l[c.chave])}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function fmt(v: any): ReactNode {
  if (v === null || v === undefined || v === "") return <span className="mudo">—</span>;
  if (typeof v === "boolean") return v ? "Sim" : "Não";
  if (Array.isArray(v)) return v.join(", ");
  if (typeof v === "object") return JSON.stringify(v);
  return String(v);
}

export function Paginacao({ pagina, total, porPagina, mudar }: { pagina: number; total: number; porPagina: number; mudar: (p: number) => void }) {
  const paginas = Math.max(1, Math.ceil(total / porPagina));
  return (
    <div className="paginacao">
      <span>{total} registro(s)</span>
      <button className="btn" disabled={pagina <= 1} onClick={() => mudar(pagina - 1)}>‹ Anterior</button>
      <span>Página {pagina} de {paginas}</span>
      <button className="btn" disabled={pagina >= paginas} onClick={() => mudar(pagina + 1)}>Próxima ›</button>
    </div>
  );
}

export function Erro({ erro, ocultarAlternativas }: { erro: any; ocultarAlternativas?: boolean }) {
  if (!erro) return null;
  const e = erro as ErroApi;
  const oc: any[] = e.detalhes?.ocorrencias || [];
  const alt = e.detalhes?.alternativas;
  return (
    <div className="erro-box" role="alert">
      <strong>{e.message || String(erro)}</strong>
      {oc.length > 0 && <OcorrenciasLista ocorrencias={oc} />}
      {e.detalhes?.falhas && (
        <ul>{e.detalhes.falhas.slice(0, 15).map((f: any, i: number) => (
          <li key={i}>{f.data}: {(f.ocorrencias || []).map((o: any) => o.descricao).join("; ")}</li>))}</ul>
      )}
      {alt && !ocultarAlternativas && <Alternativas alt={alt} />}
      {e.detalhes?.erros && <ul>{e.detalhes.erros.slice(0, 20).map((x: any, i: number) => <li key={i}>{typeof x === "string" ? x : `Linha ${x.linha}: ${x.erros?.join("; ")}`}</li>)}</ul>}
    </div>
  );
}

export function OcorrenciasLista({ ocorrencias }: { ocorrencias: any[] }) {
  return (
    <ul className="ocorrencias">
      {ocorrencias.map((o, i) => (
        <li key={i}><Badge tipo={o.severidade}>{o.regra}</Badge> {o.descricao}</li>
      ))}
    </ul>
  );
}

export function Alternativas({ alt, aplicar }: { alt: any; aplicar?: (a: any) => void }) {
  const vazio = !alt.instrutores?.length && !alt.ambientes?.length && !alt.horarios?.length;
  return (
    <div className="alternativas">
      <h3>Alternativas validadas (calculadas a partir dos cadastros)</h3>
      {vazio && <p>Nenhuma alternativa sem conflito foi encontrada na mesma semana.</p>}
      {alt.instrutores?.length > 0 && <p><b>Instrutores habilitados livres:</b> {alt.instrutores.map((i: any) => (
        <button key={i.id} className="chip" disabled={!aplicar} onClick={() => aplicar?.({ instrutor_id: i.id })}>{i.nome}</button>))}</p>}
      {alt.ambientes?.length > 0 && <p><b>Ambientes compatíveis livres:</b> {alt.ambientes.map((a: any) => (
        <button key={a.id} className="chip" disabled={!aplicar} onClick={() => aplicar?.({ ambiente_id: a.id })}>{a.codigo}</button>))}</p>}
      {alt.horarios?.length > 0 && <p><b>Outros horários livres na semana:</b> {alt.horarios.map((h: any, i: number) => (
        <button key={i} className="chip" disabled={!aplicar} onClick={() => aplicar?.({ data: h.data, periodo_inicio_id: h.periodo_inicio_id, num_periodos: h.num_periodos })}>
          {h.data.slice(8, 10)}/{h.data.slice(5, 7)} {h.inicio}–{h.fim}</button>))}</p>}
    </div>
  );
}

export function Selecao({ valor, mudar, opcoes, vazio, rotulo, id }: {
  valor: any; mudar: (v: string) => void; opcoes: { id: any; rotulo: string }[]; vazio?: string; rotulo?: string; id?: string;
}) {
  return (
    <select id={id} aria-label={rotulo} value={valor ?? ""} onChange={(e) => mudar(e.target.value)}>
      <option value="">{vazio ?? "—"}</option>
      {opcoes.map((o) => <option key={o.id} value={o.id}>{o.rotulo}</option>)}
    </select>
  );
}

export function Json({ dados }: { dados: any }) {
  return <pre className="json">{JSON.stringify(dados, null, 2)}</pre>;
}
