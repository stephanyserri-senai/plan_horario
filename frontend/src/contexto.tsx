import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { api, token } from "./api";

export type Usuario = { id: number; nome: string; email: string; perfil: string; acoes: string[]; escopo: any };
export type Cenario = { id: number; nome: string; estado: string; tipo: string; versao: number; unidade_id: number | null;
  periodo_inicio: string | null; periodo_fim: string | null; aulas: number; lock_version: number; cenario_origem_id: number | null };

type Ctx = {
  usuario: Usuario | null;
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

  const aviso = useCallback((texto: string, tipo: "ok" | "erro" | "info" = "ok") => {
    const id = Date.now() + Math.random();
    setAvisos((a) => [...a, { id, texto, tipo }]);
    setTimeout(() => setAvisos((a) => a.filter((x) => x.id !== id)), tipo === "erro" ? 9000 : 4500);
  }, []);

  const recarregarCenarios = useCallback(async () => {
    const l: Cenario[] = await api.get("/api/cenarios");
    setCenarios(l);
  }, []);

  useEffect(() => {
    const carregar = async () => {
      if (!token.get()) { setCarregado(true); return; }
      try { setUsuario(await api.get("/api/auth/me")); await recarregarCenarios(); } catch { token.set(null); }
      setCarregado(true);
    };
    carregar();
    const h = () => setUsuario(null);
    window.addEventListener("sessao-expirada", h);
    return () => window.removeEventListener("sessao-expirada", h);
  }, [recarregarCenarios]);

  const entrar = async (email: string, senha: string) => {
    const r = await api.post("/api/auth/login", { email, senha });
    token.set(r.token);
    setUsuario(await api.get("/api/auth/me"));
    await recarregarCenarios();
  };
  const sair = () => { token.set(null); setUsuario(null); };
  const pode = (a: string) => !!usuario?.acoes.includes(a);
  const cenario = cenarios.find((c) => c.id === cenarioId) || cenarios.find((c) => c.estado === "publicado") ||
    cenarios.find((c) => c.tipo !== "simulacao") || null;
  const setCenarioId = (id: number) => { setCid(id); try { localStorage.setItem("plan_cenario", String(id)); } catch { /* ignore */ } };

  if (!carregado) return <div className="carregando" role="status">Carregando…</div>;
  return (
    <C.Provider value={{ usuario, entrar, sair, pode, cenarios, cenario, setCenarioId, recarregarCenarios, aviso }}>
      {children}
      <div className="avisos" aria-live="polite">
        {avisos.map((a) => <div key={a.id} className={`aviso aviso-${a.tipo}`}>{a.texto}</div>)}
      </div>
    </C.Provider>
  );
}
