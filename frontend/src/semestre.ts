import type { Cenario } from "./contexto";

/** Semestre letivo de um planejamento (cenário), a partir do início do período: "2026/2". */
export function semestreDe(c: Pick<Cenario, "periodo_inicio"> | null | undefined): string {
  if (!c?.periodo_inicio) return "Sem período";
  const [a, m] = c.periodo_inicio.split("-").map(Number);
  return `${a}/${m <= 6 ? 1 : 2}`;
}

export function semestreAtual(hoje = new Date()): string {
  return `${hoje.getFullYear()}/${hoje.getMonth() < 6 ? 1 : 2}`;
}

const PRIORIDADE: Record<string, number> = {
  em_elaboracao: 0, em_validacao: 1, aguardando_aprovacao: 2, aprovado: 3, publicado: 4, em_otimizacao: 0, arquivado: 9,
};

/** Planejamentos de trabalho (sem simulações e arquivados) de um semestre, do mais "em andamento" ao publicado. */
export function versoesDoSemestre(cenarios: Cenario[], sem: string): Cenario[] {
  return cenarios.filter((c) => c.tipo !== "simulacao" && c.estado !== "arquivado" && semestreDe(c) === sem)
    .sort((a, b) => (PRIORIDADE[a.estado] ?? 5) - (PRIORIDADE[b.estado] ?? 5) || b.id - a.id);
}

export function semestres(cenarios: Cenario[]): string[] {
  return [...new Set(cenarios.filter((c) => c.tipo !== "simulacao" && c.estado !== "arquivado").map(semestreDe))].sort().reverse();
}

/** Versão que se abre ao escolher um semestre: a que está em edição; senão, a publicada/aprovada. */
export function principalDoSemestre(cenarios: Cenario[], sem: string): Cenario | null {
  return versoesDoSemestre(cenarios, sem)[0] || null;
}

export function rotuloVersao(c: Cenario): string {
  const est: Record<string, string> = { em_elaboracao: "Em edição", em_validacao: "Em validação", aguardando_aprovacao: "Aguardando aprovação",
    aprovado: "Aprovada", publicado: "Publicada (oficial)" };
  return `${c.tipo === "proposta" ? "Proposta de alteração" : est[c.estado] || c.estado}${c.tipo === "proposta" ? ` (${est[c.estado] || c.estado})` : ""} — ${c.nome}`;
}
