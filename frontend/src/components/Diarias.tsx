import { useMemo, useState } from "react";
import { api, dataBR, qs } from "../api";
import { useApp } from "../contexto";
import { Badge, Campo, Pagina, useCarregar } from "./ui";

const TOM: Record<string, string> = { solicitada: "alerta", aprovada: "info", paga: "ok", recusada: "erro", cancelada: "neutro" };
const ICONE: Record<string, string> = { solicitada: "⏳", aprovada: "✅", paga: "💰", recusada: "✖", cancelada: "—" };
const ACAO: Record<string, string> = { aprovada: "Aprovar", paga: "Marcar como paga", recusada: "Recusar", cancelada: "Cancelar" };
const brl = (v: number | null | undefined) => (v == null ? "—" : v.toLocaleString("pt-BR", { style: "currency", currency: "BRL" }));
const num = (v: number) => v.toLocaleString("pt-BR", { maximumFractionDigits: 1 });
const VAZIO = { instrutor_id: "", motivo: "evento", titulo: "", destino: "", data_inicio: "", data_fim: "", quantidade: "", valor_unitario: "",
  outros_recursos: "", centro_custo: "", descricao: "" };
const dias = (a: string, b: string) => (a && b && b >= a ? Math.round((Date.parse(`${b}T12:00:00`) - Date.parse(`${a}T12:00:00`)) / 864e5) + 1 : 0);

/** Supervisão: diárias (recursos extras) para instrutores em eventos e projetos. */
export default function Diarias() {
  const { aviso } = useApp();
  const [filtro, setFiltro] = useState("abertas");
  const r = useCarregar<any>(() => api.get(`/api/diarias${qs({ status: ["abertas", ""].includes(filtro) ? undefined : filtro })}`), [filtro]);
  const [f, setF] = useState<any>(VAZIO);
  const [editando, setEditando] = useState<number | null>(null);
  const [aberto, setAberto] = useState(false);
  const [resp, setResp] = useState<Record<number, string>>({});
  const itens = useMemo(() => (r.dados?.itens || []).filter((d: any) => filtro !== "abertas" || ["solicitada", "aprovada"].includes(d.status)), [r.dados, filtro]);
  const tot = r.dados?.totais || {};
  const nDias = dias(f.data_inicio, f.data_fim || f.data_inicio);
  const qtd = Number(String(f.quantidade).replace(",", ".")) || 0;
  const vu = Number(String(f.valor_unitario).replace(",", ".")) || 0;
  const mudar = (k: string, v: any) => setF((x: any) => {
    const n = { ...x, [k]: v };
    // número de diárias sugerido pelo período (pode ajustar para meia diária)
    if ((k === "data_inicio" || k === "data_fim") && (!x.quantidade || Number(x.quantidade) === dias(x.data_inicio, x.data_fim || x.data_inicio))) {
      const d = dias(n.data_inicio, n.data_fim || n.data_inicio);
      if (d) n.quantidade = String(d);
    }
    return n;
  });
  const salvar = async () => {
    try {
      const corpo = { ...f, data_fim: f.data_fim || f.data_inicio };
      if (editando) await api.put(`/api/diarias/${editando}`, corpo); else await api.post("/api/diarias", corpo);
      aviso(editando ? "Solicitação alterada." : "Diárias solicitadas. O instrutor foi avisado no portal.");
      setF(VAZIO); setEditando(null); setAberto(false); r.recarregar();
    } catch (e: any) { aviso(e.message, "erro"); }
  };
  const editar = (d: any) => {
    setF({ instrutor_id: String(d.instrutor_id), motivo: d.motivo, titulo: d.titulo, destino: d.destino || "", data_inicio: d.data_inicio, data_fim: d.data_fim,
      quantidade: String(d.quantidade), valor_unitario: d.valor_unitario ?? "", outros_recursos: d.outros_recursos || "", centro_custo: d.centro_custo || "",
      descricao: d.descricao || "" });
    setEditando(d.id); setAberto(true); window.scrollTo({ top: 0, behavior: "smooth" });
  };
  const decidir = async (d: any, status: string) => {
    const resposta = resp[d.id];
    if (["recusada", "cancelada"].includes(status) && !(resposta || "").trim()) { aviso("Escreva o motivo no campo de retorno.", "erro"); return; }
    try {
      await api.post(`/api/diarias/${d.id}/situacao`, { status, resposta });
      aviso(`"${d.titulo}": ${({ aprovada: "aprovada", paga: "paga", recusada: "recusada", cancelada: "cancelada" } as Record<string, string>)[status]}. O instrutor foi avisado.`);
      setResp((x) => ({ ...x, [d.id]: "" })); r.recarregar();
    } catch (e: any) { aviso(e.message, "erro"); }
  };
  return (
    <Pagina titulo="Diárias" descricao="Recursos extras para instrutores em eventos e projetos: registre a solicitação, aprove ou recuse (com o motivo) e marque como paga. O instrutor acompanha pelo portal.">
      <div className="dia-resumo">
        {["solicitada", "aprovada", "paga"].map((k) => tot[k] && <div key={k} className={`dia-tot st-${k}`}>
          <small>{tot[k].rotulo}s</small><b>{tot[k].qtd}</b><span>{num(tot[k].diarias)} diária(s) · {brl(tot[k].valor)}</span></div>)}
        {!aberto && <button className="btn btn-primario" onClick={() => { setF(VAZIO); setEditando(null); setAberto(true); }}>+ Nova solicitação</button>}
      </div>
      {aberto && <div className="cartao dia-form-card">
        <h3>{editando ? "Alterar solicitação" : "Nova solicitação de diárias"}</h3>
        <div className="imp-form">
          <Campo rotulo="Instrutor" obrigatorio><select value={f.instrutor_id} onChange={(e) => mudar("instrutor_id", e.target.value)}>
            <option value="">Escolha…</option>{(r.dados?.instrutores || []).map((i: any) => <option key={i.id} value={i.id}>{i.nome}{i.matricula ? ` (${i.matricula})` : ""}</option>)}</select></Campo>
          <Campo rotulo="Motivo" obrigatorio><select value={f.motivo} onChange={(e) => mudar("motivo", e.target.value)}>
            {(r.dados?.motivos || [{ valor: "evento", rotulo: "Evento" }]).map((m: any) => <option key={m.valor} value={m.valor}>{m.rotulo}</option>)}</select></Campo>
          <Campo rotulo="Evento ou projeto" obrigatorio><input value={f.titulo} onChange={(e) => mudar("titulo", e.target.value)} placeholder="ex.: Feira de robótica, Projeto Indústria 4.0" /></Campo>
          <Campo rotulo="Local / destino"><input value={f.destino} onChange={(e) => mudar("destino", e.target.value)} placeholder="cidade, empresa, escola…" /></Campo>
          <Campo rotulo="Início" obrigatorio><input type="date" value={f.data_inicio} onChange={(e) => mudar("data_inicio", e.target.value)} /></Campo>
          <Campo rotulo="Fim"><input type="date" value={f.data_fim} min={f.data_inicio} onChange={(e) => mudar("data_fim", e.target.value)} /></Campo>
          <Campo rotulo="Nº de diárias" obrigatorio ajuda={nDias ? `${nDias} dia(s) no período; aceita meia diária (ex.: 1,5)` : "aceita meia diária (ex.: 1,5)"}>
            <input inputMode="decimal" value={f.quantidade} onChange={(e) => mudar("quantidade", e.target.value)} /></Campo>
          <Campo rotulo="Valor da diária (R$)" ajuda={qtd && vu ? `Total: ${brl(qtd * vu)}` : undefined}>
            <input inputMode="decimal" value={f.valor_unitario} onChange={(e) => mudar("valor_unitario", e.target.value)} placeholder="0,00" /></Campo>
          <Campo rotulo="Centro de custo"><input value={f.centro_custo} onChange={(e) => mudar("centro_custo", e.target.value)} /></Campo>
          <Campo rotulo="Outros recursos"><input value={f.outros_recursos} onChange={(e) => mudar("outros_recursos", e.target.value)} placeholder="transporte, hospedagem, material…" /></Campo>
        </div>
        <Campo rotulo="Justificativa / atividades"><textarea rows={2} value={f.descricao} onChange={(e) => mudar("descricao", e.target.value)} /></Campo>
        <div className="acoes-linha">
          <button className="btn btn-primario" onClick={salvar}>{editando ? "Salvar alteração" : "Solicitar diárias"}</button>
          <button className="btn" onClick={() => { setAberto(false); setEditando(null); setF(VAZIO); }}>Cancelar</button>
        </div>
      </div>}
      <div className="lst-barra">
        {[["abertas", "Em aberto"], ["solicitada", "Solicitadas"], ["aprovada", "Aprovadas"], ["paga", "Pagas"], ["recusada", "Recusadas"], ["cancelada", "Canceladas"], ["", "Todas"]].map(([v, rot]) =>
          <button key={v} className={`chip-filtro ${filtro === v ? "on" : ""}`} onClick={() => setFiltro(v)}>{rot}</button>)}
      </div>
      {r.carregando && !r.dados && <p role="status">Carregando…</p>}
      {r.erro && <div className="erro-box">{r.erro}</div>}
      {r.dados && !itens.length && <div className="cur-vazio">Nenhuma solicitação aqui.</div>}
      <div className="imp-lista">
        {itens.map((d: any) => <div key={d.id} className={`imp-card dia-card st-${d.status}`}>
          <div className="imp-card-cab">
            <span className="imp-ico" aria-hidden="true">{ICONE[d.status]}</span>
            <div className="imp-card-tit"><b>{d.titulo}</b>
              <small className="mudo">{d.instrutor} · {d.motivo_rotulo}{d.destino ? ` · ${d.destino}` : ""}</small></div>
            <Badge tipo={TOM[d.status] || "info"}>{d.status_rotulo}</Badge>
          </div>
          <div className="imp-card-det">
            <span>📅 {dataBR(d.data_inicio)}{d.data_fim !== d.data_inicio ? ` a ${dataBR(d.data_fim)}` : ""}</span>
            <span><b>{num(d.quantidade)}</b> diária(s){d.valor_unitario != null ? ` × ${brl(d.valor_unitario)} = ` : ""}{d.valor_total != null && <b>{brl(d.valor_total)}</b>}</span>
            {d.centro_custo && <span className="mudo">CC {d.centro_custo}</span>}
            {d.pago_em && <span>💰 pago em {dataBR(d.pago_em)}</span>}
          </div>
          {d.outros_recursos && <p className="imp-desc">🧳 {d.outros_recursos}</p>}
          {d.descricao && <p className="imp-desc">{d.descricao}</p>}
          {d.aulas_no_periodo > 0 && ["solicitada", "aprovada"].includes(d.status) &&
            <p className="dia-alerta">⚠️ {d.aulas_no_periodo} aula(s) no período — providencie a substituição (menu Substituições).</p>}
          {d.resposta && <p className="imp-resp">💬 <b>Supervisão:</b> {d.resposta}</p>}
          {d.proximos.length > 0 && <div className="imp-atender">
            <input placeholder="Retorno ao instrutor (obrigatório para recusar ou cancelar)" value={resp[d.id] || ""} onChange={(e) => setResp({ ...resp, [d.id]: e.target.value })} />
            {d.status === "solicitada" && <button className="btn btn-pequeno" onClick={() => editar(d)}>Alterar</button>}
            {d.proximos.map((st: string) => <button key={st} className={`btn btn-pequeno ${["aprovada", "paga"].includes(st) ? "btn-primario" : ""}`} onClick={() => decidir(d, st)}>{ACAO[st]}</button>)}
          </div>}
        </div>)}
      </div>
    </Pagina>
  );
}
