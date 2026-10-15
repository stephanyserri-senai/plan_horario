import { useEffect, useState } from "react";
import { api, getUnidadeFiltro } from "./api";

const cache: Record<string, Promise<{ id: any; rotulo: string }[]>> = {};

export function invalidarOpcoes(ent?: string) {
  Object.keys(cache).forEach((k) => { if (!ent || k.split("|")[0] === ent) delete cache[k]; });
}

export function useOpcoes(ent: string | null | undefined) {
  const [ops, setOps] = useState<{ id: any; rotulo: string }[]>([]);
  useEffect(() => {
    if (!ent) return;
    const k = `${ent}|${getUnidadeFiltro()}`;  // as listas seguem a unidade escolhida no topo
    cache[k] = cache[k] || api.get(`/api/cadastros/${ent}/opcoes?limite=2000`).catch(() => []);
    let vivo = true;
    cache[k].then((o) => vivo && setOps(o));
    return () => { vivo = false; };
  }, [ent]);
  return ops;
}

export function rotuloDe(ops: { id: any; rotulo: string }[], id: any) {
  return ops.find((o) => String(o.id) === String(id))?.rotulo ?? (id ?? "");
}
