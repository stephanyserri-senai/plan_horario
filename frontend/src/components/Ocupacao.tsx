import { useState } from "react";
import { CartesianGrid, Legend, Line, LineChart, ReferenceArea, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api, qs } from "../api";
import { useApp } from "../contexto";
import { Badge, Tabela, useCarregar } from "./ui";

/** Faixas de ocupação da jornada: ideal até 80%, teto 90%. Cor de estado sempre com ícone e texto. */
export const FAIXAS: Record<string, [string, string, string]> = {
  ociosa: ["preferencia", "◐", "ociosa (< 50%)"], baixa: ["info", "▽", "baixa (50–70%)"], ideal: ["ok", "✓", "ideal (70–80%)"],
  atencao: ["alerta", "⚠", "atenção (80–90%)"], acima_teto: ["bloqueio", "⛔", "acima do teto (> 90%)"],
};

export function Faixa({ f }: { f: string }) {
  const [tom, , txt] = FAIXAS[f] || ["info", "", f];
  return <Badge tipo={tom}>{txt}</Badge>;  // o Badge já traz o ícone do estado
}

/** Barra horizontal de ocupação (0–100%+) com as marcas do ideal (80%) e do teto (90%). */
export function BarraOcupacao({ pct }: { pct: number }) {
  const v = Math.max(0, Math.min(110, Number(pct) || 0));
  const tom = pct > 90 ? "acima" : pct > 80 ? "atencao" : pct >= 70 ? "ideal" : "baixa";
  return (
    <div className="barra-ocup" role="img" aria-label={`${pct}% de ocupação`}>
      <div className="trilho">
        <span className={`barra-ocup-valor ${tom}`} style={{ width: `${(v / 110) * 100}%` }} />
        <i className="ocup-marca" style={{ left: `${(80 / 110) * 100}%` }} title="ideal 80%" />
        <i className="ocup-marca" style={{ left: `${(90 / 110) * 100}%` }} title="teto 90%" />
      </div>
      <b>{Number(pct).toLocaleString("pt-BR", { maximumFractionDigits: 1 })}%</b>
    </div>
  );
}

/** Ocupação semana a semana (instrutores × salas), com ideal/teto e as semanas futuras marcadas como previsão. */
export function GraficoSerie({ dados, altura = 260 }: { dados: any; altura?: number }) {
  const pts: any[] = dados?.pontos || [];
  if (!pts.length) return <p className="mudo">Sem semanas no período.</p>;
  const futuras = pts.filter((p) => p.previsao);
  return (
    <>
      <ResponsiveContainer width="100%" height={altura}>
        <LineChart data={pts} margin={{ top: 8, right: 72, bottom: 4, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--borda)" vertical={false} />
          <XAxis dataKey="rotulo" tick={{ fontSize: 11, fill: "var(--mudo)" }} interval="preserveStartEnd" />
          <YAxis unit="%" domain={[0, (max: number) => Math.max(100, Math.ceil(max / 10) * 10)]} tick={{ fontSize: 11, fill: "var(--mudo)" }} width={44} />
          {futuras.length > 0 && <ReferenceArea x1={futuras[0].rotulo} x2={futuras[futuras.length - 1].rotulo} fill="var(--fundo)" fillOpacity={0.9}
            label={{ value: "previsão (grade gerada)", position: "insideTopRight", fontSize: 11, fill: "var(--mudo)" }} />}
          <ReferenceLine y={80} stroke="var(--ok)" strokeDasharray="4 4" label={{ value: "ideal 80%", position: "right", fontSize: 11, fill: "var(--mudo)" }} />
          <ReferenceLine y={90} stroke="var(--erro)" strokeDasharray="4 4" label={{ value: "teto 90%", position: "right", fontSize: 11, fill: "var(--mudo)" }} />
          <Tooltip formatter={(v: any) => `${Number(v).toLocaleString("pt-BR", { maximumFractionDigits: 1 })}%`} labelFormatter={(l) => `Semana de ${l}`} />
          <Legend wrapperStyle={{ fontSize: 12 }} />
          <Line type="monotone" dataKey="instrutores_pct" name="Instrutores (% da jornada)" stroke="var(--grafico-1)" strokeWidth={2} dot={{ r: 3 }} activeDot={{ r: 5 }} />
          <Line type="monotone" dataKey="salas_pct" name="Salas (% do horário)" stroke="var(--grafico-2)" strokeWidth={2} dot={{ r: 3 }} activeDot={{ r: 5 }} />
        </LineChart>
      </ResponsiveContainer>
      <details className="tabela-dados"><summary>Ver os números (tabela)</summary>
        <Tabela colunas={[{ chave: "rotulo", rotulo: "Semana de" }, { chave: "instrutores_pct", rotulo: "Instrutores (%)", alinhar: "dir" },
          { chave: "salas_pct", rotulo: "Salas (%)", alinhar: "dir" }, { chave: "aulas_h", rotulo: "Horas de aula", alinhar: "dir" },
          { chave: "instrutores_acima_teto", rotulo: "Instrutores acima de 90%", alinhar: "dir" },
          { chave: "previsao", rotulo: "", render: (p: any) => p.previsao ? <small className="mudo">previsão</small> : "" }]} linhas={pts} chave={(p: any) => p.semana} />
      </details>
    </>
  );
}

const SITUACAO: Record<string, [string, string]> = {
  adequado: ["ok", "✓ quadro adequado"], ociosa: ["info", "◌ quadro com folga"], atencao: ["alerta", "⚠ atenção"],
  contratar: ["bloqueio", "⛔ contratar"], sem_instrutor: ["bloqueio", "⛔ sem instrutor"],
};

/** Análise do quadro de instrutores por área: demanda × capacidade (80%/90%) e proporção 5 instrutores : 4 turmas. */
export function QuadroInstrutores() {
  const { cenario } = useApp();
  const [extra, setExtra] = useState<Record<string, number>>({});
  const [simId, setSimId] = useState("");
  const sims = useCarregar<any[]>(() => api.get("/api/simulador").catch(() => []), []);
  const ext = Object.entries(extra).filter(([, n]) => n > 0).map(([a, n]) => `${a}:${n}`).join(",");
  const q = useCarregar<any>(() => cenario ? api.get(`/api/consultas/quadro-instrutores${qs({ cenario_id: cenario.id, extra: ext, simulacao_id: simId })}`) : Promise.resolve(null),
    [cenario?.id, ext, simId]);
  const d = q.dados;
  if (!d) return q.erro ? <div className="erro-box">{q.erro}</div> : <p role="status">Analisando o quadro…</p>;
  const t = d.total;
  const contratar = d.areas.filter((a: any) => a.contratar_recomendado > 0);
  return (
    <div className="quadro-instrutores">
      <div className="kpis">
        <div className="kpi"><span>Ocupação projetada da jornada</span><b>{t.ocupacao_projetada_pct}%</b><small>ideal até {d.parametros.ideal_pct}% · teto {d.parametros.teto_pct}%</small></div>
        <div className="kpi"><span>Instrutores por turma</span><b>{t.razao_instrutores_turma ?? "—"}</b><small>ideal 1,25 (5 para 4 turmas) · {t.instrutores} instrutores, {t.turmas} turmas</small></div>
        <div className="kpi"><span>Demanda de aulas por semana</span><b>{t.demanda_semana_h} h</b><small>capacidade ideal {t.capacidade_ideal_h} h · teto {t.capacidade_teto_h} h</small></div>
        <div className={`kpi ${t.contratar_recomendado ? "kpi-erro" : "kpi-ok"}`}><span>Contratações sugeridas</span><b>{t.contratar_recomendado}</b>
          <small>{t.contratar_recomendado ? `em ${contratar.map((a: any) => a.area).join(", ")}` : "nenhuma área precisa contratar"}</small></div>
      </div>
      <p className="sub">{d.explicacao} Período analisado: de {d.referencia.split("-").reverse().join("/")} a {d.fim.split("-").reverse().join("/")} ({d.semanas_restantes} semanas).</p>
      <div className="filtros">
        <label>Incluir turmas de uma simulação <select value={simId} onChange={(e) => setSimId(e.target.value)}>
          <option value="">— nenhuma —</option>{(sims.dados || []).map((s: any) => <option key={s.id} value={s.id}>{s.nome}</option>)}</select></label>
        {Object.values(extra).some((n) => n > 0) && <button className="btn-link" onClick={() => setExtra({})}>limpar turmas hipotéticas</button>}
      </div>
      <Tabela colunas={[
        { chave: "area", rotulo: "Área", render: (a: any) => <b>{a.area}</b> },
        { chave: "turmas", rotulo: "Turmas", alinhar: "dir", render: (a: any) => <span title={[...a.turmas_lista, ...a.turmas_simuladas.map((x: string) => `${x} (simulada)`)].join(", ")}>
          {a.turmas}{a.turmas_hipoteticas ? <small className="mudo"> (+{a.turmas_hipoteticas} hip.)</small> : ""}</span> },
        { chave: "instrutores", rotulo: "Instrutores", alinhar: "dir", render: (a: any) => <span>{a.instrutores} <small className="mudo">/ ideal {a.ideal_proporcao}</small></span> },
        { chave: "demanda_semana_h", rotulo: "Demanda (h/sem)", alinhar: "dir", render: (a: any) => <span title={`na grade: ${a.na_grade_h} h · ainda sem horário: ${a.sem_horario_semana_h} h`}>{a.demanda_semana_h}</span> },
        { chave: "capacidade_ideal_h", rotulo: "Capacidade 80% (h/sem)", alinhar: "dir" },
        { chave: "ocupacao_projetada_pct", rotulo: "Ocupação projetada", render: (a: any) => <BarraOcupacao pct={a.ocupacao_projetada_pct} /> },
        { chave: "situacao", rotulo: "Situação", render: (a: any) => { const [tom, txt] = SITUACAO[a.situacao] || ["info", a.situacao]; return <Badge tipo={tom}>{txt}</Badge>; } },
        { chave: "contratar_recomendado", rotulo: "O que fazer", render: (a: any) => <small>{recomendacao(a)}</small> },
        { chave: "hip", rotulo: "Simular + turmas", render: (a: any) => a.area_id ? (
          <input type="number" min={0} max={20} className="num-curto" aria-label={`Turmas a mais em ${a.area}`} value={extra[a.area_id] || ""} placeholder="0"
            onChange={(e) => setExtra({ ...extra, [a.area_id]: Math.max(0, Number(e.target.value) || 0) })} />) : null },
      ]} linhas={d.areas} chave={(a: any) => a.area_id ?? a.area} />
    </div>
  );
}

function recomendacao(a: any): string {
  const partes = [];
  if (a.situacao === "sem_instrutor") partes.push(`Não há instrutor na área para ${a.demanda_semana_h} h/semana.`);
  if (a.contratar_por_ocupacao) partes.push(`Pela ocupação: contratar ${a.contratar_por_ocupacao} instrutor(es) de 40 h para ficar em 80%.`);
  if (a.contratar_por_proporcao) partes.push(`Pela proporção 5:4: faltam ${a.contratar_por_proporcao} instrutor(es) para ${a.turmas} turma(s).`);
  if (!partes.length && a.situacao === "ociosa") partes.push("Há folga: a área pode receber mais turmas ou ceder instrutores habilitados.");
  if (!partes.length) partes.push("Quadro adequado para a demanda prevista.");
  return partes.join(" ");
}
