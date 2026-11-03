import { useMemo, useState } from "react";
import { api, dataBR, qs } from "../api";
import { useApp } from "../contexto";
import { useOpcoes } from "../hooks";
import { Badge, Campo, Erro, Modal, Pagina, useCarregar } from "./ui";

const DIAS = ["Dom", "Seg", "Ter", "Qua", "Qui", "Sex", "Sáb"];
const iso = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
const somaDias = (s: string, n: number) => { const d = new Date(`${s}T12:00:00`); d.setDate(d.getDate() + n); return iso(d); };
const segunda = (s: string) => { const d = new Date(`${s}T12:00:00`); return somaDias(s, -((d.getDay() + 6) % 7)); };
const ROT: Record<string, string> = { livre: "livre", aula: "aula", reservado: "reservado", pendente: "aguardando", bloqueado: "bloqueado",
  feriado: "feriado", indisponivel: "indisponível" };
const TOM: Record<string, string> = { pendente: "alerta", confirmado: "ok", recusado: "erro", cancelado: "neutro" };
// turnos sempre M, V ou N (no sábado: M 09–13 e V 14–18)
const sigla = (t: any) => ({ M: "M", V: "V", T: "V", N: "N", S: "M", SV: "V" } as Record<string, string>)[String(t.codigo || "").toUpperCase()]
  || ((t.inicio || "") < "12:00" ? "M" : (t.inicio || "") < "18:00" ? "V" : "N");

/** Agendamento de ambientes (substitui a planilha de ambientes × datas × turnos): grade semanal com o que está livre,
 * com aula, reservado, aguardando a supervisão ou bloqueado. Portal: o instrutor clica num horário livre e pede.
 * Supervisão: vê tudo, confirma ou recusa os pedidos e agenda direto. */
export function AgendaAmbientes({ portal }: { portal?: boolean }) {
  const { aviso, pode } = useApp();
  const supervisao = !portal && pode("solicitacoes.aprovar");
  const hoje = iso(new Date());
  const [ini, setIni] = useState(segunda(hoje));
  const [unidade, setUnidade] = useState<string>("");
  const [tipo, setTipo] = useState("");
  const [q, setQ] = useState("");
  const [soLivres, setSoLivres] = useState(false);
  const [pedido, setPedido] = useState<any>(null);
  const [versao, setVersao] = useState(0);
  const base = portal ? "/api/portal/ambientes/agenda" : "/api/ambientes/agenda";
  const r = useCarregar<any>(() => api.get(`${base}${qs({ unidade_id: unidade || undefined, inicio: ini, fim: somaDias(ini, 5), tipo_ambiente_id: tipo || undefined, q: q || undefined })}`),
    [ini, unidade, tipo, q, versao, base]);
  const lista = useCarregar<any[]>(() => api.get(portal ? "/api/portal/agendamentos" : "/api/agendamentos"), [versao, portal]);
  const d = r.dados;
  const colunas = useMemo(() => (d ? d.dias.flatMap((dia: string) => d.turnos.filter((t: any) => t.sabado === (new Date(`${dia}T12:00:00`).getDay() === 6))
    .map((t: any) => ({ dia, t }))) : []), [d]);
  const ambientes = (d?.ambientes || []).filter((a: any) => !soLivres || colunas.some(({ dia, t }: any) => a.celulas[`${dia}|${t.id}`]?.estado === "livre" && dia >= hoje));
  const mudou = () => setVersao((v) => v + 1);
  const decidir = async (g: any, status: string) => {
    let resposta: string | null = null;
    if (status === "recusado") { resposta = prompt(`Motivo da recusa de ${g.ambiente} em ${dataBR(g.data)}:`); if (!resposta) return; }
    try { await api.put(`/api/agendamentos/${g.id}`, { status, resposta }); aviso(status === "confirmado" ? "Agendamento confirmado: o instrutor foi avisado." : "Pedido recusado."); mudou(); }
    catch (e: any) { aviso(e.message, "erro"); }
  };
  const cancelar = async (g: any) => {
    if (!confirm(`Cancelar o agendamento de ${g.ambiente} em ${dataBR(g.data)} (${g.turno})?`)) return;
    try { await api.post(portal ? `/api/portal/agendamentos/${g.id}/cancelar` : `/api/agendamentos/${g.id}/cancelar`, {}); aviso("Agendamento cancelado."); mudou(); }
    catch (e: any) { aviso(e.message, "erro"); }
  };
  const pendentes = (lista.dados || []).filter((g) => g.status === "pendente");
  return (
    <div className="ag">
      <div className="ag-barra">
        <div className="ag-semana">
          <button className="btn btn-pequeno" onClick={() => setIni(somaDias(ini, -7))} aria-label="Semana anterior">‹</button>
          <b>{dataBR(ini).slice(0, 5)} a {dataBR(somaDias(ini, 5)).slice(0, 5)}</b>
          <button className="btn btn-pequeno" onClick={() => setIni(somaDias(ini, 7))} aria-label="Próxima semana">›</button>
          {ini !== segunda(hoje) && <button className="btn-link" onClick={() => setIni(segunda(hoje))}>esta semana</button>}
          <input type="date" value={ini} onChange={(e) => e.target.value && setIni(segunda(e.target.value))} aria-label="Ir para a semana" />
        </div>
        {d && d.unidades.length > 1 && <select value={unidade || d.unidade.id} onChange={(e) => setUnidade(e.target.value)} aria-label="Unidade">
          {d.unidades.map((u: any) => <option key={u.id} value={u.id}>{u.nome}</option>)}</select>}
        {d && <select value={tipo} onChange={(e) => setTipo(e.target.value)} aria-label="Tipo de ambiente"><option value="">Todos os tipos</option>
          {d.tipos.map((t: any) => <option key={t.id} value={t.id}>{t.nome}</option>)}</select>}
        <input type="search" placeholder="🔎 Sala ou laboratório" value={q} onChange={(e) => setQ(e.target.value)} />
        <label className="ag-check"><input type="checkbox" checked={soLivres} onChange={(e) => setSoLivres(e.target.checked)} /> só com horário livre</label>
      </div>
      <div className="ag-legenda">{["livre", "aula", "pendente", "reservado", "bloqueado", "feriado"].map((e) => <span key={e} className={`ag-c e-${e}`}>{ROT[e]}</span>)}
        <small className="mudo">{portal ? "Clique num horário livre para pedir o ambiente. O pedido segura o horário até a supervisão confirmar." : "Clique num horário livre para agendar (já confirmado)."}</small></div>
      {r.carregando && !d && <p role="status">Carregando a disponibilidade…</p>}
      {r.erro && <div className="erro-box">{r.erro}</div>}
      {d && <div className="ag-tabela-wrap">
        <table className="ag-tabela">
          <thead>
            <tr><th rowSpan={2} className="ag-amb">Ambiente</th>
              {d.dias.map((dia: string) => { const n = colunas.filter((c: any) => c.dia === dia).length; const dt = new Date(`${dia}T12:00:00`);
                return n ? <th key={dia} colSpan={n} className={`ag-dia ${dia === hoje ? "hoje" : ""}`}>{DIAS[dt.getDay()]} {dataBR(dia).slice(0, 5)}</th> : null; })}</tr>
            <tr>{colunas.map(({ dia, t }: any) => <th key={`${dia}|${t.id}`} className="ag-turno" title={`${t.nome} ${t.inicio}–${t.fim}`}>{sigla(t)}</th>)}</tr>
          </thead>
          <tbody>
            {ambientes.map((a: any) => (
              <tr key={a.id}>
                <th className="ag-amb"><b>{a.codigo}</b><small className="mudo">{a.nome}{a.tipo ? ` · ${a.tipo}` : ""} · {a.capacidade} lugares</small></th>
                {colunas.map(({ dia, t }: any) => {
                  const c = a.celulas[`${dia}|${t.id}`] || { estado: "indisponivel" };
                  const livre = c.estado === "livre" && dia >= hoje;
                  return <td key={`${dia}|${t.id}`} className={`ag-c e-${c.estado} ${c.meu ? "meu" : ""} ${dia < hoje ? "passado" : ""}`}
                    title={`${a.codigo} · ${DIAS[new Date(`${dia}T12:00:00`).getDay()]} ${dataBR(dia)} · ${t.nome} ${t.inicio}–${t.fim}: ${ROT[c.estado]}${c.texto ? ` (${c.texto})` : ""}`}>
                    {livre ? <button onClick={() => setPedido({ ambiente: a, dia, turno: t })} aria-label={`Agendar ${a.codigo} ${dataBR(dia)} ${t.nome}`}>+</button>
                      : <span>{c.estado === "aula" ? c.texto : c.estado === "livre" ? "" : c.meu ? "meu" : (c.texto || "").slice(0, 10)}</span>}
                  </td>;
                })}
              </tr>))}
            {!ambientes.length && <tr><td colSpan={colunas.length + 1} className="mudo">Nenhum ambiente com esses filtros.</td></tr>}
          </tbody>
        </table>
      </div>}

      {supervisao && pendentes.length > 0 && <section className="ag-pendentes">
        <h3>⏳ Pedidos aguardando ({pendentes.length})</h3>
        {pendentes.map((g) => <div key={g.id} className="ag-pedido">
          <span><b>{g.ambiente}</b> · {DIAS[new Date(`${g.data}T12:00:00`).getDay()]} {dataBR(g.data)} · {g.turno} ({g.inicio}–{g.fim})
            <small className="mudo"> — {g.instrutor || "equipe"}: {g.finalidade}{g.turma ? ` · ${g.turma}` : ""}{g.participantes ? ` · ${g.participantes} pessoas` : ""}</small></span>
          <span className="acoes-linha"><button className="btn btn-pequeno btn-primario" onClick={() => decidir(g, "confirmado")}>Confirmar</button>
            <button className="btn btn-pequeno" onClick={() => decidir(g, "recusado")}>Recusar</button></span>
        </div>)}
      </section>}

      <section className="ag-lista">
        <h3>{portal ? "Meus agendamentos" : "Agendamentos (últimos 30 dias e próximos)"}</h3>
        {!(lista.dados || []).length && <p className="mudo">Nenhum agendamento.</p>}
        {(lista.dados || []).filter((g) => portal || g.status !== "pendente").map((g) => <div key={g.id} className={`ag-pedido st-${g.status}`}>
          <span><b>{g.ambiente}</b> · {DIAS[new Date(`${g.data}T12:00:00`).getDay()]} {dataBR(g.data)} · {g.turno} ({g.inicio}–{g.fim})
            <small className="mudo"> — {!portal && g.instrutor ? `${g.instrutor}: ` : ""}{g.finalidade}</small>
            {g.resposta && <small className="ag-resp">💬 {g.resposta}</small>}</span>
          <span className="acoes-linha"><Badge tipo={TOM[g.status] || "info"}>{g.status_rotulo}</Badge>
            {["pendente", "confirmado"].includes(g.status) && g.data >= hoje && (portal || supervisao) && <button className="btn-link" onClick={() => cancelar(g)}>Cancelar</button>}</span>
        </div>)}
      </section>
      {pedido && <PedidoAmbiente portal={portal} p={pedido} fechar={() => setPedido(null)} feito={() => { setPedido(null); mudou(); }} />}
    </div>
  );
}

function PedidoAmbiente({ portal, p, fechar, feito }: { portal?: boolean; p: any; fechar: () => void; feito: () => void }) {
  const { aviso } = useApp();
  const instrutores = useOpcoes(portal ? null : "instrutores");
  const minhas = useCarregar<any>(() => (portal ? api.get("/api/portal/impressoes") : Promise.resolve(null)), [portal]);
  const [f, setF] = useState<any>({ finalidade: "", turma_id: "", participantes: "", instrutor_id: "" });
  const [erro, setErro] = useState<any>(null);
  const enviar = async () => {
    setErro(null);
    const corpo = { ambiente_id: p.ambiente.id, data: p.dia, turno_id: p.turno.id, finalidade: f.finalidade, turma_id: f.turma_id || null,
      participantes: f.participantes || null, instrutor_id: f.instrutor_id || null };
    try {
      await api.post(portal ? "/api/portal/agendamentos" : "/api/agendamentos", corpo);
      aviso(portal ? "Pedido enviado: o horário fica reservado para você até a supervisão confirmar." : "Ambiente agendado.");
      feito();
    } catch (e) { setErro(e); }
  };
  const dt = new Date(`${p.dia}T12:00:00`);
  return (
    <Modal titulo={portal ? "Pedir ambiente" : "Agendar ambiente"} aberto fechar={fechar}>
      <div className="ag-resumo">🏫 <b>{p.ambiente.codigo}</b> {p.ambiente.nome} · {p.ambiente.capacidade} lugares<br />
        📅 {DIAS[dt.getDay()]} {dataBR(p.dia)} · {p.turno.nome} ({p.turno.inicio}–{p.turno.fim})</div>
      <Campo rotulo="Para quê" obrigatorio><input value={f.finalidade} placeholder="ex.: aula prática da turma HTC-ELT-12; reunião; avaliação"
        onChange={(e) => setF({ ...f, finalidade: e.target.value })} /></Campo>
      {portal && <Campo rotulo="Turma"><select value={f.turma_id} onChange={(e) => setF({ ...f, turma_id: e.target.value })}><option value="">—</option>
        {(minhas.dados?.turmas || []).map((t: any) => <option key={t.id} value={t.id}>{t.codigo}</option>)}</select></Campo>}
      {!portal && <Campo rotulo="Para o instrutor (opcional)"><select value={f.instrutor_id} onChange={(e) => setF({ ...f, instrutor_id: e.target.value })}>
        <option value="">— equipe —</option>{instrutores.map((i) => <option key={i.id} value={i.id}>{i.rotulo}</option>)}</select></Campo>}
      <Campo rotulo="Participantes"><input type="number" min={1} max={p.ambiente.capacidade} value={f.participantes} onChange={(e) => setF({ ...f, participantes: e.target.value })} /></Campo>
      <Erro erro={erro} />
      <div className="rodape-modal"><button className="btn" onClick={fechar}>Cancelar</button>
        <button className="btn btn-primario" disabled={f.finalidade.trim().length < 5} onClick={enviar}>{portal ? "Pedir" : "Agendar"}</button></div>
    </Modal>
  );
}

/** Página da equipe: agendamento de ambientes. */
export default function Agendamentos() {
  return (
    <Pagina titulo="Agendamento de ambientes" descricao="Disponibilidade das salas e laboratórios por dia e turno (aulas da grade publicada, bloqueios e reservas). Os instrutores pedem pelo portal; a supervisão confirma ou recusa — confirmado vira bloqueio do ambiente, respeitado pelo gerador e pela validação.">
      <AgendaAmbientes />
    </Pagina>
  );
}

