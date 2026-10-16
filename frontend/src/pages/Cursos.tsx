import { useEffect, useMemo, useState } from "react";
import { api, dataBR, qs } from "../api";
import { Badge, Erro, Modal, Tabela, useCarregar } from "../components/ui";
import { useApp } from "../contexto";
import { invalidarOpcoes, useOpcoes } from "../hooks";
import { Formulario, useMeta, type EntMeta } from "./Cadastro";

const SITUACAO: Record<string, string> = { vigente: "ok", rascunho: "alerta", encerrada: "neutro" };
const aulas = (ch: number, min: number) => Math.ceil((ch * 60) / min - 1e-9);

/** Formulário de um cadastro sem os campos que a navegação já define (ex.: a UC já está dentro da versão). */
function semCampos(meta: EntMeta | undefined, fixos: string[]): EntMeta | undefined {
  return meta && { ...meta, campos: meta.campos.filter((c) => !fixos.includes(c.nome)) };
}

type Edicao = { ent: "cursos" | "matrizes" | "ucs"; valores: any; fixos: string[]; titulo: string; copiarDe?: number };

/** Cursos, matrizes e UCs por área: área → curso → versão (por tipo de oferta) → UCs, com classificação e carga horária. */
export default function EstruturaCurricular() {
  const { pode, aviso } = useApp();
  const metas = useMeta();
  const [area, setArea] = useState("");
  const [busca, setBusca] = useState("");
  const [cursoId, setCursoId] = useState<number | null>(null);
  const [versaoId, setVersaoId] = useState<number | null>(null);
  const [edicao, setEdicao] = useState<Edicao | null>(null);
  const [erro, setErro] = useState<any>(null);
  const arv = useCarregar<any[]>(() => api.get(`/api/estrutura-curricular${qs({ area_id: area })}`), [area]);
  const editavel = pode("cadastros.editar");
  const todasAreas = useOpcoes("areas") as any[];

  const areas = arv.dados || [];
  const cursos = useMemo(() => areas.flatMap((a: any) => a.cursos.map((c: any) => ({ ...c, area: a })))
    .filter((c: any) => !busca || `${c.codigo} ${c.nome}`.toLowerCase().includes(busca.toLowerCase())), [areas, busca]);
  const curso = cursos.find((c: any) => c.id === cursoId) || null;
  const versao = curso?.versoes.find((v: any) => v.id === versaoId) || null;
  // ao trocar de curso, abre a versão vigente (ou a primeira)
  useEffect(() => {
    if (curso && !versao) setVersaoId((curso.versoes.find((v: any) => v.situacao === "vigente") || curso.versoes[0])?.id ?? null);
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
      if (edicao.ent === "cursos" && __novo) { setCursoId(r.id); setVersaoId(null); }
      if (edicao.ent === "matrizes") setVersaoId(r.id);
      setEdicao(null);
      arv.recarregar();
      ucs.recarregar();
    } catch (e) { setErro(e); }
  };
  const inativarUC = async (u: any) => {
    if (!confirm(`Retirar a UC ${u.codigo} desta versão? Ela deixa de ser oferecida às turmas novas (o histórico fica guardado).`)) return;
    try { await api.post(`/api/cadastros/ucs/${u.id}/inativar`, { motivo: "Retirada da versão da matriz" }); invalidarOpcoes("ucs"); ucs.recarregar(); arv.recarregar(); }
    catch (e: any) { aviso(e.message, "erro"); }
  };
  const meta = metas.find((m) => m.chave === edicao?.ent);

  return (
    <div className="cursos-layout">
      <aside className="cursos-lista">
        <div className="filtros">
          <select aria-label="Área" value={area} onChange={(e) => { setArea(e.target.value); setCursoId(null); }}>
            <option value="">Todas as áreas</option>
            {todasAreas.map((a: any) => <option key={a.id} value={a.id}>{a.rotulo}</option>)}
          </select>
          <input type="search" placeholder="Curso ou sigla" aria-label="Pesquisar curso" value={busca} onChange={(e) => setBusca(e.target.value)} />
        </div>
        {editavel && <button className="btn btn-primario" onClick={() => { setErro(null); setEdicao({ ent: "cursos", fixos: [], titulo: "Novo curso",
          valores: { __novo: true, area_id: area ? Number(area) : "", modalidade: "presencial" } }); }}>+ Novo curso</button>}
        {arv.carregando && !arv.dados && <p role="status">Carregando…</p>}
        {arv.erro && <div className="erro-box">{arv.erro}</div>}
        {areas.map((a: any) => {
          const cs = cursos.filter((c: any) => c.area.id === a.id);
          if (!cs.length) return null;
          return <div key={a.id} className="cursos-area">
            <h4>{a.nome}</h4>
            <ul>{cs.map((c: any) => (
              <li key={c.id}><button className={c.id === cursoId ? "ativo" : ""} onClick={() => { setCursoId(c.id); setVersaoId(null); }}>
                <b>{c.codigo}</b> {c.nome}
                <small className="mudo">{c.versoes.length ? c.versoes.map((v: any) => v.tipo_oferta || "todas as ofertas").join(" · ") : "sem matriz"}</small>
              </button></li>))}</ul>
          </div>;
        })}
        {arv.dados && cursos.length === 0 && <p className="sub">Nenhum curso {busca ? "com esse nome" : "nesta área"}.</p>}
      </aside>

      <section className="cursos-detalhe">
        {!curso && <div className="vazio-painel"><p>Escolha a área e o curso ao lado para ver as versões da matriz e as UCs.</p>
          <p className="sub">Caminho: área → curso → versão (por tipo de oferta, ex.: AIT ou HTC) → UCs, com classificação e carga horária.</p></div>}
        {curso && <>
          <div className="cursos-cab">
            <div>
              <small className="mudo">{curso.area.nome}</small>
              <h3>{curso.codigo} – {curso.nome}</h3>
              <small className="mudo">{[curso.tipo, curso.modalidade, curso.carga_horaria_total ? `${curso.carga_horaria_total} h no curso` : null].filter(Boolean).join(" · ")}</small>
            </div>
            {editavel && <button className="btn" onClick={async () => { setErro(null); setEdicao({ ent: "cursos", fixos: [], titulo: `Editar curso — ${curso.codigo}`, valores: await api.get(`/api/cadastros/cursos/${curso.id}`) }); }}>Editar curso</button>}
          </div>

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

          {!versao && curso.versoes.length === 0 && <p className="sub">Este curso ainda não tem matriz. Crie a matriz e cadastre as UCs aqui mesmo.</p>}
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
            <Tabela vazio="Nenhuma UC nesta versão. Use “+ Nova UC”." linhas={ucs.dados?.ucs || []} colunas={[
              { chave: "sequencia", rotulo: "Ordem", alinhar: "dir" },
              { chave: "codigo", rotulo: "Código" },
              { chave: "nome", rotulo: "Unidade curricular" },
              { chave: "categoria", rotulo: "Classificação", render: (u: any) => u.categoria === "transversal"
                ? <span title="Qualquer instrutor pode dar"><Badge tipo="info">Transversal</Badge></span>
                : <span title="Só quem marcou a UC no perfil"><Badge tipo="neutro">Técnica</Badge></span> },
              { chave: "carga_horaria_total", rotulo: "Carga horária", alinhar: "dir", render: (u: any) => `${u.carga_horaria_total} h` },
              { chave: "_aulas", rotulo: "Aulas (dia / noite)", alinhar: "dir", render: (u: any) =>
                <span title="Cada aula vale 55 min de dia e 50 min à noite; o que falta vira outra aula">{aulas(u.carga_horaria_total, 55)} / {aulas(u.carga_horaria_total, 50)}</span> },
              { chave: "encontros_semanais", rotulo: "Dias/semana", alinhar: "dir" },
              { chave: "tipos_ambiente", rotulo: "Tipo de sala", render: (u: any) => u.tipos_ambiente.join(", ") || <span className="mudo">qualquer</span> },
              { chave: "certificacao_exigida", rotulo: "Certificação", render: (u: any) => u.certificacao_exigida || <span className="mudo">—</span> },
              ...(editavel ? [{ chave: "_acoes", rotulo: "", render: (u: any) => <span className="acoes-linha">
                <button className="btn-link" onClick={() => abrirUC(u)}>Editar</button>
                <button className="btn-link" onClick={() => inativarUC(u)}>Retirar</button></span> }] : []),
            ]} />
            {ucs.dados?.ucs.length > 0 && <p className="sub">Total: {ucs.dados.ucs.reduce((s: number, u: any) => s + u.carga_horaria_total, 0)} h em {ucs.dados.ucs.length} UC(s) ·{" "}
              {ucs.dados.ucs.filter((u: any) => u.categoria === "transversal").length} transversal(is), {ucs.dados.ucs.filter((u: any) => u.categoria !== "transversal").length} técnica(s).</p>}
          </>}
        </>}
      </section>

      <Modal titulo={edicao?.titulo || ""} aberto={!!edicao} fechar={() => setEdicao(null)} largo>
        {edicao && meta && <>
          <Formulario meta={semCampos(meta, edicao.fixos)!} valores={edicao.valores} setValores={(v) => setEdicao({ ...edicao, valores: v })} />
          <Erro erro={erro} />
          <div className="rodape-modal"><button className="btn" onClick={() => setEdicao(null)}>Cancelar</button><button className="btn btn-primario" onClick={salvar}>Salvar</button></div>
        </>}
      </Modal>
    </div>
  );
}

function rotVersao(v: any) {
  return v ? `versão ${v.versao}${v.tipo_oferta ? ` (${v.tipo_oferta})` : ""}` : "";
}
