import { useState } from "react";
import { Link } from "react-router-dom";
import { api, dataBR, qs } from "../api";
import { Badge, Tabela, useCarregar } from "./ui";
import { useApp } from "../contexto";
import { useOpcoes } from "../hooks";

const SIT: Record<string, [string, string]> = {
  atrasado: ["bloqueio", "Prazo vencido"], proximo: ["alerta", "Vence em breve"], pendente: ["info", "A providenciar"],
  providenciado: ["info", "Separado, falta entregar"], entregue: ["ok", "Entregue"],
};

/** EPIs que o curso exige de cada aluno: entram em todas as turmas do curso, com quantidade e prazo. */
export function EpisDoCurso({ cursoId, editavel, mudou }: { cursoId: number; editavel: boolean; mudou?: () => void }) {
  const { aviso } = useApp();
  const l0 = useCarregar<any[]>(() => api.get(`/api/cursos/${cursoId}/epis`), [cursoId]);
  const l = { ...l0, recarregar: () => { l0.recarregar(); mudou?.(); } };
  const [lista, setLista] = useState<string | null>(null);
  const cfg = useCarregar<any>(() => api.get(`/api/cursos/${cursoId}/epi-config`), [cursoId]);
  const dispensa = !!cfg.dados?.dispensa_epi;
  const trocarDispensa = async (v: boolean) => {
    try { await api.put(`/api/cursos/${cursoId}/epi-config`, { dispensa_epi: v }); cfg.recarregar(); mudou?.();
      aviso(v ? "Curso marcado: não precisa de EPI." : "Agora você pode montar a lista de EPIs do curso."); }
    catch (e: any) { aviso(e.message, "erro"); }
  };
  const colar = async () => {
    try {
      const r = await api.post(`/api/cursos/${cursoId}/epis/lista`, { texto: lista });
      aviso(`${r.criados.length} EPI(s) incluído(s)${r.repetidos.length ? `; ${r.repetidos.length} já estava(m) na lista` : ""}. ${r.itens_nas_turmas} item(ns) entraram no controle das turmas do curso.`);
      setLista(null);
      l.recarregar();
    } catch (e: any) { aviso(e.message, "erro"); }
  };
  const [novo, setNovo] = useState({ nome: "", quantidade_por_aluno: 1, antecedencia_dias: 15 });
  const [editando, setEditando] = useState<any | null>(null);
  const incluir = async () => {
    try {
      await api.post(`/api/cursos/${cursoId}/epis`, novo);
      aviso("EPI incluído. As turmas em andamento ou futuras do curso já receberam a lista.");
      setNovo({ nome: "", quantidade_por_aluno: 1, antecedencia_dias: 15 });
      l.recarregar();
    } catch (e: any) { aviso(e.message, "erro"); }
  };
  const salvar = async () => {
    try { await api.put(`/api/epis-curso/${editando.id}`, editando); setEditando(null); l.recarregar(); aviso("EPI atualizado."); }
    catch (e: any) { aviso(e.message, "erro"); }
  };
  const retirar = async (e: any) => {
    if (!confirm(`Retirar "${e.nome}" do curso? Sai das turmas onde ainda não foi separado nem entregue.`)) return;
    try { await api.put(`/api/epis-curso/${e.id}`, { ativo: false }); l.recarregar(); } catch (x: any) { aviso(x.message, "erro"); }
  };
  return (
    <section className="epis-curso" aria-label="EPIs do curso">
      <div className="cursos-barra"><h3 className="subtitulo">🦺 EPIs do curso</h3>
        <small className="mudo">cada turma recebe: quantidade = alunos × por aluno; prazo = início da turma − antecedência</small></div>
      {cfg.dados && <label className={`check-dispensa ${dispensa ? "ativo" : ""}`}
        title={!dispensa && (l.dados || []).length ? "Retire os EPIs da lista para marcar esta opção" : undefined}>
        <input type="checkbox" checked={dispensa} disabled={!editavel || (!dispensa && (l.dados || []).length > 0)} onChange={(e) => trocarDispensa(e.target.checked)} />
        <span><b>🚫 Este curso não precisa de EPI</b><small className="mudo">{dispensa ? "As turmas deste curso não recebem EPIs e o curso não aparece como pendente."
          : (l.dados || []).length ? "Para marcar, retire antes os EPIs da lista." : "Marque para cursos que não usam EPI (ex.: informática, gestão)."}</small></span>
      </label>}
      {!dispensa && <>
      <Tabela vazio="Nenhum EPI cadastrado para este curso." linhas={l.dados || []} chave={(e: any) => e.id} colunas={[
        { chave: "nome", rotulo: "EPI", render: (e: any) => editando?.id === e.id
          ? <input value={editando.nome} onChange={(x) => setEditando({ ...editando, nome: x.target.value })} /> : <><b>{e.nome}</b>{e.observacao && <small className="mudo"> · {e.observacao}</small>}</> },
        { chave: "quantidade_por_aluno", rotulo: "Por aluno", alinhar: "dir", render: (e: any) => editando?.id === e.id
          ? <input type="number" min={1} className="num-curto" value={editando.quantidade_por_aluno} onChange={(x) => setEditando({ ...editando, quantidade_por_aluno: x.target.value })} />
          : e.quantidade_por_aluno },
        { chave: "antecedencia_dias", rotulo: "Pronto quantos dias antes do início", alinhar: "dir", render: (e: any) => editando?.id === e.id
          ? <input type="number" min={0} className="num-curto" value={editando.antecedencia_dias} onChange={(x) => setEditando({ ...editando, antecedencia_dias: x.target.value })} />
          : `${e.antecedencia_dias} dia(s)` },
        ...(editavel ? [{ chave: "_a", rotulo: "", render: (e: any) => <span className="acoes-linha">
          {editando?.id === e.id ? <><button className="btn-link" onClick={salvar}>Salvar</button><button className="btn-link" onClick={() => setEditando(null)}>Cancelar</button></>
            : <><button className="btn-link" onClick={() => setEditando({ ...e })}>Editar</button><button className="btn-link" onClick={() => retirar(e)}>Retirar</button></>}</span> }] : []),
      ]} />
      {editavel && <div className="epi-novo">
        <input placeholder="Novo EPI (ex.: luva isolante, óculos de proteção, botina)" aria-label="Nome do EPI" value={novo.nome}
          onChange={(e) => setNovo({ ...novo, nome: e.target.value })} onKeyDown={(e) => e.key === "Enter" && novo.nome.trim() && incluir()} />
        <label>por aluno <input type="number" min={1} className="num-curto" value={novo.quantidade_por_aluno} onChange={(e) => setNovo({ ...novo, quantidade_por_aluno: Number(e.target.value) })} /></label>
        <label>pronto <input type="number" min={0} className="num-curto" value={novo.antecedencia_dias} onChange={(e) => setNovo({ ...novo, antecedencia_dias: Number(e.target.value) })} /> dias antes</label>
        <button className="btn btn-primario" disabled={!novo.nome.trim()} onClick={incluir}>+ Incluir EPI</button>
        {lista == null && <button className="btn" onClick={() => setLista("")}>📋 Colar uma lista</button>}
      </div>}
      {editavel && lista != null && <div className="epi-manual">
        <b>Colar a lista de EPIs do curso</b>
        <textarea rows={6} value={lista} autoFocus onChange={(e) => setLista(e.target.value)}
          placeholder={"Um EPI por linha. Ex.:\nLuva isolante classe 00\nÓculos de proteção; 1; 10\nProtetor auricular tipo plug; 2"} />
        <small className="mudo">Em cada linha: nome; quantidade por aluno; dias de antecedência (os dois últimos são opcionais: 1 por aluno e 15 dias).
          Pode colar direto de uma planilha. EPIs que já estão na lista são ignorados.</small>
        <div className="acoes-linha"><button className="btn" onClick={() => setLista(null)}>Cancelar</button>
          <button className="btn btn-primario" disabled={!lista.trim()} onClick={colar}>Incluir {lista.split("\n").filter((x) => x.trim()).length} EPI(s)</button></div>
      </div>}
      </>}
    </section>
  );
}

/** Controle por turma: o que comprar/separar e entregar, com prazo e as marcações (checkbox). */
export function ControleEpis({ turmaId, cursoId, situacaoInicial = "", versao = 0 }: { turmaId?: number | string; cursoId?: number | string; situacaoInicial?: string; versao?: number }) {
  const { pode, aviso } = useApp();
  const [situacao, setSituacao] = useState(situacaoInicial);
  const [busca, setBusca] = useState("");
  const r = useCarregar<any>(() => api.get(`/api/epis-turmas${qs({ turma_id: turmaId || "", curso_id: cursoId || "" })}`), [turmaId, cursoId, versao]);
  const editavel = pode("cadastros.editar");
  const [novo, setNovo] = useState<any | null>(null);
  const turmas = useOpcoes(!turmaId && novo ? "turmas" : null) as any[];
  const incluir = async () => {
    try {
      const item = await api.post("/api/epis-turmas", { ...novo, turma_id: turmaId || novo.turma_id });
      r.setDados({ ...r.dados, itens: [...r.dados.itens, item] });
      aviso(`EPI incluído na turma ${item.turma}.`);
      setNovo({ ...novo, nome: "", quantidade: "", observacao: "" });
    } catch (e: any) { aviso(e.message, "erro"); }
  };
  const excluir = async (i: any) => {
    if (!confirm(`Excluir "${i.nome}" da turma ${i.turma}?`)) return;
    try { await api.del(`/api/epis-turmas/${i.id}`); r.setDados({ ...r.dados, itens: r.dados.itens.filter((x: any) => x.id !== i.id) }); }
    catch (e: any) { aviso(e.message, "erro"); }
  };
  const nomesConhecidos = [...new Set((r.dados?.itens || []).map((i: any) => i.nome))] as string[];
  const marcar = async (i: any, dados: any) => {
    try {
      const novo = await api.put(`/api/epis-turmas/${i.id}`, dados);
      r.setDados({ ...r.dados, itens: r.dados.itens.map((x: any) => (x.id === i.id ? novo : x)) });
    } catch (e: any) { aviso(e.message, "erro"); }
  };
  const d = r.dados;
  const itens = (d?.itens || []).filter((i: any) => (!situacao || (situacao === "abertos" ? i.situacao !== "entregue" : i.situacao === situacao))
    && (!busca || `${i.turma} ${i.nome} ${i.curso || ""}`.toLowerCase().includes(busca.toLowerCase())));
  const contagem = (s: string) => (d?.itens || []).filter((i: any) => (s === "abertos" ? i.situacao !== "entregue" : i.situacao === s)).length;
  return (
    <div className="controle-epis">
      <div className="filtro-estados" role="group" aria-label="Filtrar por situação">
        <button className={`chip-estado sem-ponto ${!situacao ? "ativo" : ""}`} onClick={() => setSituacao("")}>Todos <b>{d?.itens.length ?? 0}</b></button>
        {["abertos", "atrasado", "proximo", "pendente", "providenciado", "entregue"].map((s) => (
          <button key={s} className={`chip-estado ${s === "atrasado" ? "ag-bloq" : s === "proximo" ? "ag-PJ" : s === "entregue" ? "ag-livre" : s === "abertos" ? "sem-ponto" : "ag-aula"} ${situacao === s ? "ativo" : ""}`}
            onClick={() => setSituacao(situacao === s ? "" : s)}>{s === "abertos" ? "Não entregues" : SIT[s][1]} <b>{contagem(s)}</b></button>))}
        {!turmaId && <input type="search" className="busca-larga" placeholder="Buscar turma, EPI ou curso…" aria-label="Buscar" value={busca} onChange={(e) => setBusca(e.target.value)} />}
        {editavel && !novo && <button className="btn btn-primario" onClick={() => setNovo({ turma_id: "", nome: "", quantidade: "", prazo: "", observacao: "" })}>+ Incluir EPI</button>}
      </div>
      {editavel && novo && <div className="epi-manual" role="group" aria-label="Incluir EPI na turma">
        <b>Incluir EPI {turmaId ? "nesta turma" : "numa turma"}</b>
        <div className="epi-manual-campos">
          {!turmaId && <label>Turma<select value={novo.turma_id} onChange={(e) => setNovo({ ...novo, turma_id: e.target.value })}>
            <option value="">— escolha —</option>{turmas.map((t: any) => <option key={t.id} value={t.id}>{t.rotulo}</option>)}</select></label>}
          <label className="epi-nome">EPI<input list="epis-conhecidos" value={novo.nome} placeholder="ex.: protetor facial" onChange={(e) => setNovo({ ...novo, nome: e.target.value })} />
            <datalist id="epis-conhecidos">{nomesConhecidos.map((n) => <option key={n} value={n} />)}</datalist></label>
          <label>Quantidade<input type="number" min={0} className="num-curto" value={novo.quantidade} placeholder="1/aluno" onChange={(e) => setNovo({ ...novo, quantidade: e.target.value })} /></label>
          <label>Prazo<input type="date" value={novo.prazo} onChange={(e) => setNovo({ ...novo, prazo: e.target.value })} /></label>
          <label className="epi-nome">Observação<input value={novo.observacao} placeholder="opcional" onChange={(e) => setNovo({ ...novo, observacao: e.target.value })} /></label>
        </div>
        <small className="mudo">Sem quantidade, vale 1 por aluno; sem prazo, 15 dias antes do início da turma. Para que todas as turmas do curso recebam o EPI, cadastre-o no curso.</small>
        <div className="acoes-linha">
          <button className="btn" onClick={() => setNovo(null)}>Fechar</button>
          <button className="btn btn-primario" disabled={!novo.nome.trim() || (!turmaId && !novo.turma_id)} onClick={incluir}>Incluir</button>
        </div>
      </div>}
      {r.erro && <div className="erro-box">{r.erro}</div>}
      {r.carregando && !d && <p role="status">Carregando…</p>}
      {d && <Tabela chave={(i: any) => i.id} linhas={itens}
        vazio={d.itens.length ? "Nada nesta situação." : "Nenhum EPI para controlar. Use “+ Incluir EPI” ou cadastre os EPIs no curso (Cadastros → Cursos, matrizes e UCs)."}
        colunas={[
          ...(turmaId ? [] : [{ chave: "turma", rotulo: "Turma", render: (i: any) => <><Link to={`/grade?turma=${i.turma_id}`}><b>{i.turma}</b></Link>
            <small className="mudo"> {i.alunos} aluno(s) · início {dataBR(i.inicio_turma)}</small></> }]),
          { chave: "nome", rotulo: "EPI", render: (i: any) => <><b>{i.nome}</b>{i.avulso && <> <span className="chip chip-neutro" title="incluído à mão nesta turma (não vem do curso)">avulso</span>
            {editavel && <button className="btn-link" onClick={() => excluir(i)}>excluir</button>}</>}</> },
          { chave: "quantidade", rotulo: "Qtd.", alinhar: "dir" as const },
          { chave: "prazo", rotulo: "Prazo", render: (i: any) => editavel && !i.entregue
            ? <input type="date" value={i.prazo || ""} aria-label={`Prazo de ${i.nome}`} onChange={(e) => marcar(i, { prazo: e.target.value })} />
            : dataBR(i.prazo) },
          { chave: "situacao", rotulo: "Situação", render: (i: any) => <><Badge tipo={SIT[i.situacao][0]}>{i.situacao_rotulo}</Badge>
            {!i.entregue && i.dias_para_prazo != null && <small className="mudo"> {i.dias_para_prazo < 0 ? `${-i.dias_para_prazo} dia(s) de atraso` : i.dias_para_prazo === 0 ? "vence hoje" : `faltam ${i.dias_para_prazo} dia(s)`}</small>}</> },
          { chave: "providenciado", rotulo: "Comprado / separado", render: (i: any) => <label className="check-epi">
            <input type="checkbox" checked={i.providenciado} disabled={!editavel} onChange={(e) => marcar(i, { providenciado: e.target.checked })} />
            {i.providenciado_em ? <small className="mudo">{dataBR(i.providenciado_em.slice(0, 10))}</small> : <small className="mudo">não</small>}</label> },
          { chave: "entregue", rotulo: "Entregue à turma", render: (i: any) => <label className="check-epi">
            <input type="checkbox" checked={i.entregue} disabled={!editavel} onChange={(e) => marcar(i, { entregue: e.target.checked })} />
            {i.entregue_em ? <small className="mudo">{dataBR(i.entregue_em.slice(0, 10))}</small> : <small className="mudo">não</small>}</label> },
          { chave: "observacao", rotulo: "Observação", render: (i: any) => editavel
            ? <input className="obs-epi" defaultValue={i.observacao || ""} placeholder="ex.: pedido de compra 123" aria-label={`Observação de ${i.nome}`}
                onBlur={(e) => e.target.value !== (i.observacao || "") && marcar(i, { observacao: e.target.value })} />
            : i.observacao || <span className="mudo">—</span> },
        ]} />}
      <p className="sub">Marque “comprado/separado” quando o material estiver garantido e “entregue” quando chegar à turma. Prazos vencidos ou a menos de {d?.dias_aviso ?? 7} dias aparecem no Início e em Riscos e gargalos.</p>
    </div>
  );
}

/** Prévia, no cadastro da turma, dos EPIs que o curso exige (calculados para os alunos e o início informados). */
export function PreviaEpis({ cursoId, alunos, inicio }: { cursoId: any; alunos: any; inicio: string }) {
  const l = useCarregar<any[]>(() => cursoId ? api.get(`/api/cursos/${cursoId}/epis`) : Promise.resolve([]), [cursoId]);
  const cfg = useCarregar<any>(() => cursoId ? api.get(`/api/cursos/${cursoId}/epi-config`) : Promise.resolve(null), [cursoId]);
  if (!cursoId || !l.dados) return null;
  if (cfg.dados?.dispensa_epi) return <div className="previa-epis"><b>🦺 EPIs desta turma</b> <span className="mudo">o curso não precisa de EPI.</span></div>;
  const n = Number(alunos) || 0;
  const prazo = (dias: number) => { if (!inicio) return "—"; const d = new Date(inicio + "T12:00:00"); d.setDate(d.getDate() - dias); return d.toLocaleDateString("pt-BR"); };
  return (
    <div className="previa-epis">
      <b>🦺 EPIs desta turma</b>{" "}
      {l.dados.length === 0 ? <span className="mudo">o curso ainda não tem lista de EPIs (monte em EPIs das turmas → Lista de EPIs por curso, ou marque que não precisa).</span>
        : <ul>{l.dados.map((e) => <li key={e.id}>{e.nome}: {n ? <b>{n * e.quantidade_por_aluno}</b> : <span className="mudo">informe os alunos</span>} ({e.quantidade_por_aluno} por aluno) · pronto até {prazo(e.antecedencia_dias)}</li>)}</ul>}
      {l.dados.length > 0 && <small className="mudo">Entram no controle de EPIs ao salvar; marque lá a compra/separação e a entrega.</small>}
    </div>
  );
}


/** Listas de EPIs por curso: escolha a área e o curso, monte a lista (um a um ou colando) e veja as turmas vinculadas. */
export function ListasPorCurso() {
  const { pode } = useApp();
  const [area, setArea] = useState("");
  const [busca, setBusca] = useState("");
  const [sel, setSel] = useState<any | null>(null);
  const [versao, setVersao] = useState(0);
  const r = useCarregar<any[]>(() => api.get("/api/epis-cursos"), [versao]);
  const cursos = (r.dados || []).filter((c) => (!area || String(c.area_id) === area) && (!busca || `${c.codigo} ${c.nome}`.toLowerCase().includes(busca.toLowerCase())));
  const areas = [...new Map((r.dados || []).map((c) => [String(c.area_id), c.area])).entries()].sort((a, b) => String(a[1]).localeCompare(String(b[1])));
  const grupos = [...new Set(cursos.map((c) => c.area))];
  const atual = sel && (r.dados || []).find((c) => c.id === sel.id);
  const semLista = (r.dados || []).filter((c) => !c.epis && !c.dispensa_epi && c.turmas_ativas).length;
  return (
    <div className="cursos-layout">
      <aside className="cursos-lista">
        <div className="filtros">
          <select aria-label="Área" value={area} onChange={(e) => setArea(e.target.value)}>
            <option value="">Todas as áreas</option>{areas.map(([id, nome]) => <option key={id} value={id}>{nome}</option>)}</select>
          <input type="search" placeholder="Curso ou sigla" aria-label="Pesquisar curso" value={busca} onChange={(e) => setBusca(e.target.value)} />
        </div>
        {semLista > 0 && <small className="aviso-nl">{semLista} curso(s) com turma em andamento ainda sem lista de EPIs (monte a lista ou marque que não precisa)</small>}
        {grupos.map((g) => <div key={g} className="cursos-area"><h4>{g}</h4><ul>
          {cursos.filter((c) => c.area === g).map((c) => <li key={c.id}><button className={sel?.id === c.id ? "ativo" : ""} onClick={() => setSel(c)}>
            <b>{c.codigo}</b> {c.nome}
            <small className="mudo">{c.dispensa_epi ? "🚫 não precisa de EPI" : c.epis ? `${c.epis} EPI(s)` : "⚠ sem lista de EPIs"} · {c.turmas_ativas} turma(s) ativa(s)</small></button></li>)}
        </ul></div>)}
        {r.dados && cursos.length === 0 && <p className="sub">Nenhum curso encontrado.</p>}
      </aside>
      <section className="cursos-detalhe">
        {!atual ? <div className="vazio-painel"><p>Escolha a área e o curso ao lado para montar a lista de EPIs.</p>
          <p className="sub">Toda turma do curso (as que já existem e as que forem criadas) entra automaticamente no controle de entregas, com quantidade = alunos × por aluno e prazo = início − antecedência.</p></div>
          : <>
            <div className="cursos-cab"><div><small className="mudo">{atual.area}</small><h3>{atual.codigo} – {atual.nome}</h3>
              <small className="mudo">{atual.turmas_ativas} turma(s) em andamento ou futuras vinculadas ao controle</small></div></div>
            <EpisDoCurso cursoId={atual.id} editavel={pode("cadastros.editar")} mudou={() => setVersao((v) => v + 1)} />
            <h3 className="subtitulo">Controle de entregas das turmas deste curso</h3>
            <ControleEpis cursoId={atual.id} versao={versao} />
          </>}
      </section>
    </div>
  );
}
