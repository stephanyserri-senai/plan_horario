import { useEffect, useState } from "react";
import { api, dataBR, qs } from "../api";
import { Badge, Campo, Card, Erro, Json, Modal, Pagina, Tabela, useCarregar } from "../components/ui";
import { useApp } from "../contexto";
import { useOpcoes } from "../hooks";
import { Recomendacao } from "./Planejamento";

const STATUS: Record<string, [string, string]> = {
  OTIMA: ["ok", "Solução comprovadamente ótima"], VIAVEL: ["ok", "Solução viável (otimalidade não provada)"],
  SEM_SOLUCAO_NO_LIMITE: ["alerta", "Sem solução no limite de busca (não prova inviabilidade)"], INVIAVEL: ["bloqueio", "Comprovadamente inviável"],
  MODELO_INVALIDO: ["bloqueio", "Modelo inválido"], SEM_DEMANDA: ["info", "Nada a programar"],
};

export default function Geracao() {
  const { cenario, pode, aviso, recarregarCenarios } = useApp();
  const [escopo, setEscopo] = useState<any>({ tipo: "pendentes", ids: [] as string[], regenerar_flexiveis: false });
  const [modo, setModo] = useState("completo");
  const [limite, setLimite] = useState(30);
  const [paramId, setParamId] = useState("");
  const [erro, setErro] = useState<any>(null);
  const [det, setDet] = useState<any | null>(null);
  const params = useCarregar<any[]>(() => api.get("/api/otimizacao/parametros"), []);
  const crit = useCarregar<any[]>(() => api.get("/api/otimizacao/criterios"), []);
  const execs = useCarregar<any[]>(() => cenario ? api.get(`/api/otimizacao/execucoes?cenario_id=${cenario.id}`) : Promise.resolve([]), [cenario?.id]);
  const ENT: Record<string, string> = { turma: "turmas", curso: "cursos", turno: "turnos", unidade: "unidades" };
  const ops = useOpcoes(ENT[escopo.tipo]);
  const emAndamento = (execs.dados || []).some((e) => ["pendente", "executando"].includes(e.status));
  useEffect(() => {
    if (!emAndamento) return;
    const t = setInterval(() => { execs.recarregar(); }, 2500);
    return () => { clearInterval(t); recarregarCenarios(); };
  }, [emAndamento]);
  const conj = (params.dados || []).find((p) => String(p.id) === paramId) || (params.dados || []).find((p) => p.padrao);
  if (!cenario) return <Pagina titulo="Geração inteligente"><p>Selecione um cenário.</p></Pagina>;
  const executar = async () => {
    setErro(null);
    try {
      const r = await api.post("/api/otimizacao/executar", { cenario_id: cenario.id, escopo: { ...escopo, ids: escopo.ids.map(Number) }, modo, limite_tempo_s: limite, parametros_id: paramId || undefined });
      aviso(`Execução #${r.execucao_id} iniciada em segundo plano.`, "info");
      execs.recarregar();
      recarregarCenarios();
    } catch (e) { setErro(e); }
  };
  return (
    <Pagina titulo="Geração inteligente de horários" descricao="Solver de restrições (Google OR-Tools CP-SAT). Restrições obrigatórias nunca viram penalidades; os pesos só ordenam soluções que já respeitam todas elas.">
      <div className="grid-2">
        <Card titulo="Nova execução">
          <Campo rotulo="Escopo"><select value={escopo.tipo} onChange={(e) => setEscopo({ ...escopo, tipo: e.target.value, ids: [] })}>
            <option value="pendentes">Somente atividades pendentes</option><option value="instituicao">Toda a instituição</option>
            <option value="unidade">Unidade(s)</option><option value="curso">Curso(s)</option><option value="turno">Turno(s)</option><option value="turma">Turma(s)</option></select></Campo>
          {ENT[escopo.tipo] && <Campo rotulo="Selecione"><select multiple size={5} value={escopo.ids} onChange={(e) => setEscopo({ ...escopo, ids: [...e.target.selectedOptions].map((o) => o.value) })}>
            {ops.map((o) => <option key={o.id} value={o.id}>{o.rotulo}</option>)}</select></Campo>}
          <Campo rotulo="A partir de (opcional)" ajuda="Para replanejar um período em andamento sem mexer no passado."><input type="date" value={escopo.a_partir_de || ""} onChange={(e) => setEscopo({ ...escopo, a_partir_de: e.target.value || undefined })} /></Campo>
          <label><input type="checkbox" checked={escopo.regenerar_flexiveis} onChange={(e) => setEscopo({ ...escopo, regenerar_flexiveis: e.target.checked })} /> Regenerar aulas flexíveis já programadas (aulas fixas são preservadas)</label>
          <Campo rotulo="Modo"><select value={modo} onChange={(e) => setModo(e.target.value)}>
            <option value="completo">Completo — toda a demanda é obrigatória (pode provar inviabilidade)</option>
            <option value="parcial">Parcial — aloca o máximo possível e explica o restante</option></select></Campo>
          <Campo rotulo="Conjunto de pesos"><select value={paramId} onChange={(e) => setParamId(e.target.value)}><option value="">Padrão</option>
            {(params.dados || []).map((p) => <option key={p.id} value={p.id}>{p.nome} (v{p.versao})</option>)}</select></Campo>
          <Campo rotulo="Limite de tempo (s)"><input type="number" min={5} max={3600} value={limite} onChange={(e) => setLimite(Number(e.target.value))} /></Campo>
          <Erro erro={erro} />
          {pode("otimizacao.executar") ? <button className="btn btn-primario" disabled={emAndamento || !["em_elaboracao", "em_validacao"].includes(cenario.estado)} onClick={executar}>
            {emAndamento ? "Execução em andamento…" : "Gerar horários"}</button> : <p className="mudo">Seu perfil não executa o gerador.</p>}
          {!["em_elaboracao", "em_validacao"].includes(cenario.estado) && <p className="aviso-inline">Cenário “{cenario.estado}”: crie uma cópia ou proposta para gerar horários.</p>}
        </Card>
        <Card titulo="Pesos que serão utilizados">
          <Tabela colunas={[{ chave: "descricao", rotulo: "Critério" }, { chave: "unidade", rotulo: "Unidade" }, { chave: "peso", rotulo: "Peso", alinhar: "dir", render: (c: any) => conj?.pesos?.[c.criterio] ?? c.peso_padrao }]}
            linhas={crit.dados || []} chave={(c) => c.criterio} />
          <p className="sub">Escala: pontos = peso × valor bruto. Ajuste em Configurações.</p>
        </Card>
      </div>
      <Card titulo="Execuções deste cenário">
        <Tabela colunas={[{ chave: "id", rotulo: "#" }, { chave: "criado_em", rotulo: "Solicitada", render: (e: any) => new Date(e.criado_em).toLocaleString("pt-BR") },
          { chave: "escopo", rotulo: "Escopo", render: (e: any) => `${e.escopo.tipo}${e.escopo.ids?.length ? ` (${e.escopo.ids.join(",")})` : ""}` },
          { chave: "status", rotulo: "Execução", render: (e: any) => <Badge tipo={e.status === "concluida" ? "ok" : e.status === "falha" ? "bloqueio" : "info"}>{e.status}</Badge> },
          { chave: "status_solver", rotulo: "Resultado", render: (e: any) => e.status_solver ? <Badge tipo={STATUS[e.status_solver]?.[0] || "info"}>{STATUS[e.status_solver]?.[1] || e.status_solver}</Badge> : "—" },
          { chave: "tempo_s", rotulo: "Tempo (s)", alinhar: "dir" }, { chave: "objetivo", rotulo: "Objetivo", alinhar: "dir" }]}
          linhas={execs.dados || []} aoClicar={async (e) => setDet(await api.get(`/api/otimizacao/execucoes/${e.id}`))} />
      </Card>
      <Modal titulo={det ? `Execução #${det.id}` : ""} aberto={!!det} fechar={() => setDet(null)} largo>{det && <DetalheExecucao e={det} />}</Modal>
    </Pagina>
  );
}

function DetalheExecucao({ e }: { e: any }) {
  const r = e.resultado || {};
  const s = r.solver || {};
  return (
    <div>
      <p><Badge tipo={STATUS[e.status_solver]?.[0] || "info"}>{STATUS[e.status_solver]?.[1] || e.status}</Badge> {e.motivo_termino}</p>
      <dl className="dl">
        <dt>Tempo</dt><dd>{e.tempo_s} s (limite {e.parametros.limite_tempo_s} s)</dd>
        <dt>Modo</dt><dd>{e.parametros.modo}</dd>
        <dt>Objetivo / limite inferior</dt><dd>{e.objetivo ?? "—"} / {e.limite_inferior ?? "—"}</dd>
        <dt>Atividades / ocupações fixas</dt><dd>{r.atividades} / {r.ocupacoes_fixas}</dd>
        {r.aplicacao && <><dt>Aulas criadas</dt><dd>{r.aplicacao.aulas_criadas} (substituídas: {r.aplicacao.aulas_substituidas}; datas puladas: {r.aplicacao.datas_puladas.length})</dd></>}
      </dl>
      {e.pontuacao_por_criterio?.length > 0 && <Card titulo="Pontuação por critério (modelo semanal do solver)">
        <Tabela colunas={[{ chave: "criterio", rotulo: "Critério" }, { chave: "valor_bruto", rotulo: "Valor", alinhar: "dir" }, { chave: "peso", rotulo: "Peso", alinhar: "dir" }, { chave: "pontos", rotulo: "Pontos", alinhar: "dir" }]}
          linhas={e.pontuacao_por_criterio} /></Card>}
      {e.diagnosticos?.length > 0 && <Card titulo="Diagnóstico"><ul>{e.diagnosticos.map((d: string, i: number) => <li key={i}>{d}</li>)}</ul></Card>}
      {r.aplicacao?.riscos_conclusao?.length > 0 && <Card titulo="Riscos de não conclusão"><Tabela colunas={[{ chave: "atividade", rotulo: "Atividade" }, { chave: "faltam_h", rotulo: "Faltam (h)" }, { chave: "data_limite", rotulo: "Prazo", render: (x: any) => dataBR(x.data_limite) }, { chave: "motivo", rotulo: "Motivo" }]} linhas={r.aplicacao.riscos_conclusao} chave={(_x, i) => i} /></Card>}
      {r.aplicacao?.datas_puladas?.length > 0 && <details><summary>Datas puladas ({r.aplicacao.datas_puladas.length})</summary>
        <Tabela colunas={[{ chave: "atividade", rotulo: "Atividade" }, { chave: "data", rotulo: "Data", render: (x: any) => dataBR(x.data) }, { chave: "motivo", rotulo: "Motivo" }]} linhas={r.aplicacao.datas_puladas.slice(0, 200)} chave={(_x, i) => i} /></details>}
      {s.nao_alocados?.length > 0 && <Card titulo="Atividades não alocadas"><Json dados={s.nao_alocados} /></Card>}
      {r.gargalos?.length > 0 && <Card titulo="Gargalos relacionados">{r.gargalos.map((g: any, i: number) => <p key={i}><Badge tipo="alerta">{g.tipo}</Badge> {g.descricao}</p>)}</Card>}
      {r.explicacoes?.map((x: any, i: number) => <Card key={i} titulo="Explicação"><Recomendacao r={x} /></Card>)}
      <details><summary>Parâmetros utilizados</summary><Json dados={e.parametros} /></details>
      <details><summary>Estatísticas do solver</summary><Json dados={s.estatisticas} /></details>
    </div>
  );
}
