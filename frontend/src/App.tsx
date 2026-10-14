import { useState } from "react";
import { NavLink, Navigate, Route, Routes, useNavigate } from "react-router-dom";
import { api } from "./api";
import { EstadoCenario } from "./components/ui";
import { useApp } from "./contexto";
import Auditoria from "./pages/Auditoria";
import Cadastro from "./pages/Cadastro";
import Configuracoes from "./pages/Configuracoes";
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

const MENU: { para: string; rotulo: string; icone: string; acao?: string }[] = [
  { para: "/", rotulo: "Dashboard", icone: "▦", acao: "indicadores.ler" },
  { para: "/grade", rotulo: "Grade horária", icone: "▤", acao: "alocacoes.ler" },
  { para: "/planejamento", rotulo: "Planejamento", icone: "☰", acao: "alocacoes.ler" },
  { para: "/geracao", rotulo: "Geração inteligente", icone: "⚙", acao: "alocacoes.ler" },
  { para: "/simulador", rotulo: "Simulador de capacidade", icone: "◇", acao: "simulacao.executar" },
  { para: "/cadastros/turmas", rotulo: "Turmas", icone: "👥", acao: "cadastros.ler" },
  { para: "/cadastros/instrutores", rotulo: "Instrutores", icone: "👤", acao: "cadastros.ler" },
  { para: "/cadastros/ucs", rotulo: "Unidades curriculares", icone: "📘", acao: "cadastros.ler" },
  { para: "/cadastros/cursos", rotulo: "Cursos e matrizes", icone: "🎓", acao: "cadastros.ler" },
  { para: "/cadastros/ambientes", rotulo: "Ambientes", icone: "🏫", acao: "cadastros.ler" },
  { para: "/cadastros/recursos", rotulo: "Recursos e equipamentos", icone: "🔧", acao: "cadastros.ler" },
  { para: "/gargalos", rotulo: "Capacidade e gargalos", icone: "⚠", acao: "indicadores.ler" },
  { para: "/relatorios", rotulo: "Relatórios", icone: "⎙", acao: "exportacao.executar" },
  { para: "/importacao", rotulo: "Importação", icone: "⇪", acao: "importacao.executar" },
  { para: "/usuarios", rotulo: "Usuários e permissões", icone: "🔑", acao: "usuarios.gerenciar" },
  { para: "/configuracoes", rotulo: "Configurações", icone: "⚒", acao: "cadastros.ler" },
  { para: "/auditoria", rotulo: "Auditoria", icone: "🕮", acao: "auditoria.ler" },
];

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
  const { usuario, sair, pode, cenarios, cenario, setCenarioId, definirSenha } = useApp();
  const [menuAberto, setMenuAberto] = useState(false);
  if (definirSenha) return <DefinirSenha />;
  if (!usuario) return <Login />;
  return (
    <div className="app">
      <aside className={`lateral ${menuAberto ? "aberto" : ""}`}>
        <div className="marca">Planejamento<br /><small>Acadêmico</small></div>
        <nav aria-label="Menu principal">
          {MENU.filter((m) => !m.acao || pode(m.acao)).map((m) => (
            <NavLink key={m.para} to={m.para} end={m.para === "/"} onClick={() => setMenuAberto(false)}>
              <span aria-hidden="true" className="ico">{m.icone}</span> {m.rotulo}
            </NavLink>
          ))}
        </nav>
      </aside>
      <div className="principal">
        <header className="topo">
          <button className="btn-icone menu-mobile" aria-label="Abrir menu" onClick={() => setMenuAberto(!menuAberto)}>☰</button>
          <div className="seletor-cenario">
            <label htmlFor="cen">Cenário</label>
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
            <button className="btn" onClick={sair}>Sair</button>
          </div>
        </header>
        <main>
          <Routes>
            <Route path="/" element={<Dashboard />} />
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
