import { useEffect, useState } from "react";
import { api } from "./api";

const cache: Record<string, Promise<{ id: any; rotulo: string }[]>> = {};

export function invalidarOpcoes(ent?: string) {
  Object.keys(cache).forEach((k) => { if (!ent || k === ent) delete cache[k]; });
}

export function useOpcoes(ent: string | null | undefined) {
  const [ops, setOps] = useState<{ id: any; rotulo: string }[]>([]);
  useEffect(() => {
    if (!ent) return;
    cache[ent] = cache[ent] || api.get(`/api/cadastros/${ent}/opcoes?limite=2000`).catch(() => []);
    let vivo = true;
    cache[ent].then((o) => vivo && setOps(o));
    return () => { vivo = false; };
  }, [ent]);
  return ops;
}

export function rotuloDe(ops: { id: any; rotulo: string }[], id: any) {
  return ops.find((o) => String(o.id) === String(id))?.rotulo ?? (id ?? "");
}
