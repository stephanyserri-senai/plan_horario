import type { ReactNode } from "react";
import { Bar, BarChart, CartesianGrid, LabelList, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

/** Estilo único dos gráficos: grade fina e discreta, barras finas com ponta arredondada, valor no topo,
 * linhas de referência (ideal 80%, teto 90%) e um cartão de detalhe ao passar o mouse. */

export const pctBR = (v: any) => `${Number(v || 0).toLocaleString("pt-BR", { maximumFractionDigits: 1 })}%`;
export const EIXO = { fontSize: 11, fill: "var(--mudo)" };
export const GRADE = { stroke: "var(--borda)", strokeOpacity: 0.7, vertical: false } as const;

/** Cartão do tooltip: título + uma linha por série (marcador colorido, rótulo e valor em tinta de texto). */
export function CartaoTooltip({ active, payload, label, titulo, formatar = pctBR, extra }: any) {
  if (!active || !payload?.length) return null;
  const linha = payload[0]?.payload;
  return (
    <div className="tt-cartao">
      <div className="tt-titulo">{titulo ? titulo(label, linha) : label}</div>
      {payload.filter((p: any) => p.value != null).map((p: any) => (
        <div key={p.dataKey} className="tt-linha">
          <span className="tt-marca" style={{ background: p.color || p.stroke || p.fill }} />
          <span className="tt-rotulo">{p.name}</span><b>{formatar(p.value)}</b>
        </div>
      ))}
      {extra && extra(linha)}
    </div>
  );
}

/** Nome em maiúsculas vira "Economia criativa" (mais curto e fácil de ler no eixo). */
export const capitalizar = (t: string) => /[a-zà-ú]/.test(t) || t.includes("/") ? t : t.charAt(0) + t.slice(1).toLowerCase();

/** Rótulo inclinado, para muitas colunas com nomes longos (o nome inteiro aparece). */
function RotuloInclinado({ x, y, payload }: any) {
  return (
    <g transform={`translate(${x},${y + 6})`}>
      <text textAnchor="end" transform="rotate(-38)" fontSize={11} fill="var(--mudo)">{capitalizar(String(payload?.value ?? ""))}<title>{payload?.value}</title></text>
    </g>
  );
}

/** Rótulo do eixo X quebrado em até duas linhas (nomes longos de área cabem sem inclinar). */
function RotuloQuebrado({ x, y, payload, largura = 12 }: any) {
  const palavras = capitalizar(String(payload?.value ?? "")).split(/\s+/);
  const linhas: string[] = [];
  for (const p of palavras) {
    const ult = linhas[linhas.length - 1];
    if (ult && (ult + " " + p).length <= largura) linhas[linhas.length - 1] = ult + " " + p;
    else linhas.push(p);
  }
  const vis = linhas.slice(0, 2);
  if (linhas.length > 2) vis[1] = vis[1].slice(0, largura - 1) + "…";
  return (
    <text x={x} y={y + 12} textAnchor="middle" fontSize={11} fill="var(--mudo)">
      {vis.map((l, i) => <tspan key={i} x={x} dy={i ? 13 : 0}>{l}</tspan>)}
      <title>{payload?.value}</title>
    </text>
  );
}

/** Colunas verticais de uma série (ex.: ocupação por turno, por dia, por área). */
export function Colunas({ dados, x, y, nome, cor = "var(--grafico-1)", altura = 240, referencias = true, formatar = pctBR,
  maximo = 100, extraTooltip }: {
  dados: any[]; x: string; y: string; nome: string; cor?: string; altura?: number; referencias?: boolean;
  formatar?: (v: any) => string; maximo?: number; extraTooltip?: (linha: any) => ReactNode;
}) {
  if (!dados?.length) return <p className="mudo">Sem dados no período.</p>;
  const longos = dados.some((d) => String(d[x]).length > 9);
  const inclinar = longos && dados.length > 6;
  const maxNome = Math.max(...dados.map((d) => String(d[x]).length));
  return (
    <ResponsiveContainer width="100%" height={altura + (inclinar ? 40 : 0)}>
      <BarChart data={dados} margin={{ top: 22, right: referencias ? 56 : 8, bottom: 0, left: inclinar ? 8 : -8 }} barCategoryGap="22%">
        <CartesianGrid {...GRADE} />
        <XAxis dataKey={x} interval={0} tickLine={false} axisLine={{ stroke: "var(--borda)" }}
          height={inclinar ? Math.min(110, 14 + maxNome * 5.2) : longos ? 40 : 26} tick={inclinar ? <RotuloInclinado /> : longos ? <RotuloQuebrado /> : EIXO} />
        <YAxis domain={[0, (m: number) => Math.max(maximo, Math.ceil(m / 10) * 10)]} tickFormatter={(v) => `${v}%`} tick={EIXO}
          tickLine={false} axisLine={false} width={46} ticks={maximo === 100 ? [0, 25, 50, 75, 100] : undefined} />
        {referencias && <ReferenceLine y={80} stroke="var(--ok)" strokeDasharray="4 4" strokeOpacity={0.8}
          label={{ value: "ideal 80%", position: "right", fontSize: 10, fill: "var(--mudo)" }} />}
        {referencias && <ReferenceLine y={90} stroke="var(--erro)" strokeDasharray="4 4" strokeOpacity={0.8}
          label={{ value: "teto 90%", position: "right", fontSize: 10, fill: "var(--mudo)" }} />}
        <Tooltip cursor={{ fill: "var(--fundo)", opacity: 0.7 }} content={<CartaoTooltip formatar={formatar} extra={extraTooltip} titulo={(l: any) => capitalizar(String(l))} />} />
        <Bar dataKey={y} name={nome} fill={cor} radius={[5, 5, 0, 0]} maxBarSize={36} isAnimationActive={false}>
          <LabelList dataKey={y} position="top" formatter={(v: any) => formatar(v)} style={{ fontSize: 11, fontWeight: 600, fill: "var(--texto)" }} />
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

/** Cabeçalho de gráfico: título, frase curta do que mostra e um destaque (o maior valor). */
export function CabecalhoGrafico({ titulo, sub, destaque }: { titulo: ReactNode; sub?: ReactNode; destaque?: ReactNode }) {
  return (
    <div className="graf-cab">
      <div><h3>{titulo}</h3>{sub && <p>{sub}</p>}</div>
      {destaque && <div className="graf-destaque">{destaque}</div>}
    </div>
  );
}

/** "Maior: Noite · 22%" a partir dos dados. */
export function maior(dados: any[], x: string, y: string, formatar = pctBR) {
  if (!dados?.length) return null;
  const m = dados.reduce((a, b) => (Number(b[y]) > Number(a[y]) ? b : a));
  return <><small>maior</small><b>{formatar(m[y])}</b><small>{capitalizar(String(m[x]))}</small></>;
}
