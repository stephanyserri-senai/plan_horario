import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api, dataBR } from "../api";
import { Badge, Erro, Modal, useCarregar } from "../components/ui";
import { useApp } from "../contexto";
import { invalidarOpcoes } from "../hooks";
import { Formulario, useMeta, type EntMeta } from "./Cadastro";
import { EpisDoCurso } from "../components/Epis";

const SITUACAO: Record<string, string> = { vigente: "ok", rascunho: "alerta", encerrada: "neutro" };
const aulas = (ch: number, min: number) => Math.ceil((ch * 60) / min - 1e-9);

/** Formulário de um cadastro sem os campos que a navegação já define (ex.: a UC já está dentro da versão). */
function semCampos(meta: EntMeta | undefined, fixos: string[]): EntMeta | undefined {
  return meta && { ...meta, campos: meta.campos.filter((c) => !fixos.includes(c.nome)) };
}

type Edicao = { ent: "cursos" | "matrizes" | "ucs"; valores: any; fixos: string[]; titulo: string; copiarDe?: number };

/** Cursos, matrizes e UCs por área: área → curso → versão (por tipo de oferta) → UCs, com classificação e carga horária. */
export default function EstruturaCurricular({ visao = "estrutura" }: { visao?: string }) {
  const { pode, aviso } = useApp();
  const metas = useMeta();
  // navegação: áreas → cursos da área → curso (versões e UCs); fica no endereço (?area=…&curso=…) para voltar e compartilhar
  const [sp, setSp] = useSearchParams();
  const area = sp.get("area") || "";
  const cursoId = sp.get("curso") ? Number(sp.get("curso")) : null;
  const ir = (a: string | number | null, c: number | null, v: number | null = null) => {
    const n = new URLSearchParams(sp);
    if (a) n.set("area", String(a)); else n.delete("area");
    if (c) n.set("curso", String(c)); else n.delete("curso");
    if (v) n.set("versao", String(v)); else n.delete("versao");
    if (visao !== "estrutura") n.set("aba", "estrutura");  // das listas: abre o item na navegação
    setSp(n);
    setVersaoId(v);
    window.scrollTo({ top: 0, behavior: "smooth" });
  };
  const [busca, setBusca] = useState("");
  const [versaoId, setVersaoId] = useState<number | null>(null);
  const [edicao, setEdicao] = useState<Edicao | null>(null);
  const [erro, setErro] = useState<any>(null);
  const [rev, setRev] = useState(0);  // recarrega as listas depois de salvar
  const arv = useCarregar<any[]>(() => api.get("/api/estrutura-curricular"), []);
  const editavel = pode("cadastros.editar");

  const areas = arv.dados || [];
  const todosCursos = useMemo(() => areas.flatMap((a: any) => a.cursos.map((c: any) => ({ ...c, area: a }))), [areas]);
  const cursos = todosCursos.filter((c: any) => !busca || `${c.codigo} ${c.nome}`.toLowerCase().includes(busca.toLowerCase()));
  const curso = todosCursos.find((c: any) => c.id === cursoId) || null;
  const areaAtual = areas.find((a: any) => String(a.id) === area) || curso?.area || null;
  const versao = curso?.versoes.find((v: any) => v.id === versaoId) || null;
  // ao trocar de curso, abre a versão vigente (ou a primeira)
  useEffect(() => {
    const pedida = Number(sp.get("versao")) || null;
    if (curso && !versao) setVersaoId((curso.versoes.find((v: any) => v.id === pedida) || curso.versoes.find((v: any) => v.situacao === "vigente") || curso.versoes[0])?.id ?? null);
  }, [curso?.id, curso?.versoes.length]);
  const ucs = useCarregar<any>(() => versaoId ? api.get(`/api/estrutura-curricular/versoes/${versaoId}`) : Promise.resolve(null), [versaoId]);

  const abrirUC = async (u?: any) => {
    setErro(null);
    const valores = u ? await api.get(`/api/cadastros/ucs/${u.id}`) : { __novo: true, matriz_id: versaoId, categoria: "tecnica", encontros_semanais: 2, sequencia: (ucs.dados?.ucs.length || 0) + 1 };
    setEdicao({ ent: "ucs", valores, fixos: ["matriz_id"], titulo: u ? `Editar UC — ${u.codigo}` : `Nova UC — ${curso.codigo} ${rotVersao(versao)}` });
  };
  const salvar = async () => {
    if (!edicao) return;
    setErro(null);
    const { __novo, ...corpo } = edicao.valores;
    try {
      let r: any;
      if (edicao.copiarDe) r = await api.post(`/api/cadastros/matrizes/${edicao.copiarDe}/nova_versao`, corpo);
      else if (__novo) r = await api.post(`/api/cadastros/${edicao.ent}`, corpo);
      else r = await api.put(`/api/cadastros/${edicao.ent}/${corpo.id}`, corpo);
      invalidarOpcoes(edicao.ent);
      aviso(edicao.copiarDe ? "Nova versão criada com as UCs copiadas." : "Registro salvo.");
      if (edicao.ent === "cursos" && __novo) ir(r.area_id || area, r.id);
      if (edicao.ent === "matrizes") setVersaoId(r.id);
      setEdicao(null);
      arv.recarregar();
      ucs.recarregar();
      setRev((x) => x + 1);
    } catch (e) { setErro(e); }
  };
  const inativarUC = async (u: any) => {
    if (!confirm(`Retirar a UC ${u.codigo} desta versão? Ela deixa de ser oferecida às turmas novas (o histórico fica guardado).`)) return;
    try { await api.post(`/api/cadastros/ucs/${u.id}/inativar`, { motivo: "Retirada da versão da matriz" }); invalidarOpcoes("ucs"); ucs.recarregar(); arv.recarregar(); }
    catch (e: any) { aviso(e.message, "erro"); }
  };
  const meta = metas.find((m) => m.chave === edicao?.ent);

  const novoCurso = () => { setErro(null); setEdicao({ ent: "cursos", fixos: [], titulo: "Novo curso",
    valores: { __novo: true, area_id: areaAtual ? areaAtual.id : "", modalidade: "presencial" } }); };
  const totalUcs = ucs.dados?.ucs.reduce((t: number, u: any) => t + u.carga_horaria_total, 0) || 0;
  const modal = (
    <Modal titulo={edicao?.titulo || ""} aberto={!!edicao} fechar={() => setEdicao(null)} largo>
      {edicao && meta && <>
        <Formulario meta={semCampos(meta, edicao.fixos)!} valores={edicao.valores} setValores={(v) => setEdicao({ ...edicao, valores: v })} />
        <Erro erro={erro} />
        <div className="rodape-modal"><button className="btn" onClick={() => setEdicao(null)}>Cancelar</button><button className="btn btn-primario" onClick={salvar}>Salvar</button></div>
      </>}
    </Modal>
  );
  const editarCurso = async (c: any) => { setErro(null); setEdicao({ ent: "cursos", fixos: [], titulo: `Editar curso — ${c.codigo}`, valores: await api.get(`/api/cadastros/cursos/${c.id}`) }); };
  const editarVersao = async (v: any) => { setErro(null); setEdicao({ ent: "matrizes", fixos: ["curso_id", "matriz_origem_id"], titulo: `Versão ${v.versao}`, valores: await api.get(`/api/cadastros/matrizes/${v.id}`) }); };
  const listas: PropsLista = { areas, cursos: todosCursos, abrir: ir, editarCurso, editarVersao, editarUC: abrirUC, novoCurso, editavel, rev,
    mudou: () => { arv.recarregar(); setRev((x) => x + 1); } };
  if (visao !== "estrutura") return (
    <div className="cur">
      {arv.carregando && !arv.dados && <p role="status">Carregando…</p>}
      {arv.erro && <div className="erro-box">{arv.erro}</div>}
      {arv.dados && visao === "cursos" && <ListaCursos {...listas} />}
      {arv.dados && visao === "matrizes" && <ListaVersoes {...listas} />}
      {arv.dados && visao === "ucs" && <ListaUcs {...listas} />}
      {modal}
    </div>
  );
  return (
    <div className="cur">
      <nav className="cur-trilha" aria-label="Caminho">
        <button className={!areaAtual && !curso ? "atual" : ""} onClick={() => ir(null, null)}>📚 Todas as áreas</button>
        {areaAtual && <><span aria-hidden="true">›</span><button className={!curso ? "atual" : ""} onClick={() => ir(areaAtual.id, null)}>{icone(areaAtual.nome)} {nomeArea(areaAtual.nome)}</button></>}
        {curso && <><span aria-hidden="true">›</span><span className="atual">{curso.codigo} – {curso.nome}</span></>}
        <span className="cur-trilha-acoes">
          <input type="search" placeholder="🔎 Buscar curso ou sigla em todas as áreas" aria-label="Buscar curso" value={busca} onChange={(e) => setBusca(e.target.value)} />
          {editavel && <button className="btn btn-primario" onClick={novoCurso}>+ Novo curso</button>}
        </span>
      </nav>
      {arv.carregando && !arv.dados && <p role="status">Carregando…</p>}
      {arv.erro && <div className="erro-box">{arv.erro}</div>}

      {busca && <div className="cur-grade">
        {cursos.map((c: any) => <CartaoCurso key={c.id} c={c} abrir={() => { setBusca(""); ir(c.area.id, c.id); }} mostrarArea />)}
        {!cursos.length && <div className="cur-vazio">Nenhum curso com “{busca}”.</div>}
      </div>}

      {!busca && !areaAtual && !curso && arv.dados && <>
        <p className="sub">Escolha a área para ver os cursos; no curso ficam as versões da matriz (uma por tipo de oferta, ex.: AIT ou HTC) e as UCs.</p>
        <div className="cur-grade">
          {areas.map((a: any) => {
            const turmas = a.cursos.reduce((t: number, c: any) => t + c.turmas_ativas.length, 0);
            const ucsA = a.cursos.reduce((t: number, c: any) => t + (c.versoes[0]?.ucs || 0), 0);
            return (
              <button key={a.id} className="cur-area" onClick={() => ir(a.id, null)}>
                <span className="cur-icone" aria-hidden="true">{icone(a.nome)}</span>
                <span className="cur-area-nome"><b>{nomeArea(a.nome)}</b><small className="mudo">{a.unidade}</small></span>
                <span className="cur-nums">
                  <span><b>{a.cursos.length}</b><small>curso(s)</small></span>
                  <span><b>{turmas}</b><small>turma(s) ativa(s)</small></span>
                  <span><b>{a.instrutores}</b><small>instrutor(es)</small></span>
                </span>
                <span className="cur-siglas">{a.cursos.slice(0, 6).map((c: any) => <span key={c.id} className="cur-sigla">{c.codigo}</span>)}
                  {!a.cursos.length && <small className="mudo">sem cursos ainda</small>}{ucsA > 0 && <small className="mudo">{ucsA} UCs</small>}</span>
              </button>
            );
          })}
        </div>
      </>}

      {!busca && areaAtual && !curso && <>
        <div className="cur-cab-area">
          <span className="cur-icone grande" aria-hidden="true">{icone(areaAtual.nome)}</span>
          <div><h3>{nomeArea(areaAtual.nome)}</h3><small className="mudo">{areaAtual.unidade} · {areaAtual.cursos.length} curso(s) · {areaAtual.instrutores} instrutor(es) na área</small></div>
        </div>
        <div className="cur-grade">
          {areaAtual.cursos.map((c: any) => <CartaoCurso key={c.id} c={c} abrir={() => ir(areaAtual.id, c.id)} />)}
          {editavel && <button className="cur-curso cur-novo" onClick={novoCurso}><span className="cur-icone">＋</span><b>Novo curso em {nomeArea(areaAtual.nome)}</b>
            <small className="mudo">Depois crie a matriz e cadastre as UCs aqui mesmo.</small></button>}
          {!areaAtual.cursos.length && !editavel && <div className="cur-vazio">Nenhum curso nesta área.</div>}
        </div>
      </>}

      {!busca && curso && <section className="cur-detalhe">
        <div className="cur-cab">
          <span className="cur-sigla grande">{curso.codigo}</span>
          <div className="cur-cab-txt">
            <h3>{curso.nome}</h3>
            <small className="mudo">{[curso.tipo, curso.modalidade].filter(Boolean).join(" · ")}</small>
          </div>
          <div className="cur-nums">
            <span><b>{curso.carga_horaria_total || "—"}</b><small>h no curso</small></span>
            <span><b>{curso.versoes.length}</b><small>versão(ões)</small></span>
            <span><b>{curso.turmas_ativas.length}</b><small>turma(s) ativa(s)</small></span>
            <span><b>{curso.dispensa_epi ? "—" : curso.epis}</b><small>{curso.dispensa_epi ? "não usa EPI" : "EPI(s)"}</small></span>
          </div>
          {editavel && <button className="btn" onClick={async () => { setErro(null); setEdicao({ ent: "cursos", fixos: [], titulo: `Editar curso — ${curso.codigo}`, valores: await api.get(`/api/cadastros/cursos/${curso.id}`) }); }}>Editar curso</button>}
        </div>
        {curso.turmas_ativas.length > 0 && <div className="cur-turmas"><small className="mudo">Turmas em andamento:</small>
          {curso.turmas_ativas.map((t: string) => <span key={t} className="chip-area">{t}</span>)}</div>}

        <h4 className="cur-sec">Versões da matriz <small className="mudo">— uma por tipo de oferta quando o currículo muda (ex.: AIT e HTC)</small></h4>
        <div className="versoes" role="tablist" aria-label="Versões da matriz">
          {curso.versoes.map((v: any) => (
            <button key={v.id} role="tab" aria-selected={v.id === versaoId} className={`versao ${v.id === versaoId ? "ativa" : ""}`} onClick={() => setVersaoId(v.id)}>
              <b>{v.tipo_oferta || "Todas as ofertas"}</b> <span>versão {v.versao}</span>
              <small><Badge tipo={SITUACAO[v.situacao] || "info"}>{v.situacao}</Badge> {v.ucs} UC(s) · {v.ch_total} h{v.turmas ? ` · ${v.turmas} turma(s)` : ""}</small>
            </button>))}
          {editavel && <button className="versao versao-nova" onClick={() => { setErro(null); setEdicao(versao
            ? { ent: "matrizes", fixos: ["curso_id", "matriz_origem_id", "situacao"], titulo: `Nova versão de ${curso.codigo} (copia as UCs da ${rotVersao(versao)})`, copiarDe: versao.id,
                valores: { __novo: true, versao: "", tipo_oferta: "", vigencia_inicio: "" } }
            : { ent: "matrizes", fixos: ["curso_id", "matriz_origem_id"], titulo: `Matriz de ${curso.codigo}`,
                valores: { __novo: true, curso_id: curso.id, versao: String(new Date().getFullYear()), situacao: "vigente" } }); }}>
            + {versao ? "Nova versão" : "Criar a matriz"}
            <small>{versao ? "copia as UCs da versão aberta; ex.: uma para AIT e outra para HTC" : "depois cadastre as UCs"}</small>
          </button>}
        </div>

        {!versao && curso.versoes.length === 0 && <div className="cur-vazio">Este curso ainda não tem matriz. Crie a matriz e cadastre as UCs aqui mesmo.</div>}
        {versao && <>
          <div className="cursos-barra">
            <span className="sub">{versao.tipo_oferta ? `Versão própria das turmas ${versao.tipo_oferta}.` : "Vale para todas as ofertas sem versão própria."}
              {versao.vigencia_inicio ? ` Vigente desde ${dataBR(versao.vigencia_inicio)}.` : ""}
              {ucs.dados?.em_uso_por_turmas ? ` Usada por ${ucs.dados.em_uso_por_turmas} turma(s).` : ""}</span>
            <span className="acoes-linha">
              {editavel && <button className="btn-link" onClick={async () => { setErro(null); setEdicao({ ent: "matrizes", fixos: ["curso_id", "matriz_origem_id"], titulo: `Versão ${versao.versao}`, valores: await api.get(`/api/cadastros/matrizes/${versao.id}`) }); }}>Editar versão</button>}
              {editavel && <button className="btn btn-primario" onClick={() => abrirUC()}>+ Nova UC</button>}
            </span>
          </div>
          {ucs.erro && <div className="erro-box">{ucs.erro}</div>}
          {ucs.dados && <div className="ucs-resumo">
            <span><b>{ucs.dados.ucs.length}</b> UC(s)</span><span><b>{totalUcs}</b> h no total</span>
            <span><b>{ucs.dados.ucs.filter((u: any) => u.categoria !== "transversal").length}</b> técnica(s)</span>
            <span><b>{ucs.dados.ucs.filter((u: any) => u.categoria === "transversal").length}</b> transversal(is)</span>
            <span><b>{ucs.dados.ucs.filter((u: any) => u.certificacao_exigida).length}</b> exigem certificação</span>
          </div>}
          <ol className="ucs-lista">
            {(ucs.dados?.ucs || []).map((u: any) => (
              <li key={u.id} className="uc-linha">
                <span className="uc-seq">{u.sequencia}</span>
                <span className="uc-id"><b>{u.codigo}</b> {u.nome}
                  <span className="uc-tags">{u.categoria === "transversal"
                    ? <span title="Qualquer instrutor pode dar"><Badge tipo="info">Transversal</Badge></span>
                    : <span title="Só quem marcou a UC no perfil"><Badge tipo="neutro">Técnica</Badge></span>}
                    {u.certificacao_exigida && <span className="chip-area ca-vence">🎓 exige {u.certificacao_exigida}</span>}
                    <span className="chip-area">🏫 {u.tipos_ambiente.join(", ") || "qualquer sala"}</span></span></span>
                <span className="uc-ch"><b>{u.carga_horaria_total} h</b>
                  <span className="barra-pct fina"><span className="barra-pct-v bp-neutro" style={{ width: `${totalUcs ? (100 * u.carga_horaria_total) / totalUcs : 0}%` }} /></span>
                  <small className="mudo" title="Cada aula vale 55 min de dia e 50 min à noite; o que falta vira outra aula">{aulas(u.carga_horaria_total, 55)} aulas (dia) · {aulas(u.carga_horaria_total, 50)} (noite) · {u.encontros_semanais} dia(s)/sem</small></span>
                {editavel && <span className="uc-acoes"><button className="btn-link" onClick={() => abrirUC(u)}>Editar</button>
                  <button className="btn-link" onClick={() => inativarUC(u)}>Retirar</button></span>}
              </li>
            ))}
          </ol>
          {ucs.dados && !ucs.dados.ucs.length && <div className="cur-vazio">Nenhuma UC nesta versão. Use “+ Nova UC”.</div>}
        </>}
        <EpisDoCurso cursoId={curso.id} editavel={editavel} />
      </section>}
      {modal}
    </div>
  );
}

/** Cartão de curso: sigla, nome, tipo, carga, versões da matriz e turmas em andamento. */
function CartaoCurso({ c, abrir, mostrarArea }: { c: any; abrir: () => void; mostrarArea?: boolean }) {
  const ucs = c.versoes.reduce((m: number, v: any) => Math.max(m, v.ucs), 0);
  return (
    <button className="cur-curso" onClick={abrir}>
      <span className="cur-curso-topo"><span className="cur-sigla">{c.codigo}</span>
        {mostrarArea && <small className="mudo">{icone(c.area.nome)} {nomeArea(c.area.nome)}</small>}</span>
      <b className="cur-curso-nome">{c.nome}</b>
      <small className="mudo">{[c.tipo, c.modalidade, c.carga_horaria_total ? `${c.carga_horaria_total} h` : null].filter(Boolean).join(" · ")}</small>
      <span className="cur-versoes">{c.versoes.length ? c.versoes.map((v: any) => <span key={v.id} className={`chip-area ${v.situacao === "vigente" ? "ca-principal" : ""}`}>
        {v.tipo_oferta || "todas"} · v{v.versao}</span>) : <span className="chip-area ca-vence">sem matriz</span>}</span>
      <span className="cur-rodape"><span>📘 {ucs} UC(s)</span><span>👥 {c.turmas_ativas.length} turma(s)</span>
        <span>{c.dispensa_epi ? "🦺 não usa EPI" : `🦺 ${c.epis} EPI(s)`}</span></span>
    </button>
  );
}

const ICONES: [RegExp, string][] = [[/energ|elétr|eletr/i, "⚡"], [/automaç/i, "🤖"], [/automot/i, "🚗"], [/mecatr/i, "🦾"], [/mecân/i, "⚙️"],
  [/instrument/i, "📟"], [/log[ií]st/i, "📦"], [/porto/i, "⚓"], [/dds|ti\b|inform|sistem/i, "💻"], [/criativ|design|gráf/i, "🎨"], [/gest|admin/i, "📊"],
  [/química|quimic/i, "🧪"], [/construç|civil/i, "🏗️"], [/alimen/i, "🍞"], [/segur/i, "🦺"]];
function icone(nome: string) { return (ICONES.find(([r]) => r.test(nome || "")) || [null, "📚"])[1]; }
function nomeArea(n: string) { return n && n === n.toUpperCase() && !n.includes("/") ? n.charAt(0) + n.slice(1).toLowerCase() : n; }

// ---------------------------------------------------------------------------- listas (mesmo estilo da navegação)
type PropsLista = {
  areas: any[]; cursos: any[]; abrir: (a: any, c: number | null, v?: number | null) => void; editarCurso: (c: any) => void; editarVersao: (v: any) => void;
  editarUC: (u?: any) => void; novoCurso: () => void; editavel: boolean; rev: number; mudou: () => void;
};

function Chips({ op, valor, mudar }: { op: [string, string][]; valor: string; mudar: (v: string) => void }) {
  return <div className="ci-rapidos" role="group">{op.map(([k, rot]) => <button key={k} className={`chip-filtro ${valor === k ? "on" : ""}`} onClick={() => mudar(k)}>{rot}</button>)}</div>;
}

function FiltroArea({ areas, valor, mudar }: { areas: any[]; valor: string; mudar: (v: string) => void }) {
  return <select aria-label="Área" value={valor} onChange={(e) => mudar(e.target.value)}>
    <option value="">Todas as áreas</option>{areas.map((a: any) => <option key={a.id} value={a.id}>{icone(a.nome)} {nomeArea(a.nome)}</option>)}</select>;
}

/** Lista de cursos: uma linha por curso (sigla, nome, área, versões, UCs, turmas, EPIs) — clique abre na navegação. */
function ListaCursos({ areas, cursos, abrir, editarCurso, novoCurso, editavel, rev, mudou }: PropsLista) {
  const { aviso } = useApp();
  const [q, setQ] = useState("");
  const [area, setArea] = useState("");
  const [filtro, setFiltro] = useState("");
  const inativos = useCarregar<any>(() => (filtro === "inativos" ? api.get("/api/cadastros/cursos?ativo=false&por_pagina=500") : Promise.resolve(null)), [filtro, rev]);
  const lista = cursos.filter((c: any) => (!area || String(c.area.id) === area) && (!q || `${c.codigo} ${c.nome}`.toLowerCase().includes(q.toLowerCase()))
    && (filtro !== "sem_matriz" || !c.versoes.length) && (filtro !== "com_turmas" || c.turmas_ativas.length));
  const inativar = async (c: any, ativar = false) => {
    if (!ativar && !confirm(`Inativar o curso ${c.codigo}? Ele sai das listas e das turmas novas (o histórico fica guardado).`)) return;
    try { await api.post(`/api/cadastros/cursos/${c.id}/${ativar ? "reativar" : "inativar"}`, {}); invalidarOpcoes("cursos"); aviso(ativar ? "Curso reativado." : "Curso inativado."); mudou(); }
    catch (e: any) { aviso(e.message, "erro"); }
  };
  return (
    <>
      <div className="lst-barra">
        <input type="search" placeholder="🔎 Sigla ou nome do curso" aria-label="Pesquisar curso" value={q} onChange={(e) => setQ(e.target.value)} />
        <FiltroArea areas={areas} valor={area} mudar={setArea} />
        <Chips valor={filtro} mudar={setFiltro} op={[["", "Ativos"], ["com_turmas", "Com turmas"], ["sem_matriz", "Sem matriz"], ["inativos", "Inativos"]]} />
        {editavel && <button className="btn btn-primario" onClick={novoCurso}>+ Novo curso</button>}
      </div>
      {filtro !== "inativos" && <div className="ucs-resumo"><span><b>{lista.length}</b> curso(s)</span>
        <span><b>{lista.reduce((t: number, c: any) => t + c.turmas_ativas.length, 0)}</b> turma(s) ativa(s)</span>
        <span><b>{lista.filter((c: any) => !c.versoes.length).length}</b> sem matriz</span></div>}
      <ul className="lst">
        {filtro !== "inativos" && lista.map((c: any) => (
          <li key={c.id} className="lst-linha" onClick={() => abrir(c.area.id, c.id)}>
            <span className="cur-sigla">{c.codigo}</span>
            <span className="lst-id"><b>{c.nome}</b><small className="mudo">{[c.tipo, c.modalidade, c.carga_horaria_total ? `${c.carga_horaria_total} h` : null].filter(Boolean).join(" · ")}</small></span>
            <span className="chip-area">{icone(c.area.nome)} {nomeArea(c.area.nome)}</span>
            <span className="cur-versoes">{c.versoes.length ? c.versoes.map((v: any) => <span key={v.id} className={`chip-area ${v.situacao === "vigente" ? "ca-principal" : ""}`}>{v.tipo_oferta || "todas"} · v{v.versao}</span>)
              : <span className="chip-area ca-vence">sem matriz</span>}</span>
            <span className="lst-nums"><span title="UCs na versão vigente">📘 {c.versoes.reduce((m: number, v: any) => Math.max(m, v.ucs), 0)}</span>
              <span title="Turmas em andamento">👥 {c.turmas_ativas.length}</span><span title="EPIs do curso">🦺 {c.dispensa_epi ? "—" : c.epis}</span></span>
            <span className="lst-acoes" onClick={(e) => e.stopPropagation()}>
              {editavel && <button className="btn-link" onClick={() => editarCurso(c)}>Editar</button>}
              {editavel && <button className="btn-link lst-discreto" onClick={() => inativar(c)}>Inativar</button>}
              <button className="btn btn-pequeno" onClick={() => abrir(c.area.id, c.id)}>Abrir ›</button>
            </span>
          </li>
        ))}
        {filtro === "inativos" && (inativos.dados?.itens || []).map((c: any) => (
          <li key={c.id} className="lst-linha inativo">
            <span className="cur-sigla">{c.codigo}</span>
            <span className="lst-id"><b>{c.nome}</b><small className="mudo">inativo</small></span>
            <span /><span /><span />
            <span className="lst-acoes">{editavel && <button className="btn btn-pequeno" onClick={() => inativar(c, true)}>Reativar</button>}</span>
          </li>
        ))}
      </ul>
      {((filtro !== "inativos" && !lista.length) || (filtro === "inativos" && inativos.dados && !inativos.dados.itens.length)) &&
        <div className="cur-vazio">Nenhum curso {filtro === "inativos" ? "inativo" : "com esses filtros"}.</div>}
    </>
  );
}

/** Lista de versões da matriz: curso, tipo de oferta, situação, vigência, UCs e turmas — clique abre a versão no curso. */
function ListaVersoes({ areas, cursos, abrir, editarVersao, editavel }: PropsLista) {
  const [q, setQ] = useState("");
  const [area, setArea] = useState("");
  const [sit, setSit] = useState("");
  const versoes = cursos.flatMap((c: any) => c.versoes.map((v: any) => ({ ...v, curso: c })))
    .filter((v: any) => (!area || String(v.curso.area.id) === area) && (!sit || v.situacao === sit)
      && (!q || `${v.curso.codigo} ${v.curso.nome} ${v.versao} ${v.tipo_oferta || ""}`.toLowerCase().includes(q.toLowerCase())));
  return (
    <>
      <div className="lst-barra">
        <input type="search" placeholder="🔎 Curso, versão ou oferta (ex.: HTC)" aria-label="Pesquisar versão" value={q} onChange={(e) => setQ(e.target.value)} />
        <FiltroArea areas={areas} valor={area} mudar={setArea} />
        <Chips valor={sit} mudar={setSit} op={[["", "Todas"], ["vigente", "Vigentes"], ["rascunho", "Rascunho"], ["encerrada", "Encerradas"]]} />
      </div>
      <p className="sub">Cada curso tem uma matriz e, quando o currículo muda para um tipo de oferta (ex.: AIT ou HTC), uma versão própria. Para criar uma versão,
        abra o curso e use “+ Nova versão” (copia as UCs).</p>
      <ul className="lst">
        {versoes.map((v: any) => (
          <li key={v.id} className="lst-linha" onClick={() => abrir(v.curso.area.id, v.curso.id, v.id)}>
            <span className="cur-sigla">{v.curso.codigo}</span>
            <span className="lst-id"><b>{v.tipo_oferta ? `Versão ${v.tipo_oferta}` : "Todas as ofertas"} · {v.versao}</b><small className="mudo">{v.curso.nome}</small></span>
            <span><Badge tipo={SITUACAO[v.situacao] || "info"}>{v.situacao}</Badge></span>
            <span className="mudo lst-peq">{v.vigencia_inicio ? `desde ${dataBR(v.vigencia_inicio)}` : "sem data de vigência"}</span>
            <span className="lst-nums"><span title="UCs">📘 {v.ucs}</span><span title="Carga horária">⏱ {v.ch_total} h</span><span title="Turmas que usam a versão">👥 {v.turmas}</span></span>
            <span className="lst-acoes" onClick={(e) => e.stopPropagation()}>
              {editavel && <button className="btn-link" onClick={() => editarVersao(v)}>Editar</button>}
              <button className="btn btn-pequeno" onClick={() => abrir(v.curso.area.id, v.curso.id, v.id)}>Abrir ›</button>
            </span>
          </li>
        ))}
      </ul>
      {!versoes.length && <div className="cur-vazio">Nenhuma versão com esses filtros.</div>}
    </>
  );
}

/** Lista de UCs de todos os cursos: classificação, carga, sala, certificação, quantos instrutores podem dar e turmas. */
function ListaUcs({ areas, abrir, editarUC, editavel, rev, mudou }: PropsLista) {
  const { aviso } = useApp();
  const [q, setQ] = useState("");
  const [area, setArea] = useState("");
  const [filtro, setFiltro] = useState("");
  const [limite, setLimite] = useState(80);
  const ativas = filtro !== "retiradas";
  const r = useCarregar<any[]>(() => api.get(`/api/estrutura-curricular/ucs?ativas=${ativas}`), [ativas, rev]);
  const todas = r.dados || [];
  const lista = todas.filter((u: any) => (!area || String(u.area_id) === area)
    && (!q || `${u.codigo} ${u.nome} ${u.curso} ${u.curso_nome}`.toLowerCase().includes(q.toLowerCase()))
    && (filtro !== "tecnica" || u.categoria !== "transversal") && (filtro !== "transversal" || u.categoria === "transversal")
    && (filtro !== "cert" || u.certificacao_exigida) && (filtro !== "fragil" || (u.habilitados != null && u.habilitados <= 1)));
  const maxCh = Math.max(1, ...lista.map((u: any) => u.carga_horaria_total));
  const retirar = async (u: any, reativar = false) => {
    if (!reativar && !confirm(`Retirar a UC ${u.codigo} da versão ${u.versao}${u.tipo_oferta ? ` (${u.tipo_oferta})` : ""} de ${u.curso}? O histórico fica guardado.`)) return;
    try { await api.post(`/api/cadastros/ucs/${u.id}/${reativar ? "reativar" : "inativar"}`, { motivo: reativar ? undefined : "Retirada da versão da matriz" });
      invalidarOpcoes("ucs"); aviso(reativar ? "UC de volta à versão." : "UC retirada."); mudou(); }
    catch (e: any) { aviso(e.message, "erro"); }
  };
  const fragil = todas.filter((u: any) => u.habilitados != null && u.habilitados <= 1).length;
  return (
    <>
      <div className="lst-barra">
        <input type="search" placeholder="🔎 Código, nome da UC ou curso" aria-label="Pesquisar UC" value={q} onChange={(e) => setQ(e.target.value)} />
        <FiltroArea areas={areas} valor={area} mudar={setArea} />
        <Chips valor={filtro} mudar={(v) => { setFiltro(v); setLimite(80); }} op={[["", "Todas"], ["tecnica", "Técnicas"], ["transversal", "Transversais"], ["cert", "🎓 Exigem certificação"],
          ["fragil", `⚠ Com 0 ou 1 instrutor${fragil ? ` (${fragil})` : ""}`], ["retiradas", "Retiradas"]]} />
      </div>
      {r.carregando && !r.dados && <p role="status">Carregando…</p>}
      {r.erro && <div className="erro-box">{r.erro}</div>}
      {r.dados && ativas && <div className="ucs-resumo"><span><b>{lista.length}</b> UC(s)</span>
        <span><b>{lista.reduce((t: number, u: any) => t + u.carga_horaria_total, 0)}</b> h</span>
        <span><b>{lista.filter((u: any) => u.categoria !== "transversal").length}</b> técnica(s)</span>
        <span><b>{lista.filter((u: any) => u.categoria === "transversal").length}</b> transversal(is)</span>
        <span><b>{lista.filter((u: any) => u.habilitados === 0).length}</b> sem instrutor habilitado</span></div>}
      <ol className="ucs-lista">
        {lista.slice(0, limite).map((u: any) => (
          <li key={u.id} className={`uc-linha lst-uc ${ativas ? "" : "inativo"}`} onClick={() => ativas && abrir(u.area_id, u.curso_id, u.matriz_id)}>
            <span className="cur-sigla">{u.curso}</span>
            <span className="uc-id"><b>{u.codigo}</b> {u.nome}
              <span className="uc-tags">{u.categoria === "transversal" ? <Badge tipo="info">Transversal</Badge> : <Badge tipo="neutro">Técnica</Badge>}
                {u.certificacao_exigida && <span className="chip-area ca-vence">🎓 exige {u.certificacao_exigida}</span>}
                <span className="chip-area">🏫 {u.tipos_ambiente.join(", ") || "qualquer sala"}</span>
                <span className="chip-area">{u.tipo_oferta ? `versão ${u.tipo_oferta}` : "todas as ofertas"} · v{u.versao}</span></span></span>
            <span className="uc-ch"><b>{u.carga_horaria_total} h</b>
              <span className="barra-pct fina"><span className="barra-pct-v bp-neutro" style={{ width: `${(100 * u.carga_horaria_total) / maxCh}%` }} /></span>
              <small className="mudo">{aulas(u.carga_horaria_total, 55)} aulas (dia) · {aulas(u.carga_horaria_total, 50)} (noite) · {u.encontros_semanais} dia(s)/sem</small></span>
            <span className="lst-hab">{u.habilitados == null ? <small className="mudo" title="Qualquer instrutor pode dar">👤 qualquer instrutor</small>
              : <small className={u.habilitados === 0 ? "falta-txt" : u.habilitados === 1 ? "alerta-txt" : "ok-txt"} title="Instrutores que podem dar a UC">
                👤 {u.habilitados} instrutor(es)</small>}<small className="mudo">👥 {u.turmas} turma(s)</small></span>
            <span className="uc-acoes" onClick={(e) => e.stopPropagation()}>
              {ativas && editavel && <button className="btn-link" onClick={() => editarUC(u)}>Editar</button>}
              {ativas && editavel && <button className="btn-link lst-discreto" onClick={() => retirar(u)}>Retirar</button>}
              {!ativas && editavel && <button className="btn btn-pequeno" onClick={() => retirar(u, true)}>Reativar</button>}
            </span>
          </li>
        ))}
      </ol>
      {lista.length > limite && <button className="btn" onClick={() => setLimite(limite + 120)}>Mostrar mais ({lista.length - limite})</button>}
      {r.dados && !lista.length && <div className="cur-vazio">Nenhuma UC com esses filtros.</div>}
    </>
  );
}

function rotVersao(v: any) {
  return v ? `versão ${v.versao}${v.tipo_oferta ? ` (${v.tipo_oferta})` : ""}` : "";
}
