import { useEffect, useState } from "react";
import { api, dataBR } from "../api";
import { Badge, Campo, Card, Erro, Modal, Pagina, rotulo, Tabela, useCarregar } from "../components/ui";
import { StatusProcessamento } from "../components/Processamento";
import { AvisoSomenteLeitura } from "../components/AvisoSomenteLeitura";
import { useApp } from "../contexto";
import { useOpcoes } from "../hooks";
import { Recomendacao } from "./Planejamento";

const STATUS: Record<string, [string, string]> = {
  OTIMA: ["ok", "Melhor grade possível encontrada"], VIAVEL: ["ok", "Grade gerada com sucesso"],
  SEM_SOLUCAO_NO_LIMITE: ["alerta", "Não terminou no tempo disponível"], INVIAVEL: ["bloqueio", "Impossível encaixar tudo"],
  MODELO_INVALIDO: ["bloqueio", "Dados de cadastro inconsistentes"], SEM_DEMANDA: ["info", "Nada a programar"],
};
const EXPLICA_STATUS: Record<string, string> = {
  OTIMA: "Todas as aulas solicitadas foram encaixadas sem conflitos, e não existe arranjo melhor segundo os critérios configurados.",
  VIAVEL: "Todas as aulas solicitadas foram encaixadas sem conflitos. Pode existir um arranjo ligeiramente melhor; aumente o tempo de busca nas opções avançadas se quiser tentar.",
  SEM_SOLUCAO_NO_LIMITE: "O sistema não encontrou uma grade completa no tempo disponível. Isso não significa que seja impossível: tente o modo “encaixar o máximo possível” ou aumente o tempo de busca.",
  INVIAVEL: "Com os cadastros atuais não há como encaixar todas as aulas sem conflito. Veja abaixo o que está faltando (instrutor, sala ou horário) e as sugestões.",
  MODELO_INVALIDO: "Há inconsistências nos cadastros que impedem a geração. Veja o diagnóstico abaixo.",
  SEM_DEMANDA: "Não havia aulas pendentes para programar no escopo escolhido.",
};
const SITUACAO: Record<string, [string, string]> = {
  pendente: ["info", "Aguardando processamento"], executando: ["info", "Processando…"], concluida: ["ok", "Concluída"], falha: ["bloqueio", "Falhou"],
  cancelada: ["alerta", "Cancelada"],
};
const ESCOPO: Record<string, string> = { pendentes: "Aulas pendentes", instituicao: "Tudo", unidade: "Unidade", curso: "Curso", turno: "Turno", turma: "Turma", simulacao: "Simulação" };

export default function Geracao() {
  const { cenario, pode, aviso, recarregarCenarios, unidade } = useApp();
  const [escopo, setEscopo] = useState<any>({ tipo: "pendentes", ids: [] as string[], regenerar_flexiveis: false });
  const [modo, setModo] = useState("parcial");
  const [limite, setLimite] = useState(60);
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
    const t = setInterval(() => { execs.recarregar(); }, 5000);
    return () => { clearInterval(t); recarregarCenarios(); };
  }, [emAndamento]);
  const conj = (params.dados || []).find((p) => String(p.id) === paramId) || (params.dados || []).find((p) => p.padrao);
  if (!cenario) return <Pagina titulo="Gerar horários"><p>Escolha o semestre no topo da página.</p></Pagina>;
  const editavel = ["em_elaboracao", "em_validacao"].includes(cenario.estado);
  const executar = async () => {
    setErro(null);
    try {
      const r = await api.post("/api/otimizacao/executar", { cenario_id: cenario.id, escopo: { ...escopo, ids: escopo.ids.map(Number), unidade_id: unidade ? Number(unidade) : undefined }, modo, limite_tempo_s: limite, parametros_id: paramId || undefined });
      aviso(r.modo_execucao === "fila" ? "Pedido registrado! A grade está sendo gerada; isso costuma levar de 2 a 5 minutos." : "Geração iniciada.", "info");
      execs.recarregar();
      recarregarCenarios();
    } catch (e) { setErro(e); }
  };
  return (
    <Pagina titulo="Gerar horários" descricao="O sistema monta a grade automaticamente, sem nenhum conflito de turma, instrutor ou sala, respeitando disponibilidades e cargas horárias.">
      <StatusProcessamento ativo={emAndamento} aoConcluir={() => execs.recarregar()} />
      <div className="grid-2">
        <Card titulo="1. O que deseja gerar?">
          <Campo rotulo="Gerar horários para"><select value={escopo.tipo} onChange={(e) => setEscopo({ ...escopo, tipo: e.target.value, ids: [] })}>
            <option value="pendentes">Somente as aulas que ainda não têm horário (recomendado)</option>
            <option value="instituicao">{unidade ? "Todas as turmas da unidade" : "Todas as turmas do semestre"}</option>
            {!unidade && <option value="unidade">Unidades específicas</option>}<option value="curso">Cursos específicos</option><option value="turno">Turnos específicos</option><option value="turma">Turmas específicas</option></select></Campo>
          {ENT[escopo.tipo] && <Campo rotulo="Selecione (Ctrl/⌘ + clique para escolher vários)"><select multiple size={5} value={escopo.ids} onChange={(e) => setEscopo({ ...escopo, ids: [...e.target.selectedOptions].map((o) => o.value) })}>
            {ops.map((o) => <option key={o.id} value={o.id}>{o.rotulo}</option>)}</select></Campo>}
          <Campo rotulo="Se não couber tudo"><select value={modo} onChange={(e) => setModo(e.target.value)}>
            <option value="parcial">Encaixar o máximo possível e explicar o que faltou (recomendado)</option>
            <option value="completo">Só aceitar se couber tudo (senão, mostrar por que é impossível)</option></select></Campo>
          <details className="avancado">
            <summary>Opções avançadas</summary>
            <Campo rotulo="Replanejar somente a partir de" ajuda="Útil no meio do semestre: o que já passou não é alterado."><input type="date" value={escopo.a_partir_de || ""} onChange={(e) => setEscopo({ ...escopo, a_partir_de: e.target.value || undefined })} /></Campo>
            <label><input type="checkbox" checked={escopo.regenerar_flexiveis} onChange={(e) => setEscopo({ ...escopo, regenerar_flexiveis: e.target.checked })} /> Refazer também aulas já programadas que não estão marcadas como fixas</label>
            <Campo rotulo="Prioridades (conjunto de pesos)"><select value={paramId} onChange={(e) => setParamId(e.target.value)}><option value="">Padrão da instituição</option>
              {(params.dados || []).map((p) => <option key={p.id} value={p.id}>{p.nome}</option>)}</select></Campo>
            <Campo rotulo="Tempo máximo de busca (segundos)" ajuda="Mais tempo pode encontrar uma grade melhor em cenários grandes."><input type="number" min={10} max={1200} value={limite} onChange={(e) => setLimite(Number(e.target.value))} /></Campo>
          </details>
          <Erro erro={erro} />
          {pode("otimizacao.executar") ? <button className="btn btn-primario btn-grande" disabled={emAndamento || !editavel} onClick={executar}>
            {emAndamento ? "Gerando horários…" : "Gerar horários"}</button> : <p className="mudo">Seu perfil pode consultar, mas não gerar horários.</p>}
          {!editavel && <AvisoSomenteLeitura />}
        </Card>
        <Card titulo="Como o sistema escolhe a melhor grade">
          <p className="sub">Regras obrigatórias (nunca são quebradas): nenhum conflito de turma, instrutor ou sala; instrutor habilitado; sala compatível e com capacidade; disponibilidades, feriados e bloqueios respeitados.</p>
          <p className="sub">Entre as grades possíveis, o sistema prefere a que atende melhor os critérios abaixo (quanto maior a importância, mais o critério pesa):</p>
          <Tabela colunas={[{ chave: "descricao", rotulo: "Critério" }, { chave: "peso", rotulo: "Importância", render: (c: any) => <Nivel peso={conj?.pesos?.[c.criterio] ?? c.peso_padrao} /> }]}
            linhas={crit.dados || []} chave={(c) => c.criterio} />
          <p className="sub">A importância de cada critério pode ser ajustada em Configurações.</p>
        </Card>
      </div>
      <Card titulo="2. Resultados das gerações deste semestre">
        <Tabela colunas={[{ chave: "criado_em", rotulo: "Solicitada em", render: (e: any) => new Date(e.criado_em).toLocaleString("pt-BR") },
          { chave: "escopo", rotulo: "Para", render: (e: any) => ESCOPO[e.escopo.tipo] || e.escopo.tipo },
          { chave: "status", rotulo: "Situação", render: (e: any) => <Badge tipo={SITUACAO[e.status]?.[0] || "info"}>{SITUACAO[e.status]?.[1] || e.status}</Badge> },
          { chave: "status_solver", rotulo: "Resultado", render: (e: any) => e.status_solver ? <Badge tipo={STATUS[e.status_solver]?.[0] || "info"}>{STATUS[e.status_solver]?.[1] || e.status_solver}</Badge> : "—" },
          { chave: "ver", rotulo: "", render: (e: any) => e.status === "concluida" || e.status === "falha" ? <span className="btn-link">Ver explicação ›</span> : null }]}
          linhas={execs.dados || []} vazio="Nenhuma geração ainda. Use o botão “Gerar horários” acima."
          aoClicar={async (e) => setDet(await api.get(`/api/otimizacao/execucoes/${e.id}`))} />
      </Card>
      <Modal titulo="Resultado da geração" aberto={!!det} fechar={() => setDet(null)} largo>{det && <DetalheExecucao e={det} criterios={crit.dados || []} />}</Modal>
    </Pagina>
  );
}

function DetalheExecucao({ e, criterios }: { e: any; criterios: any[] }) {
  const r = e.resultado || {};
  const s = r.solver || {};
  const ap = r.aplicacao;
  const nao = (s.nao_alocados || r.diagnostico_parcial?.nao_alocados || []) as any[];
  const desc = (c: string) => criterios.find((x) => x.criterio === c)?.descricao || rotulo(c);
  const unid = (c: string) => criterios.find((x) => x.criterio === c)?.unidade || "";
  return (
    <div className="explicacao">
      <p className="destaque"><Badge tipo={STATUS[e.status_solver]?.[0] || (e.status === "falha" ? "bloqueio" : "info")}>{STATUS[e.status_solver]?.[1] || SITUACAO[e.status]?.[1] || e.status}</Badge></p>
      <p>{EXPLICA_STATUS[e.status_solver] || e.motivo_termino || (e.status === "falha" ? "O processamento falhou. Tente novamente; se persistir, avise o administrador." : "")}</p>
      <Tabela colunas={[{ chave: "k", rotulo: "Resumo" }, { chave: "v", rotulo: "", alinhar: "dir" }]} chave={(l) => l.k} linhas={[
        ...(ap ? [{ k: "Aulas criadas na grade", v: ap.aulas_criadas }, { k: "Aulas antigas substituídas", v: ap.aulas_substituidas },
          { k: "Datas sem aula por feriado ou bloqueio", v: ap.datas_puladas?.length ?? 0 }] : []),
        { k: "Atividades que não couberam", v: nao.length },
        { k: "Tempo de processamento", v: e.tempo_s != null ? `${Math.round(e.tempo_s)} s` : "—" },
      ]} />
      {nao.length > 0 && <Card titulo="O que não coube na grade">
        <Tabela colunas={[{ chave: "descricao", rotulo: "Turma / unidade curricular" }, { chave: "encontros", rotulo: "Aulas semanais necessárias", alinhar: "dir" },
          { chave: "alocados", rotulo: "Conseguidas", alinhar: "dir", render: (n: any) => n.alocados ?? 0 }]} linhas={nao} chave={(_n, i) => i} />
        <p className="sub">Veja abaixo o motivo de cada caso e o que pode ser feito.</p>
      </Card>}
      {e.diagnosticos?.length > 0 && <Card titulo="Observações"><ul>{e.diagnosticos.map((d: string, i: number) => <li key={i}>{d}</li>)}</ul></Card>}
      {ap?.riscos_conclusao?.length > 0 && <Card titulo="Disciplinas que podem não terminar no prazo">
        <Tabela colunas={[{ chave: "atividade", rotulo: "Turma / unidade curricular" }, { chave: "faltam_h", rotulo: "Horas faltando", alinhar: "dir" },
          { chave: "data_limite", rotulo: "Prazo", render: (x: any) => dataBR(x.data_limite) }, { chave: "motivo", rotulo: "Motivo" }]} linhas={ap.riscos_conclusao} chave={(_x, i) => i} /></Card>}
      {r.gargalos?.length > 0 && <Card titulo="Pontos de falta de capacidade">{r.gargalos.map((g: any, i: number) => <p key={i}><Badge tipo="alerta">{rotulo(g.tipo)}</Badge> {g.descricao}</p>)}</Card>}
      {r.explicacoes?.map((x: any, i: number) => <Card key={i} titulo="Por que não coube e o que fazer"><Recomendacao r={x} /></Card>)}
      {e.pontuacao_por_criterio?.length > 0 && <Card titulo="Qualidade da grade gerada (por semana típica)">
        <Tabela colunas={[{ chave: "criterio", rotulo: "Critério", render: (c: any) => desc(c.criterio) },
          { chave: "valor_bruto", rotulo: "Resultado", alinhar: "dir", render: (c: any) => `${Number(c.valor_bruto).toLocaleString("pt-BR", { maximumFractionDigits: 1 })} ${unid(c.criterio)}` }]}
          linhas={e.pontuacao_por_criterio} chave={(c) => c.criterio} />
        <p className="sub">Quanto menor o número, melhor (por exemplo, menos janelas e menos trocas de sala).</p>
      </Card>}
      {ap?.datas_puladas?.length > 0 && <details><summary>Datas sem aula por feriado ou bloqueio ({ap.datas_puladas.length})</summary>
        <Tabela colunas={[{ chave: "atividade", rotulo: "Turma / unidade curricular" }, { chave: "data", rotulo: "Data", render: (x: any) => dataBR(x.data) }, { chave: "motivo", rotulo: "Motivo" }]} linhas={ap.datas_puladas.slice(0, 200)} chave={(_x, i) => i} /></details>}
    </div>
  );
}

/** Importância em 5 níveis (escala logarítmica dos pesos), em vez do número cru. */
function Nivel({ peso }: { peso: number }) {
  const p = Number(peso) || 0;
  const n = p <= 0 ? 0 : p < 1 ? 1 : p < 10 ? 2 : p < 30 ? 3 : p < 200 ? 4 : 5;
  const nome = ["desligado", "muito baixa", "baixa", "média", "alta", "muito alta"][n];
  return <span className="nivel" title={`Importância ${nome} (peso ${p})`} aria-label={`Importância ${nome}`}>
    {[1, 2, 3, 4, 5].map((i) => <i key={i} className={i <= n ? "on" : ""} />)}<small>{nome}</small></span>;
}
