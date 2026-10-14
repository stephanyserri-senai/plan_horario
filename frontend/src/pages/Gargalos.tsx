import { useState } from "react";
import { api, qs } from "../api";
import { Badge, Campo, Card, Kpi, Modal, Pagina, Tabela, useCarregar } from "../components/ui";
import { useApp } from "../contexto";
import { useOpcoes } from "../hooks";
import { Recomendacao } from "./Planejamento";

const TIPOS: Record<string, string> = {
  deficit_capacidade_total: "Déficit de capacidade total", deficit_turno: "Déficit no turno", deficit_habilitacao: "Déficit de habilitação profissional",
  conflito_distribuicao: "Conflito de distribuição de horários", indisponibilidade_equipamentos: "Indisponibilidade de equipamentos",
  inviabilidade_calendario: "Inviabilidade pedagógica ou de calendário",
};

export default function Gargalos() {
  const { cenario } = useApp();
  const [inicio, setInicio] = useState("");
  const [fim, setFim] = useState("");
  const [rec, setRec] = useState<any | null>(null);
  const [q, setQ] = useState<any>({});
  const ambientes = useOpcoes("ambientes");
  const g = useCarregar<any>(() => cenario ? api.get(`/api/gargalos${qs({ cenario_id: cenario.id, inicio, fim })}`) : Promise.resolve(null), [cenario?.id, inicio, fim]);
  if (!cenario) return <Pagina titulo="Capacidade e gargalos"><p>Selecione um cenário.</p></Pagina>;
  const perguntar = async (url: string) => setRec(await api.get(url));
  return (
    <Pagina titulo="Capacidade e gargalos" descricao="Fluxo máximo entre demanda e recursos compatíveis: ambientes, instrutores e equipamentos não intercambiáveis nunca são somados."
      acoes={<div className="filtros"><label>Início <input type="date" value={inicio} onChange={(e) => setInicio(e.target.value)} /></label><label>Fim <input type="date" value={fim} onChange={(e) => setFim(e.target.value)} /></label></div>}>
      {g.carregando && <p role="status">Analisando…</p>}
      {g.erro && <div className="erro-box">{g.erro}</div>}
      {g.dados && <>
        <div className="kpis">
          <Kpi rotulo="Demanda semanal analisada" valor={`${g.dados.demanda_total_h} h`} detalhe={`${g.dados.demandas_consideradas} demanda(s)`} />
          {Object.entries(TIPOS).map(([k, r]) => <Kpi key={k} rotulo={r} valor={g.dados.resumo[k]?.quantidade || 0} detalhe={g.dados.resumo[k] ? `${g.dados.resumo[k].deficit_h} h de déficit` : "sem ocorrência"} tom={g.dados.resumo[k] ? "alerta" : "ok"} />)}
        </div>
        <p className="sub">{g.dados.observacao}</p>
        {g.dados.gargalos.map((x: any, i: number) => (
          <Card key={i} titulo={<><Badge tipo="alerta">{TIPOS[x.tipo]}</Badge> {x.recurso}{x.turno ? ` · ${x.turno}` : ""}</>}>
            <p>{x.descricao}</p>
            <p className="sub"><b>Como foi calculado:</b> {x.calculo}</p>
            {x.alternativas?.length > 0 && <><b>Alternativas:</b><ul>{x.alternativas.map((a: string, k: number) => <li key={k}>{a}</li>)}</ul></>}
            {x.itens && <details><summary>Demandas envolvidas ({x.itens.length})</summary><Tabela colunas={Object.keys(x.itens[0] || {}).map((c) => ({ chave: c, rotulo: c }))} linhas={x.itens} chave={(_l, k) => k} /></details>}
          </Card>
        ))}
        {g.dados.gargalos.length === 0 && <Card><p><Badge tipo="ok">Sem gargalos agregados</Badge> A demanda cabe nos recursos compatíveis. A confirmação final depende do gerador de horários.</p></Card>}
      </>}
      <Card titulo="Perguntas de planejamento">
        <p className="sub">Respostas calculadas a partir dos cadastros e da grade atual. Nada é alterado: são análises para apoiar a decisão.</p>
        <div className="perguntas">
          <div className="pergunta">
            <h3>Onde falta sala, laboratório ou instrutor?</h3>
            <p>Mostra cada ponto em que a demanda das turmas passa da capacidade disponível e indica salas compatíveis que estão com horário sobrando.</p>
            <button className="btn btn-primario" onClick={() => perguntar(`/api/recomendacoes/liberar_capacidade?cenario_id=${cenario.id}`)}>Ver onde falta capacidade</button>
          </div>
          <div className="pergunta">
            <h3>Quais disciplinas podem não terminar no prazo?</h3>
            <p>Compara, para cada turma, a carga horária que ainda falta com os dias letivos que restam até o prazo da unidade curricular.</p>
            <button className="btn btn-primario" onClick={() => perguntar(`/api/recomendacoes/ucs_risco?cenario_id=${cenario.id}`)}>Ver disciplinas em risco</button>
          </div>
          <div className="pergunta">
            <h3>E se uma sala ou laboratório ficasse disponível por mais horas?</h3>
            <p>Simula quanto da falta de capacidade seria resolvida ampliando o horário de uso de um ambiente (ex.: abrir o laboratório também à noite).</p>
            <div className="linha">
              <select aria-label="Sala ou laboratório" value={q.amb || ""} onChange={(e) => setQ({ ...q, amb: e.target.value })}><option value="">Escolha a sala ou laboratório</option>{ambientes.map((t) => <option key={t.id} value={t.id}>{t.rotulo}</option>)}</select>
              <input type="number" min={1} aria-label="Horas a mais por semana" placeholder="horas a mais/semana" style={{ width: 170 }} value={q.horas || ""} onChange={(e) => setQ({ ...q, horas: e.target.value })} />
              <button className="btn" disabled={!q.amb || !q.horas} onClick={() => perguntar(`/api/recomendacoes/ampliar_ambiente${qs({ cenario_id: cenario.id, ambiente_id: q.amb, horas: q.horas })}`)}>Simular</button>
            </div>
          </div>
        </div>
      </Card>
      <Modal titulo="Recomendação" aberto={!!rec} fechar={() => setRec(null)} largo>{rec && <Recomendacao r={rec} />}</Modal>
    </Pagina>
  );
}
