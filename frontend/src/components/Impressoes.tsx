import { useMemo, useState } from "react";
import { api, baixar, dataBR, qs } from "../api";
import { useApp } from "../contexto";
import { Badge, Campo, Erro, Pagina, useCarregar } from "./ui";

// regra: a impressão é pedida até a quinta-feira da semana anterior ao uso
const DIA_LIMITE = 3;  // quinta
const iso = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
export function prazoPara(dataUso: string): string {
  const d = new Date(`${dataUso}T12:00:00`);
  d.setDate(d.getDate() - ((d.getDay() + 6) % 7) - 7 + DIA_LIMITE);
  return iso(d);
}
const TOM: Record<string, string> = { pendente: "alerta", em_producao: "info", pronta: "ok", entregue: "neutro", recusada: "erro", cancelada: "neutro" };
const ICONE: Record<string, string> = { pendente: "⏳", em_producao: "🖨", pronta: "✅", entregue: "📦", recusada: "✖", cancelada: "—" };
const ACAO: Record<string, string> = { em_producao: "Em produção", pronta: "Marcar como pronta", entregue: "Entregue", recusada: "Recusar" };

const MAX_PDF = 4 * 1024 * 1024;  // 4 MB
const mb = (b: number) => (b < 102400 ? `${Math.max(1, Math.round(b / 1024))} KB` : `${(b / 1048576).toLocaleString("pt-BR", { maximumFractionDigits: 1 })} MB`);

function CartaoPedido({ p, children, mostrarInstrutor, urlPdf }: { p: any; children?: React.ReactNode; mostrarInstrutor?: boolean; urlPdf: string }) {
  const { aviso } = useApp();
  return (
    <div className={`imp-card st-${p.status}`}>
      <div className="imp-card-cab">
        <span className="imp-ico" aria-hidden="true">{ICONE[p.status]}</span>
        <div className="imp-card-tit"><b>{p.titulo}</b>
          <small className="mudo">{mostrarInstrutor ? `${p.instrutor} · ` : ""}{p.turma ? `${p.turma} · ` : ""}uso em {dataBR(p.data_uso)} · pedido até {dataBR(p.prazo)}</small></div>
        <Badge tipo={TOM[p.status] || "info"}>{p.status_rotulo}</Badge>
      </div>
      <div className="imp-card-det">
        <span>📄 <b>{p.copias}</b> cópia(s){p.paginas ? ` × ${p.paginas} página(s)` : ""}</span>
        <span>{p.frente_verso ? "Frente e verso" : "Só frente"} · {p.colorido ? "Colorido" : "Preto e branco"}</span>
        {p.paginas && <span className="mudo">≈ {p.folhas} folha(s)</span>}
        {p.tem_pdf && <button className="btn-link" onClick={() => baixar(urlPdf, p.arquivo_nome).catch((e: any) => aviso(e.message, "erro"))}
          title="Baixar o PDF para imprimir">📄 {p.arquivo_nome} ({mb(p.arquivo_tamanho || 0)})</button>}
        {p.arquivo_url && <a href={p.arquivo_url} target="_blank" rel="noreferrer">🔗 arquivo</a>}
      </div>
      {p.descricao && <p className="imp-desc">{p.descricao}</p>}
      {p.resposta && <p className="imp-resp">💬 <b>Coordenação:</b> {p.resposta}</p>}
      {children}
    </div>
  );
}

/** Portal do instrutor: pedir impressão (até a quinta da semana anterior ao uso) e acompanhar o retorno da coordenação. */
export function MinhasImpressoes() {
  const { aviso } = useApp();
  const r = useCarregar<any>(() => api.get("/api/portal/impressoes"), []);
  const vazio = (uso: string) => ({ titulo: "", descricao: "", arquivo_url: "", copias: 1, paginas: "", frente_verso: false, colorido: false, data_uso: uso, turma_id: "" });
  const [f, setF] = useState<any>(null);
  const [erro, setErro] = useState<any>(null);
  const [enviando, setEnviando] = useState(false);
  const [pdf, setPdf] = useState<File | null>(null);
  const [chaveArq, setChaveArq] = useState(0);
  const d = r.dados;
  const form = f || (d ? vazio(d.primeiro_uso_possivel) : null);
  if (r.carregando && !d) return <p role="status">Carregando…</p>;
  if (r.erro) return <div className="erro-box">{r.erro}</div>;
  if (!d || !form) return null;
  const prazo = prazoPara(form.data_uso);
  const noPrazo = d.hoje <= prazo;
  const enviar = async () => {
    setErro(null); setEnviando(true);
    try {
      const novo = await api.post("/api/portal/impressoes", { ...form, turma_id: form.turma_id || null, paginas: form.paginas || null });
      if (pdf) {
        const fd = new FormData(); fd.append("arquivo", pdf);
        try { await api.upload(`/api/portal/impressoes/${novo.id}/pdf`, fd); }
        catch (e: any) { aviso(`Pedido enviado, mas o PDF não subiu: ${e.message}`, "erro"); setF(vazio(form.data_uso)); r.recarregar(); return; }
      }
      aviso("Pedido de impressão enviado à coordenação. Você recebe o retorno aqui e nas notificações.");
      setF(vazio(form.data_uso)); setPdf(null); setChaveArq((k) => k + 1); r.recarregar();
    } catch (e) { setErro(e); } finally { setEnviando(false); }
  };
  const cancelar = async (p: any) => {
    if (!confirm(`Cancelar o pedido "${p.titulo}"?`)) return;
    try { await api.post(`/api/portal/impressoes/${p.id}/cancelar`, {}); r.recarregar(); } catch (e: any) { aviso(e.message, "erro"); }
  };
  const abertos = d.pedidos.filter((p: any) => ["pendente", "em_producao", "pronta"].includes(p.status));
  return (
    <div className="card imp-portal">
      <h2>🖨 Pedidos de impressão</h2>
      <p className="sub">Peça a impressão do material até a <b>quinta-feira da semana anterior</b> ao dia em que vai usar (ex.: para usar na
        quarta 18/11, peça até a quinta 12/11). A coordenação dá o retorno aqui — em produção, pronta para retirar ou entregue.</p>
      <div className="imp-form">
        <Campo rotulo="O que imprimir" obrigatorio><input value={form.titulo} placeholder="ex.: apostila de comandos elétricos" onChange={(e) => setF({ ...form, titulo: e.target.value })} /></Campo>
        <Campo rotulo="Dia de uso" obrigatorio ajuda={noPrazo ? `Pedir até ${dataBR(prazo)} (quinta-feira)` : `Fora do prazo: o pedido deveria ter sido feito até ${dataBR(prazo)}`}>
          <input type="date" min={d.primeiro_uso_possivel} value={form.data_uso} onChange={(e) => setF({ ...form, data_uso: e.target.value })} /></Campo>
        <Campo rotulo="Turma"><select value={form.turma_id} onChange={(e) => setF({ ...form, turma_id: e.target.value })}>
          <option value="">—</option>{d.turmas.map((t: any) => <option key={t.id} value={t.id}>{t.codigo}</option>)}</select></Campo>
        <Campo rotulo="Cópias" obrigatorio><input type="number" min={1} max={2000} value={form.copias} onChange={(e) => setF({ ...form, copias: e.target.value })} /></Campo>
        <Campo rotulo="Páginas por cópia"><input type="number" min={1} max={1000} value={form.paginas} onChange={(e) => setF({ ...form, paginas: e.target.value })} /></Campo>
        <div className="imp-opcoes">
          <label><input type="checkbox" checked={form.frente_verso} onChange={(e) => setF({ ...form, frente_verso: e.target.checked })} /> Frente e verso</label>
          <label><input type="checkbox" checked={form.colorido} onChange={(e) => setF({ ...form, colorido: e.target.checked })} /> Colorido</label>
        </div>
        <Campo rotulo="PDF para imprimir" ajuda={pdf ? `${pdf.name} · ${mb(pdf.size)}` : "Até 4 MB. Maior que isso, use o link abaixo."}>
          <input key={chaveArq} type="file" accept="application/pdf,.pdf" onChange={(e) => {
            const a = e.target.files?.[0] || null;
            if (a && a.size > MAX_PDF) { aviso(`O PDF tem ${mb(a.size)}; o limite é 4 MB. Para arquivo maior, mande o link.`, "erro"); e.target.value = ""; setPdf(null); return; }
            if (a && !a.name.toLowerCase().endsWith(".pdf")) { aviso("Envie o material em PDF.", "erro"); e.target.value = ""; setPdf(null); return; }
            setPdf(a);
          }} /></Campo>
        <Campo rotulo="Ou link do arquivo" ajuda="Drive, OneDrive… com acesso para a coordenação."><input value={form.arquivo_url} placeholder="https://"
          onChange={(e) => setF({ ...form, arquivo_url: e.target.value })} /></Campo>
        <Campo rotulo="Observação"><input value={form.descricao} placeholder="ex.: grampear; separar por grupo" onChange={(e) => setF({ ...form, descricao: e.target.value })} /></Campo>
      </div>
      <Erro erro={erro} />
      <div className="acoes-linha">
        <button className="btn btn-primario" disabled={enviando || !noPrazo || (!pdf && !form.arquivo_url.trim()) || form.titulo.trim().length < 3 || !(Number(form.copias) > 0)} onClick={enviar}>Enviar pedido</button>
        {noPrazo && !pdf && !form.arquivo_url.trim() && <small className="mudo">Anexe o PDF (ou o link do arquivo) para enviar.</small>}
        {!noPrazo && <small className="erro-txt">Para essa data o prazo já passou (até {dataBR(prazo)}). Escolha a partir de {dataBR(d.primeiro_uso_possivel)}.</small>}
      </div>
      <h3>Meus pedidos {abertos.length ? <small className="mudo">({abertos.length} em andamento)</small> : null}</h3>
      {!d.pedidos.length && <p className="mudo">Nenhum pedido ainda.</p>}
      <div className="imp-lista">
        {d.pedidos.map((p: any) => <CartaoPedido key={p.id} p={p} urlPdf={`/api/portal/impressoes/${p.id}/pdf`}>
          {p.status === "pendente" && <div className="acoes-linha"><button className="btn-link" onClick={() => cancelar(p)}>Cancelar pedido</button></div>}
        </CartaoPedido>)}
      </div>
    </div>
  );
}

/** Coordenação: pedidos de impressão dos instrutores, com o retorno (em produção, pronta, entregue ou recusada). */
export default function Impressoes() {
  const { aviso } = useApp();
  const [filtro, setFiltro] = useState("abertos");
  const r = useCarregar<any[]>(() => api.get(`/api/impressoes${qs({ status: ["abertos", ""].includes(filtro) ? undefined : filtro })}`), [filtro]);
  const [resp, setResp] = useState<Record<number, string>>({});
  const lista = useMemo(() => (r.dados || []).filter((p) => filtro !== "abertos" || ["pendente", "em_producao", "pronta"].includes(p.status)), [r.dados, filtro]);
  const n = (st: string) => (r.dados || []).filter((p) => p.status === st).length;
  const atender = async (p: any, status: string) => {
    const resposta = resp[p.id];
    if (status === "recusada" && !(resposta || "").trim()) { aviso("Escreva o motivo da recusa no campo de retorno.", "erro"); return; }
    try {
      await api.put(`/api/impressoes/${p.id}`, { status, resposta });
      aviso(`Pedido "${p.titulo}": ${({ em_producao: "em produção", pronta: "pronto para retirar", entregue: "entregue", recusada: "recusado" } as Record<string, string>)[status]}. O instrutor foi avisado no portal.`);
      setResp((x) => ({ ...x, [p.id]: "" })); r.recarregar();
    } catch (e: any) { aviso(e.message, "erro"); }
  };
  return (
    <Pagina titulo="Pedidos de impressão" descricao="Os instrutores pedem pelo portal até a quinta-feira da semana anterior ao uso. Dê o retorno: em produção, pronta para retirar (o instrutor é avisado), entregue — ou recuse com o motivo.">
      <div className="lst-barra">
        {[["abertos", "Em aberto"], ["pendente", `Aguardando (${n("pendente")})`], ["em_producao", "Em produção"], ["pronta", "Prontas"],
          ["entregue", "Entregues"], ["recusada", "Recusadas"], ["", "Todos"]].map(([v, rot]) =>
          <button key={v} className={`chip-filtro ${filtro === v ? "on" : ""}`} onClick={() => setFiltro(v)}>{rot}</button>)}
      </div>
      {r.carregando && !r.dados && <p role="status">Carregando…</p>}
      {r.erro && <div className="erro-box">{r.erro}</div>}
      {r.dados && !lista.length && <div className="cur-vazio">Nenhum pedido aqui.</div>}
      <div className="imp-lista">
        {lista.map((p) => <CartaoPedido key={p.id} p={p} mostrarInstrutor urlPdf={`/api/impressoes/${p.id}/pdf`}>
          {p.proximos.length > 0 && <div className="imp-atender">
            <input placeholder="Retorno ao instrutor (ex.: pronto na sala da coordenação)" value={resp[p.id] || ""} onChange={(e) => setResp({ ...resp, [p.id]: e.target.value })} />
            {p.proximos.map((st: string) => <button key={st} className={`btn btn-pequeno ${st === "pronta" ? "btn-primario" : ""}`} onClick={() => atender(p, st)}>{ACAO[st]}</button>)}
          </div>}
        </CartaoPedido>)}
      </div>
    </Pagina>
  );
}
