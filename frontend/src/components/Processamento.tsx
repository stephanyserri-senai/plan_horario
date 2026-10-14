import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import { useApp } from "../contexto";

/** Aviso amigável enquanto uma geração/simulação está sendo processada em segundo plano.
 *  Atualiza sozinho e oferece "Processar agora" se a espera passar do normal. */
export function StatusProcessamento({ ativo, aoConcluir }: { ativo: boolean; aoConcluir?: () => void }) {
  const { aviso, pode } = useApp();
  const [st, setSt] = useState<any | null>(null);
  const [enviando, setEnviando] = useState(false);
  const antes = useRef(false);
  useEffect(() => {
    if (!ativo) {
      if (antes.current) aoConcluir?.();
      antes.current = false;
      return;
    }
    antes.current = true;
    let vivo = true;
    const carregar = () => api.get("/api/processamento").then((r) => vivo && setSt(r)).catch(() => {});
    carregar();
    const t = setInterval(carregar, 10000);
    return () => { vivo = false; clearInterval(t); };
  }, [ativo]);
  if (!ativo) return null;
  const espera = st?.pendentes?.espera_min ?? 0;
  const fila = st?.modo === "fila";
  const demorando = fila && espera >= (st?.acionamento_automatico ? 8 : 20);
  const processarAgora = async () => {
    setEnviando(true);
    try { const r = await api.post("/api/processamento/acionar"); aviso(r.mensagem, r.resultado === "acionado" ? "info" : "erro"); }
    catch (e: any) { aviso(e.message, "erro"); }
    finally { setEnviando(false); }
  };
  return (
    <div className="processando" role="status" aria-live="polite">
      <span className="spinner" aria-hidden="true" />
      <div>
        <b>Processando…</b>{" "}
        {fila ? (st?.acionamento_automatico
          ? "Isso costuma levar de 2 a 5 minutos. Você pode continuar usando o sistema; esta página atualiza sozinha."
          : "O processamento começa automaticamente em até ~15 minutos. Você pode continuar usando o sistema; esta página atualiza sozinha.")
          : "Aguarde alguns instantes; esta página atualiza sozinha."}
        {fila && espera > 0 && <small className="mudo"> (aguardando há {Math.round(espera)} min)</small>}
        {demorando && (pode("otimizacao.executar") || pode("simulacao.executar")) && <div>
          <span>Está demorando mais que o normal. </span>
          <button className="btn" disabled={enviando} onClick={processarAgora}>{enviando ? "Enviando…" : "Processar agora"}</button>
        </div>}
      </div>
    </div>
  );
}
