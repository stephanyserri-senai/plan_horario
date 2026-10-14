import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { api, token } from "./api";
import { carregarConfigAuth, supabase, tipoLinkInicial, type ConfigAuth } from "./auth";

export type Usuario = { id: number; nome: string; email: string; perfil: string; acoes: string[]; escopo: any };
export type Cenario = { id: number; nome: string; estado: string; tipo: string; versao: number; unidade_id: number | null;
  periodo_inicio: string | null; periodo_fim: string | null; aulas: number; lock_version: number; cenario_origem_id: number | null };

type Ctx = {
  usuario: Usuario | null;
  auth: ConfigAuth | null;
  erroAcesso: string | null;
  definirSenha: boolean;
  concluirDefinicaoSenha: () => Promise<void>;
  recuperarSenha: (email: string) => Promise<void>;
  entrar: (email: string, senha: string) => Promise<void>;
  sair: () => void;
  pode: (acao: string) => boolean;
  cenarios: Cenario[];
  cenario: Cenario | null;
  setCenarioId: (id: number) => void;
  recarregarCenarios: () => Promise<void>;
  aviso: (texto: string, tipo?: "ok" | "erro" | "info") => void;
};

const C = createContext<Ctx>(null as any);
export const useApp = () => useContext(C);

export function Provedor({ children }: { children: ReactNode }) {
  const [usuario, setUsuario] = useState<Usuario | null>(null);
  const [carregado, setCarregado] = useState(false);
  const [cenarios, setCenarios] = useState<Cenario[]>([]);
  const [cenarioId, setCid] = useState<number | null>(() => { try { return Number(localStorage.getItem("plan_cenario")) || null; } catch { return null; } });
  const [avisos, setAvisos] = useState<{ id: number; texto: string; tipo: string }[]>([]);
  const [auth, setAuth] = useState<ConfigAuth | null>(null);
  const [erroAcesso, setErroAcesso] = useState<string | null>(null);
  const [definirSenha, setDefinirSenha] = useState(tipoLinkInicial === "invite" || tipoLinkInicial === "recovery");

  const aviso = useCallback((texto: string, tipo: "ok" | "erro" | "info" = "ok") => {
    const id = Date.now() + Math.random();
    setAvisos((a) => [...a, { id, texto, tipo }]);
    setTimeout(() => setAvisos((a) => a.filter((x) => x.id !== id)), tipo === "erro" ? 9000 : 4500);
  }, []);

  const recarregarCenarios = useCallback(async () => {
    const l: Cenario[] = await api.get("/api/cenarios");
    setCenarios(l);
  }, []);

  const carregarUsuario = useCallback(async () => {
    try {
      setUsuario(await api.get("/api/auth/me"));
      setErroAcesso(null);
      await recarregarCenarios();
    } catch (e: any) {
      setUsuario(null);
      // 403: autenticado no Supabase, mas sem cadastro/permissão na plataforma
      if (e?.status === 403) setErroAcesso(e.message);
      else token.set(null);
    }
  }, [recarregarCenarios]);

  useEffect(() => {
    let cancelar: (() => void) | undefined;
    const carregar = async () => {
      try {
        const cfg = await carregarConfigAuth();
        setAuth(cfg);
        const sb = supabase();
        if (sb) {
          const { data } = await sb.auth.getSession();
          if (data.session && !definirSenha) await carregarUsuario();
          const { data: sub } = sb.auth.onAuthStateChange((evento) => {
            if (evento === "SIGNED_OUT") setUsuario(null);
            if (evento === "PASSWORD_RECOVERY") setDefinirSenha(true);
          });
          cancelar = () => sub.subscription.unsubscribe();
        } else if (token.get()) {
          await carregarUsuario();
        }
      } catch (e: any) {
        setErroAcesso(e?.message || "Não foi possível contatar a API.");
      }
      setCarregado(true);
    };
    carregar();
    const h = () => setUsuario(null);
    window.addEventListener("sessao-expirada", h);
    return () => { window.removeEventListener("sessao-expirada", h); cancelar?.(); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const entrar = async (email: string, senha: string) => {
    const sb = supabase();
    if (sb) {
      const { error } = await sb.auth.signInWithPassword({ email, password: senha });
      if (error) throw new Error(error.message === "Invalid login credentials" ? "E-mail ou senha inválidos." : error.message);
    } else {
      const r = await api.post("/api/auth/login", { email, senha });
      token.set(r.token);
    }
    await carregarUsuario();
  };
  const sair = () => {
    supabase()?.auth.signOut();
    token.set(null);
    setUsuario(null);
    setErroAcesso(null);
  };
  const recuperarSenha = async (email: string) => {
    const sb = supabase();
    if (!sb) throw new Error("No modo local, a senha é redefinida pelo administrador.");
    const { error } = await sb.auth.resetPasswordForEmail(email, { redirectTo: window.location.origin });
    if (error) throw new Error(error.message);
  };
  const concluirDefinicaoSenha = async () => {
    setDefinirSenha(false);
    window.history.replaceState(null, "", window.location.pathname);
    await carregarUsuario();
  };
  const pode = (a: string) => !!usuario?.acoes.includes(a);
  const cenario = cenarios.find((c) => c.id === cenarioId) || cenarios.find((c) => c.estado === "publicado") ||
    cenarios.find((c) => c.tipo !== "simulacao") || null;
  const setCenarioId = (id: number) => { setCid(id); try { localStorage.setItem("plan_cenario", String(id)); } catch { /* ignore */ } };

  if (!carregado) return <div className="carregando" role="status">Carregando…</div>;
  return (
    <C.Provider value={{ usuario, auth, erroAcesso, definirSenha, concluirDefinicaoSenha, recuperarSenha, entrar, sair, pode, cenarios, cenario, setCenarioId, recarregarCenarios, aviso }}>
      {children}
      <div className="avisos" aria-live="polite">
        {avisos.map((a) => <div key={a.id} className={`aviso aviso-${a.tipo}`}>{a.texto}</div>)}
      </div>
    </C.Provider>
  );
}
