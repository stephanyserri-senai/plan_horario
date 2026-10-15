import { useState } from "react";
import { api } from "../api";
import { Abas, Campo, Card, Erro, Modal, Pagina, Tabela, useCarregar } from "../components/ui";
import { useApp } from "../contexto";
import { useOpcoes } from "../hooks";

/** Os quatro perfis da plataforma. */
const PERFIS: Record<string, string> = { administrador: "Administrador", planejador: "Planejador", instrutor: "Instrutor", observador: "Observador" };
const AJUDA_PERFIL: Record<string, string> = {
  administrador: "Gestão do projeto: tudo, inclusive usuários, configurações, aprovação e publicação.",
  planejador: "Usa o planejamento: cadastros, grade, geração de horários, simulações, importação e relatórios.",
  instrutor: "Portal do instrutor: os próprios dados, turmas, observações e notificações.",
  observador: "Só acompanha: consulta cadastros, grade, cronograma, indicadores e baixa relatórios, sem alterar nada.",
};

export default function Usuarios() {
  const [aba, setAba] = useState("usuarios");
  return (
    <Pagina titulo="Usuários e permissões" descricao="Perfis configuráveis e escopo por unidade, curso ou turma. A autorização é sempre validada no servidor.">
      <Abas abas={[{ id: "usuarios", rotulo: "Usuários" }, { id: "perfis", rotulo: "Perfis e ações" }]} ativa={aba} mudar={setAba} />
      {aba === "usuarios" ? <ListaUsuarios /> : <Perfis />}
    </Pagina>
  );
}

function ListaUsuarios() {
  const { auth, aviso } = useApp();
  const supabase = auth?.modo === "supabase";
  const us = useCarregar<any[]>(() => api.get("/api/usuarios"), []);
  const [ed, setEd] = useState<any | null>(null);
  const [erro, setErro] = useState<any>(null);
  const unidades = useOpcoes("unidades");
  const cursos = useOpcoes("cursos");
  const turmas = useOpcoes("turmas");
  const instrutores = useOpcoes("instrutores");
  const fontes: Record<string, any[]> = { unidade: unidades, curso: cursos, turma: turmas };
  const salvar = async () => {
    setErro(null);
    try {
      const r = ed.id ? await api.put(`/api/usuarios/${ed.id}`, ed) : await api.post("/api/usuarios", ed);
      if (r.convite) aviso(r.convite.enviado ? "Convite enviado pelo Supabase Auth." : `Usuário criado; convite não enviado: ${r.convite.erro}`, r.convite.enviado ? "ok" : "info");
      setEd(null); us.recarregar();
    } catch (e) { setErro(e); }
  };
  return (
    <>
      <button className="btn btn-primario" onClick={() => setEd({ nome: "", email: "", perfil: "observador", escopos: [], acesso_global: false })}>+ Novo usuário</button>
      <Tabela colunas={[{ chave: "nome", rotulo: "Nome" }, { chave: "email", rotulo: "E-mail" }, { chave: "perfil", rotulo: "Perfil", render: (u: any) => u.perfil === "instrutor" ? <>Instrutor {u.instrutor_id ? "" : <small className="tom-erro">(sem vínculo)</small>}</> : PERFIS[u.perfil] || u.perfil }, { chave: "acesso_global", rotulo: "Acesso global" },
        { chave: "escopos", rotulo: "Escopo", render: (u: any) => u.escopos.map((e: any) => `${e.tipo} #${e.id}`).join(", ") || (u.acesso_global ? "todas" : "nenhum") },
        { chave: "ativo", rotulo: "Ativo" },
        ...(supabase ? [{ chave: "vinculado_supabase", rotulo: "Acesso Supabase", render: (u: any) => u.vinculado_supabase ? "vinculado" : <span onClick={(e) => e.stopPropagation()}>aguardando 1º acesso <button className="btn-link" onClick={async () => {
          const r = await api.post(`/api/usuarios/${u.id}/convite`); aviso(r.enviado ? "Convite reenviado." : r.erro, r.enviado ? "ok" : "erro"); }}>reenviar convite</button></span> }] : []), { chave: "ultimo_acesso", rotulo: "Último acesso", render: (u: any) => u.ultimo_acesso ? new Date(u.ultimo_acesso).toLocaleString("pt-BR") : "—" }]}
        linhas={us.dados || []} aoClicar={(u) => setEd({ ...u })} />
      <Modal titulo={ed?.id ? "Editar usuário" : "Novo usuário"} aberto={!!ed} fechar={() => setEd(null)} largo>
        {ed && <>
          <div className="form-grid">
            <Campo rotulo="Nome" obrigatorio><input value={ed.nome} onChange={(e) => setEd({ ...ed, nome: e.target.value })} /></Campo>
            <Campo rotulo="E-mail" obrigatorio><input type="email" disabled={!!ed.id} value={ed.email} onChange={(e) => setEd({ ...ed, email: e.target.value })} /></Campo>
            {supabase ? <p className="sub">A senha é definida pelo próprio usuário no Supabase Auth (convite por e-mail).</p> :
              <Campo rotulo={ed.id ? "Nova senha (opcional)" : "Senha"} obrigatorio={!ed.id} ajuda="Mínimo 8 caracteres; armazenada com bcrypt."><input type="password" autoComplete="new-password" value={ed.senha || ""} onChange={(e) => setEd({ ...ed, senha: e.target.value })} /></Campo>}
            <Campo rotulo="Perfil" ajuda={AJUDA_PERFIL[ed.perfil]}><select value={ed.perfil} onChange={(e) => setEd({ ...ed, perfil: e.target.value })}>
              {Object.entries(PERFIS).map(([p, r]) => <option key={p} value={p}>{r}</option>)}</select></Campo>
            {ed.perfil === "instrutor" && <Campo rotulo="Cadastro do instrutor" obrigatorio ajuda="O instrutor só vê e atualiza os próprios dados e turmas no portal.">
              <select value={ed.instrutor_id ?? ""} onChange={(e) => setEd({ ...ed, instrutor_id: e.target.value ? Number(e.target.value) : null })}>
                <option value="">— (ou mesmo e-mail do cadastro)</option>{instrutores.map((o) => <option key={o.id} value={o.id}>{o.rotulo}</option>)}</select></Campo>}
            <Campo rotulo="Acesso"><label><input type="checkbox" checked={ed.acesso_global} onChange={(e) => setEd({ ...ed, acesso_global: e.target.checked })} /> Todas as unidades</label>
              {ed.id && <label><input type="checkbox" checked={ed.ativo} onChange={(e) => setEd({ ...ed, ativo: e.target.checked })} /> Ativo</label>}</Campo>
          </div>
          {!ed.acesso_global && ed.perfil !== "instrutor" && <Card titulo="Escopo de acesso">
            {ed.escopos.map((e: any, i: number) => <div key={i} className="linha">
              <select value={e.tipo} onChange={(x) => { const n = [...ed.escopos]; n[i] = { tipo: x.target.value, id: "" }; setEd({ ...ed, escopos: n }); }}><option value="unidade">Unidade</option><option value="curso">Curso</option><option value="turma">Turma</option></select>
              <select value={e.id} onChange={(x) => { const n = [...ed.escopos]; n[i] = { ...e, id: x.target.value }; setEd({ ...ed, escopos: n }); }}><option value="">—</option>{(fontes[e.tipo] || []).map((o) => <option key={o.id} value={o.id}>{o.rotulo}</option>)}</select>
              <button className="btn-link" onClick={() => setEd({ ...ed, escopos: ed.escopos.filter((_: any, k: number) => k !== i) })}>remover</button></div>)}
            <button className="btn" onClick={() => setEd({ ...ed, escopos: [...ed.escopos, { tipo: "unidade", id: "" }] })}>+ Escopo</button>
          </Card>}
          <Erro erro={erro} />
          <div className="rodape-modal"><button className="btn btn-primario" onClick={salvar}>Salvar</button></div>
        </>}
      </Modal>
    </>
  );
}

function Perfis() {
  const p = useCarregar<any>(() => api.get("/api/perfis"), []);
  const { aviso, pode } = useApp();
  if (!p.dados) return <p>Carregando…</p>;
  const { perfis, acoes, matriz } = p.dados;
  const alternar = async (perfil: string, acao: string, on: boolean) => {
    const novas = on ? [...matriz[perfil], acao] : matriz[perfil].filter((a: string) => a !== acao);
    try { await api.put(`/api/perfis/${perfil}`, { acoes: novas }); p.recarregar(); } catch (e: any) { aviso(e.message, "erro"); }
  };
  return (
    <div className="tabela-wrap"><table className="tabela"><thead><tr><th>Ação</th>{perfis.map((x: string) => <th key={x}>{PERFIS[x] || x}</th>)}</tr></thead>
      <tbody>{Object.entries(acoes).map(([a, d]: any) => <tr key={a}><th>{d}<br /><small><code>{a}</code></small></th>{perfis.map((x: string) => (
        <td key={x}><input type="checkbox" aria-label={`${x}: ${d}`} disabled={!pode("usuarios.gerenciar")} checked={matriz[x].includes(a)} onChange={(e) => alternar(x, a, e.target.checked)} /></td>))}</tr>)}</tbody></table></div>
  );
}
