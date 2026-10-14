import { useState } from "react";
import { NavLink, Navigate, Route, Routes, useNavigate } from "react-router-dom";
import { api } from "./api";
import { Campo, Erro, EstadoCenario, Modal } from "./components/ui";
import { useApp } from "./contexto";
import Acompanhamento from "./pages/Acompanhamento";
import Auditoria from "./pages/Auditoria";
import Cadastro from "./pages/Cadastro";
import Configuracoes from "./pages/Configuracoes";
import Cronograma from "./pages/Cronograma";
import Dashboard from "./pages/Dashboard";
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
    { para: "/", rotulo: "Início", icone: "▦", acao: "indicadores.ler" },
    { para: "/acompanhamento", rotulo: "Acompanhamento", icone: "📊", acao: "indicadores.ler" },
    { para: "/cronograma", rotulo: "Cronograma (Gantt)", icone: "▬", acao: "indicadores.ler" },
    { para: "/grade", rotulo: "Grade horária", icone: "▤", acao: "alocacoes.ler" },
    { para: "/geracao", rotulo: "Gerar horários", icone: "⚙", acao: "alocacoes.ler" },
    { para: "/planejamento", rotulo: "Cenários e aprovação", icone: "☰", acao: "alocacoes.ler" },
    { para: "/simulador", rotulo: "Simular nova turma", icone: "◇", acao: "simulacao.executar" },
    { para: "/gargalos", rotulo: "Capacidade e gargalos", icone: "⚠", acao: "indicadores.ler" },
    { para: "/relatorios", rotulo: "Relatórios", icone: "⎙", acao: "exportacao.executar" },
  ] },
  { grupo: "Cadastros", itens: [
    { para: "/cadastros/turmas", rotulo: "Turmas", icone: "👥", acao: "cadastros.ler" },
    { para: "/cadastros/instrutores", rotulo: "Instrutores", icone: "👤", acao: "cadastros.ler" },
    { para: "/cadastros/ucs", rotulo: "Unidades curriculares", icone: "📘", acao: "cadastros.ler" },
    { para: "/cadastros/cursos", rotulo: "Cursos e matrizes", icone: "🎓", acao: "cadastros.ler" },
    { para: "/cadastros/ambientes", rotulo: "Salas e laboratórios", icone: "🏫", acao: "cadastros.ler" },
    { para: "/cadastros/recursos", rotulo: "Recursos e equipamentos", icone: "🔧", acao: "cadastros.ler" },
    { para: "/cadastros/unidades", rotulo: "Unidades, áreas e calendário", icone: "🏢", acao: "cadastros.ler" },
    { para: "/cadastros/turnos", rotulo: "Turnos e horários", icone: "🕘", acao: "cadastros.ler" },
    { para: "/importacao", rotulo: "Importar planilha", icone: "⇪", acao: "importacao.executar" },
  ] },
  { grupo: "Administração", itens: [
    { para: "/usuarios", rotulo: "Usuários e permissões", icone: "🔑", acao: "usuarios.gerenciar" },
    { para: "/configuracoes", rotulo: "Configurações", icone: "⚒", acao: "cadastros.ler" },
    { para: "/auditoria", rotulo: "Auditoria", icone: "🕮", acao: "auditoria.ler" },
  ] },
];

function TrocarSenha({ fechar }: { fechar: () => void }) {
  const { aviso } = useApp();
  const [f, setF] = useState({ atual: "", nova: "", conf: "" });
  const [erro, setErro] = useState<any>(null);
  const salvar = async () => {
    setErro(null);
    if (f.nova !== f.conf) return setErro(new Error("A confirmação não confere com a nova senha."));
    try { await api.post("/api/auth/senha", { senha_atual: f.atual, nova_senha: f.nova }); aviso("Senha alterada."); fechar(); } catch (e) { setErro(e); }
  };
  return (
    <Modal titulo="Alterar minha senha" aberto fechar={fechar}>
      <Campo rotulo="Senha atual"><input type="password" autoComplete="current-password" value={f.atual} onChange={(e) => setF({ ...f, atual: e.target.value })} /></Campo>
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
  const { usuario, sair, pode, cenarios, cenario, setCenarioId, definirSenha, auth } = useApp();
  const [menuAberto, setMenuAberto] = useState(false);
  const [trocarSenha, setTrocarSenha] = useState(false);
  if (definirSenha) return <DefinirSenha />;
  if (!usuario) return <Login />;
  return (
    <div className="app">
      <aside className={`lateral ${menuAberto ? "aberto" : ""}`}>
        <div className="marca">Planejamento<br /><small>Acadêmico</small></div>
        <nav aria-label="Menu principal">
          {MENU.map((g) => {
            const itens = g.itens.filter((m) => !m.acao || pode(m.acao));
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
          <div className="seletor-cenario">
            <label htmlFor="cen" title="O cenário é o período letivo/versão de planejamento em que você está trabalhando.">Cenário</label>
            <select id="cen" value={cenario?.id ?? ""} onChange={(e) => setCenarioId(Number(e.target.value))}>
              {cenarios.filter((c) => c.estado !== "arquivado" || c.id === cenario?.id).map((c) => (
                <option key={c.id} value={c.id}>{c.tipo === "simulacao" ? "[Simulação] " : c.tipo === "proposta" ? "[Proposta] " : ""}{c.nome} (v{c.versao})</option>
              ))}
            </select>
            {cenario && <EstadoCenario estado={cenario.estado} />}
          </div>
          <BuscaGlobal />
          <div className="usuario">
            <span>{usuario.nome} <small>({usuario.perfil})</small></span>
            {auth?.modo !== "supabase" && <button className="btn-link" onClick={() => setTrocarSenha(true)}>Alterar senha</button>}
            <button className="btn" onClick={sair}>Sair</button>
          </div>
        </header>
        {trocarSenha && <TrocarSenha fechar={() => setTrocarSenha(false)} />}
        <main>
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/acompanhamento" element={<Acompanhamento />} />
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
            <Route path="/auditoria" element={<Auditoria />} />
            <Route path="*" element={<Navigate to="/" />} />
          </Routes>
        </main>
      </div>
    </div>
  );
}
