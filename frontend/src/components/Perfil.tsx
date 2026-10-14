import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useApp } from "../contexto";
import { useOpcoes } from "../hooks";

const PERFIL: Record<string, string> = { instrutor: "Instrutor(a)", administrador: "Administrador(a)", planejador: "Planejador(a)", coordenador: "Coordenador(a)", gestor: "Gestor(a)", consulta: "Somente consulta" };
const CORES = ["#1e5bd8", "#2f8f6b", "#b5562a", "#7a3fd1", "#c23b6b", "#1f7a99", "#8a6d00"];
type Tema = "auto" | "light" | "dark";

export function iniciais(nome: string) {
  const p = nome.replace(/\(.*?\)/g, "").trim().split(/\s+/).filter((x) => x.length > 2 || /^[A-ZÀ-Ú]/.test(x));
  return ((p[0]?.[0] || "?") + (p.length > 1 ? p[p.length - 1][0] : "")).toUpperCase();
}

export function aplicarTema(t: Tema) {
  if (t === "auto") document.documentElement.removeAttribute("data-theme");
  else document.documentElement.setAttribute("data-theme", t);
  try { localStorage.setItem("tema", t); } catch { /* armazenamento indisponível */ }
}
export function temaSalvo(): Tema {
  try { return (localStorage.getItem("tema") as Tema) || "auto"; } catch { return "auto"; }
}

/** Avatar redondo no canto superior direito; ao clicar, mostra quem está logado e as ações da conta. */
export default function Perfil({ trocarSenha }: { trocarSenha: () => void }) {
  const { usuario, sair, pode } = useApp();
  const [aberto, setAberto] = useState(false);
  const [tema, setTema] = useState<Tema>(temaSalvo());
  const ref = useRef<HTMLDivElement>(null);
  const nav = useNavigate();
  const unidades = useOpcoes(usuario?.perfil === "instrutor" ? null : "unidades");
  useEffect(() => {
    if (!aberto) return;
    const fora = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) setAberto(false); };
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape") setAberto(false); };
    document.addEventListener("mousedown", fora);
    document.addEventListener("keydown", esc);
    return () => { document.removeEventListener("mousedown", fora); document.removeEventListener("keydown", esc); };
  }, [aberto]);
  if (!usuario) return null;
  const cor = CORES[(usuario.id || 0) % CORES.length];
  const esc = usuario.escopo?.unidades as number[] | null;
  const nomesUn = esc == null ? "Todas as unidades" : unidades.filter((u) => esc.includes(u.id)).map((u) => u.rotulo).join(", ") || "—";
  const ir = (p: string) => { setAberto(false); nav(p); };
  return (
    <div className="perfil" ref={ref}>
      <button className="perfil-botao" aria-haspopup="menu" aria-expanded={aberto} aria-label={`Conta de ${usuario.nome}`} onClick={() => setAberto(!aberto)}>
        <span className="avatar" style={{ background: cor }}>{iniciais(usuario.nome)}</span>
        <span className="perfil-nome">{usuario.nome.split(" ")[0]}</span>
        <span aria-hidden="true" className="perfil-seta">▾</span>
      </button>
      {aberto && (
        <div className="perfil-menu" role="menu">
          <div className="perfil-cab">
            <span className="avatar avatar-grande" style={{ background: cor }}>{iniciais(usuario.nome)}</span>
            <div>
              <b>{usuario.nome}</b>
              <small>{usuario.email}</small>
              <span className="perfil-papel">{PERFIL[usuario.perfil] || usuario.perfil}</span>
            </div>
          </div>
          {usuario.perfil !== "instrutor" && <dl className="perfil-info">
            <dt>Acesso</dt><dd>{nomesUn}</dd>
            <dt>Pode</dt><dd>{[pode("alocacoes.editar") && "editar a grade", pode("cadastros.editar") && "cadastrar", pode("cenarios.publicar") && "publicar",
              pode("exportacao.executar") && "exportar"].filter(Boolean).join(" · ") || "consultar"}</dd>
          </dl>}
          <div className="perfil-tema" role="group" aria-label="Tema">
            {([["auto", "🖥️ Automático"], ["light", "☀️ Claro"], ["dark", "🌙 Escuro"]] as [Tema, string][]).map(([t, r]) => (
              <button key={t} className={tema === t ? "ativo" : ""} aria-pressed={tema === t} onClick={() => { setTema(t); aplicarTema(t); }}>{r}</button>))}
          </div>
          <button role="menuitem" className="perfil-item" onClick={() => { setAberto(false); trocarSenha(); }}>🔑 Alterar minha senha</button>
          {pode("usuarios.gerenciar") && <button role="menuitem" className="perfil-item" onClick={() => ir("/usuarios")}>👥 Usuários e permissões</button>}
          {pode("configuracoes.editar") && <button role="menuitem" className="perfil-item" onClick={() => ir("/configuracoes")}>⚙️ Configurações</button>}
          {usuario.perfil !== "instrutor" && <button role="menuitem" className="perfil-item" onClick={() => ir("/")}>🏠 Início e passo a passo</button>}
          <button role="menuitem" className="perfil-item perfil-sair" onClick={sair}>↩ Sair</button>
        </div>
      )}
    </div>
  );
}
