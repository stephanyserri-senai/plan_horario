import { useState } from "react";
import { api } from "../api";
import { useApp } from "../contexto";
import { Badge, useCarregar } from "./ui";

/** Totais da prévia da estrutura curricular (total = EaD + presencial) e, em planilha antiga sem a divisão,
 *  a escolha da distribuição antes de importar (nada é assumido sem confirmação). */
export function ResumoCargasPrevia({ previa, redefinir }: { previa: any; redefinir: (opcoes: any) => void }) {
  const c = previa.cargas;
  const [tipo, setTipo] = useState<string>(previa.opcoes?.distribuicao?.tipo || "presencial");
  const [pct, setPct] = useState<number>(previa.opcoes?.distribuicao?.valor ?? 20);
  if (!c) return null;
  return (
    <div className="imp-cargas">
      <div className="imp-cargas-kpis">
        <div><small>Carga total (aluno)</small><b>{c.total} h</b></div>
        <div><small>EaD</small><b>{c.ead} h</b></div>
        <div><small>Presencial (vira aula)</small><b>{c.presencial} h</b></div>
        {c.inconsistencias > 0 && <div><small>Inconsistências</small><b className="falta-txt">{c.inconsistencias}</b></div>}
        {c.divisao_pendente > 0 && <div><small>Sem divisão</small><b className="alerta-txt">{c.divisao_pendente}</b></div>}
      </div>
      <div className="tabela-rolagem"><table className="tabela">
        <thead><tr><th>Curso</th><th>Versão</th><th>Público</th><th>UCs</th><th>Total</th><th>EaD</th><th>Presencial</th><th>Novas</th><th>Atualizadas</th><th>Sem mudança</th><th>Com erro</th></tr></thead>
        <tbody>{c.matrizes.map((m: any, i: number) => <tr key={i}><td>{m.curso}</td><td>{m.versao}</td><td>{m.publico || "todos"}</td><td>{m.ucs}</td>
          <td>{m.total} h</td><td>{m.ead} h</td><td>{m.presencial} h</td><td>{m.criar}</td><td>{m.atualizar}</td><td>{m.sem_alteracao}</td>
          <td>{m.com_erro + m.pendentes || ""}</td></tr>)}</tbody>
      </table></div>
      {c.divisao_pendente > 0 && <div className="imp-dist">
        <b>⚠ {c.divisao_pendente} UC(s) sem a divisão EaD/presencial (planilha antiga).</b>
        <span className="sub">Defina como distribuir as horas antes de importar — ou envie a planilha com as colunas “Modalidade da UC”, “Carga horária EaD (h)” e “Carga horária presencial (h)”.</span>
        <div className="linha">
          <label><input type="radio" checked={tipo === "presencial"} onChange={() => setTipo("presencial")} /> Tudo presencial</label>
          <label><input type="radio" checked={tipo === "ead"} onChange={() => setTipo("ead")} /> Tudo EaD</label>
          <label><input type="radio" checked={tipo === "percentual_ead"} onChange={() => setTipo("percentual_ead")} /> Percentual EaD:
            {" "}<input type="number" min={0} max={100} value={pct} onChange={(e) => setPct(Number(e.target.value))} disabled={tipo !== "percentual_ead"} /> %</label>
          <button className="btn btn-primario" onClick={() => redefinir({ distribuicao: { tipo, valor: pct } })}>Aplicar à prévia</button>
        </div>
      </div>}
    </div>
  );
}

/** Impacto da divisão EaD/presencial nas aulas já programadas do semestre selecionado, e a correção. */
export function ImpactoCarga() {
  const { cenario, pode, aviso } = useApp();
  const r = useCarregar<any>(() => (cenario ? api.get(`/api/cenarios/${cenario.id}/impacto-carga`) : Promise.resolve(null)), [cenario?.id]);
  const [aplicando, setAplicando] = useState(false);
  if (!cenario) return <p className="sub">Escolha o semestre no topo para ver o impacto nas aulas já programadas.</p>;
  const d = r.dados;
  const aplicar = async () => {
    setAplicando(true);
    try {
      const x = await api.post(`/api/cenarios/${cenario.id}/aplicar-carga`, {});
      aviso(`${x.aulas_removidas} aula(s) acima da carga presencial removida(s) (${x.horas_removidas} h). ${x.horas_faltando ? `Faltam ${x.horas_faltando} h: gere os horários de novo.` : ""}`);
      r.recarregar();
    } catch (e: any) { aviso(e.message, "erro"); } finally { setAplicando(false); }
  };
  return (
    <div className="imp-cargas">
      {r.carregando && !d && <p role="status">Calculando o impacto…</p>}
      {d && !d.itens.length && <p className="ok-txt">✔ As aulas de “{cenario.nome}” já respeitam a carga presencial das UCs.</p>}
      {d && d.itens.length > 0 && <>
        <p>Em <b>{cenario.nome}</b>: {d.resumo.turma_ucs} turma×UC com diferença · <b>{d.resumo.aulas_a_remover}</b> aula(s) programada(s) acima da carga
          presencial ({d.resumo.horas_a_remover} h) · faltam {d.resumo.horas_faltando} h. Aulas <b>realizadas</b> e fixas nunca são removidas.</p>
        <div className="tabela-rolagem"><table className="tabela">
          <thead><tr><th>Turma</th><th>UC</th><th>Modalidade</th><th>Total</th><th>EaD</th><th>Presencial</th><th>Realizadas</th><th>Programadas</th><th>Remover</th><th>Falta</th></tr></thead>
          <tbody>{d.itens.map((i: any) => <tr key={`${i.turma_uc_id}-${i.grupo}`}><td>{i.turma}{i.grupo ? ` (g${i.grupo})` : ""}</td><td>{i.uc}</td>
            <td>{i.modalidade}{!i.divisao_confirmada && <> <Badge tipo="alerta">a confirmar</Badge></>}</td><td>{i.total_h} h</td><td>{i.ead_h} h</td><td>{i.presencial_h} h</td>
            <td>{i.realizadas_h} h{i.realizadas_acima && <> <Badge tipo="alerta">acima</Badge></>}</td><td>{i.programadas_h} h</td>
            <td>{i.aulas_a_remover ? `${i.aulas_a_remover} aula(s) · ${i.horas_a_remover} h` : "—"}{i.aulas_fixas_mantidas ? ` (+${i.aulas_fixas_mantidas} fixa(s) mantida(s))` : ""}</td>
            <td>{i.falta_h ? `${i.falta_h} h` : "—"}</td></tr>)}</tbody>
        </table></div>
        {pode("alocacoes.editar") && <div className="acoes">
          <button className="btn btn-primario" disabled={aplicando || !d.resumo.aulas_a_remover} onClick={aplicar}>Aplicar a correção neste semestre</button>
          <span className="sub">Só em semestre em elaboração/validação; no publicado, crie uma proposta de alteração. O que faltar, gere de novo em “Gerar horários”.</span>
        </div>}
      </>}
      {r.erro && <div className="erro-box">{r.erro}</div>}
    </div>
  );
}
