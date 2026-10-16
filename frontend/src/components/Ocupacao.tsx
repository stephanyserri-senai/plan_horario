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

/** Ocupação semana a semana (instrutores × salas), com ideal/teto e as semanas futuras marcadas como previsão.
 *  Com `comparar` (pontos com *_com), mostra também a ocupação com a(s) turma(s) simulada(s): tracejado = hoje, contínuo = com a turma. */
export function GraficoSerie({ dados, altura = 260, comparar = false }: { dados: any; altura?: number; comparar?: boolean }) {
  const pts: any[] = dados?.pontos || [];
  if (!pts.length) return <p className="mudo">Sem semanas no período.</p>;
  const futuras = pts.filter((p) => p.previsao);
  const pct = (v: any) => `${Number(v).toLocaleString("pt-BR", { maximumFractionDigits: 1 })}%`;
  const colsComparar = comparar ? [{ chave: "instrutores_pct_com", rotulo: "Instrutores com a turma (%)", alinhar: "dir" as const },
    { chave: "salas_pct_com", rotulo: "Salas com a turma (%)", alinhar: "dir" as const }, { chave: "aulas_h_com", rotulo: "Horas de aula com a turma", alinhar: "dir" as const }] : [];
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
          <Tooltip formatter={pct} labelFormatter={(l) => `Semana de ${l}`} />
          <Legend wrapperStyle={{ fontSize: 12 }} />
          {comparar ? <>
            <Line type="monotone" dataKey="instrutores_pct" name="Instrutores hoje" stroke="var(--grafico-1)" strokeWidth={1.5} strokeDasharray="5 4" dot={false} />
            <Line type="monotone" dataKey="instrutores_pct_com" name="Instrutores com a nova turma" stroke="var(--grafico-1)" strokeWidth={2.5} dot={{ r: 3 }} activeDot={{ r: 5 }} />
            <Line type="monotone" dataKey="salas_pct" name="Salas hoje" stroke="var(--grafico-2)" strokeWidth={1.5} strokeDasharray="5 4" dot={false} />
            <Line type="monotone" dataKey="salas_pct_com" name="Salas com a nova turma" stroke="var(--grafico-2)" strokeWidth={2.5} dot={{ r: 3 }} activeDot={{ r: 5 }} />
          </> : <>
            <Line type="monotone" dataKey="instrutores_pct" name="Instrutores (% da jornada)" stroke="var(--grafico-1)" strokeWidth={2} dot={{ r: 3 }} activeDot={{ r: 5 }} />
            <Line type="monotone" dataKey="salas_pct" name="Salas (% do horário)" stroke="var(--grafico-2)" strokeWidth={2} dot={{ r: 3 }} activeDot={{ r: 5 }} />
          </>}
        </LineChart>
      </ResponsiveContainer>
      <details className="tabela-dados"><summary>Ver os números (tabela)</summary>
        <Tabela colunas={[{ chave: "rotulo", rotulo: "Semana de" }, { chave: "instrutores_pct", rotulo: comparar ? "Instrutores hoje (%)" : "Instrutores (%)", alinhar: "dir" },
          { chave: "salas_pct", rotulo: comparar ? "Salas hoje (%)" : "Salas (%)", alinhar: "dir" }, { chave: "aulas_h", rotulo: "Horas de aula", alinhar: "dir" },
          ...colsComparar,
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

/** Análise do quadro de instrutores por área: demanda × capacidade (80%/90%), encaixe de uma turma nova e o aviso da proporção 5:4. */
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
        <div className={`kpi ${t.areas_sem_encaixe?.length ? "kpi-erro" : "kpi-ok"}`}><span>Cabe mais uma turma?</span>
          <b>{t.areas_sem_encaixe?.length ? `${t.areas_sem_encaixe.length} área(s) sem encaixe` : "sim, em todas"}</b>
          <small>{t.areas_sem_encaixe?.length ? t.areas_sem_encaixe.join(", ") : "folga até 90%, de preferência em 3 + 2 turnos"}</small></div>
        <div className="kpi"><span>Instrutores por turma (aviso)</span><b>{t.razao_instrutores_turma ?? "—"}</b><small>referência 1,25 (5 para 4 turmas) · {t.instrutores} instrutores, {t.turmas} turmas{t.avisos_proporcao ? ` · ${t.avisos_proporcao} área(s) abaixo` : ""}</small></div>
        <div className="kpi"><span>Demanda de aulas por semana</span><b>{t.demanda_semana_h} h</b><small>capacidade ideal {t.capacidade_ideal_h} h · teto {t.capacidade_teto_h} h</small></div>
        <div className={`kpi ${t.contratar_recomendado ? "kpi-erro" : "kpi-ok"}`}><span>Contratações sugeridas</span><b>{t.contratar_recomendado}</b>
          <small>{t.contratar_recomendado ? `pela ocupação, em ${contratar.map((a: any) => a.area).join(", ")}` : "pela ocupação, nenhuma área precisa contratar"}</small></div>
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
        { chave: "instrutores", rotulo: "Instrutores", alinhar: "dir", render: (a: any) => <span title={a.instrutores_outras_areas.map((o: any) =>
            `${o.nome} (área principal: ${o.area_principal || "—"}) — ${o.aula_semana_h} h/sem aqui, ${Math.round(o.fracao * 100)}% da jornada`).join("\n")}>
          {a.instrutores}{a.instrutores_outras_areas.length > 0 && <small className="mudo"> + {a.instrutores_outras_areas.length} de outra área</small>}
          <br /><small className="mudo">ref. 5:4 = {a.ideal_proporcao}</small></span> },
        { chave: "demanda_semana_h", rotulo: "Demanda (h/sem)", alinhar: "dir", render: (a: any) => <span title={`na grade: ${a.na_grade_h} h · ainda sem horário: ${a.sem_horario_semana_h} h`}>{a.demanda_semana_h}</span> },
        { chave: "capacidade_ideal_h", rotulo: "Capacidade 80% (h/sem)", alinhar: "dir" },
        { chave: "ocupacao_projetada_pct", rotulo: "Ocupação projetada", render: (a: any) => <BarraOcupacao pct={a.ocupacao_projetada_pct} /> },
        { chave: "nova_turma", rotulo: "Cabe nova turma?", render: (a: any) => <NovaTurma n={a.nova_turma} /> },
        { chave: "situacao", rotulo: "Situação", render: (a: any) => { const [tom, txt] = SITUACAO[a.situacao] || ["info", a.situacao]; return <Badge tipo={tom}>{txt}</Badge>; } },
        { chave: "contratar_recomendado", rotulo: "O que fazer", render: (a: any) => <small>{recomendacao(a)}</small> },
        { chave: "hip", rotulo: "Simular + turmas", render: (a: any) => a.area_id ? (
          <input type="number" min={0} max={20} className="num-curto" aria-label={`Turmas a mais em ${a.area}`} value={extra[a.area_id] || ""} placeholder="0"
            onChange={(e) => setExtra({ ...extra, [a.area_id]: Math.max(0, Number(e.target.value) || 0) })} />) : null },
      ]} linhas={d.areas} chave={(a: any) => a.area_id ?? a.area} />
    </div>
  );
}

const MODO: Record<string, string> = { divisao_preferida: "em 2 UCs", uma_uc: "em 1 UC", um_instrutor: "com um só instrutor", dividida: "dividida entre vários" };

/** Cabe mais uma turma nos turnos livres (até 90%)? Mostra a divisão encontrada (de preferência 3 + 2). */
function NovaTurma({ n }: { n: any }) {
  if (!n) return null;
  const plano = (n.plano || []).map((p: any) => `${p.instrutor} (${p.turnos})`).join(" + ");
  return (
    <span title={`Turma nova típica da área: ${n.turnos_semana} turno(s) por semana; divisão preferida ${n.divisao_preferida.join(" + ")}. `
      + `Turnos livres até o teto: ${n.turnos_livres_total} em ${n.instrutores_com_folga} instrutor(es).`}>
      {n.cabe ? <Badge tipo="ok">sim, {n.divisao_preferida.join(" + ")} {MODO[n.modo] && n.modo !== "divisao_preferida" ? MODO[n.modo] : ""}</Badge>
        : <Badge tipo="bloqueio">não cabe</Badge>}
      <br /><small className="mudo">{n.cabe ? plano : `precisa de ${n.turnos_semana} turnos; há ${n.turnos_livres_total} livres`}</small>
    </span>
  );
}

function recomendacao(a: any): string {
  const partes = [];
  if (a.situacao === "sem_instrutor") partes.push(`Não há instrutor na área para ${a.demanda_semana_h} h/semana.`);
  if (a.contratar_recomendado) partes.push(`Pela ocupação: contratar ${a.contratar_recomendado} instrutor(es) de 40 h para ficar em 80%.`);
  if (a.turmas && a.nova_turma && !a.nova_turma.cabe && !a.aviso_proporcao) partes.push("Não cabe mais uma turma com o quadro atual: para abrir outra, contrate ou habilite instrutor de outra área.");
  if (a.aviso_proporcao) partes.push(`⚠ Aviso: ${a.aviso_proporcao.texto}`);
  if (!partes.length && a.situacao === "ociosa") partes.push("Há folga: a área pode receber mais turmas ou ceder instrutores habilitados.");
  if (!partes.length) partes.push("Quadro adequado para a demanda prevista.");
  return partes.join(" ");
}
