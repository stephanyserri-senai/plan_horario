import { useState } from "react";
import { api, qs } from "../api";
import { useApp } from "../contexto";
import { Badge, useCarregar } from "./ui";

const STATUS: Record<string, [string, string]> = { nova: ["info", "Nova"], lida: ["alerta", "Lida"], resolvida: ["ok", "Resolvida"] };

/** Observações e sugestões enviadas pelos instrutores no portal, para a coordenação ler e responder. */
export default function ObservacoesInstrutores() {
  const { pode } = useApp();
  const [status, setStatus] = useState("nova");
  const r = useCarregar<any[]>(() => api.get(`/api/observacoes-instrutores${qs({ status })}`), [status]);
  if (!pode("observacoes.gerenciar")) return <p className="sub">Seu perfil não tem acesso às observações dos instrutores.</p>;
  return (
    <div>
      <div className="filtros">
        <select aria-label="Situação" value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="nova">Novas</option><option value="lida">Lidas</option><option value="resolvida">Resolvidas</option><option value="">Todas</option></select>
        <span className="sub">Enviadas pelos instrutores no portal, sobre as turmas e UCs atribuídas a eles.</span>
      </div>
      {r.erro && <div className="erro-box">{r.erro}</div>}
      {r.dados && !r.dados.length && <p className="ok-txt">Nenhuma observação {status ? STATUS[status][1].toLowerCase() : ""} no momento.</p>}
      <div className="portal-obs">{(r.dados || []).map((o) => <Item key={o.id} o={o} mudou={r.recarregar} />)}</div>
    </div>
  );
}

function Item({ o, mudou }: { o: any; mudou: () => void }) {
  const { aviso } = useApp();
  const [resposta, setResposta] = useState(o.resposta || "");
  const salvar = async (corpo: any, msg: string) => {
    try { await api.put(`/api/observacoes-instrutores/${o.id}`, corpo); aviso(msg); mudou(); } catch (e: any) { aviso(e.message, "erro"); }
  };
  return (
    <article className={`portal-cartao obs-${o.status}`}>
      <div className="portal-cartao-cab">
        <div><b>{o.instrutor}</b> <small className="mudo">· {o.turma || "geral"}{o.uc ? ` · ${o.uc}` : ""}</small></div>
        <Badge tipo={STATUS[o.status][0]}>{STATUS[o.status][1]}</Badge>
      </div>
      <small className="mudo">{o.tipo_rotulo} · {new Date(o.criado_em).toLocaleString("pt-BR")}</small>
      <p>{o.texto}</p>
      {o.resposta && o.status !== "nova" && <div className="portal-resposta"><b>Resposta{o.respondido_por ? ` de ${o.respondido_por}` : ""}:</b> {o.resposta}</div>}
      <textarea rows={2} placeholder="Resposta para o instrutor (ele vê no portal)" value={resposta} onChange={(e) => setResposta(e.target.value)} />
      <div className="acoes">
        {o.status === "nova" && <button className="btn" onClick={() => salvar({ status: "lida" }, "Marcada como lida.")}>Marcar como lida</button>}
        <button className="btn" disabled={!resposta.trim() || resposta === (o.resposta || "")} onClick={() => salvar({ resposta }, "Resposta enviada.")}>Responder</button>
        {o.status !== "resolvida" ? <button className="btn btn-primario" onClick={() => salvar({ status: "resolvida", ...(resposta.trim() && resposta !== (o.resposta || "") ? { resposta } : {}) }, "Observação resolvida.")}>Resolver</button>
          : <button className="btn-link" onClick={() => salvar({ status: "lida" }, "Reaberta.")}>Reabrir</button>}
      </div>
    </article>
  );
}
