import { useState } from "react";
import { api } from "../api";
import { Abas, Campo, Card, Erro, Pagina, Tabela, useCarregar } from "../components/ui";
import { useApp } from "../contexto";
import { ListaEntidade, useMeta } from "./Cadastro";

export default function Configuracoes() {
  const [aba, setAba] = useState("pesos");
  const metas = useMeta();
  const aux = ["unidades", "setores", "deslocamentos", "turnos", "periodos", "calendarios", "calendario_excecoes", "horarios_funcionamento", "bloqueios"];
  const [ent, setEnt] = useState(aux[0]);
  return (
    <Pagina titulo="Configurações" descricao="Regras, pesos e parâmetros editáveis sem alteração de código. Toda mudança é auditada.">
      <Abas abas={[{ id: "pesos", rotulo: "Pesos de otimização" }, { id: "limiares", rotulo: "Limiares e parâmetros" }, { id: "estrutura", rotulo: "Unidades, turnos e calendário" }, { id: "aprendizado", rotulo: "Aprendizado (Fase 8)" }]} ativa={aba} mudar={setAba} />
      {aba === "pesos" && <Pesos />}
      {aba === "limiares" && <Limiares />}
      {aba === "estrutura" && <>
        <Abas abas={aux.map((a) => ({ id: a, rotulo: metas.find((m) => m.chave === a)?.rotulo || a }))} ativa={ent} mudar={setEnt} />
        <ListaEntidade key={ent} ent={ent} />
      </>}
      {aba === "aprendizado" && <Aprendizado />}
    </Pagina>
  );
}

function Pesos() {
  const { pode, aviso } = useApp();
  const ps = useCarregar<any[]>(() => api.get("/api/otimizacao/parametros"), []);
  const crit = useCarregar<any[]>(() => api.get("/api/otimizacao/criterios"), []);
  const [ed, setEd] = useState<any | null>(null);
  const [erro, setErro] = useState<any>(null);
  return (
    <div className="grid-2">
      <Card titulo="Conjuntos de pesos">
        <Tabela colunas={[{ chave: "nome", rotulo: "Nome" }, { chave: "versao", rotulo: "Versão" }, { chave: "padrao", rotulo: "Padrão" }, { chave: "limite_tempo_s", rotulo: "Limite (s)" }]}
          linhas={ps.dados || []} aoClicar={(p) => setEd({ ...p, pesos: { ...p.pesos } })} />
        {pode("configuracoes.editar") && <button className="btn" onClick={() => setEd({ nome: "Novo conjunto", pesos: {}, limite_tempo_s: 30 })}>+ Novo conjunto</button>}
      </Card>
      {ed && <Card titulo={`Editar: ${ed.nome}`}>
        <Campo rotulo="Nome"><input value={ed.nome} onChange={(e) => setEd({ ...ed, nome: e.target.value })} /></Campo>
        <Campo rotulo="Limite de tempo padrão (s)"><input type="number" value={ed.limite_tempo_s} onChange={(e) => setEd({ ...ed, limite_tempo_s: e.target.value })} /></Campo>
        <label><input type="checkbox" checked={!!ed.padrao} onChange={(e) => setEd({ ...ed, padrao: e.target.checked })} /> Conjunto padrão</label>
        <Tabela colunas={[{ chave: "descricao", rotulo: "Critério" }, { chave: "unidade", rotulo: "Unidade" },
          { chave: "peso", rotulo: "Peso", render: (c: any) => <input type="number" step="any" min={0} aria-label={c.descricao} style={{ width: 90 }} value={ed.pesos[c.criterio] ?? c.peso_padrao}
            onChange={(e) => setEd({ ...ed, pesos: { ...ed.pesos, [c.criterio]: Number(e.target.value) } })} /> }]} linhas={crit.dados || []} chave={(c) => c.criterio} />
        <Campo rotulo="Mínimo de períodos por dia (aula isolada abaixo disso)"><input type="number" min={1} value={ed.pesos.min_periodos_dia ?? 2} onChange={(e) => setEd({ ...ed, pesos: { ...ed.pesos, min_periodos_dia: Number(e.target.value) } })} /></Campo>
        <p className="sub">Escala: pontos = peso × valor bruto. Cada execução guarda uma cópia dos pesos (com a versão do conjunto). Restrições obrigatórias não são configuradas aqui: nunca viram penalidades.</p>
        <Erro erro={erro} />
        {pode("configuracoes.editar") && <button className="btn btn-primario" onClick={async () => { setErro(null); try { await api.post("/api/otimizacao/parametros", ed); aviso("Pesos salvos (nova versão)."); setEd(null); ps.recarregar(); } catch (e) { setErro(e); } }}>Salvar</button>}
      </Card>}
    </div>
  );
}

function Limiares() {
  const { pode, aviso } = useApp();
  const cfg = useCarregar<any[]>(() => api.get("/api/configuracoes"), []);
  const [vals, setVals] = useState<Record<string, any>>({});
  return (
    <>{(cfg.dados || []).map((c) => (
      <Card key={c.chave} titulo={c.chave}>
        <p className="sub">{c.descricao}</p>
        <div className="form-grid">{Object.entries(c.valor).map(([k, v]: any) => (
          <Campo key={k} rotulo={k}><input value={vals[c.chave]?.[k] ?? v} onChange={(e) => setVals({ ...vals, [c.chave]: { ...(vals[c.chave] || {}), [k]: typeof v === "number" ? Number(e.target.value) : e.target.value } })} /></Campo>))}</div>
        {pode("configuracoes.editar") && <button className="btn btn-primario" onClick={async () => { await api.put(`/api/configuracoes/${c.chave}`, { valor: vals[c.chave] || {} }); aviso("Configuração salva."); cfg.recarregar(); }}>Salvar</button>}
      </Card>))}</>
  );
}

function Aprendizado() {
  const { pode } = useApp();
  const av = useCarregar<any>(() => pode("aprendizado.gerenciar") ? api.get("/api/aprendizado/avaliacao") : Promise.resolve(null), []);
  const regs = useCarregar<any>(() => pode("aprendizado.gerenciar") ? api.get("/api/aprendizado/registros") : Promise.resolve(null), []);
  if (!pode("aprendizado.gerenciar")) return <p>Seu perfil não gerencia os registros de aprendizado.</p>;
  return (
    <>
      {av.dados && <Card titulo="Prontidão para aprendizado de preferências">
        <p><b>Situação:</b> {av.dados.situacao}</p>
        <p>Registros revisados e aptos: {av.dados.registros_revisados_aptos} / mínimo {av.dados.minimo_para_treino}. Linha de base: {av.dados.linha_de_base}</p>
        <ul>{av.dados.protocolo.map((p: string, i: number) => <li key={i}>{p}</li>)}</ul>
      </Card>}
      <Card titulo="Registros de decisão (revise antes de incluir no treinamento)">
        <Tabela colunas={[{ chave: "id", rotulo: "#" }, { chave: "tipo", rotulo: "Tipo" }, { chave: "motivo", rotulo: "Motivo" }, { chave: "criado_em", rotulo: "Quando", render: (r: any) => new Date(r.criado_em).toLocaleString("pt-BR") },
          { chave: "dados", rotulo: "Dados", render: (r: any) => <small>{JSON.stringify(r.dados).slice(0, 120)}</small> },
          { chave: "incluir_treinamento", rotulo: "Incluir no treino", render: (r: any) => <input type="checkbox" aria-label="Incluir no treinamento" checked={r.incluir_treinamento}
            onChange={async (e) => { await api.put(`/api/aprendizado/registros/${r.id}`, { incluir_treinamento: e.target.checked }); regs.recarregar(); av.recarregar(); }} /> },
          { chave: "x", rotulo: "", render: (r: any) => <button className="btn-link" onClick={async () => { await api.del(`/api/aprendizado/registros/${r.id}`); regs.recarregar(); }}>Excluir</button> }]}
          linhas={regs.dados?.itens || []} />
      </Card>
    </>
  );
}
