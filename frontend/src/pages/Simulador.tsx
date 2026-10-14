import { useEffect, useState } from "react";
import { api, baixar, DIAS } from "../api";
import { Badge, Campo, Card, Erro, fmt, Kpi, Modal, Pagina, rotulo, Tabela, useCarregar } from "../components/ui";
import { StatusProcessamento } from "../components/Processamento";
import { useApp } from "../contexto";
import { useOpcoes } from "../hooks";

const SIT: Record<string, string> = { pendente: "Aguardando processamento", executando: "Processando…", em_execucao: "Processando…", concluida: "Concluída", falha: "Falhou" };
const VIAB: Record<string, [string, string]> = {
  provavel: ["ok", "Provável (capacidade agregada suficiente)"], condicionada: ["alerta", "Condicionada a ajustes"],
  inviavel_sem_novos_recursos: ["bloqueio", "Inviável sem novos recursos"], viavel: ["ok", "Viável — existe grade que respeita todas as restrições"],
  inviavel_comprovado: ["bloqueio", "Comprovadamente inviável nas condições informadas"], indeterminado: ["alerta", "Indeterminado no limite de busca"],
};

export default function Simulador() {
  const { cenario, cenarios, aviso } = useApp();
  const [p, setP] = useState<any>({ quantidade_turmas: 1, alunos_por_turma: 30, dias_semana: [0, 1, 2, 3, 4], num_grupos: 1, ucs_sequenciais: true });
  const [base, setBase] = useState<string>("");
  const [res, setRes] = useState<any | null>(null);
  const [erro, setErro] = useState<any>(null);
  const [rodando, setRodando] = useState(false);
  const [det, setDet] = useState<any | null>(null);
  const cursos = useOpcoes("cursos");
  const unidades = useOpcoes("unidades");
  const turnos = useOpcoes("turnos");
  const calendarios = useOpcoes("calendarios");
  const matrizes = useCarregar<any>(() => p.curso_id ? api.get(`/api/cadastros/matrizes?curso_id=${p.curso_id}&por_pagina=100`) : Promise.resolve({ itens: [] }), [p.curso_id]);
  const ucs = useCarregar<any>(() => p.matriz_id ? api.get(`/api/cadastros/ucs?matriz_id=${p.matriz_id}&por_pagina=200`) : Promise.resolve({ itens: [] }), [p.matriz_id]);
  const lista = useCarregar<any[]>(() => api.get("/api/simulador"), []);
  useEffect(() => { if (!base && cenario) setBase(String(cenario.id)); }, [cenario?.id]);
  const emAndamento = (lista.dados || []).some((s) => ["pendente", "executando", "em_execucao"].includes(s.status));
  useEffect(() => {
    if (!emAndamento) return;
    const t = setInterval(lista.recarregar, 10000);
    return () => clearInterval(t);
  }, [emAndamento]);
  const set = (k: string, v: any) => setP({ ...p, [k]: v });
  const corpo = () => ({ cenario_base_id: Number(base), nome: p.nome || "Nova oferta", parametros: {
    ...p, curso_id: Number(p.curso_id), matriz_id: Number(p.matriz_id), unidade_id: Number(p.unidade_id), turno_id: p.turno_id ? Number(p.turno_id) : null,
    calendario_id: p.calendario_id ? Number(p.calendario_id) : null, quantidade_turmas: Number(p.quantidade_turmas), alunos_por_turma: Number(p.alunos_por_turma),
    num_grupos: Number(p.num_grupos), encontros_semanais: p.encontros_semanais ? Number(p.encontros_semanais) : null, uc_ids: p.uc_ids?.length ? p.uc_ids.map(Number) : null } });
  const agregada = async () => { setErro(null); setRodando(true); try { setRes({ agregada: await api.post("/api/simulador/agregada", corpo()) }); lista.recarregar(); } catch (e) { setErro(e); } finally { setRodando(false); } };
  const completa = async () => { setErro(null); try { const r = await api.post("/api/simulador/completa", { ...corpo(), limite_tempo_s: 20 }); aviso(r.mensagem || "Simulação iniciada; o resultado aparecerá na lista ao lado.", "info"); lista.recarregar(); } catch (e) { setErro(e); } };
  return (
    <Pagina titulo="Simulador de capacidade" descricao="Descubra se cabe uma nova turma antes de abri-la. Nada aqui altera os horários publicados.">
      <StatusProcessamento ativo={emAndamento} />
      <p className="sub"><b>Como usar:</b> preencha a oferta pretendida e clique em <b>Verificação rápida</b> (resposta imediata, estimativa de capacidade).
        Se quiser certeza, use <b>Montar grade de teste</b>: o sistema tenta montar a grade real com as novas turmas e diz se cabe e o que mudar.</p>
      <div className="grid-2">
        <Card titulo="Nova oferta pretendida">
          <div className="form-grid">
            <Campo rotulo="Nome da simulação"><input value={p.nome || ""} onChange={(e) => set("nome", e.target.value)} /></Campo>
            <Campo rotulo="Cenário base" obrigatorio><select value={base} onChange={(e) => setBase(e.target.value)}>{cenarios.filter((c) => c.tipo !== "simulacao").map((c) => <option key={c.id} value={c.id}>{c.nome}</option>)}</select></Campo>
            <Campo rotulo="Curso" obrigatorio><select value={p.curso_id || ""} onChange={(e) => setP({ ...p, curso_id: e.target.value, matriz_id: "" })}><option value="">—</option>{cursos.map((c) => <option key={c.id} value={c.id}>{c.rotulo}</option>)}</select></Campo>
            <Campo rotulo="Matriz curricular" obrigatorio><select value={p.matriz_id || ""} onChange={(e) => set("matriz_id", e.target.value)}><option value="">—</option>{(matrizes.dados?.itens || []).map((m: any) => <option key={m.id} value={m.id}>{m.versao}</option>)}</select></Campo>
            <Campo rotulo="Unidade de oferta" obrigatorio><select value={p.unidade_id || ""} onChange={(e) => set("unidade_id", e.target.value)}><option value="">—</option>{unidades.map((c) => <option key={c.id} value={c.id}>{c.rotulo}</option>)}</select></Campo>
            <Campo rotulo="Turno desejado"><select value={p.turno_id || ""} onChange={(e) => set("turno_id", e.target.value)}><option value="">Qualquer</option>{turnos.map((c) => <option key={c.id} value={c.id}>{c.rotulo}</option>)}</select></Campo>
            <Campo rotulo="Calendário"><select value={p.calendario_id || ""} onChange={(e) => set("calendario_id", e.target.value)}><option value="">Da unidade</option>{calendarios.map((c) => <option key={c.id} value={c.id}>{c.rotulo}</option>)}</select></Campo>
            <Campo rotulo="Quantidade de turmas"><input type="number" min={1} value={p.quantidade_turmas} onChange={(e) => set("quantidade_turmas", e.target.value)} /></Campo>
            <Campo rotulo="Alunos por turma"><input type="number" min={1} value={p.alunos_por_turma} onChange={(e) => set("alunos_por_turma", e.target.value)} /></Campo>
            <Campo rotulo="Grupos por turma"><input type="number" min={1} max={16} value={p.num_grupos} onChange={(e) => set("num_grupos", e.target.value)} /></Campo>
            <Campo rotulo="Início" obrigatorio><input type="date" value={p.data_inicio || ""} onChange={(e) => set("data_inicio", e.target.value)} /></Campo>
            <Campo rotulo="Término" obrigatorio><input type="date" value={p.data_fim || ""} onChange={(e) => set("data_fim", e.target.value)} /></Campo>
            <Campo rotulo="Encontros semanais por UC" ajuda="Vazio = conforme cadastro da UC"><input type="number" min={1} value={p.encontros_semanais || ""} onChange={(e) => set("encontros_semanais", e.target.value)} /></Campo>
            <Campo rotulo="Distribuição semanal (dias)"><div className="checks">{DIAS.slice(0, 6).map((d, i) => <label key={i}><input type="checkbox" checked={p.dias_semana.includes(i)}
              onChange={(e) => set("dias_semana", e.target.checked ? [...p.dias_semana, i].sort() : p.dias_semana.filter((x: number) => x !== i))} /> {d.slice(0, 3)}</label>)}</div></Campo>
            <Campo rotulo="UCs (vazio = todas da matriz)"><select multiple size={5} value={p.uc_ids || []} onChange={(e) => set("uc_ids", [...e.target.selectedOptions].map((o) => o.value))}>
              {(ucs.dados?.itens || []).map((u: any) => <option key={u.id} value={u.id}>{u.codigo} – {u.nome} ({u.carga_horaria_total} h)</option>)}</select></Campo>
            <Campo rotulo="Opções"><label><input type="checkbox" checked={p.ucs_sequenciais} onChange={(e) => set("ucs_sequenciais", e.target.checked)} /> UCs em sequência (não simultâneas)</label>
              <label><input type="checkbox" checked={!!p.acessibilidade} onChange={(e) => set("acessibilidade", e.target.checked)} /> Requer acessibilidade</label></Campo>
          </div>
          <Erro erro={erro} />
          <div className="acoes"><button className="btn btn-primario" disabled={rodando} onClick={agregada}>{rodando ? "Verificando…" : "Verificação rápida"}</button>
            <button className="btn" disabled={emAndamento} onClick={completa}>Montar grade de teste (alguns minutos)</button></div>
        </Card>
        <Card titulo="Simulações anteriores" extra={<button className="btn" onClick={lista.recarregar}>Atualizar</button>}>
          <Tabela colunas={[{ chave: "nome", rotulo: "Nome" }, { chave: "tipo", rotulo: "Tipo", render: (s: any) => s.tipo === "completa" ? "Grade de teste" : "Verificação rápida" },
            { chave: "status", rotulo: "Situação", render: (s: any) => SIT[s.status] || s.status },
            { chave: "viabilidade", rotulo: "Resultado", render: (s: any) => s.viabilidade ? <Badge tipo={VIAB[s.viabilidade]?.[0] || "info"}>{VIAB[s.viabilidade]?.[1] || s.viabilidade}</Badge> : "—" },
            { chave: "a", rotulo: "", render: (s: any) => <span className="acoes-linha" onClick={(e) => e.stopPropagation()}>
              <button className="btn-link" onClick={() => baixar(`/api/exportar/simulacao/${s.id}?formato=xlsx`, `simulacao_${s.id}.xlsx`)}>XLSX</button>
              <button className="btn-link" onClick={async () => { if (confirm("Remover simulação e suas turmas simuladas?")) { await api.del(`/api/simulador/${s.id}`); lista.recarregar(); } }}>Remover</button></span> }]}
            linhas={lista.dados || []} vazio="Nenhuma simulação ainda." aoClicar={async (s) => setDet(await api.get(`/api/simulador/${s.id}`))} />
        </Card>
      </div>
      {res?.agregada && <ResultadoAgregado r={res.agregada} />}
      <Modal titulo={det ? `Simulação #${det.id} — ${det.nome}` : ""} aberto={!!det} fechar={() => setDet(null)} largo>
        {det && (det.tipo === "agregada" ? <ResultadoAgregado r={det.resultado} /> : <ResultadoCompleto r={det.resultado} />)}
      </Modal>
    </Pagina>
  );
}

function ResultadoAgregado({ r }: { r: any }) {
  if (!r) return null;
  return (
    <Card titulo={<>Resultado agregado: <Badge tipo={VIAB[r.viabilidade_estimada]?.[0]}>{VIAB[r.viabilidade_estimada]?.[1]}</Badge></>}>
      <p className="aviso-inline">{r.aviso}</p>
      <div className="kpis">
        <Kpi rotulo="Carga horária adicional" valor={`${r.carga_horaria_adicional_semanal_h} h/sem`} />
        <Kpi rotulo="Déficit adicional gerado" valor={`${r.deficit_adicional_h} h/sem`} tom={r.deficit_adicional_h ? "erro" : "ok"} />
        <Kpi rotulo="Gargalos antes → depois" valor={`${r.antes.gargalos} → ${r.depois.gargalos}`} detalhe={`${r.antes.deficit_h} h → ${r.depois.deficit_h} h de déficit`} />
      </div>
      <div className="grid-2">
        <Card titulo="Compatibilidade por UC"><Tabela colunas={[{ chave: "uc", rotulo: "UC" }, { chave: "ambientes_compativeis", rotulo: "Ambientes compatíveis" }, { chave: "instrutores_habilitados", rotulo: "Instrutores habilitados" }]} linhas={r.compatibilidade_por_uc} chave={(l) => l.uc} /></Card>
        <Card titulo="Capacidade atual por turno"><Tabela colunas={[{ chave: "turno", rotulo: "Turno" }, { chave: "taxa_ocupacao_atual_pct", rotulo: "Ocupação %", alinhar: "dir" }, { chave: "horas_ociosas", rotulo: "Horas ociosas", alinhar: "dir" }]} linhas={r.capacidade_por_turno} chave={(l) => l.turno} /></Card>
        <Card titulo="Laboratórios"><Tabela colunas={[{ chave: "codigo", rotulo: "Ambiente" }, { chave: "taxa_ocupacao_pct", rotulo: "Ocupação %", alinhar: "dir" }, { chave: "horas_ociosas", rotulo: "Ociosas (h)", alinhar: "dir" }]} linhas={r.laboratorios} chave={(l) => l.codigo} /></Card>
        <Card titulo="Instrutores com folga"><Tabela colunas={[{ chave: "nome", rotulo: "Instrutor" }, { chave: "restante_semanal_h", rotulo: "Folga (h/sem)", alinhar: "dir" }]} linhas={r.instrutores_com_folga} chave={(l) => l.nome} /></Card>
      </div>
      {r.gargalos_gerados.map((g: any, i: number) => <p key={i}><Badge tipo="alerta">{rotulo(g.tipo)}</Badge> {g.descricao}</p>)}
      {r.condicoes_necessarias.length > 0 && <><h3>Condições necessárias para viabilizar</h3><ul>{r.condicoes_necessarias.map((c: string, i: number) => <li key={i}>{c}</li>)}</ul></>}
    </Card>
  );
}

const SOLVER: Record<string, string> = {
  OTIMA: "foi possível montar a grade completa", VIAVEL: "foi possível montar a grade completa", INVIAVEL: "não é possível encaixar tudo nas condições informadas",
  SEM_SOLUCAO_NO_LIMITE: "não foi encontrada uma grade no tempo disponível", MODELO_INVALIDO: "há inconsistências nos cadastros", SEM_DEMANDA: "não havia aulas para programar",
};

function ResultadoCompleto({ r }: { r: any }) {
  if (!r) return <p>Ainda processando… o resultado aparece aqui assim que terminar.</p>;
  if (r.erro) return <div className="erro-box">{r.erro}</div>;
  const c = r.completa || {};
  return (
    <div className="explicacao">
      <p className="destaque"><Badge tipo={VIAB[r.viabilidade]?.[0]}>{VIAB[r.viabilidade]?.[1] || r.viabilidade}</Badge></p>
      {r.mensagem && <p>{r.mensagem}</p>}
      <p>Ao tentar montar a grade com as novas turmas, {SOLVER[c.status_solver] || "o processamento terminou"}
        {c.aplicacao ? ` (${c.aplicacao.aulas_criadas} aula(s) de teste criadas).` : "."}</p>
      {r.comparacao && <Card titulo="Como fica a instituição com as novas turmas">
        <Tabela colunas={[{ chave: "k", rotulo: "Indicador" }, { chave: "a", rotulo: "Hoje", alinhar: "dir" }, { chave: "b", rotulo: "Com novas turmas", alinhar: "dir" }]} chave={(l) => l.k}
          linhas={[["Aulas", "aulas"], ["Horas programadas", "horas_programadas"], ["Ocupação das salas (%)", "taxa_ocupacao_ambientes_pct"], ["Ocupação dos instrutores (%)", "ocupacao_media_instrutores_pct"],
            ["Instrutores sobrecarregados", "instrutores_criticos"], ["Horários vagos entre aulas dos instrutores (h)", "janelas_instrutores_h"]].map(([k, cc]) => ({ k, a: fmt(r.comparacao.atual[cc]), b: fmt(r.comparacao.com_novas_turmas[cc]) }))} />
      </Card>}
      {c.nao_alocados?.length > 0 && <Card titulo="O que não coube">
        <Tabela colunas={[{ chave: "descricao", rotulo: "Turma / unidade curricular" }, { chave: "encontros", rotulo: "Aulas semanais necessárias", alinhar: "dir" },
          { chave: "alocados", rotulo: "Conseguidas", alinhar: "dir", render: (n: any) => n.alocados ?? 0 }]} linhas={c.nao_alocados} chave={(_n, i) => i} /></Card>}
      {r.alternativas && <Card titulo="O que poderia viabilizar">
        <Tabela colunas={[{ chave: "alternativa", rotulo: "Alternativa" }, { chave: "viavel", rotulo: "Resultado", render: (a: any) => a.viavel == null ? "não testada" : a.viavel ? <Badge tipo="ok">resolve</Badge> : <Badge tipo="bloqueio">não resolve</Badge> }, { chave: "detalhes", rotulo: "Observação" }]}
          linhas={r.alternativas} chave={(_a, i) => i} /></Card>}
      {c.diagnosticos?.length > 0 && <Card titulo="Observações"><ul>{c.diagnosticos.map((d: string, i: number) => <li key={i}>{d}</li>)}</ul></Card>}
      {r.agregada && <ResultadoAgregado r={r.agregada} />}
    </div>
  );
}
