import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api, baixar } from "../api";
import { Abas, Badge, Campo, Card, Erro, Pagina, Tabela, useCarregar } from "../components/ui";
import Exportar from "./Exportar";
import { useApp } from "../contexto";

const TIPOS: [string, string][] = [
  ["estrutura_curricular", "Cursos, matrizes e UCs (planilha única)"], ["ambientes", "Salas e laboratórios"],
  ["levantamento_instrutores", "Levantamento de instrutores (áreas, disponibilidade, UCs, certificações)"], ["turmas", "Turmas"],
  ["turma_ucs", "Turma × UC (datas e carga já realizada)"], ["aulas", "Aulas (grade)"],
  ["cursos", "Somente cursos"], ["matrizes", "Somente matrizes"], ["ucs", "Somente UCs"], ["instrutores", "Somente instrutores"],
  ["competencias", "Somente competências"], ["disponibilidade_instrutores", "Somente disponibilidade de instrutores"], ["unidades", "Dados complementares das unidades"],
];
const NOME_TIPO = Object.fromEntries(TIPOS);
const ACOES: Record<string, string> = { criar: "Novo", atualizar: "Atualizado", sem_alteracao: "Sem alteração", erro: "Com erro" };
const SIGLAS: Record<string, string> = { uc: "UC", ucs: "UCs", ch: "CH", id: "ID", h: "(h)", pct: "(%)", nr: "NR" };
const CAMPOS: Record<string, string> = {
  codigo: "Código", nome: "Nome", matricula: "Matrícula", email: "E-mail", unidade: "Unidade", unidade_codigo: "Unidade", area: "Área",
  carga_horaria_contratual: "Carga contratual (h/semana)", limite_ch_letiva: "Limite de aulas por semana (h)", max_horas_dia: "Máximo de horas por dia",
  turnos: "Turnos de trabalho", dias: "Dias disponíveis", modalidade: "Modalidade", ucs_pleno: "UCs que ministra", ucs_supervisionado: "UCs sob supervisão",
  certificacoes: "Certificações", areas_competencia: "Formação e especialidades", turma_codigo: "Turma", uc_codigo: "UC", curso_codigo: "Curso",
  versao: "Versão da matriz", data_inicio: "Data de início", data_fim: "Data de término", data_limite: "Data-limite", ch_realizada: "CH já realizada",
  qtd_alunos: "Alunos", turno: "Turno", tipo_curso: "Tipo de curso", carga_horaria_total: "Carga horária total",
};
/** Nome legível de um campo técnico ("carga_horaria_contratual" → "Carga contratual (h/semana)"). */
export function rotuloCampo(c: string) {
  if (CAMPOS[c]) return CAMPOS[c];
  const t = c.split("_").filter(Boolean).map((p) => SIGLAS[p] || p).join(" ");
  return t.charAt(0).toUpperCase() + t.slice(1);
}
const MODELOS: [string, string, string][] = [
  ["estrutura_curricular", "📚", "Cursos, matrizes e UCs"], ["ambientes", "🏫", "Salas e laboratórios"],
  ["levantamento_instrutores", "👩‍🏫", "Levantamento de instrutores"], ["turmas", "👥", "Turmas"],
];

export default function ImportarExportar() {
  const { pode } = useApp();
  const [sp, setSp] = useSearchParams();
  const podeImp = pode("importacao.executar"), podeExp = pode("exportacao.executar");
  const aba = sp.get("aba") || (podeImp ? "importar" : "exportar");
  return (
    <Pagina titulo="Importar e exportar" descricao="Traga dados por planilha ou baixe a grade, a ocupação e os cadastros prontos em Excel e PDF.">
      <Abas abas={[...(podeImp ? [{ id: "importar", rotulo: "⇪ Importar planilha" }] : []), ...(podeExp ? [{ id: "exportar", rotulo: "⬇ Exportar" }] : [])]}
        ativa={aba} mudar={(a) => setSp({ aba: a })} />
      {aba === "importar" && podeImp && <Importacao />}
      {aba === "exportar" && podeExp && <Exportar />}
    </Pagina>
  );
}

function Importacao() {
  const { cenarios, cenario, aviso, auth } = useApp();
  const [arquivo, setArquivo] = useState<File | null>(null);
  const [sp] = useSearchParams();
  const [tipo, setTipo] = useState(sp.get("tipo") || "");
  const [cen, setCen] = useState<string>("");
  const [previa, setPrevia] = useState<any | null>(null);
  const [mapa, setMapa] = useState<Record<string, string | null>>({});
  const [erro, setErro] = useState<any>(null);
  const [rel, setRel] = useState<any | null>(null);
  const [filtroAcao, setFiltroAcao] = useState("");
  const hist = useCarregar<any[]>(() => api.get("/api/importacao"), []);
  const enviar = async () => {
    if (!arquivo) return;
    setErro(null); setRel(null);
    const f = new FormData();
    f.append("arquivo", arquivo);
    if (tipo) f.append("tipo", tipo);
    if (cen || cenario) f.append("cenario_id", cen || String(cenario?.id));
    try { const p = await api.upload("/api/importacao/previa", f); setPrevia(p); setMapa(p.mapeamento); setTipo(p.tipo); } catch (e) { setErro(e); }
  };
  const remapear = async (extra: any = {}) => {
    try { const p = await api.post(`/api/importacao/${previa.id}/remapear`, { mapeamento: mapa, tipo, planilha: previa.planilha, ...extra }); setPrevia(p); setMapa(p.mapeamento); } catch (e) { setErro(e); }
  };
  const confirmar = async (ignorar: boolean) => {
    setErro(null);
    try { const r = await api.post(`/api/importacao/${previa.id}/confirmar`, { ignorar_erros: ignorar }); setRel(r); aviso("Importação gravada."); setPrevia(null); hist.recarregar(); } catch (e) { setErro(e); }
  };
  const itens = (previa?.itens || []).filter((i: any) => !filtroAcao || i.acao === filtroAcao);
  return (
    <>
      <ol className="passos">
        <li><span>1</span><div><b>Baixe o modelo</b><small>Cada modelo traz instruções, listas de opções e uma linha de exemplo.</small></div></li>
        <li><span>2</span><div><b>Preencha no Excel</b><small>Uma linha por registro; as colunas obrigatórias estão marcadas.</small></div></li>
        <li><span>3</span><div><b>Envie e confira</b><small>A prévia mostra o que será criado ou atualizado; nada é gravado sem a sua confirmação.</small></div></li>
      </ol>
      <section className="card">
        <h2>Modelos de planilha</h2>
        <div className="exp-grid">{MODELOS.map(([t, ic, r]) => (
          <div key={t} className="exp-cartao"><div className="exp-ico" aria-hidden="true">{ic}</div>
            <div className="exp-corpo"><b>{r}</b><div className="exp-acoes">
              <button className="btn" onClick={() => baixar(`/api/importacao/modelo/${t}`, `modelo_${t}.xlsx`)}>⬇ Baixar modelo</button></div></div></div>))}
        </div>
      </section>
      <Card titulo="1. Selecionar arquivo">
        <div className="form-grid">
          <Campo rotulo="Arquivo (.xlsx, .csv)" ajuda={auth ? `Tamanho máximo: ${auth.limite_upload_mb} MB` : undefined}><input type="file" accept=".xlsx,.xlsm,.csv,.txt" onChange={(e) => setArquivo(e.target.files?.[0] || null)} /></Campo>
          <Campo rotulo="Tipo de dados" ajuda="Vazio = identificar pelos cabeçalhos"><select value={tipo} onChange={(e) => setTipo(e.target.value)}><option value="">Detectar automaticamente</option>{TIPOS.map(([t, r]) => <option key={t} value={t}>{r}</option>)}</select></Campo>
          <Campo rotulo="Cenário de destino (aulas)" ajuda="Somente cenários em elaboração; horários publicados nunca são sobrescritos.">
            <select value={cen} onChange={(e) => setCen(e.target.value)}><option value="">Cenário atual</option>{cenarios.filter((c) => c.estado === "em_elaboracao").map((c) => <option key={c.id} value={c.id}>{c.nome}</option>)}</select></Campo>
        </div>
        <div className="acoes"><button className="btn btn-primario" disabled={!arquivo} onClick={enviar}>Gerar prévia</button>
          {tipo && <button className="btn" onClick={() => baixar(`/api/importacao/modelo/${tipo}`, `modelo_${tipo}.xlsx`)}>Baixar modelo: {NOME_TIPO[tipo] || tipo}</button>}</div>
        <Erro erro={erro} />
      </Card>
      {previa && <>
        <Card titulo={`2. Mapeamento de colunas — ${NOME_TIPO[previa.tipo] || previa.tipo}`}>
          {previa.arquivo_ja_processado && <p className="aviso-inline"><Badge tipo="alerta">Arquivo já importado</Badge> Este arquivo (mesmo conteúdo) foi confirmado na importação #{previa.arquivo_ja_processado.importacao_id}. Registros existentes serão reconhecidos pela chave e não duplicados.</p>}
          {previa.planilhas.length > 1 && <Campo rotulo="Planilha"><select value={previa.planilha} onChange={(e) => remapear({ planilha: e.target.value })}>{previa.planilhas.map((p: string) => <option key={p}>{p}</option>)}</select></Campo>}
          <div className="form-grid">{Object.entries(previa.campos).map(([campo, info]: any) => (
            <Campo key={campo} rotulo={rotuloCampo(campo)} obrigatorio={info.obrigatorio}><select value={mapa[campo] ?? ""} onChange={(e) => setMapa({ ...mapa, [campo]: e.target.value || null })}>
              <option value="">(não importar)</option>{previa.cabecalhos.map((c: string) => <option key={c}>{c}</option>)}</select></Campo>))}</div>
          <button className="btn" onClick={() => remapear()}>Aplicar mapeamento e revalidar</button>
        </Card>
        <Card titulo="3. Prévia e validação">
          <p>{Object.entries(previa.resumo).map(([k, v]) => <Badge key={k} tipo={k === "erro" ? "bloqueio" : k === "criar" ? "ok" : "info"}>{ACOES[k] || rotuloCampo(k)}: {String(v)}</Badge>)}</p>
          <select aria-label="Filtrar ação" value={filtroAcao} onChange={(e) => setFiltroAcao(e.target.value)}><option value="">Todas as linhas</option>{["criar", "atualizar", "sem_alteracao", "erro"].map((a) => <option key={a} value={a}>{ACOES[a]}</option>)}</select>
          <Tabela colunas={[{ chave: "linha", rotulo: "Linha" }, { chave: "acao", rotulo: "Ação", render: (i: any) => <Badge tipo={i.acao === "erro" ? "bloqueio" : i.acao === "criar" ? "ok" : "info"}>{ACOES[i.acao] || i.acao}</Badge> },
            { chave: "valores", rotulo: "Valores", render: (i: any) => <small>{Object.entries(i.valores).filter(([, v]) => v != null).map(([k, v]) => `${rotuloCampo(k)}: ${v}`).join(" · ")}</small> },
            { chave: "erros", rotulo: "Erros / avisos", render: (i: any) => <small>{[...i.erros, ...i.avisos].join("; ")}</small> }]} linhas={itens.slice(0, 500)} chave={(i) => i.linha} />
          <p className="sub">Corrija o arquivo e gere nova prévia, ajuste o mapeamento, ou confirme ignorando as linhas com erro (elas constarão no relatório).</p>
          <div className="acoes"><button className="btn btn-primario" disabled={previa.resumo.erro > 0} onClick={() => confirmar(false)}>Confirmar importação</button>
            {previa.resumo.erro > 0 && <button className="btn" onClick={() => confirmar(true)}>Confirmar ignorando {previa.resumo.erro} linha(s) com erro</button>}
            <button className="btn" onClick={async () => { await api.post(`/api/importacao/${previa.id}/descartar`); setPrevia(null); hist.recarregar(); }}>Descartar</button></div>
        </Card>
      </>}
      {rel && <Card titulo="Resultado"><p>Criados: {rel.criados} · Atualizados: {rel.atualizados} · Sem alteração: {rel.sem_alteracao} · Ignorados por erro: {rel.ignorados_por_erro}</p>
        {rel.aulas_bloqueadas?.length > 0 && <><h3>Aulas bloqueadas pela validação</h3><ul>{rel.aulas_bloqueadas.map((b: any, i: number) => <li key={i}>Linha {b.linha}: {b.motivo} {(b.ocorrencias || []).map((o: any) => o.descricao).join("; ")}</li>)}</ul></>}</Card>}
      <Card titulo="Histórico de importações">
        <Tabela colunas={[{ chave: "id", rotulo: "#" }, { chave: "arquivo", rotulo: "Arquivo" }, { chave: "tipo", rotulo: "Tipo", render: (i: any) => NOME_TIPO[i.tipo] || i.tipo }, { chave: "status", rotulo: "Situação" },
          { chave: "criado_em", rotulo: "Enviado", render: (i: any) => new Date(i.criado_em).toLocaleString("pt-BR") }, { chave: "hash", rotulo: "SHA-256", render: (i: any) => <code>{i.hash.slice(0, 12)}…</code> },
          { chave: "r", rotulo: "Relatório", render: (i: any) => <>{["xlsx", "pdf"].map((f) => <button key={f} className="btn-link" onClick={() => baixar(`/api/importacao/${i.id}/relatorio?formato=${f}`, `importacao_${i.id}.${f}`)}>{f === "xlsx" ? "Excel" : "PDF"}</button>)}</> }]}
          linhas={hist.dados || []} />
      </Card>
    </>
  );
}
