import { useEffect, useMemo, useState } from "react";
import { useParams, useSearchParams } from "react-router-dom";
import { api, dataBR, DIAS, qs } from "../api";
import { Abas, Badge, Campo, Erro, fmt, Modal, Pagina, Paginacao, Tabela, useCarregar } from "../components/ui";
import { useApp } from "../contexto";
import { invalidarOpcoes, rotuloDe, useOpcoes } from "../hooks";

export type CampoMeta = { nome: string; tipo: string; obrigatorio: boolean; somente_leitura: boolean; rotulo: string; ref?: string; opcoes?: any[]; pessoal?: boolean };
export type EntMeta = { chave: string; rotulo: string; grupo: string; campos: CampoMeta[]; busca: string[]; inativavel: boolean; pk: string[] };

let metaCache: Promise<EntMeta[]> | null = null;
export function useMeta() {
  const [m, setM] = useState<EntMeta[]>([]);
  useEffect(() => { metaCache = metaCache || api.get("/api/meta/entidades"); metaCache.then(setM).catch(() => { metaCache = null; }); }, []);
  return m;
}

const RELACIONADOS: Record<string, string[]> = {
  turmas: ["turmas", "turma_ucs"],
  instrutores: ["instrutores", "competencias", "disponibilidade_instrutores", "habilitacoes", "instrutor_unidades"],
  ucs: ["ucs", "uc_recursos", "uc_prerequisitos"],
  cursos: ["cursos", "matrizes", "ucs"],
  ambientes: ["ambientes", "tipos_ambiente", "disponibilidade_ambientes", "recursos_ambientes"],
  recursos: ["recursos", "recursos_ambientes"],
  unidades: ["unidades", "calendarios", "calendario_excecoes", "bloqueios", "horarios_funcionamento", "setores", "deslocamentos"],
  turnos: ["turnos", "periodos"],
};

// Explicação curta, em linguagem simples, mostrada no topo de cada cadastro.
const AJUDA: Record<string, string> = {
  turmas: "Cada turma pertence a um curso/matriz. Ao criar a turma, as unidades curriculares da matriz são incluídas automaticamente na aba “Turma × UC” (é o que será programado).",
  turma_ucs: "Disciplinas que cada turma vai cursar. Indique aqui instrutor ou sala preferidos, se houver.",
  instrutores: "Cadastre o instrutor e, nas abas ao lado, o que ele pode ministrar (Competências) e quando está disponível (Disponibilidade). Sem competência cadastrada o sistema não o escala.",
  competencias: "Quais unidades curriculares cada instrutor está habilitado a ministrar.",
  disponibilidade_instrutores: "Dias e horários em que cada instrutor pode dar aula. Sem registros, considera-se disponível em todo o horário de funcionamento.",
  ucs: "Disciplinas da matriz: carga horária, quantas aulas por semana e o tipo de sala exigido (ex.: laboratório de informática).",
  cursos: "Cursos ofertados e suas matrizes curriculares (versões do currículo).",
  matrizes: "Versões do currículo de cada curso. Use “Nova versão” para copiar uma matriz existente.",
  ambientes: "Salas, laboratórios e oficinas: capacidade de alunos, tipo e equipamentos. O sistema só coloca a aula em sala compatível.",
  tipos_ambiente: "Categorias de sala (ex.: sala teórica, laboratório de informática) usadas para casar disciplina e sala.",
  recursos: "Equipamentos e materiais (ex.: projetor, kits). Podem ser exigidos por disciplinas.",
  unidades: "Escolas/unidades da instituição. Nas abas ao lado: calendário letivo, feriados e bloqueios.",
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

function valorCelula(c: CampoMeta, v: any) {
  if (c.tipo === "ref" && c.ref) return <CelulaRef ent={c.ref} id={v} />;
  if (c.tipo === "date") return dataBR(v);
  if (c.tipo === "dias") return (v || []).map((d: number) => DIAS[d]?.slice(0, 3)).join(", ");
  if (c.tipo === "dia") return DIAS[v] ?? v;
  if (c.tipo === "time") return v ? String(v).slice(0, 5) : "";
  return fmt(v);
}

export function Formulario({ meta, valores, setValores }: { meta: EntMeta; valores: any; setValores: (v: any) => void }) {
  const set = (k: string, v: any) => setValores({ ...valores, [k]: v });
  return (
    <div className="form-grid">
      {meta.campos.filter((c) => !c.somente_leitura && !(c.nome === "id" && meta.pk.length === 1)).map((c) => (
        <CampoEntrada key={c.nome} c={c} v={valores[c.nome]} set={(v) => set(c.nome, v)} />
      ))}
    </div>
  );
}

function CampoEntrada({ c, v, set }: { c: CampoMeta; v: any; set: (v: any) => void }) {
  const ops = useOpcoes(c.tipo === "ref" || c.tipo === "multiref" ? c.ref : null);
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
    case "enum":
      input = <select value={v ?? ""} onChange={(e) => set(e.target.value)}><option value="">—</option>{c.opcoes!.map((o) => <option key={o} value={o}>{o}</option>)}</select>;
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
  return <Campo rotulo={rotulo + (c.pessoal ? " (dado pessoal)" : "")} obrigatorio={c.obrigatorio}>{input}</Campo>;
}

export function ListaEntidade({ ent }: { ent: string }) {
  const metas = useMeta();
  const meta = metas.find((m) => m.chave === ent);
  const { pode, aviso } = useApp();
  const [sp] = useSearchParams();
  const [q, setQ] = useState("");
  const [pagina, setPagina] = useState(1);
  const [ativo, setAtivo] = useState<string>("true");
  const [filtros, setFiltros] = useState<Record<string, string>>(() => (sp.get("id") ? { id: sp.get("id")! } : {}) as Record<string, string>);
  const [edicao, setEdicao] = useState<any | null>(null);
  const [erro, setErro] = useState<any>(null);
  const [historico, setHistorico] = useState<any[] | null>(null);
  const [duplicar, setDuplicar] = useState<any | null>(null);
  useEffect(() => { setPagina(1); setFiltros((sp.get("id") ? { id: sp.get("id")! } : {}) as Record<string, string>); }, [ent, sp]);
  const lista = useCarregar(() => api.get(`/api/cadastros/${ent}${qs({ q, pagina, por_pagina: 25, ativo: meta?.inativavel ? ativo : "", ...filtros })}`),
    [ent, q, pagina, ativo, JSON.stringify(filtros), meta?.inativavel]);
  const colunas = useMemo(() => (meta?.campos || []).filter((c) => !OCULTAR_LISTA.has(c.nome) && c.tipo !== "multiref").slice(0, 9).map((c) => ({
    chave: c.nome, rotulo: c.rotulo, render: (l: any) => valorCelula(c, l[c.nome]),
  })), [meta]);
  const refsFiltro = (meta?.campos || []).filter((c) => c.tipo === "ref" || c.tipo === "enum").slice(0, 3);
  if (!meta) return <p>Carregando…</p>;

  const salvar = async () => {
    setErro(null);
    try {
      const novo = edicao.__novo;
      const corpo = { ...edicao };
      delete corpo.__novo;
      if (novo) await api.post(`/api/cadastros/${ent}`, corpo);
      else await api.put(`/api/cadastros/${ent}/${idDe(meta, edicao)}`, corpo);
      invalidarOpcoes(ent);
      aviso("Registro salvo.");
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
        {editavel && <button className="btn btn-primario" onClick={() => { setErro(null); setEdicao({ __novo: true }); }}>+ Novo</button>}
      </div>
      {lista.erro && <div className="erro-box">{lista.erro}</div>}
      <Tabela colunas={[...colunas, {
        chave: "_acoes", rotulo: "Ações", render: (l: any) => (
          <div className="acoes-linha" onClick={(e) => e.stopPropagation()}>
            {editavel && <button className="btn-link" onClick={() => { setErro(null); setEdicao({ ...l }); }}>Editar</button>}
            {editavel && meta.inativavel && <button className="btn-link" onClick={() => alternarAtivo(l)}>{l.ativo ? "Inativar" : "Reativar"}</button>}
            {editavel && !meta.inativavel && <button className="btn-link" onClick={() => excluir(l)}>Excluir</button>}
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
      }]} linhas={lista.dados?.itens || []} chave={(l) => idDe(meta, l)} />
      {lista.dados && <Paginacao pagina={pagina} total={lista.dados.total} porPagina={25} mudar={setPagina} />}
      <Modal titulo={edicao?.__novo ? `Novo — ${meta.rotulo}` : `Editar — ${meta.rotulo}`} aberto={!!edicao} fechar={() => setEdicao(null)} largo>
        {edicao && <>
          <Formulario meta={meta} valores={edicao} setValores={setEdicao} />
          {ent === "turmas" && edicao.__novo && <p className="sub">As ofertas (turma × UC) da matriz serão criadas automaticamente como “previstas”.</p>}
          <Erro erro={erro} />
          <div className="rodape-modal"><button className="btn" onClick={() => setEdicao(null)}>Cancelar</button><button className="btn btn-primario" onClick={salvar}>Salvar</button></div>
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
  const lista = c.tipo === "enum" ? (c.opcoes || []).map((o) => ({ id: o, rotulo: o })) : ops;
  return (
    <select aria-label={`Filtrar por ${c.rotulo}`} value={valor} onChange={(e) => mudar(e.target.value)}>
      <option value="">{c.rotulo}: todos</option>
      {lista.map((o) => <option key={o.id} value={o.id}>{o.rotulo}</option>)}
    </select>
  );
}

export default function Cadastro() {
  const { ent = "turmas" } = useParams();
  const metas = useMeta();
  const rel = RELACIONADOS[ent] || [ent];
  const [aba, setAba] = useState(rel[0]);
  useEffect(() => setAba(rel[0]), [ent]);
  const meta = metas.find((m) => m.chave === ent);
  return (
    <Pagina titulo={meta?.rotulo || "Cadastros"} descricao={AJUDA[ent] || "Inclua, pesquise e edite registros. Tudo é validado e fica registrado no histórico."}>
      {rel.length > 1 && <Abas abas={rel.map((r) => ({ id: r, rotulo: metas.find((m) => m.chave === r)?.rotulo || r }))} ativa={aba} mudar={setAba} />}
      {aba !== ent && AJUDA[aba] && <p className="sub">{AJUDA[aba]}</p>}
      <ListaEntidade key={aba} ent={aba} />
    </Pagina>
  );
}
