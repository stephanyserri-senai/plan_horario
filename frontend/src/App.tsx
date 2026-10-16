import { useState } from "react";
import { NavLink, Navigate, Route, Routes, useNavigate } from "react-router-dom";
import { api } from "./api";
import { Campo, Erro, EstadoCenario, Modal } from "./components/ui";
import { useApp } from "./contexto";
import { useOpcoes } from "./hooks";
import { supabase } from "./auth";
import Perfil from "./components/Perfil";
import PortalInstrutor from "./pages/PortalInstrutor";
import { principalDoSemestre, rotuloVersao, semestreDe, semestres, versoesDoSemestre } from "./semestre";
import Acompanhamento from "./pages/Acompanhamento";
import Consultas from "./pages/Consultas";
import Auditoria from "./pages/Auditoria";
import Cadastro from "./pages/Cadastro";
import Configuracoes from "./pages/Configuracoes";
import Regras from "./pages/Regras";
import Solicitacoes from "./pages/Solicitacoes";
import Epis from "./pages/Epis";
import Cronograma from "./pages/Cronograma";
import Inicio from "./pages/Inicio";
import Gargalos from "./pages/Gargalos";
import Geracao from "./pages/Geracao";
import Grade from "./pages/Grade";
import Importacao from "./pages/Importacao";
import Login, { DefinirSenha } from "./pages/Login";
import Planejamento from "./pages/Planejamento";
import Relatorios from "./pages/Relatorios";
import Simulador from "./pages/Simulador";
import Usuarios from "./pages/Usuarios";

type Item = { para: string; rotulo: string; icone: string; acao?: string };
const MENU: { grupo: string; itens: Item[] }[] = [
  { grupo: "Planejamento", itens: [
    { para: "/", rotulo: "Início", icone: "▦", acao: "alocacoes.ler" },
    { para: "/acompanhamento", rotulo: "Ocupação e andamento", icone: "📊", acao: "indicadores.ler" },
    { para: "/consultas", rotulo: "Consultas", icone: "🔎", acao: "alocacoes.ler" },
    { para: "/cronograma", rotulo: "Cronograma (Gantt)", icone: "▬", acao: "indicadores.ler" },
    { para: "/grade", rotulo: "Grade horária", icone: "▤", acao: "alocacoes.ler" },
    { para: "/geracao", rotulo: "Gerar horários", icone: "⚙", acao: "alocacoes.ler" },
    { para: "/planejamento", rotulo: "Semestres e aprovação", icone: "☰", acao: "alocacoes.ler" },
    { para: "/simulador", rotulo: "Simular nova turma", icone: "◇", acao: "simulacao.executar" },
    { para: "/gargalos", rotulo: "Riscos e gargalos", icone: "⚠", acao: "indicadores.ler" },
    { para: "/relatorios", rotulo: "Relatórios", icone: "⎙", acao: "exportacao.executar" },
    { para: "/solicitacoes", rotulo: "Solicitações dos instrutores", icone: "📝", acao: "solicitacoes.aprovar" },
    { para: "/epis", rotulo: "EPIs das turmas", icone: "🦺", acao: "cadastros.ler" },
  ] },
  { grupo: "Cadastros", itens: [
    { para: "/cadastros/turmas", rotulo: "Turmas", icone: "👥", acao: "cadastros.ler" },
    { para: "/cadastros/instrutores", rotulo: "Instrutores", icone: "👤", acao: "cadastros.ler" },
    { para: "/cadastros/cursos", rotulo: "Cursos, matrizes e UCs", icone: "🎓", acao: "cadastros.ler" },
    { para: "/cadastros/ambientes", rotulo: "Salas e laboratórios", icone: "🏫", acao: "cadastros.ler" },
    { para: "/cadastros/recursos", rotulo: "Recursos e equipamentos", icone: "🔧", acao: "cadastros.ler" },
    { para: "/cadastros/unidades", rotulo: "Unidades, áreas e calendário", icone: "🏢", acao: "cadastros.ler" },
    { para: "/cadastros/turnos", rotulo: "Turnos e horários", icone: "🕘", acao: "cadastros.ler" },
    { para: "/importacao", rotulo: "Importar e exportar", icone: "⇅", acao: "importacao.executar|exportacao.executar" },
  ] },
  { grupo: "Administração", itens: [
    { para: "/usuarios", rotulo: "Usuários e permissões", icone: "🔑", acao: "usuarios.gerenciar" },
    { para: "/regras", rotulo: "Regras do sistema", icone: "📘", acao: "cadastros.ler" },
    { para: "/configuracoes", rotulo: "Configurações", icone: "⚒", acao: "cadastros.ler" },
    { para: "/auditoria", rotulo: "Auditoria", icone: "🕮", acao: "auditoria.ler" },
  ] },
];

/** Trabalho por semestre: escolhe-se o semestre; a versão só aparece quando há mais de uma (ex.: publicada + proposta). */
function SeletorSemestre() {
  const { cenarios, cenario, setCenarioId } = useApp();
  const nav = useNavigate();
  const sems = semestres(cenarios);
  const atual = cenario ? semestreDe(cenario) : "";
  const versoes = versoesDoSemestre(cenarios, atual);
  if (!cenario) return <div className="seletor-cenario"><button className="btn btn-primario" onClick={() => nav("/planejamento")}>+ Criar o primeiro semestre</button></div>;
  return (
    <div className="seletor-cenario">
      <label htmlFor="sem">Semestre</label>
      <select id="sem" value={cenario.tipo === "simulacao" ? "" : atual} onChange={(e) => { const p = principalDoSemestre(cenarios, e.target.value); if (p) setCenarioId(p.id); }}>
        {cenario.tipo === "simulacao" && <option value="">Simulação: {cenario.nome}</option>}
        {sems.map((s) => <option key={s} value={s}>{s}</option>)}
      </select>
      {versoes.length > 1 && cenario.tipo !== "simulacao" && <select aria-label="Versão do semestre" value={cenario.id} onChange={(e) => setCenarioId(Number(e.target.value))}>
        {versoes.map((c) => <option key={c.id} value={c.id}>{rotuloVersao(c)}</option>)}</select>}
      <EstadoCenario estado={cenario.estado} />
    </div>
  );
}

/** Filtro de unidade do topo: vale para todas as páginas de consulta (cadastros, grade, cronograma, indicadores, relatórios…). */
function SeletorUnidade() {
  const { unidade, setUnidade } = useApp();
  const unidades = useOpcoes("unidades");
  if (unidades.length < 2) return null;
  return (
    <div className="seletor-unidade-topo">
      <label htmlFor="unid">Unidade</label>
      <select id="unid" value={unidade} onChange={(e) => setUnidade(e.target.value)} className={unidade ? "filtrado" : ""}>
        <option value="">Todas as unidades</option>
        {unidades.map((u) => <option key={u.id} value={u.id}>{String(u.rotulo).replace(/^Unidade\s+/i, "")}</option>)}
      </select>
    </div>
  );
}

function TrocarSenha({ fechar }: { fechar: () => void }) {
  const { aviso, auth } = useApp();
  const sb = auth?.modo === "supabase";
  const [f, setF] = useState({ atual: "", nova: "", conf: "" });
  const [erro, setErro] = useState<any>(null);
  const salvar = async () => {
    setErro(null);
    if (f.nova.length < 8) return setErro(new Error("A nova senha deve ter ao menos 8 caracteres."));
    if (f.nova !== f.conf) return setErro(new Error("A confirmação não confere com a nova senha."));
    try {
      if (sb) {
        const { error } = await supabase()!.auth.updateUser({ password: f.nova });
        if (error) throw new Error(error.message);
      } else await api.post("/api/auth/senha", { senha_atual: f.atual, nova_senha: f.nova });
      aviso("Senha alterada."); fechar();
    } catch (e) { setErro(e); }
  };
  return (
    <Modal titulo="Alterar minha senha" aberto fechar={fechar}>
      {!sb && <Campo rotulo="Senha atual"><input type="password" autoComplete="current-password" value={f.atual} onChange={(e) => setF({ ...f, atual: e.target.value })} /></Campo>}
      <Campo rotulo="Nova senha" ajuda="Mínimo de 8 caracteres."><input type="password" autoComplete="new-password" value={f.nova} onChange={(e) => setF({ ...f, nova: e.target.value })} /></Campo>
      <Campo rotulo="Confirme a nova senha"><input type="password" autoComplete="new-password" value={f.conf} onChange={(e) => setF({ ...f, conf: e.target.value })} /></Campo>
      <Erro erro={erro} />
      <div className="rodape-modal"><button className="btn" onClick={fechar}>Cancelar</button><button className="btn btn-primario" onClick={salvar}>Salvar</button></div>
    </Modal>
  );
}

function BuscaGlobal() {
  const [q, setQ] = useState("");
  const [res, setRes] = useState<{ ent: string; id: any; rotulo: string }[]>([]);
  const nav = useNavigate();
  const buscar = async (t: string) => {
    setQ(t);
    if (t.length < 2) return setRes([]);
    const ents = ["turmas", "instrutores", "ambientes", "ucs", "cursos"];
    const r = await Promise.all(ents.map((e) => api.get(`/api/cadastros/${e}/opcoes?q=${encodeURIComponent(t)}&limite=5`).then((l: any[]) => l.map((x) => ({ ...x, ent: e }))).catch(() => [])));
    setRes(r.flat().slice(0, 12));
  };
  return (
    <div className="busca-global">
      <input type="search" placeholder="Pesquisa rápida (turma, instrutor, sala, UC…)" aria-label="Pesquisa global" value={q} onChange={(e) => buscar(e.target.value)} />
      {res.length > 0 && (
        <ul className="busca-res">
          {res.map((r) => (
            <li key={r.ent + r.id}><button onClick={() => { setRes([]); setQ(""); nav(r.ent === "turmas" || r.ent === "instrutores" || r.ent === "ambientes" ? `/grade?${r.ent.slice(0, -1).replace("instrutore", "instrutor")}=${r.id}` : `/cadastros/${r.ent}?id=${r.id}`); }}>
              <small>{r.ent}</small> {r.rotulo}</button></li>
          ))}
        </ul>
      )}
    </div>
  );
}

export default function App() {
  const { usuario, pode, definirSenha, unidade } = useApp();
  const [menuAberto, setMenuAberto] = useState(false);
  const [trocarSenha, setTrocarSenha] = useState(false);
  if (definirSenha) return <DefinirSenha />;
  if (!usuario) return <Login />;
  if (usuario.perfil === "instrutor") return <>
    <PortalInstrutor trocarSenha={() => setTrocarSenha(true)} />
    {trocarSenha && <TrocarSenha fechar={() => setTrocarSenha(false)} />}
  </>;
  return (
    <div className="app">
      <aside className={`lateral ${menuAberto ? "aberto" : ""}`}>
        <div className="marca"><img src="/icone.png" alt="" width={40} height={40} /><span>Planejamento<br /><small>Acadêmico</small></span></div>
        <nav aria-label="Menu principal">
          {MENU.map((g) => {
            const itens = g.itens.filter((m) => !m.acao || m.acao.split("|").some((a) => pode(a)));
            return itens.length > 0 && <div key={g.grupo} className="grupo-menu">
              <div className="grupo-titulo">{g.grupo}</div>
              {itens.map((m) => (
                <NavLink key={m.para} to={m.para} end={m.para === "/"} onClick={() => setMenuAberto(false)}>
                  <span aria-hidden="true" className="ico">{m.icone}</span> {m.rotulo}
                </NavLink>
              ))}
            </div>;
          })}
        </nav>
      </aside>
      <div className="principal">
        <header className="topo">
          <button className="btn-icone menu-mobile" aria-label="Abrir menu" onClick={() => setMenuAberto(!menuAberto)}>☰</button>
          <SeletorSemestre />
          <SeletorUnidade />
          <BuscaGlobal />
          <Perfil trocarSenha={() => setTrocarSenha(true)} />
        </header>
        {trocarSenha && <TrocarSenha fechar={() => setTrocarSenha(false)} />}
        <main key={unidade /* trocar a unidade recarrega a página com o novo filtro */}>
          <Routes>
            <Route path="/" element={<Inicio />} />
            <Route path="/indicadores" element={<Navigate to="/acompanhamento" replace />} />
            <Route path="/acompanhamento" element={<Acompanhamento />} />
            <Route path="/consultas" element={<Consultas />} />
            <Route path="/cronograma" element={<Cronograma />} />
            <Route path="/grade" element={<Grade />} />
            <Route path="/planejamento" element={<Planejamento />} />
            <Route path="/geracao" element={<Geracao />} />
            <Route path="/simulador" element={<Simulador />} />
            <Route path="/cadastros/:ent" element={<Cadastro />} />
            <Route path="/gargalos" element={<Gargalos />} />
            <Route path="/relatorios" element={<Relatorios />} />
            <Route path="/importacao" element={<Importacao />} />
            <Route path="/usuarios" element={<Usuarios />} />
            <Route path="/configuracoes" element={<Configuracoes />} />
            <Route path="/regras" element={<Regras />} />
            <Route path="/solicitacoes" element={<Solicitacoes />} />
            <Route path="/epis" element={<Epis />} />
            <Route path="/auditoria" element={<Auditoria />} />
            <Route path="*" element={<Navigate to="/" />} />
          </Routes>
        </main>
      </div>
    </div>
  );
}
