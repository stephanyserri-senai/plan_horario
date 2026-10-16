import { ReactNode, useState } from "react";
import { useApp } from "../contexto";
import { Erro } from "./ui";

/** Sugestão do sistema com o botão "Aceitar": ao aceitar, a ação é aplicada na hora (pela mesma validação de sempre). */
export function Sugestao({ texto, detalhe, aplicar, rotulo = "Aceitar sugestão", confirmar, feito, desabilitada, recusar }: {
  texto: ReactNode; detalhe?: ReactNode; aplicar: () => Promise<any>; rotulo?: string; confirmar?: string; feito?: (r: any) => void; desabilitada?: boolean;
  recusar?: () => Promise<any>;  // "não serve": registra a recusa para o sistema aprender
}) {
  const [recusada, setRecusada] = useState(false);
  const { aviso } = useApp();
  const [rodando, setRodando] = useState(false);
  const [erro, setErro] = useState<any>(null);
  const [ok, setOk] = useState(false);
  const aceitar = async () => {
    if (confirmar && !confirm(confirmar)) return;
    setErro(null); setRodando(true);
    try { const r = await aplicar(); setOk(true); aviso("Sugestão aplicada."); feito?.(r); }
    catch (e) { setErro(e); } finally { setRodando(false); }
  };
  return (
    <div className={`sugestao ${ok ? "sugestao-ok" : ""}`}>
      <span className="sugestao-ico" aria-hidden="true">💡</span>
      <div className="sugestao-txt"><b>Sugestão do sistema:</b> {texto}{detalhe && <div><small className="mudo">{detalhe}</small></div>}<Erro erro={erro} /></div>
      {ok ? <span className="sugestao-feito">✔ aplicada</span> : recusada ? <span className="mudo">recusada</span> : <span className="sugestao-botoes">
        <button className="btn btn-primario" disabled={rodando || desabilitada} onClick={aceitar}>{rodando ? "Aplicando…" : `✔ ${rotulo}`}</button>
        {recusar && <button className="btn-link" onClick={async () => { await recusar().catch(() => null); setRecusada(true); }}>Não serve</button>}</span>}
    </div>
  );
}
