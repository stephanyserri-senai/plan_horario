import { useState } from "react";
import { api, dataBR } from "../api";
import { Sugestao } from "../components/Sugestao";
import { Badge, Campo, Erro, Modal, Pagina, Tabela, useCarregar } from "../components/ui";
import { useApp } from "../contexto";

const ST: Record<string, string> = { pendente: "alerta", aprovada: "ok", recusada: "bloqueio", cancelada: "info" };
const GRUPO: Record<string, string> = { recomendado: "livre, da área e com a UC", excecao: "livre (outra área ou sem a UC: exceção justificada)",
  parcial: "livre só em parte das aulas", indisponivel: "indisponível" };

/** Coordenação: pedidos de folga e de substituição enviados pelos instrutores no portal. */
export default function Solicitacoes() {
  const [status, setStatus] = useState("pendente");
  const [sel, setSel] = useState<number | null>(null);
  const lista = useCarregar<any[]>(() => api.get(`/api/solicitacoes-instrutores${status ? `?status=${status}` : ""}`), [status]);
  return (
    <Pagina titulo="Solicitações dos instrutores" descricao="Folgas e substituições pedidas pelo portal. Aprove (com o substituto escolhido ou sugerido) ou recuse com uma resposta.">
      <div className="filtros"><label>Situação <select value={status} onChange={(e) => setStatus(e.target.value)}>
        <option value="pendente">Aguardando decisão</option><option value="aprovada">Aprovadas</option><option value="recusada">Recusadas</option>
        <option value="cancelada">Canceladas</option><option value="">Todas</option></select></label></div>
      {lista.erro && <div className="erro-box">{lista.erro}</div>}
      <Tabela colunas={[
        { chave: "instrutor", rotulo: "Instrutor", render: (x: any) => <b>{x.instrutor}</b> },
        { chave: "tipo_rotulo", rotulo: "Pedido" },
        { chave: "periodo", rotulo: "Quando", render: (x: any) => <>{dataBR(x.data_inicio)}{x.data_fim !== x.data_inicio ? ` a ${dataBR(x.data_fim)}` : ""}<br /><small className="mudo">{x.turnos.join(", ")}</small></> },
        { chave: "justificativa", rotulo: "Justificativa", render: (x: any) => <small>{x.justificativa}</small> },
        { chave: "status", rotulo: "Situação", render: (x: any) => <Badge tipo={ST[x.status] || "info"}>{x.status_rotulo}</Badge> },
      ]} linhas={lista.dados || []} chave={(x: any) => x.id} vazio="Nenhuma solicitação nesta situação." aoClicar={(x: any) => setSel(x.id)} />
      {sel && <Modal titulo="Solicitação do instrutor" aberto={!!sel} fechar={() => setSel(null)} largo>
        <Detalhe id={sel} fechar={(mudou) => { setSel(null); if (mudou) lista.recarregar(); }} />
      </Modal>}
    </Pagina>
  );
}

function Detalhe({ id, fechar }: { id: number; fechar: (mudou: boolean) => void }) {
  const { aviso } = useApp();
  const d = useCarregar<any>(() => api.get(`/api/solicitacoes-instrutores/${id}`), [id]);
  const [resposta, setResposta] = useState("");
  const [sub, setSub] = useState("");
  const [erro, setErro] = useState<any>(null);
  const [rodando, setRodando] = useState(false);
  const s = d.dados;
  if (!s) return d.erro ? <div className="erro-box">{d.erro}</div> : <p role="status">Carregando…</p>;
  const decidir = async (corpo: any) => {
    setErro(null); setRodando(true);
    try {
      const r = await api.put(`/api/solicitacoes-instrutores/${id}`, { resposta, ...corpo });
      aviso(r.status === "aprovada" ? `Aprovada${r.efeitos?.substituidas ? `: ${r.efeitos.substituidas} aula(s) com ${r.efeitos.substituto}` : ""}.` : "Pedido recusado.");
      fechar(true); return r;
    } catch (e) { setErro(e); throw e; } finally { setRodando(false); }
  };
  const pendente = s.status === "pendente";
  return (
    <div className="explicacao">
      <p><b>{s.instrutor}</b> pede <b>{s.tipo_rotulo.toLowerCase()}</b> de {dataBR(s.data_inicio)}{s.data_fim !== s.data_inicio ? ` a ${dataBR(s.data_fim)}` : ""} ({s.turnos.join(", ")}).</p>
      <blockquote>{s.justificativa}</blockquote>
      <p>{s.aulas_afetadas ? <>Aulas no período: <b>{s.aulas_afetadas}</b> — {s.resumo_aulas}</> : "Não há aulas dele(a) neste período."}
        {s.tipo === "folga" && " Aprovada, a folga vira bloqueio na agenda do instrutor."}</p>
      {!pendente && <p><Badge tipo={ST[s.status]}>{s.status_rotulo}</Badge> {s.resposta}</p>}
      {pendente && <>
        <Campo rotulo="Resposta ao instrutor" ajuda="Obrigatória para recusar; aparece no portal do instrutor.">
          <textarea rows={2} value={resposta} onChange={(e) => setResposta(e.target.value)} placeholder="Ex.: aprovado; Fulano assume as aulas." /></Campo>
        {s.sugestao && <Sugestao texto={<>aprovar e passar as {s.aulas_afetadas} aula(s) para <b>{s.sugestao.nome}</b></>} detalhe={s.sugestao.motivo}
          rotulo="Aceitar sugestão e aprovar" aplicar={() => decidir({ aprovar: true, aceitar_sugestao: true })} />}
        {s.aulas_afetadas > 0 && !s.sugestao && <p className="aviso-inline">Nenhum instrutor livre em todas as aulas: escolha alguém abaixo ou aprove sem substituto.</p>}
        {s.aulas_afetadas > 0 && <Campo rotulo="Ou escolha o substituto">
          <select value={sub} onChange={(e) => setSub(e.target.value)}><option value="">—</option>
            {(s.candidatos || []).filter((c: any) => c.grupo !== "indisponivel").map((c: any) => <option key={c.id} value={c.id}>{c.nome} — {GRUPO[c.grupo]}{c.na_escola ? " · na escola (PL/PJ)" : ""}</option>)}</select></Campo>}
        <Erro erro={erro} />
        <div className="acoes">
          <button className="btn" disabled={rodando} onClick={() => decidir({ aprovar: false }).catch(() => null)}>Recusar</button>
          {s.aulas_afetadas > 0 && <button className="btn" disabled={rodando} onClick={() => decidir({ aprovar: true }).catch(() => null)}>Aprovar sem substituto</button>}
          <button className="btn btn-primario" disabled={rodando || (s.aulas_afetadas > 0 && !sub)} onClick={() => decidir({ aprovar: true, substituto_id: sub ? Number(sub) : null }).catch(() => null)}>
            {s.aulas_afetadas > 0 ? "Aprovar com o escolhido" : "Aprovar"}</button>
        </div>
      </>}
    </div>
  );
}
