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
  const turmas = useOpcoes("turmas");
  const turnos = useOpcoes("turnos");
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
      <Card titulo="Perguntas de planejamento (recomendações explicáveis)">
        <div className="form-grid">
          <Campo rotulo="O que acontece se uma turma mudar de turno?"><div className="linha">
            <select aria-label="Turma" value={q.turma || ""} onChange={(e) => setQ({ ...q, turma: e.target.value })}><option value="">Turma</option>{turmas.map((t) => <option key={t.id} value={t.id}>{t.rotulo}</option>)}</select>
            <select aria-label="Novo turno" value={q.turno || ""} onChange={(e) => setQ({ ...q, turno: e.target.value })}><option value="">Novo turno</option>{turnos.map((t) => <option key={t.id} value={t.id}>{t.rotulo}</option>)}</select>
            <button className="btn" disabled={!q.turma || !q.turno} onClick={() => perguntar(`/api/recomendacoes/mudanca_turno${qs({ cenario_id: cenario.id, turma_id: q.turma, turno_id: q.turno })}`)}>Avaliar</button></div></Campo>
          <Campo rotulo="Impacto de ampliar a disponibilidade de um ambiente"><div className="linha">
            <select aria-label="Ambiente" value={q.amb || ""} onChange={(e) => setQ({ ...q, amb: e.target.value })}><option value="">Ambiente</option>{ambientes.map((t) => <option key={t.id} value={t.id}>{t.rotulo}</option>)}</select>
            <input type="number" aria-label="Horas semanais" placeholder="h/sem" style={{ width: 80 }} value={q.horas || ""} onChange={(e) => setQ({ ...q, horas: e.target.value })} />
            <button className="btn" disabled={!q.amb || !q.horas} onClick={() => perguntar(`/api/recomendacoes/ampliar_ambiente${qs({ cenario_id: cenario.id, ambiente_id: q.amb, horas: q.horas })}`)}>Avaliar</button></div></Campo>
          <Campo rotulo="Quais alterações liberariam capacidade?"><button className="btn" onClick={() => perguntar(`/api/recomendacoes/liberar_capacidade?cenario_id=${cenario.id}`)}>Analisar</button></Campo>
          <Campo rotulo="Quais UCs apresentam risco de não conclusão?"><button className="btn" onClick={() => perguntar(`/api/recomendacoes/ucs_risco?cenario_id=${cenario.id}`)}>Analisar</button></Campo>
        </div>
      </Card>
      <Modal titulo="Recomendação" aberto={!!rec} fechar={() => setRec(null)} largo>{rec && <Recomendacao r={rec} />}</Modal>
    </Pagina>
  );
}
