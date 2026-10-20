import { useEffect, useMemo, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { api, baixar, dataBR, DIAS, qs } from "../api";
import { Abas, Badge, Campo, Erro, fmt, Modal, Pagina, Paginacao, Tabela, useCarregar } from "../components/ui";
import { useApp } from "../contexto";
import { invalidarOpcoes, rotuloDe, useOpcoes } from "../hooks";
import { CompetenciasUCs, JornadaInstrutor, PreviaCodigoTurma } from "../components/CamposEspeciais";
import ObservacoesInstrutores from "../components/ObservacoesInstrutores";
import EstruturaCurricular from "./Cursos";
import { ControleEpis, PreviaEpis } from "../components/Epis";
import { Anel, CartaoInstrutor, PerfilInstrutor } from "../components/PerfilInstrutor";
import QuadroDisponibilidade from "../components/QuadroDisponibilidade";

export type CampoMeta = { nome: string; tipo: string; obrigatorio: boolean; somente_leitura: boolean; rotulo: string; ref?: string; opcoes?: any[]; pessoal?: boolean;
  secao?: "principal" | "avancado" | "auto"; ajuda?: string };
export type EntMeta = { chave: string; rotulo: string; grupo: string; campos: CampoMeta[]; busca: string[]; inativavel: boolean; fixa?: boolean; pk: string[] };

let metaCache: Promise<EntMeta[]> | null = null;
export function useMeta() {
  const [m, setM] = useState<EntMeta[]>([]);
  useEffect(() => { metaCache = metaCache || api.get("/api/meta/entidades"); metaCache.then(setM).catch(() => { metaCache = null; }); }, []);
  return m;
}

const RELACIONADOS: Record<string, string[]> = {
  turmas: ["turmas", "turma_ucs", "epis"],
  // certificações e matriz de competências ficam no perfil de cada instrutor (clique no cartão)
  instrutores: ["instrutores", "observacoes", "disponibilidade_instrutores"],
  ucs: ["ucs", "uc_recursos"],
  cursos: ["estrutura", "cursos", "matrizes", "ucs"],
  ambientes: ["ambientes", "tipos_ambiente", "disponibilidade_ambientes", "recursos_ambientes"],
  recursos: ["recursos", "recursos_ambientes"],
  unidades: ["unidades", "areas", "calendarios", "calendario_excecoes", "bloqueios"],
  turnos: ["turnos", "periodos"],
};

// Explicação curta, em linguagem simples, mostrada no topo de cada cadastro.
const AJUDA: Record<string, string> = {
  turmas: "Escolha o curso e digite só o número e o tipo de oferta (HTC, AIT, AIB, EMP…): o código (ex.: HTC-ELT-12), o nome, a área, a unidade e a matriz vêm do curso, e as UCs da matriz entram sozinhas na aba “Turma × UC”. As datas vêm do semestre e podem ser ajustadas ao prazo de cada turma.",
  turma_ucs: "Disciplinas que cada turma vai cursar. Indique aqui instrutor ou sala preferidos, se houver.",
  instrutores: "Clique no instrutor para abrir o perfil: visão geral, competências e certificações (marque as UCs que ele ministra), aderência aos cursos e PDI. No cadastro ficam a área, a modalidade e os turnos e dias em que pode dar aula.",
  competencias: "Quais unidades curriculares cada instrutor está habilitado a ministrar.",
  disponibilidade_instrutores: "Uma linha por instrutor: os turnos em que pode dar aula em cada dia e a carga conforme a modalidade. Mensalista tem jornada semanal fixa (aulas até 90% dela); horista recebe todo mês um termo de horas, que define as horas de aula do mês e pode mudar. Os turnos e dias se editam no cadastro do instrutor.",
  ucs: "Disciplinas da matriz: carga horária, quantas aulas por semana e o tipo de sala exigido (ex.: laboratório de informática).",
  cursos: "Escolha a área e o curso: as versões da matriz (uma por tipo de oferta, ex.: AIT ou HTC, quando o currículo muda) e as UCs de cada versão, com classificação e carga horária, ficam no mesmo lugar. A sigla do curso (ex.: ELT) entra no código das turmas: HTC-ELT-12.",
  matrizes: "Versões do currículo de cada curso. Use “Nova versão” para copiar uma matriz existente.",
  ambientes: "Salas, laboratórios e oficinas: capacidade de alunos, tipo e equipamentos. O sistema só coloca a aula em sala compatível.",
  tipos_ambiente: "Categorias de sala (ex.: sala teórica, laboratório de informática) usadas para casar disciplina e sala.",
  recursos: "Equipamentos e materiais (ex.: projetor, kits). Podem ser exigidos por disciplinas.",
  unidades: "As unidades (Beira Mar e Porto) e suas áreas são fixas da instituição. Aqui você consulta e mantém o calendário letivo, feriados e bloqueios.",
  areas: "Áreas tecnológicas de cada unidade (fixas). Cursos, turmas, instrutores e ambientes devem indicar sua área.",
  calendarios: "Período letivo de cada unidade.",
  calendario_excecoes: "Feriados, recessos e dias sem aula: o sistema não programa aulas nessas datas.",
  bloqueios: "Indisponibilidades pontuais de sala, instrutor ou turma (ex.: manutenção, evento).",
  turnos: "Turnos (manhã, tarde, noite). Na aba “Períodos”, cadastre os horários de cada aula do turno (ex.: 07:30–08:20).",
  periodos: "Horários de aula de cada turno. As aulas sempre ocupam um ou mais períodos seguidos.",
};

const OCULTAR_LISTA = new Set(["criado_em", "atualizado_em", "regras_operacionais", "restricoes", "restricoes_pedagogicas", "competencias", "maquinas",
  "requisitos_seguranca", "condicoes", "areas_competencia", "restricoes_deslocamento", "descricao"]);

function idDe(meta: EntMeta, l: any) {
  return meta.pk.map((k) => l[k]).join(":");
}

function CelulaRef({ ent, id }: { ent: string; id: any }) {
  const ops = useOpcoes(ent);
  return <>{id == null ? <span className="mudo">—</span> : rotuloDe(ops, id)}</>;
}

// rótulos amigáveis de valores de listas (o banco guarda o código)
const VALOR_ENUM: Record<string, string> = { tecnico: "Técnico (todas as modalidades)", basico: "Básico (só AIB e qualificações)",
  mensalista: "Mensalista", horista: "Horista", em_formacao: "Em formação (legado)", ferias: "Férias", manutencao: "Manutenção",
  pleno: "Sim", parcial: "Em partes", tecnica: "Técnica (só quem marcou no perfil)", transversal: "Transversal (qualquer instrutor)" };
const rotEnum = (o: any) => VALOR_ENUM[o] ?? o;
const CURTO: Record<string, string> = { tecnico: "Técnico", basico: "Básico", tecnica: "Técnica", transversal: "Transversal" };  // na lista, o rótulo curto

function valorCelula(c: CampoMeta, v: any) {
  if (c.tipo === "enum") return v == null || v === "" ? <span className="mudo">—</span> : <span title={rotEnum(v)}>{CURTO[v] ?? rotEnum(v)}</span>;
  if (c.tipo === "ref" && c.ref) return <CelulaRef ent={c.ref} id={v} />;
  if (c.tipo === "date") return dataBR(v);
  if (c.tipo === "dias") return (v || []).map((d: number) => DIAS[d]?.slice(0, 3)).join(", ");
  if (c.tipo === "dia") return DIAS[v] ?? v;
  if (c.tipo === "time") return v ? String(v).slice(0, 5) : "";
  return fmt(v);
}

const LARGOS = new Set(["multiref", "competencias", "disponibilidade", "jornada"]);

/** Formulário em seções: o essencial de cara, o resto em "Mais opções"; campos que vêm de outro cadastro não aparecem. */
export function Formulario({ meta, valores, setValores }: { meta: EntMeta; valores: any; setValores: (v: any) => void }) {
  const { unidade: unidadeTopo } = useApp();
  const temUnidade = meta.campos.some((c) => c.nome === "unidade_id");
  // com a unidade escolhida no topo, o cadastro novo já nasce nela (o campo nem aparece)
  useEffect(() => {
    if (unidadeTopo && temUnidade && !valores.unidade_id) setValores({ ...valores, unidade_id: Number(unidadeTopo) });
  }, [unidadeTopo, temUnidade, valores.unidade_id]);
  const areas = useOpcoes(meta.chave === "instrutores" || meta.chave === "ambientes" ? "areas" : null) as any[];
  const cursos = useOpcoes(meta.chave === "turmas" ? "cursos" : null) as any[];
  const set = (k: string, v: any) => {
    const n = { ...valores, [k]: v };
    // instrutor: horas por dia acompanham a carga contratual (40 h/sem = 8 h/dia = até 2 turnos), salvo ajuste manual
    if (meta.chave === "instrutores" && k === "carga_horaria_contratual" && !valores.__horas_manual && Number(v) > 0)
      n.max_horas_dia = Math.min(12, Math.max(1, Math.round(Number(v) / 5)));
    // regra dos 90%: aulas em até 9 de 10 turnos (40 h → 36 h) ou 4 de 5 (20 h → 16 h)
    if (meta.chave === "instrutores" && k === "carga_horaria_contratual" && Number(v) > 0) {
      const teto = Math.floor(Math.floor(Number(v) / 4) * 0.9 + 1e-9) * 4;
      if (teto > 0 && (!n.limite_ch_letiva || Number(n.limite_ch_letiva) > teto)) n.limite_ch_letiva = teto;
    }
    if (meta.chave === "instrutores" && (k === "carga_horaria_contratual" || k === "max_horas_dia") && n.jornada) {
      const dois = Number(n.max_horas_dia) >= 8;
      if (dois !== (n.jornada.length === 2)) { n.jornada = ""; n.__disp = true; }  // a jornada antiga não vale mais: escolher de novo
    }
    if (k === "max_horas_dia") n.__horas_manual = true;
    // instrutor e sala: a unidade é a da área principal
    if (k === "area_id" && (meta.chave === "instrutores" || meta.chave === "ambientes")) {
      const a = areas.find((x: any) => String(x.id) === String(v));
      if (a?.unidade_id) n.unidade_id = a.unidade_id;
    }
    // turma: a unidade (e os turnos possíveis) vêm do curso
    if (k === "curso_id" && meta.chave === "turmas") {
      const c = cursos.find((x: any) => String(x.id) === String(v));
      if (c?.unidade_id && String(c.unidade_id) !== String(valores.unidade_id)) { n.unidade_id = c.unidade_id; n.turno_id = ""; }
    }
    setValores(n);
  };
  const setVarios = (o: Record<string, any>) => setValores({ ...valores, ...o });
  const unidadeAuto = meta.chave === "instrutores" || meta.chave === "ambientes";
  const editaveis = meta.campos.filter((c) => !c.somente_leitura && !(c.nome === "id" && meta.pk.length === 1) && c.secao !== "auto"
    && !(valores.todas_areas && (c.nome === "area_id" || c.nome === "areas_ids"))
    && !(unidadeAuto && c.nome === "unidade_id" && !valores.todas_areas)
    && !(unidadeTopo && c.nome === "unidade_id"));
  // unidade de contexto (para listar só turnos e áreas da unidade certa)
  const unidadeCtx = valores.unidade_id || (meta.chave === "turmas" ? cursos.find((x: any) => String(x.id) === String(valores.curso_id))?.unidade_id : undefined);
  const render = (c: CampoMeta) => {
    if (c.tipo === "competencias") return <CompetenciasUCs key={c.nome} valores={valores} set={(v) => set("ucs_competencia", v)} />;
    if (c.tipo === "jornada") return <JornadaInstrutor key={c.nome} valores={valores} setVarios={setVarios} />;
    return <CampoEntrada key={c.nome} c={c} v={valores[c.nome]} set={(v) => set(c.nome, v)} unidadeId={unidadeCtx}
      excluir={c.nome === "areas_ids" ? valores.area_id : undefined} />;
  };
  const principais = editaveis.filter((c) => (c.secao || "principal") === "principal");
  const avancados = editaveis.filter((c) => c.secao === "avancado");
  return (
    <>
      <div className="form-grid">{principais.filter((c) => !LARGOS.has(c.tipo)).map(render)}</div>
      {meta.chave === "turmas" && <PreviaCodigoTurma valores={valores} />}
      {principais.filter((c) => LARGOS.has(c.tipo)).map((c) => <div key={c.nome} className="campo-largo">{render(c)}</div>)}
      {avancados.length > 0 && <details className="mais-opcoes">
        <summary>Mais opções <small className="mudo">({avancados.length} campos opcionais)</small></summary>
        <div className="form-grid">{avancados.filter((c) => !LARGOS.has(c.tipo)).map(render)}</div>
        {avancados.filter((c) => LARGOS.has(c.tipo)).map((c) => <div key={c.nome} className="campo-largo">{render(c)}</div>)}
      </details>}
    </>
  );
}

/** Valores iniciais de um registro novo (ex.: turma já com as datas do semestre selecionado). */
function novoPadrao(ent: string, cenario: any): any {
  if (ent === "turmas") return { dias_possiveis: [0, 1, 2, 3, 4], data_inicio: cenario?.periodo_inicio || "", data_fim: cenario?.periodo_fim || "" };
  if (ent === "instrutores") return { carga_horaria_contratual: 40, max_horas_dia: 8, limite_ch_letiva: 36, disp_dias: [0, 1, 2, 3, 4], ucs_competencia: [] };
  return {};
}

function CampoEntrada({ c, v, set, unidadeId, excluir }: { c: CampoMeta; v: any; set: (v: any) => void; unidadeId?: any; excluir?: any }) {
  const todas = useOpcoes(c.tipo === "ref" || c.tipo === "multiref" ? c.ref : null);
  // a área precisa ser da mesma unidade do cadastro
  const { unidade: unidadeTopo } = useApp();
  const unidadesOps = useOpcoes(c.nome === "area_id" && !unidadeTopo ? "unidades" : null);
  const porUnidade = (c.ref === "areas" && c.nome !== "area_id") || c.ref === "turnos" || c.ref === "periodos";
  const ops = (porUnidade && unidadeId ? todas.filter((o: any) => String(o.unidade_id) === String(unidadeId)) : todas)
    .filter((o: any) => excluir == null || String(o.id) !== String(excluir))
    // área principal: todas as áreas, com a unidade (a unidade do cadastro vem dela)
    .map((o: any) => c.nome === "area_id" && o.unidade_id && !unidadeTopo ? { ...o, rotulo: `${o.rotulo} – ${(unidadesOps.find((u) => u.id === o.unidade_id)?.rotulo || "").replace("Unidade ", "")}` } : o);
  const rotulo = c.rotulo;
  let input;
  switch (c.tipo) {
    case "bool":
      input = <input type="checkbox" checked={!!v} onChange={(e) => set(e.target.checked)} />;
      break;
    case "int": case "number":
      input = <input type="number" step={c.tipo === "int" ? 1 : "any"} value={v ?? ""} onChange={(e) => set(e.target.value)} />;
      break;
    case "date":
      input = <input type="date" value={v ? String(v).slice(0, 10) : ""} onChange={(e) => set(e.target.value)} />;
      break;
    case "datetime":
      input = <input type="datetime-local" value={v ? String(v).slice(0, 16) : ""} onChange={(e) => set(e.target.value)} />;
      break;
    case "time":
      input = <input type="time" value={v ? String(v).slice(0, 5) : ""} onChange={(e) => set(e.target.value)} />;
      break;
    case "text":
      input = <textarea rows={2} value={v ?? ""} onChange={(e) => set(e.target.value)} />;
      break;
    case "oferta":
      input = <><input list={`lista-${c.nome}`} value={v ?? ""} placeholder="HTC, AIT, AIB, EMP…" onChange={(e) => set(e.target.value.toUpperCase())} />
        <datalist id={`lista-${c.nome}`}>{(c.opcoes || []).map((o: any) => <option key={o.valor} value={o.valor}>{o.rotulo}</option>)}</datalist></>;
      break;
    case "enum":
      input = <select value={v ?? ""} onChange={(e) => set(e.target.value)}><option value="">—</option>{c.opcoes!.map((o) => <option key={o} value={o}>{rotEnum(o)}</option>)}</select>;
      break;
    case "dia":
      input = <select value={v ?? ""} onChange={(e) => set(e.target.value)}><option value="">—</option>{DIAS.map((d, i) => <option key={i} value={i}>{d}</option>)}</select>;
      break;
    case "dias": {
      const sel: number[] = v || [];
      input = <div className="checks">{DIAS.map((d, i) => (
        <label key={i}><input type="checkbox" checked={sel.includes(i)} onChange={(e) => set(e.target.checked ? [...sel, i].sort() : sel.filter((x) => x !== i))} /> {d.slice(0, 3)}</label>))}</div>;
      break;
    }
    case "ref":
      input = <select value={v ?? ""} onChange={(e) => set(e.target.value)}><option value="">—</option>{ops.map((o) => <option key={o.id} value={o.id}>{o.rotulo}</option>)}</select>;
      break;
    case "multiref": {
      const sel: number[] = (v || []).map(Number);
      input = <div className="checks">{ops.map((o) => (
        <label key={o.id}><input type="checkbox" checked={sel.includes(Number(o.id))} onChange={(e) => set(e.target.checked ? [...sel, Number(o.id)] : sel.filter((x) => x !== Number(o.id)))} /> {o.rotulo}</label>))}</div>;
      break;
    }
    default:
      input = <input type="text" value={v ?? ""} onChange={(e) => set(e.target.value)} />;
  }
  return <Campo rotulo={rotulo + (c.pessoal ? " (dado pessoal)" : "")} obrigatorio={c.obrigatorio || c.nome === "_numero"} ajuda={c.ajuda}>{input}</Campo>;
}

export function ListaEntidade({ ent }: { ent: string }) {
  const metas = useMeta();
  const meta = metas.find((m) => m.chave === ent);
  const { pode, aviso, cenario, auth, unidade: unidadeTopo } = useApp();
  const [sp] = useSearchParams();
  const [q, setQ] = useState("");
  const [pagina, setPagina] = useState(1);
  const [ativo, setAtivo] = useState<string>("true");
  const [filtros, setFiltros] = useState<Record<string, string>>(() => (sp.get("id") ? { id: sp.get("id")! } : {}) as Record<string, string>);
  const [edicao, setEdicao] = useState<any | null>(null);
  const [erro, setErro] = useState<any>(null);
  const [historico, setHistorico] = useState<any[] | null>(null);
  const [duplicar, setDuplicar] = useState<any | null>(null);
  const [acesso, setAcesso] = useState<any | null>(null);
  const [perfil, setPerfil] = useState<number | null>(null);
  const [visao, setVisao] = useState<"cartoes" | "tabela">("cartoes");
  const equipe = useCarregar<any>(() => (ent === "instrutores" ? api.get("/api/aderencia/equipe") : Promise.resolve(null)), [ent, unidadeTopo]);
  const adPor: Record<number, any> = useMemo(() => Object.fromEntries((equipe.dados?.instrutores || []).map((x: any) => [x.instrutor_id, x])), [equipe.dados]);
  const resumo = useCarregar<any>(() => (ent === "instrutores" ? api.get(`/api/instrutores/resumo${qs({ cenario_id: cenario?.id })}`) : Promise.resolve(null)), [ent, unidadeTopo, cenario?.id]);
  const [ordem, setOrdem] = useState("nome");
  const [rapido, setRapido] = useState("");
  useEffect(() => { setPagina(1); setFiltros((sp.get("id") ? { id: sp.get("id")! } : {}) as Record<string, string>); }, [ent, sp]);
  const porPagina = ent === "instrutores" ? 60 : 25;
  const lista = useCarregar(() => api.get(`/api/cadastros/${ent}${qs({ q, pagina, por_pagina: porPagina, ativo: meta?.inativavel ? ativo : "", ...filtros })}`),
    [ent, q, pagina, ativo, JSON.stringify(filtros), meta?.inativavel]);
  // ?id=…&editar=1 (vindo de outra aba, ex.: disponibilidade): abre a edição do registro
  useEffect(() => {
    const itens = lista.dados?.itens;
    if (sp.get("editar") && sp.get("id") && itens?.length === 1 && String(itens[0].id) === sp.get("id") && !edicao) setEdicao({ ...itens[0] });
  }, [lista.dados]);
  const colunas = useMemo(() => [...(meta?.campos || [])].sort((a, b) => Number(!["codigo", "matricula", "nome"].includes(a.nome)) - Number(!["codigo", "matricula", "nome"].includes(b.nome))).filter((c) => !OCULTAR_LISTA.has(c.nome) && !LARGOS.has(c.tipo) && !c.nome.startsWith("_") && c.tipo !== "oferta")
    .filter((c) => !(unidadeTopo && c.nome === "unidade_id"))  // unidade já escolhida no topo: coluna redundante
    .slice(0, 9).map((c) => ({
    chave: c.nome, rotulo: c.rotulo, render: (l: any) => valorCelula(c, l[c.nome]),
  })), [meta, unidadeTopo]);
  const refsFiltro = (meta?.campos || []).filter((c) => (c.tipo === "ref" || c.tipo === "enum") && !(unidadeTopo && c.nome === "unidade_id")).slice(0, 3);
  if (!meta) return <p>Carregando…</p>;

  const salvar = async () => {
    setErro(null);
    try {
      const novo = edicao.__novo;
      if (ent === "instrutores" && (edicao.__novo || edicao.__disp) && !edicao.jornada && !edicao.disp_personalizada) {
        setErro(new Error("Escolha os turnos de trabalho do instrutor (M, V ou N; com 40 h, MV ou VN).")); return;
      }
      const corpo = { ...edicao };
      delete corpo.__novo;
      if (!corpo.__disp) { delete corpo.disp_turnos; delete corpo.disp_dias; delete corpo.jornada; }  // só regrava a disponibilidade se foi alterada
      delete corpo.__disp;
      delete corpo.__horas_manual;
      const salvo = novo ? await api.post(`/api/cadastros/${ent}`, corpo) : await api.put(`/api/cadastros/${ent}/${idDe(meta, edicao)}`, corpo);
      invalidarOpcoes(ent);
      if (ent === "turmas" && novo) {
        const ep = await api.get(`/api/epis-turmas?turma_id=${salvo.id}`).catch(() => null);
        const cfg = await api.get(`/api/cursos/${salvo.curso_id}/epi-config`).catch(() => null);
        aviso(ep?.itens?.length ? `Turma ${salvo.codigo} criada. ${ep.itens.length} EPI(s) do curso entraram no controle de entregas (menu EPIs das turmas).`
          : cfg?.dispensa_epi ? `Turma ${salvo.codigo} criada (o curso não precisa de EPI).`
          : `Turma ${salvo.codigo} criada. O curso ainda não tem lista de EPIs: monte-a em EPIs das turmas → Lista de EPIs por curso.`);
      } else aviso("Registro salvo.");
      setEdicao(null);
      lista.recarregar();
    } catch (e) { setErro(e); }
  };
  const alternarAtivo = async (l: any) => {
    const motivo = l.ativo ? prompt("Motivo da inativação (opcional):") : null;
    try {
      await api.post(`/api/cadastros/${ent}/${idDe(meta, l)}/${l.ativo ? "inativar" : "reativar"}`, { motivo });
      invalidarOpcoes(ent);
      lista.recarregar();
    } catch (e: any) { aviso(e.message, "erro"); }
  };
  const excluir = async (l: any) => {
    if (!confirm("Excluir este vínculo?")) return;
    try { await api.del(`/api/cadastros/${ent}/${idDe(meta, l)}`); lista.recarregar(); } catch (e: any) { aviso(e.message, "erro"); }
  };
  const verHistorico = async (l: any) => setHistorico(await api.get(`/api/cadastros/${ent}/${idDe(meta, l)}/historico`));
  const editavel = pode("cadastros.editar");

  return (
    <div>
      <div className="filtros">
        <input type="search" placeholder={`Pesquisar ${meta.busca.join(", ") || ""}`} aria-label="Pesquisar" value={q} onChange={(e) => { setQ(e.target.value); setPagina(1); }} />
        {meta.inativavel && (
          <select aria-label="Situação" value={ativo} onChange={(e) => setAtivo(e.target.value)}>
            <option value="true">Ativos</option><option value="false">Inativos</option><option value="">Todos</option>
          </select>
        )}
        {refsFiltro.map((c) => <FiltroRef key={c.nome} c={c} valor={filtros[c.nome] || ""} mudar={(v) => { setFiltros({ ...filtros, [c.nome]: v }); setPagina(1); }} />)}
        {filtros.id && <button className="chip" onClick={() => setFiltros({})}>Registro #{filtros.id} ✕</button>}
        {editavel && !meta.fixa && <button className="btn btn-primario" onClick={() => { setErro(null); setEdicao({ __novo: true, ...novoPadrao(ent, cenario) }); }}>+ Novo</button>}
        {meta.fixa && <span className="sub">🔒 Cadastro fixo da instituição: não é possível incluir, excluir ou renomear.</span>}
      </div>
      {lista.erro && <div className="erro-box">{lista.erro}</div>}
      {ent === "instrutores" && equipe.dados && <ResumoEquipe e={equipe.dados} visao={visao} setVisao={setVisao} itens={lista.dados?.itens || []} r={resumo.dados || {}} />}
      {ent === "instrutores" && visao === "cartoes" && <div className="ci-barra">
        <div className="ci-rapidos" role="group" aria-label="Filtro rápido">
          {[["", "Todos"], ["alertas", "⚠ Com alertas"], ["mensalista", "Mensalistas"], ["horista", "Horistas"], ["pdi", "Com PDI em aberto"]].map(([k, rot]) => (
            <button key={k} className={`chip-filtro ${rapido === k ? "on" : ""}`} onClick={() => setRapido(k)}>{rot}</button>))}
        </div>
        <label className="mudo">Ordenar por <select value={ordem} onChange={(e) => setOrdem(e.target.value)} aria-label="Ordenar instrutores">
          <option value="nome">Nome</option><option value="aderencia_menor">Menor aderência</option><option value="aderencia_maior">Maior aderência</option>
          <option value="ocupacao_maior">Mais aulas na semana</option><option value="ocupacao_menor">Menos aulas na semana</option><option value="alertas">Alertas primeiro</option>
        </select></label>
      </div>}
      {ent === "instrutores" && visao === "cartoes" ? <div className="grade-inst">
        {ordenarInstrutores((lista.dados?.itens || []).filter((l: any) => {
          const r = resumo.dados?.[l.id];
          return !rapido || (rapido === "alertas" ? r?.alertas?.length : rapido === "pdi" ? r?.pdi?.abertos : l.modalidade === rapido);
        }), ordem, adPor, resumo.dados || {}).map((l: any) => <CartaoInstrutor key={l.id} l={l} ad={adPor[l.id]} r={resumo.dados?.[l.id]} abrir={() => setPerfil(l.id)}
          acoes={<>
            {editavel && <button className="btn-link" onClick={() => { setErro(null); setEdicao({ ...l }); }}>Editar</button>}
            {!l._acesso_portal && pode("usuarios.gerenciar") && <button className="btn-link" onClick={() => setAcesso({ id: l.id, nome: l.nome, email: l.email || "", senha: "" })}>Acesso ao portal</button>}
            <button className="btn-link" onClick={() => verHistorico(l)}>Histórico</button>
            {editavel && <button className="btn-link ci-inativar" onClick={() => alternarAtivo(l)}>{l.ativo ? "Inativar" : "Reativar"}</button>}
          </>} />)}
        {lista.dados && !lista.dados.itens.filter((l: any) => { const r = resumo.dados?.[l.id];
          return !rapido || (rapido === "alertas" ? r?.alertas?.length : rapido === "pdi" ? r?.pdi?.abertos : l.modalidade === rapido); }).length &&
          <div className="ci-vazio">{rapido === "alertas" ? "✔ Nenhum instrutor com alerta: disponibilidade, certificações, termos e PDI em dia." : "Nenhum instrutor neste filtro."}</div>}
      </div> : <Tabela colunas={[...(ent === "instrutores" ? [{
        chave: "_ader", rotulo: "Aderência", render: (l: any) => adPor[l.id] ? <button className="btn-link sem-sublinhado" onClick={(e) => { e.stopPropagation(); setPerfil(l.id); }}>
          <Anel valor={adPor[l.id].geral} tamanho={40} /></button> : "—",
      }] : []), ...colunas, {
        chave: "_acoes", rotulo: "Ações", render: (l: any) => (
          <div className="acoes-linha" onClick={(e) => e.stopPropagation()}>
            {editavel && ent !== "areas" && <button className="btn-link" onClick={() => { setErro(null); setEdicao({ ...l }); }}>Editar</button>}
            {editavel && meta.inativavel && <button className="btn-link" onClick={() => alternarAtivo(l)}>{l.ativo ? "Inativar" : "Reativar"}</button>}
            {editavel && !meta.inativavel && !meta.fixa && <button className="btn-link" onClick={() => excluir(l)}>Excluir</button>}
            {ent === "instrutores" && (l._acesso_portal
              ? <Badge tipo="ok">portal ✓</Badge>
              : pode("usuarios.gerenciar") && <button className="btn-link" onClick={() => setAcesso({ id: l.id, nome: l.nome, email: l.email || "", senha: "" })}>Acesso ao portal</button>)}
            {ent === "instrutores" && l.atualizado_pelo_instrutor_em && <Badge tipo="info">atualizado pelo instrutor em {new Date(l.atualizado_pelo_instrutor_em).toLocaleDateString("pt-BR")}</Badge>}
            {editavel && ent === "turmas" && <button className="btn-link" onClick={() => setDuplicar({ id: l.id, codigo: `${l.codigo}-COPIA`, nome: `${l.nome} (cópia)` })}>Duplicar</button>}
            {editavel && ent === "matrizes" && <button className="btn-link" onClick={async () => {
              const v = prompt("Identificação da nova versão da matriz:");
              if (!v) return;
              try { await api.post(`/api/cadastros/matrizes/${l.id}/nova_versao`, { versao: v }); aviso("Nova versão criada (UCs, competências e requisitos copiados)."); lista.recarregar(); }
              catch (e: any) { aviso(e.message, "erro"); }
            }}>Nova versão</button>}
            {l.id != null && <button className="btn-link" onClick={() => verHistorico(l)}>Histórico</button>}
            {meta.inativavel && !l.ativo && <Badge tipo="alerta">inativo</Badge>}
          </div>
        ),
      }]} linhas={lista.dados?.itens || []} chave={(l) => idDe(meta, l)} aoClicar={ent === "instrutores" ? (l: any) => setPerfil(l.id) : undefined} />}
      {ent === "instrutores" && <PerfilInstrutor id={perfil} fechar={() => { setPerfil(null); equipe.recarregar(); resumo.recarregar(); }}
        editar={editavel ? () => { const l = (lista.dados?.itens || []).find((x: any) => x.id === perfil); setPerfil(null); if (l) { setErro(null); setEdicao({ ...l }); } } : undefined} />}
      {lista.dados && <Paginacao pagina={pagina} total={lista.dados.total} porPagina={porPagina} mudar={setPagina} />}
      <Modal titulo={edicao?.__novo ? `Novo — ${meta.rotulo}` : `Editar — ${meta.rotulo}`} aberto={!!edicao} fechar={() => setEdicao(null)} largo>
        {edicao && <>
          <Formulario meta={meta} valores={edicao} setValores={setEdicao} />
          {ent === "turmas" && edicao.__novo && <p className="sub">As ofertas (turma × UC) da matriz serão criadas automaticamente como “previstas”.</p>}
          {ent === "turmas" && <PreviaEpis cursoId={edicao.curso_id} alunos={edicao.qtd_alunos} inicio={edicao.data_inicio} />}
          <Erro erro={erro} />
          <div className="rodape-modal"><button className="btn" onClick={() => setEdicao(null)}>Cancelar</button><button className="btn btn-primario" onClick={salvar}>Salvar</button></div>
        </>}
      </Modal>
      <Modal titulo={`Acesso ao portal — ${acesso?.nome || ""}`} aberto={!!acesso} fechar={() => setAcesso(null)}>
        {acesso && <>
          <p className="sub">O instrutor entra com este e-mail e só vê os próprios dados, turmas e horários. O que ele atualizar aparece direto neste cadastro.</p>
          <Campo rotulo="E-mail de login" obrigatorio><input type="email" value={acesso.email} onChange={(e) => setAcesso({ ...acesso, email: e.target.value })} /></Campo>
          {auth?.modo === "supabase" ? <p className="sub">Ele recebe um convite por e-mail para criar a própria senha.</p> :
            <Campo rotulo="Senha inicial" obrigatorio ajuda="Mínimo de 8 caracteres. Entregue ao instrutor; ele pode trocá-la no menu do perfil.">
              <input type="text" autoComplete="off" value={acesso.senha} onChange={(e) => setAcesso({ ...acesso, senha: e.target.value })} /></Campo>}
          <div className="rodape-modal"><button className="btn" onClick={() => setAcesso(null)}>Cancelar</button><button className="btn btn-primario" onClick={async () => {
            try {
              const r = await api.post(`/api/instrutores/${acesso.id}/acesso`, { email: acesso.email, senha: acesso.senha });
              aviso(r.convite ? (r.convite.enviado ? "Convite enviado por e-mail." : `Acesso criado; convite não enviado: ${r.convite.erro}`) : "Acesso criado. Informe o e-mail e a senha inicial ao instrutor.");
              setAcesso(null); lista.recarregar();
            } catch (e: any) { aviso(e.message, "erro"); }
          }}>Liberar acesso</button></div>
        </>}
      </Modal>
      <Modal titulo="Duplicar turma" aberto={!!duplicar} fechar={() => setDuplicar(null)}>
        {duplicar && <>
          <Campo rotulo="Novo código" obrigatorio><input value={duplicar.codigo} onChange={(e) => setDuplicar({ ...duplicar, codigo: e.target.value })} /></Campo>
          <Campo rotulo="Novo nome"><input value={duplicar.nome} onChange={(e) => setDuplicar({ ...duplicar, nome: e.target.value })} /></Campo>
          <div className="rodape-modal"><button className="btn btn-primario" onClick={async () => {
            try { await api.post(`/api/cadastros/turmas/${duplicar.id}/duplicar`, { codigo: duplicar.codigo, nome: duplicar.nome }); aviso("Turma duplicada; edite os parâmetros antes de gerar horários."); setDuplicar(null); lista.recarregar(); }
            catch (e: any) { aviso(e.message, "erro"); }
          }}>Duplicar</button></div>
        </>}
      </Modal>
      <Modal titulo="Histórico de alterações" aberto={!!historico} fechar={() => setHistorico(null)} largo>
        <Tabela colunas={[{ chave: "em", rotulo: "Quando", render: (h: any) => new Date(h.em).toLocaleString("pt-BR") }, { chave: "usuario", rotulo: "Usuário" },
          { chave: "acao", rotulo: "Ação" }, { chave: "motivo", rotulo: "Motivo" },
          { chave: "dif", rotulo: "Alterações", render: (h: any) => <Diferenca antes={h.antes} depois={h.depois} /> }]} linhas={historico || []} chave={(_h, i) => i} />
      </Modal>
    </div>
  );
}

export function Diferenca({ antes, depois }: { antes: any; depois: any }) {
  if (!antes) return <small>{depois ? "registro criado" : ""}</small>;
  const ch = Object.keys(depois || {}).filter((k) => JSON.stringify(antes?.[k]) !== JSON.stringify(depois?.[k]) && k !== "atualizado_em");
  return <small>{ch.map((k) => <div key={k}><b>{k}</b>: {fmt(antes?.[k])} → {fmt(depois?.[k])}</div>)}</small>;
}

function FiltroRef({ c, valor, mudar }: { c: CampoMeta; valor: string; mudar: (v: string) => void }) {
  const ops = useOpcoes(c.tipo === "ref" ? c.ref : null);
  const lista = c.tipo === "enum" ? (c.opcoes || []).map((o) => ({ id: o, rotulo: rotEnum(o) })) : ops;
  return (
    <select aria-label={`Filtrar por ${c.rotulo}`} value={valor} onChange={(e) => mudar(e.target.value)}>
      <option value="">{c.rotulo}: todos</option>
      {lista.map((o) => <option key={o.id} value={o.id}>{o.rotulo}</option>)}
    </select>
  );
}

const ROTULO_ABA: Record<string, string> = { disponibilidade_instrutores: "Disponibilidade e termos de horas", observacoes: "💬 Observações dos instrutores", estrutura: "Por área e curso", epis: "🦺 EPIs das turmas", cursos: "Lista de cursos",
  matrizes: "Lista de versões", ucs: "Lista de UCs" };

/** Explica o portal do instrutor e, no login pelo Supabase, convida todos os instrutores com e-mail de uma vez. */
function AcessosPortal() {
  const { pode, auth, aviso } = useApp();
  const [r, setR] = useState<any>(null);
  if (!pode("usuarios.gerenciar")) return null;
  return (
    <div className="importar-rapido">
      <div><b>Portal do instrutor</b><br /><small className="mudo">Cada instrutor pode entrar com o próprio login para atualizar áreas, UCs, disponibilidade e certificações,
        ver as turmas e horários dele e enviar observações. Use “Acesso ao portal” na linha do instrutor.</small>
        {r && <><br /><small>{r.criados.length} convite(s) enviado(s){r.falhas.length ? ` · ${r.falhas.length} sem convite: ${r.falhas.map((f: any) => `${f.instrutor} (${f.motivo})`).join("; ")}` : ""}</small></>}</div>
      {auth?.modo === "supabase" && <button className="btn btn-primario" onClick={async () => {
        if (!confirm("Enviar convite por e-mail a todos os instrutores ativos com e-mail e ainda sem acesso?")) return;
        try { setR(await api.post("/api/instrutores/acessos-em-lote")); } catch (e: any) { aviso(e.message, "erro"); }
      }}>Convidar todos com e-mail</button>}
    </div>
  );
}

const IMPORTACAO: Record<string, { tipo: string; titulo: string; texto: string }> = {
  cursos: { tipo: "estrutura_curricular", titulo: "Cadastre tudo por planilha", texto: "Uma linha por UC: o curso, a matriz e as UCs são criados e ligados automaticamente." },
  ucs: { tipo: "estrutura_curricular", titulo: "Cadastre tudo por planilha", texto: "Uma linha por UC: o curso, a matriz e as UCs são criados e ligados automaticamente." },
  ambientes: { tipo: "ambientes", titulo: "Cadastre as salas por planilha", texto: "Uma linha por sala/laboratório, com tipo, capacidade e áreas (ou TODAS)." },
  instrutores: { tipo: "levantamento_instrutores", titulo: "Levantamento de instrutores", texto: "Uma linha por instrutor: áreas, turnos e dias disponíveis, UCs que ministra e certificações." },
  turmas: { tipo: "turmas", titulo: "Cadastre as turmas por planilha", texto: "Uma linha por turma; as UCs da matriz são ligadas automaticamente." },
};

export default function Cadastro() {
  const { ent = "turmas" } = useParams();
  const { pode } = useApp();
  const metas = useMeta();
  const rel = RELACIONADOS[ent] || [ent];
  const [sp] = useSearchParams();
  const abaUrl = sp.get("aba");
  const [aba, setAba] = useState(abaUrl && rel.includes(abaUrl) ? abaUrl : rel[0]);
  const [versao, setVersao] = useState(0);
  useEffect(() => setAba(abaUrl && rel.includes(abaUrl) ? abaUrl : rel[0]), [ent, abaUrl]);
  const meta = metas.find((m) => m.chave === ent);
  return (
    <Pagina titulo={meta?.rotulo || "Cadastros"} descricao={AJUDA[ent] || "Inclua, pesquise e edite registros. Tudo é validado e fica registrado no histórico."}>
      {rel.length > 1 && <Abas abas={rel.filter((r) => r !== "observacoes" || pode("observacoes.gerenciar"))
        .map((r) => ({ id: r, rotulo: ROTULO_ABA[r] || metas.find((m) => m.chave === r)?.rotulo || r }))} ativa={aba} mudar={setAba} />}
      {aba !== ent && AJUDA[aba] && <p className="sub">{AJUDA[aba]}</p>}
      {IMPORTACAO[ent] && aba !== "observacoes" && pode("importacao.executar") && <div className="importar-rapido">
        <div><b>{IMPORTACAO[ent].titulo}</b><br /><small className="mudo">{IMPORTACAO[ent].texto}</small></div>
        <button className="btn" onClick={() => baixar(`/api/importacao/modelo/${IMPORTACAO[ent].tipo}`, `modelo_${IMPORTACAO[ent].tipo}.xlsx`)}>Baixar modelo</button>
        <Link className="btn btn-primario" to={`/importacao?tipo=${IMPORTACAO[ent].tipo}`}>Importar planilha</Link>
      </div>}
      {aba === "turnos" && <TurnosPadrao aoCriar={() => setVersao((v) => v + 1)} />}
      {ent === "instrutores" && aba === "instrutores" && <AcessosPortal />}
      {aba === "observacoes" ? <ObservacoesInstrutores /> : aba === "estrutura" ? <EstruturaCurricular /> : aba === "epis" ? <ControleEpis /> : aba === "disponibilidade_instrutores" ? <QuadroDisponibilidade /> : <ListaEntidade key={`${aba}-${versao}`} ent={aba} />}
    </Pagina>
  );
}

/** Atalho: cria manhã, tarde e noite com 4 aulas cada (padrão da instituição) numa unidade sem turnos. */
function TurnosPadrao({ aoCriar }: { aoCriar: () => void }) {
  const { pode, aviso, unidade: unidadeTopo } = useApp();
  const unidades = useOpcoes("unidades");
  const [u, setU] = useState(unidadeTopo);
  if (!pode("cadastros.editar")) return null;
  return (
    <div className="card turnos-padrao">
      <b>Unidade nova?</b> Crie de uma vez os turnos padrão: manhã 07:30–11:30 e tarde 13:30–17:30 (4 aulas de 55 min, intervalos 09:20–09:40 e 15:20–15:40)
      e noite 18:30–22:00 (4 aulas de 50 min, intervalo 20:10–20:20).
      <div className="filtros">
        {!unidadeTopo && <select aria-label="Unidade" value={u} onChange={(e) => setU(e.target.value)}><option value="">Escolha a unidade…</option>
          {unidades.map((x) => <option key={x.id} value={x.id}>{x.rotulo}</option>)}</select>}
        <button className="btn btn-primario" disabled={!u} onClick={async () => {
          try { const r = await api.post(`/api/unidades/${u}/turnos-padrao`); aviso(r.mensagem); invalidarOpcoes("turnos"); invalidarOpcoes("periodos"); setU(unidadeTopo); aoCriar(); }
          catch (e: any) { aviso(e.message, "erro"); }
        }}>Criar turnos padrão{unidadeTopo ? ` em ${(unidades.find((x) => String(x.id) === unidadeTopo)?.rotulo || "").replace(/^Unidade\s+/i, "")}` : ""}</button>
      </div>
    </div>
  );
}

/** Topo da lista de instrutores: média de aderência da equipe, a troca cartões/tabela e a cobertura das UCs por área. */
function ResumoEquipe({ e, visao, setVisao, itens, r }: { e: any; visao: string; setVisao: (v: any) => void; itens: any[]; r: Record<number, any> }) {
  const horistas = itens.filter((l) => l.modalidade === "horista").length;
  const ocup = itens.map((l) => r[l.id]?.semestre?.pct_contrato).filter((x) => x != null) as number[];
  const media = ocup.length ? ocup.reduce((a, b) => a + b, 0) / ocup.length : null;
  const comAlerta = itens.filter((l) => r[l.id]?.alertas?.length).length;
  const pdi = itens.reduce((t, l) => t + (r[l.id]?.pdi?.abertos || 0), 0);
  const umSo = e.cobertura.reduce((t: number, c: any) => t + c.um_so, 0);
  const ninguem = e.cobertura.reduce((t: number, c: any) => t + c.sem_ninguem, 0);
  return (
    <>
      <div className="resumo-equipe">
        <div className="re-media"><Anel valor={e.media} tamanho={56} rotulo="Aderência média" /><div><b>Aderência média da equipe</b>
          <small className="mudo">Clique em um instrutor para ver o perfil, a aderência por curso e o PDI.</small></div></div>
        <div className="re-kpis">
          <div><b>{itens.length}</b><small>instrutores</small><span className="mudo">{itens.length - horistas} mensalistas · {horistas} horistas</span></div>
          <div><b>{media == null ? "—" : `${media.toLocaleString("pt-BR", { maximumFractionDigits: 1 })}%`}</b><small>ocupação média</small><span className="mudo">aulas sobre o contrato</span></div>
          <div className={comAlerta ? "re-alerta" : ""}><b>{comAlerta}</b><small>com alertas</small><span className="mudo">cadastro, certificação, termo</span></div>
          <div><b>{pdi}</b><small>itens de PDI</small><span className="mudo">em aberto</span></div>
        </div>
        <div className="re-visao" role="group" aria-label="Forma de exibir">
          <button className={`btn ${visao === "cartoes" ? "btn-primario" : ""}`} onClick={() => setVisao("cartoes")}>▦ Cartões</button>
          <button className={`btn ${visao === "tabela" ? "btn-primario" : ""}`} onClick={() => setVisao("tabela")}>☰ Tabela</button>
        </div>
      </div>
      {e.por_area?.length > 0 && <div className="re-areas">
        <span className="re-areas-tit"><b>Aderência por área</b><small className="mudo">média dos instrutores que atuam nela</small></span>
        <div className="re-areas-lista">
          {e.por_area.map((a: any) => (
            <div key={a.area_id} className="re-area-card" title={`${a.instrutores} instrutor(es) · ${a.principais} com a área como principal · ${a.com_100} com 100%`}>
              <Anel valor={a.media} tamanho={46} rotulo={`Aderência em ${a.area}`} />
              <span><b>{a.area.includes("/") ? a.area : a.area.charAt(0) + a.area.slice(1).toLowerCase()}</b><small className="mudo">{a.instrutores} instrutor(es){a.com_100 ? ` · ${a.com_100} com 100%` : ""}</small></span>
            </div>
          ))}
        </div>
      </div>}
      <details className="cobertura">
        <summary>
          <span className="cob-seta" aria-hidden="true">▸</span>
          <b>Cobertura das UCs por área</b>
          <span className="mudo">quantas UCs técnicas têm instrutor reserva (2 ou mais habilitados)</span>
          <span className="cob-resumo">
            {ninguem > 0 && <Badge tipo="bloqueio">{ninguem} UC(s) sem ninguém</Badge>}
            {umSo > 0 ? <Badge tipo="alerta">{umSo} UC(s) dependem de uma pessoa só</Badge> : !ninguem && <Badge tipo="ok">todas com reserva</Badge>}
          </span>
        </summary>
        <p className="sub">Quando só um instrutor pode dar a UC, uma falta, licença ou treinamento dele deixa a turma sem aula. A barra mostra, em cada área,
          as UCs <span className="leg leg-ok">com reserva</span>, as que <span className="leg leg-um">dependem de 1 pessoa</span> e as
          <span className="leg leg-zero"> sem ninguém</span>. Clique na área para ver quais UCs e quem as dá — o PDI de cada instrutor sugere quem habilitar.</p>
        <div className="cob-grade">
          {e.cobertura.map((c: any) => <AreaCobertura key={c.area_id} c={c} />)}
        </div>
      </details>
    </>
  );
}

function AreaCobertura({ c }: { c: any }) {
  const [aberta, setAberta] = useState(false);
  const pct = (n: number) => `${(100 * n) / (c.ucs || 1)}%`;
  const ok = !c.um_so && !c.sem_ninguem;
  return (
    <div className={`cob-area ${ok ? "cob-ok" : ""}`}>
      <button className="cob-cab" onClick={() => setAberta(!aberta)} aria-expanded={aberta} disabled={ok}>
        <span className="cob-nome"><b>{c.area}</b><small className="mudo">{c.ucs} UC(s) técnica(s)</small></span>
        <span className="cob-barra" role="img" aria-label={`${c.duas_ou_mais} com reserva, ${c.um_so} com uma pessoa só, ${c.sem_ninguem} sem ninguém`}>
          <span className="cb-ok" style={{ width: pct(c.duas_ou_mais) }} /><span className="cb-um" style={{ width: pct(c.um_so) }} /><span className="cb-zero" style={{ width: pct(c.sem_ninguem) }} />
        </span>
        <span className="cob-txt">{ok ? <span className="ok-txt">✓ todas com reserva</span> : <>
          {c.sem_ninguem > 0 && <span className="falta-txt">{c.sem_ninguem} sem ninguém</span>}
          {c.sem_ninguem > 0 && c.um_so > 0 && " · "}
          {c.um_so > 0 && <span className="alerta-txt">{c.um_so} com 1 só</span>}
          <span className="mudo"> {aberta ? "▾" : "▸"}</span></>}</span>
      </button>
      {aberta && <ul className="cob-ucs">
        {c.criticas.map((u: any) => (
          <li key={`${u.curso}-${u.uc}`}><span className={`cb-ponto ${u.habilitados.length ? "cb-um" : "cb-zero"}`} />
            <span><b>{u.uc}</b> {u.nome} <small className="mudo">({u.curso})</small></span>
            <small>{u.habilitados.length ? <>só <b>{u.habilitados[0]}</b></> : <span className="falta-txt">ninguém habilitado</span>}</small></li>
        ))}
      </ul>}
    </div>
  );
}

function ordenarInstrutores(itens: any[], ordem: string, ad: Record<number, any>, r: Record<number, any>) {
  const g = (l: any) => ad[l.id]?.geral ?? 0, o = (l: any) => r[l.id]?.semestre?.media_semanal_h ?? 0, a = (l: any) => r[l.id]?.alertas?.length ?? 0;
  const f: Record<string, (x: any, y: any) => number> = {
    aderencia_menor: (x, y) => g(x) - g(y), aderencia_maior: (x, y) => g(y) - g(x), ocupacao_maior: (x, y) => o(y) - o(x),
    ocupacao_menor: (x, y) => o(x) - o(y), alertas: (x, y) => a(y) - a(x),
  };
  return f[ordem] ? [...itens].sort((x, y) => f[ordem](x, y) || String(x.nome).localeCompare(String(y.nome))) : itens;
}
