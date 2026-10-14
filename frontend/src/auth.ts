// Autenticação no navegador.
// - modo "local": token JWT emitido pela API (/api/auth/login), guardado no localStorage.
// - modo "supabase": sessão do Supabase Auth (supabase-js); o access token é enviado à API,
//   que o valida no servidor. Apenas a URL do projeto e a chave PÚBLICA (anon/publishable)
//   chegam ao navegador — obtidas em tempo de execução de /api/auth/config.
import { createClient, type SupabaseClient } from "@supabase/supabase-js";

export type ConfigAuth = { modo: "local" | "supabase"; supabase_url: string | null; supabase_anon_key: string | null; executor: string; limite_upload_mb: number };

// Captura o tipo de link (convite/recuperação) ANTES de o supabase-js consumir o hash da URL.
export const tipoLinkInicial: string | null = (() => {
  try { return new URLSearchParams(window.location.hash.replace(/^#/, "")).get("type"); } catch { return null; }
})();

let config: ConfigAuth | null = null;
let cliente: SupabaseClient | null = null;

export async function carregarConfigAuth(): Promise<ConfigAuth> {
  if (!config) {
    const r = await fetch("/api/auth/config");
    if (!r.ok) throw new Error(`API indisponível (${r.status}).`);
    config = await r.json();
  }
  return config!;
}

export function configAuth() {
  return config;
}

export function supabase(): SupabaseClient | null {
  if (config?.modo !== "supabase" || !config.supabase_url || !config.supabase_anon_key) return null;
  if (!cliente) cliente = createClient(config.supabase_url, config.supabase_anon_key, { auth: { persistSession: true, autoRefreshToken: true, detectSessionInUrl: true } });
  return cliente;
}

const CHAVE_TOKEN = "plan_token";
export const tokenLocal = {
  get: () => { try { return localStorage.getItem(CHAVE_TOKEN); } catch { return null; } },
  set: (t: string | null) => { try { t ? localStorage.setItem(CHAVE_TOKEN, t) : localStorage.removeItem(CHAVE_TOKEN); } catch { /* sem armazenamento */ } },
};

export async function obterToken(): Promise<string | null> {
  const sb = supabase();
  if (sb) {
    const { data } = await sb.auth.getSession();
    return data.session?.access_token ?? null;
  }
  return tokenLocal.get();
}
