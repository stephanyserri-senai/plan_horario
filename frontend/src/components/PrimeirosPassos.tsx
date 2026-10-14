import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { useApp } from "../contexto";

/** Checklist do que falta para chegar à grade pronta. Some quando tudo está feito
 *  (e pode ser recolhido pelo usuário). */
export function PrimeirosPassos() {
  const { cenario, pode } = useApp();
  const [d, setD] = useState<any | null>(null);
  const [oculto, setOculto] = useState(() => { try { return localStorage.getItem("plan.passos.oculto") === "1"; } catch { return false; } });
  useEffect(() => { api.get(`/api/primeiros-passos${cenario ? `?cenario_id=${cenario.id}` : ""}`).then(setD).catch(() => setD(null)); }, [cenario?.id]);
  if (!d || !pode("cadastros.ler")) return null;
  const completo = d.concluidos === d.total;
  if (completo || oculto) return oculto && !completo ? <p className="sub"><button className="btn-link" onClick={() => { setOculto(false); try { localStorage.removeItem("plan.passos.oculto"); } catch { /* */ } }}>Mostrar primeiros passos</button></p> : null;
  const proximo = d.passos.find((p: any) => !p.feito);
  return (
    <section className="card passos" aria-label="Primeiros passos">
      <div className="passos-topo">
        <h2>Primeiros passos — {d.concluidos} de {d.total} concluídos</h2>
        <button className="btn-link" onClick={() => { setOculto(true); try { localStorage.setItem("plan.passos.oculto", "1"); } catch { /* */ } }}>Ocultar</button>
      </div>
      <div className="barra"><span style={{ width: `${(100 * d.concluidos) / d.total}%` }} /></div>
      <ol>
        {d.passos.map((p: any) => (
          <li key={p.chave} className={p.feito ? "feito" : p === proximo ? "proximo" : ""}>
            <span className="marca-passo" aria-hidden="true">{p.feito ? "✔" : "○"}</span>
            <Link to={p.link}>{p.titulo}</Link>
            {p.feito ? <small className="mudo"> ({p.qtd})</small> : p === proximo && <small> ← próximo passo</small>}
          </li>
        ))}
      </ol>
      <p className="sub">Dica: em <Link to="/importacao">Importar planilha</Link> você pode trazer vários cadastros de uma vez a partir de um arquivo Excel.</p>
    </section>
  );
}
