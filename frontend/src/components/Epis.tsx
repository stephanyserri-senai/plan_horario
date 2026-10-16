import { useState } from "react";
import { Link } from "react-router-dom";
import { api, dataBR, qs } from "../api";
import { Badge, Tabela, useCarregar } from "./ui";
import { useApp } from "../contexto";

const SIT: Record<string, [string, string]> = {
  atrasado: ["bloqueio", "Prazo vencido"], proximo: ["alerta", "Vence em breve"], pendente: ["info", "A providenciar"],
  providenciado: ["info", "Separado, falta entregar"], entregue: ["ok", "Entregue"],
};

/** EPIs que o curso exige de cada aluno: entram em todas as turmas do curso, com quantidade e prazo. */
export function EpisDoCurso({ cursoId, editavel }: { cursoId: number; editavel: boolean }) {
  const { aviso } = useApp();
  const l = useCarregar<any[]>(() => api.get(`/api/cursos/${cursoId}/epis`), [cursoId]);
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
      </div>}
    </section>
  );
}

/** Controle por turma: o que comprar/separar e entregar, com prazo e as marcações (checkbox). */
export function ControleEpis({ turmaId, situacaoInicial = "" }: { turmaId?: number | string; situacaoInicial?: string }) {
  const { pode, aviso } = useApp();
  const [situacao, setSituacao] = useState(situacaoInicial);
  const [busca, setBusca] = useState("");
  const r = useCarregar<any>(() => api.get(`/api/epis-turmas${qs({ turma_id: turmaId || "" })}`), [turmaId]);
  const editavel = pode("cadastros.editar");
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
      </div>
      {r.erro && <div className="erro-box">{r.erro}</div>}
      {r.carregando && !d && <p role="status">Carregando…</p>}
      {d && <Tabela chave={(i: any) => i.id} linhas={itens}
        vazio={d.itens.length ? "Nada nesta situação." : "Nenhum EPI para controlar. Cadastre os EPIs no curso (Cadastros → Cursos, matrizes e UCs)."}
        colunas={[
          ...(turmaId ? [] : [{ chave: "turma", rotulo: "Turma", render: (i: any) => <><Link to={`/grade?turma=${i.turma_id}`}><b>{i.turma}</b></Link>
            <small className="mudo"> {i.alunos} aluno(s) · início {dataBR(i.inicio_turma)}</small></> }]),
          { chave: "nome", rotulo: "EPI", render: (i: any) => <b>{i.nome}</b> },
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
  if (!cursoId || !l.dados) return null;
  const n = Number(alunos) || 0;
  const prazo = (dias: number) => { if (!inicio) return "—"; const d = new Date(inicio + "T12:00:00"); d.setDate(d.getDate() - dias); return d.toLocaleDateString("pt-BR"); };
  return (
    <div className="previa-epis">
      <b>🦺 EPIs desta turma</b>{" "}
      {l.dados.length === 0 ? <span className="mudo">o curso não tem EPIs cadastrados (cadastre em Cursos, matrizes e UCs).</span>
        : <ul>{l.dados.map((e) => <li key={e.id}>{e.nome}: {n ? <b>{n * e.quantidade_por_aluno}</b> : <span className="mudo">informe os alunos</span>} ({e.quantidade_por_aluno} por aluno) · pronto até {prazo(e.antecedencia_dias)}</li>)}</ul>}
      {l.dados.length > 0 && <small className="mudo">Entram no controle de EPIs ao salvar; marque lá a compra/separação e a entrega.</small>}
    </div>
  );
}
