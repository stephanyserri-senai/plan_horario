import { useState } from "react";
import { baixar, qs } from "../api";
import { useApp } from "../contexto";
import { useOpcoes } from "../hooks";

type Item = { id: string; ic: string; titulo: string; desc: string; url: string; nome: string; filtro?: [string, string, string]; precisaSemestre?: boolean };

const GRADE: Item[] = [
  { id: "turmas", ic: "👥", titulo: "Horário das turmas", desc: "Uma aba por turma com a semana a semana (UC, instrutor e sala de cada dia) e quanto falta de cada UC.",
    url: "/api/exportar/horario_turmas", nome: "horario_turmas.xlsx", filtro: ["turma_id", "turmas", "Todas as turmas"], precisaSemestre: true },
  { id: "instrutores", ic: "👩‍🏫", titulo: "Agenda e ocupação dos instrutores", desc: "Resumo de ocupação (horas por semana, folga, % ocupado) e a agenda de cada instrutor.",
    url: "/api/exportar/agenda_instrutores", nome: "agenda_instrutores.xlsx", filtro: ["instrutor_id", "instrutores", "Todos os instrutores"], precisaSemestre: true },
  { id: "ambientes", ic: "🏫", titulo: "Uso das salas e laboratórios", desc: "Quanto cada ambiente é usado (horas livres e ocupadas) e o quadro semanal de cada um.",
    url: "/api/exportar/uso_ambientes", nome: "salas_e_laboratorios.xlsx", filtro: ["ambiente_id", "ambientes", "Todos os ambientes"], precisaSemestre: true },
  { id: "carga", ic: "📊", titulo: "Carga horária por turma e UC", desc: "Para cada turma × UC: carga total, realizada, programada, o que falta e o risco de não terminar.",
    url: "/api/exportar/indicadores/turmas", nome: "carga_horaria_turmas_ucs.xlsx", precisaSemestre: true },
  { id: "lista", ic: "📋", titulo: "Lista completa de aulas", desc: "Todas as aulas do semestre, uma por linha (data, horário, turma, UC, instrutor, sala).",
    url: "/api/exportar/grade", nome: "aulas.xlsx", precisaSemestre: true },
  { id: "gargalos", ic: "⚠️", titulo: "Gargalos de capacidade", desc: "Onde falta sala, laboratório ou instrutor.", url: "/api/exportar/indicadores/gargalos", nome: "gargalos.xlsx", precisaSemestre: true },
];
const CADASTROS: Item[] = [
  { id: "c_est", ic: "📚", titulo: "Cursos, matrizes e UCs", desc: "No formato da planilha de importação.", url: "/api/exportar/cadastro/estrutura_curricular", nome: "cadastro_cursos_ucs.xlsx" },
  { id: "c_amb", ic: "🏫", titulo: "Salas e laboratórios", desc: "No formato da planilha de importação.", url: "/api/exportar/cadastro/ambientes", nome: "cadastro_salas.xlsx" },
  { id: "c_ins", ic: "👩‍🏫", titulo: "Instrutores (levantamento)", desc: "Áreas, turnos, dias, UCs que ministra e certificações.", url: "/api/exportar/cadastro/levantamento_instrutores", nome: "cadastro_instrutores.xlsx" },
  { id: "c_tur", ic: "👥", titulo: "Turmas", desc: "No formato da planilha de importação.", url: "/api/exportar/cadastro/turmas", nome: "cadastro_turmas.xlsx" },
];

function Cartao({ it, cenarioId }: { it: Item; cenarioId?: number }) {
  const [fid, setFid] = useState("");
  const [baixando, setBaixando] = useState(false);
  const ops = useOpcoes(it.filtro?.[1]);
  const bloqueado = it.precisaSemestre && !cenarioId;
  const ir = async () => {
    setBaixando(true);
    const p: Record<string, any> = it.precisaSemestre ? { cenario_id: cenarioId, formato: "xlsx" } : {};
    if (it.filtro && fid) p[it.filtro[0]] = fid;
    try { await baixar(`${it.url}${qs(p)}`, it.nome); } finally { setBaixando(false); }
  };
  return (
    <div className="exp-cartao">
      <div className="exp-ico" aria-hidden="true">{it.ic}</div>
      <div className="exp-corpo">
        <b>{it.titulo}</b>
        <p>{it.desc}</p>
        <div className="exp-acoes">
          {it.filtro && <select aria-label={`Filtrar ${it.titulo}`} value={fid} onChange={(e) => setFid(e.target.value)}>
            <option value="">{it.filtro[2]}</option>{ops.map((o) => <option key={o.id} value={o.id}>{o.rotulo}</option>)}</select>}
          <button className="btn btn-primario" disabled={bloqueado || baixando} onClick={ir}>{baixando ? "Gerando…" : "⬇ Baixar Excel"}</button>
        </div>
      </div>
    </div>
  );
}

/** Exportações prontas para uso: grade do semestre selecionado e cadastros (no formato de importação). */
export default function Exportar() {
  const { cenario } = useApp();
  return (
    <>
      <section className="card">
        <h2>Do semestre {cenario ? `— ${cenario.nome}` : ""}</h2>
        <p className="sub">{cenario ? "Usa o semestre e a versão selecionados no topo da tela." : "Crie ou selecione um semestre para exportar a grade."}</p>
        <div className="exp-grid">{GRADE.map((it) => <Cartao key={it.id} it={it} cenarioId={cenario?.id} />)}</div>
        <p className="sub">Precisa de CSV ou PDF, de um período específico ou do comparativo entre versões? Use <a href="/relatorios">Relatórios</a>.</p>
      </section>
      <section className="card">
        <h2>Cadastros</h2>
        <p className="sub">Saem no mesmo formato da importação: dá para corrigir no Excel e enviar de volta em “Importar”.</p>
        <div className="exp-grid">{CADASTROS.map((it) => <Cartao key={it.id} it={it} />)}</div>
      </section>
    </>
  );
}
