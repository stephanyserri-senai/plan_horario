// Elementos visuais simples e acessíveis: barras de carga horária, medidores de
// ocupação, anel de progresso e mini-gráfico semanal. A informação nunca depende
// só da cor: há sempre texto (e título ao passar o mouse).

const n1 = (v: number) => (Number(v) || 0).toLocaleString("pt-BR", { maximumFractionDigits: 1 });

/** Barra empilhada de carga horária: realizada | programada | sem horário. */
export function BarraCH({ total, realizada, programada, compacta }: { total: number; realizada: number; programada: number; compacta?: boolean }) {
  const t = Math.max(total || 0, 0.0001);
  const r = Math.min(realizada || 0, t), p = Math.min(programada || 0, t - r), f = Math.max(t - r - p, 0);
  const pct = (x: number) => `${(100 * x) / t}%`;
  const dica = `${n1(r)} h realizadas · ${n1(p)} h programadas · ${n1(f)} h sem horário (total ${n1(total)} h)`;
  return (
    <div className={`barra-ch ${compacta ? "compacta" : ""}`} title={dica}>
      <div className="trilho" role="img" aria-label={dica}>
        {r > 0 && <span className="seg realizada" style={{ width: pct(r) }} />}
        {p > 0 && <span className="seg programada" style={{ width: pct(p) }} />}
        {f > 0 && <span className="seg falta" style={{ width: pct(f) }} />}
      </div>
      {!compacta && <div className="barra-txt">
        <span>{Math.round((100 * (r + p)) / t)}% com horário</span>
        {f > 0.01 ? <span className="falta-txt">faltam {n1(f)} h</span> : <span className="ok-txt">✔ completo</span>}
      </div>}
    </div>
  );
}

export function LegendaCH() {
  return (
    <div className="legenda" aria-hidden="true">
      <span><i className="realizada" /> Realizada</span><span><i className="programada" /> Programada</span><span><i className="falta" /> Sem horário</span>
    </div>
  );
}

/** Medidor de ocupação (%), com faixas: pouco usado, adequado, quase no limite, acima do limite. */
export function Medidor({ pct, alerta = 85, critico = 100, detalhe }: { pct: number; alerta?: number; critico?: number; detalhe?: string }) {
  const v = Number(pct) || 0;
  const faixa = v > critico ? ["erro", "⛔ acima do limite"] : v >= alerta ? ["alerta", "⚠ quase no limite"] : v < 30 ? ["baixo", "pouco usado"] : ["ok", "adequado"];
  return (
    <div className="medidor" title={`${n1(v)}% — ${faixa[1]}${detalhe ? ` · ${detalhe}` : ""}`}>
      <div className="trilho" role="img" aria-label={`Ocupação ${n1(v)}%, ${faixa[1]}`}>
        <span className={`fill fill-${faixa[0]}`} style={{ width: `${Math.min(v, 100)}%` }} />
        <span className="marca-limite" style={{ left: `${alerta}%` }} />
      </div>
      <div className="barra-txt"><b>{Math.round(v)}%</b><span className={`faixa-${faixa[0]}`}>{faixa[1]}</span></div>
    </div>
  );
}

/** Anel de progresso para indicadores-resumo. */
export function Anel({ pct, rotulo, detalhe, tamanho = 96 }: { pct: number; rotulo: string; detalhe?: string; tamanho?: number }) {
  const v = Math.max(0, Math.min(Number(pct) || 0, 100));
  const r = 40, c = 2 * Math.PI * r;
  return (
    <div className="anel" title={`${rotulo}: ${n1(v)}%`}>
      <svg width={tamanho} height={tamanho} viewBox="0 0 100 100" role="img" aria-label={`${rotulo}: ${n1(v)}%`}>
        <circle cx="50" cy="50" r={r} className="anel-trilho" />
        <circle cx="50" cy="50" r={r} className="anel-valor" strokeDasharray={`${(c * v) / 100} ${c}`} transform="rotate(-90 50 50)" />
        <text x="50" y="55" textAnchor="middle" className="anel-txt">{Math.round(v)}%</text>
      </svg>
      <div><div className="anel-rotulo">{rotulo}</div>{detalhe && <div className="kpi-det">{detalhe}</div>}</div>
    </div>
  );
}

/** Horas por dia da semana (seg–sáb) em mini-barras. */
export function MiniSemana({ horas }: { horas: Record<string, number> }) {
  const dias = ["seg", "ter", "qua", "qui", "sex", "sáb"];
  const max = Math.max(1, ...dias.map((d) => horas?.[d] || 0));
  return (
    <div className="mini-semana" role="img" aria-label={dias.map((d) => `${d}: ${n1(horas?.[d] || 0)} h`).join(", ")}>
      {dias.map((d) => (
        <div key={d} className="dia" title={`${d}: ${n1(horas?.[d] || 0)} h por semana`}>
          <span className="col" style={{ height: `${(100 * (horas?.[d] || 0)) / max}%` }} />
          <small>{d}</small>
        </div>
      ))}
    </div>
  );
}

/** Linha do tempo do ciclo do cenário. */
export function FluxoCenario({ estado }: { estado: string }) {
  const etapas = [["em_elaboracao", "Elaboração"], ["em_validacao", "Validação"], ["aguardando_aprovacao", "Aprovação"], ["aprovado", "Aprovado"], ["publicado", "Publicado"]];
  const atual = etapas.findIndex(([e]) => e === estado);
  if (atual < 0) return null;
  return (
    <ol className="fluxo" aria-label="Etapas do cenário">
      {etapas.map(([e, r], i) => <li key={e} className={i < atual ? "feita" : i === atual ? "atual" : ""} aria-current={i === atual ? "step" : undefined}>
        <span className="bolinha">{i < atual ? "✔" : i + 1}</span>{r}</li>)}
    </ol>
  );
}
