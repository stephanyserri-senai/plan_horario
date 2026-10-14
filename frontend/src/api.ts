// Cliente HTTP da API. Toda autorização é validada no servidor; o frontend
// apenas oculta ações que o perfil não possui.
export class ErroApi extends Error {
  status: number;
  codigo?: string;
  detalhes?: any;
  constructor(status: number, mensagem: string, codigo?: string, detalhes?: any) {
    super(mensagem);
    this.status = status;
    this.codigo = codigo;
    this.detalhes = detalhes;
  }
}

const CHAVE_TOKEN = "plan_token";
export const token = {
  get: () => { try { return localStorage.getItem(CHAVE_TOKEN); } catch { return null; } },
  set: (t: string | null) => { try { t ? localStorage.setItem(CHAVE_TOKEN, t) : localStorage.removeItem(CHAVE_TOKEN); } catch { /* sem armazenamento */ } },
};

async function req<T = any>(metodo: string, caminho: string, corpo?: any, form?: FormData): Promise<T> {
  const headers: Record<string, string> = {};
  const t = token.get();
  if (t) headers["Authorization"] = `Bearer ${t}`;
  if (corpo !== undefined && !form) headers["Content-Type"] = "application/json";
  const r = await fetch(caminho, { method: metodo, headers, body: form ?? (corpo !== undefined ? JSON.stringify(corpo) : undefined) });
  if (r.status === 401) {
    token.set(null);
    window.dispatchEvent(new Event("sessao-expirada"));
  }
  if (!r.ok) {
    let j: any = {};
    try { j = await r.json(); } catch { /* corpo vazio */ }
    throw new ErroApi(r.status, j.erro || j.detail || `Erro ${r.status}`, j.codigo, j.detalhes);
  }
  const ct = r.headers.get("content-type") || "";
  return (ct.includes("application/json") ? r.json() : (r.blob() as any)) as Promise<T>;
}

export const api = {
  get: <T = any>(c: string) => req<T>("GET", c),
  post: <T = any>(c: string, b?: any) => req<T>("POST", c, b ?? {}),
  put: <T = any>(c: string, b?: any) => req<T>("PUT", c, b ?? {}),
  del: <T = any>(c: string) => req<T>("DELETE", c),
  upload: <T = any>(c: string, f: FormData) => req<T>("POST", c, undefined, f),
};

export async function baixar(caminho: string, nome: string) {
  const b: Blob = await req("GET", caminho);
  const url = URL.createObjectURL(b);
  const a = document.createElement("a");
  a.href = url;
  a.download = nome;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
}

export function qs(p: Record<string, any>) {
  const s = new URLSearchParams();
  Object.entries(p).forEach(([k, v]) => { if (v !== undefined && v !== null && v !== "") s.set(k, String(v)); });
  const r = s.toString();
  return r ? `?${r}` : "";
}

export const DIAS = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"];
export const DIAS_CURTOS = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"];

export function iso(d: Date) {
  const z = new Date(d.getTime() - d.getTimezoneOffset() * 60000);
  return z.toISOString().slice(0, 10);
}
export function segundaDe(d: Date) {
  const x = new Date(d);
  const w = (x.getDay() + 6) % 7;
  x.setDate(x.getDate() - w);
  return x;
}
export function addDias(d: Date, n: number) {
  const x = new Date(d);
  x.setDate(x.getDate() + n);
  return x;
}
export function dataBR(s?: string | null) {
  if (!s) return "";
  const [a, m, d] = s.slice(0, 10).split("-");
  return `${d}/${m}/${a}`;
}
