import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, dataBR, qs } from "../api";
import { useApp } from "../contexto";
import { Avatar, BarraPct } from "./PerfilInstrutor";
import { Badge, Modal, useCarregar } from "./ui";

const DIAS_CURTOS = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb"];
const NOME_TURNO: Record<string, string> = { M: "Manhã", V: "Tarde", N: "Noite", S: "Sábado" };
const h = (v: number) => `${Number(v || 0).toLocaleString("pt-BR", { maximumFractionDigits: 1 })} h`;
const mesAtual = () => new Date().toISOString().slice(0, 7);

/** Disponibilidade dos instrutores numa linha por pessoa (turnos de cada dia) e a carga conforme a modalidade:
 * mensalista com jornada semanal fixa (teto de 90%) e horista com o termo de horas do mês, que muda a cada mês. */
export default function QuadroDisponibilidade() {
  const { cenario, pode } = useApp();
  const nav = useNavigate();
  const [q, setQ] = useState("");
  const [modalidade, setModalidade] = useState("");
  const [mes, setMes] = useState(mesAtual());
  const [termos, setTermos] = useState<any | null>(null);
  const r = useCarregar<any>(() => api.get(`/api/instrutores/disponibilidade${qs({ q, modalidade, mes, cenario_id: cenario?.id })}`), [q, modalidade, mes, cenario?.id]);
  const d = r.dados;
  const editavel = pode("cadastros.editar");
  return (
    <div className="quadro-disp">
      <div className="qd-resumo">
        <div className="qd-mod"><span className="modalidade modalidade-mensalista">Mensalista</span>
          <small><b>{d?.resumo.mensalistas ?? "—"}</b> instrutor(es) · jornada semanal fixa (ex.: 40 h), aulas até 90% dela</small></div>
        <div className="qd-mod"><span className="modalidade modalidade-horista">Horista</span>
          <small><b>{d?.resumo.horistas ?? "—"}</b> instrutor(es) · termo de horas a cada mês (ajustável numa urgência, com a concordância do instrutor)</small></div>
        {d?.resumo.horistas_sem_termo > 0 && <Badge tipo="alerta">{d.resumo.horistas_sem_termo} horista(s) sem termo de {d.rotulo_mes}</Badge>}
        {d?.resumo.sem_disponibilidade > 0 && <Badge tipo="bloqueio">{d.resumo.sem_disponibilidade} sem disponibilidade</Badge>}
      </div>
      <div className="filtros">
        <input type="search" placeholder="Pesquisar nome ou matrícula" aria-label="Pesquisar instrutor" value={q} onChange={(e) => setQ(e.target.value)} />
        <select aria-label="Modalidade" value={modalidade} onChange={(e) => setModalidade(e.target.value)}>
          <option value="">Mensalistas e horistas</option><option value="mensalista">Só mensalistas</option><option value="horista">Só horistas</option>
        </select>
        <label className="qd-mes">Termo do mês <input type="month" value={mes} onChange={(e) => setMes(e.target.value || mesAtual())} /></label>
        <span className="qd-legenda">{Object.entries(NOME_TURNO).map(([k, v]) => <span key={k}><span className={`tq tq-${k}`}>{k}</span> {v}</span>)}</span>
      </div>
      {r.erro && <div className="erro-box">{r.erro}</div>}
      {r.carregando && !d && <p role="status">Carregando…</p>}
      {d && <div className="tabela-wrap">
        <table className="tabela qd-tabela">
          <thead><tr><th>Instrutor</th>{DIAS_CURTOS.map((x) => <th key={x} className="qd-dia">{x}</th>)}<th>Disponível</th><th>Carga e ocupação</th><th>Ações</th></tr></thead>
          <tbody>
            {d.instrutores.map((l: any) => (
              <tr key={l.id}>
                <td><div className="qd-inst"><Avatar nome={l.nome} /><div><b>{l.nome}</b><small className="mudo">{l.matricula} ·{" "}
                  <span className={`modalidade modalidade-${l.modalidade}`}>{l.modalidade === "horista" ? "Horista" : "Mensalista"}</span></small></div></div></td>
                {l.dias.map((x: any) => (
                  <td key={x.dia} className="qd-dia" title={x.janelas.length ? x.janelas.join(" · ") : "sem aula neste dia"}>
                    {x.turnos.length ? x.turnos.map((t: string) => <span key={t} className={`tq tq-${t}`} aria-label={NOME_TURNO[t]}>{t}</span>)
                      : x.janelas.length ? <small className="mudo">{x.janelas[0]}</small> : <span className="mudo">—</span>}
                  </td>
                ))}
                <td className="dir qd-disp">{l.sem_disponibilidade ? <Badge tipo="bloqueio">não cadastrada</Badge> : `${h(l.disponivel_semana_h)}/sem`}</td>
                <td className="qd-carga"><Carga l={l} rotuloMes={d.rotulo_mes} /></td>
                <td><div className="acoes-linha">
                  {editavel && <button className="btn-link" onClick={() => nav(`/cadastros/instrutores?aba=instrutores&id=${l.id}&editar=1`)}>Editar disponibilidade</button>}
                  {l.modalidade === "horista" && <button className="btn-link" onClick={() => setTermos(l)}>Termos de horas</button>}
                </div></td>
              </tr>
            ))}
          </tbody>
        </table>
        {!d.instrutores.length && <p className="mudo">Nenhum instrutor encontrado.</p>}
      </div>}
      <TermosHorista inst={termos} fechar={() => { setTermos(null); r.recarregar(); }} />
    </div>
  );
}

function Carga({ l, rotuloMes }: { l: any; rotuloMes: string }) {
  if (l.modalidade !== "horista") {
    const o = l.ocupacao;
    return (
      <div className="qd-c">
        <span><b>{h(l.carga_semanal)}/sem</b> <small className="mudo">· aulas até {h(l.limite_letivo)}</small></span>
        {o && <><BarraPct valor={o.pct_jornada} fina neutra /><small className="mudo">{h(o.media_semanal_h)}/sem de aula · {o.pct_jornada}% da jornada</small></>}
      </div>
    );
  }
  const t = l.termo;
  if (!t.tem_termo) return (
    <div className="qd-c"><Badge tipo="alerta">sem termo de {rotuloMes}</Badge>
      <small className="mudo">vale o limite semanal do cadastro ({h(l.limite_letivo)}){t.programadas_h ? ` · ${h(t.programadas_h)} programadas no mês` : ""}</small></div>
  );
  return (
    <div className="qd-c">
      <span><b>{h(t.horas_aula)}</b> <small className="mudo">no termo de {t.rotulo}{t.horas_outras ? ` + ${h(t.horas_outras)} outras` : ""}
        {t.dias_semana?.length ? ` · ${t.dias_semana.map((x: number) => DIAS_CURTOS[x]).join(", ")}` : ""}</small></span>
      {t.programadas_h != null && <><BarraPct valor={t.pct} fina neutra /><small className={t.excedente_h ? "alerta-txt" : "mudo"}>
        {h(t.programadas_h)} programadas{t.excedente_h ? ` · ${h(t.excedente_h)} acima do termo (ajustável)` : ` · ${h(t.livre_h)} livres`}</small></>}
      {l.termos_no_semestre && l.termos_no_semestre.com_termo < l.termos_no_semestre.meses &&
        <small className="mudo">{l.termos_no_semestre.com_termo} de {l.termos_no_semestre.meses} meses do semestre com termo</small>}
    </div>
  );
}

/** Termos de horas do horista (janela): o mesmo painel do perfil do instrutor. */
export function TermosHorista({ inst, fechar }: { inst: any | null; fechar: () => void }) {
  return (
    <Modal titulo={`Termos de horas — ${inst?.nome || ""}`} aberto={!!inst} fechar={fechar} largo>
      {inst && <PainelTermo instId={inst.id} nome={inst.nome} />}
    </Modal>
  );
}

const SIT_MES: Record<string, [string, string]> = { passado: ["neutro", "mês passado"], atual: ["info", "mês atual"], proximo: ["alerta", "próximo mês"], futuro: ["neutro", "futuro"] };

/** Termo de horas do horista mês a mês: horas de aula do mês (e outras ocupações), dias do termo, o que já está programado (horas
 * lançadas) e os dias com aula fora do termo. O termo é feito no fim de cada mês para o mês seguinte: o painel mostra o prazo e a
 * sugestão — o que não estava previsto no termo deste mês (dia em que foi preciso contar com o instrutor) entra no do mês seguinte.
 * `url` + `somenteLeitura`: a visão do próprio instrutor no portal. */
export function PainelTermo({ instId, nome, url, somenteLeitura }: { instId: number; nome: string; url?: string; somenteLeitura?: boolean }) {
  const { cenario, pode, aviso } = useApp();
  const r = useCarregar<any>(() => api.get(url || `/api/instrutores/${instId}/termos${qs({ cenario_id: cenario?.id })}`), [instId, cenario?.id, url]);
  const [edit, setEdit] = useState<Record<string, any>>({});
  const [ajuste, setAjuste] = useState<any | null>(null);
  const editavel = !somenteLeitura && pode("cadastros.editar");
  const salvar = async (m: any) => {
    const v = { horas_aula: m.horas_aula, horas_outras: m.horas_outras || 0, observacao: m.observacao || "", dias_semana: m.dias_semana || [],
      agenda: m.agenda || {}, ...edit[m.mes] };
    if (v.horas_aula === undefined || v.horas_aula === "") { aviso("Informe as horas de aula do termo.", "erro"); return; }
    try {
      const x = await api.put(`/api/instrutores/${instId}/termos/${m.mes}${qs({ cenario_id: cenario?.id })}`, v);
      aviso(x.aviso || `Termo de ${x.rotulo} salvo: ${h(x.horas_aula)} de aula.`, x.aviso ? "erro" : undefined);
      setEdit((e) => { const n = { ...e }; delete n[m.mes]; return n; });
      r.recarregar();
    } catch (e: any) { aviso(e.message, "erro"); }
  };
  const ajustar = async () => {
    try {
      const x = await api.post(`/api/instrutores/${instId}/termos/${ajuste.mes}/ajuste${qs({ cenario_id: cenario?.id })}`,
        { horas_aula: ajuste.horas_aula === "" ? null : ajuste.horas_aula, incluir_dias: ajuste.incluir_dias, incluir_turnos: ajuste.incluir_turnos,
          motivo: ajuste.motivo, concordancia: ajuste.concordancia });
      aviso(`Termo de ${x.rotulo} ajustado. ${x.ajuste}`);
      setAjuste(null);
      r.recarregar();
    } catch (e: any) { aviso(e.message, "erro"); }
  };
  const campo = (m: any, k: string) => (edit[m.mes]?.[k] ?? m[k] ?? "");
  const mudar = (m: any, k: string, v: any) => setEdit((e) => ({ ...e, [m.mes]: { ...e[m.mes], [k]: v } }));
  const agenda = (m: any): Agenda => edit[m.mes]?.agenda ?? m.agenda ?? {};
  const [abertos, setAbertos] = useState<Set<string>>(new Set());
  const aberto = (m: any) => abertos.has(m.mes) || (!abertos.has(`-${m.mes}`) && (m.situacao === "atual" || m.situacao === "proximo"));
  const alternar = (m: any) => setAbertos((x) => { const n = new Set(x); const ab = aberto(m);
    n.delete(m.mes); n.delete(`-${m.mes}`); n.add(ab ? `-${m.mes}` : m.mes); return n; });
  const nomesDias = (ds: number[]) => ds.map((d) => DIAS_CURTOS[d]).join(", ");
  const px = r.dados?.proximo;
  if (r.carregando && !r.dados) return <p role="status">Carregando…</p>;
  if (r.erro) return <div className="erro-box">{r.erro}</div>;
  if (!r.dados) return null;
  if (r.dados.instrutor?.modalidade !== "horista") return <p className="sub">{nome} é mensalista: jornada semanal fixa, sem termo de horas.</p>;
  return (
    <div className="termo-painel">
      <p className="sub">{somenteLeitura
        ? "Seu termo de horas: as horas de aula de cada mês, os dias combinados e as horas já lançadas na grade. O termo é feito no fim de cada mês para o mês seguinte."
        : <>O termo de horas define a disponibilidade do horista no mês: as horas de aula, outras ocupações e, se for o caso, os dias da semana. É feito
          <b> no fim de cada mês para o mês seguinte</b>. Precisou do instrutor num dia fora do termo? Numa urgência ajuste o termo do mês (com a concordância
          dele) e <b>inclua o dia no termo do mês seguinte</b>.</>}</p>
      {px && <div className={`termo-proximo ${px.tem_termo ? "feito" : ""}`}>
        <div className="termo-proximo-cab">
          <span className="termo-proximo-ico" aria-hidden="true">{px.tem_termo ? "✅" : "🗓"}</span>
          <div><b>Termo de <span className="cap">{px.rotulo}</span></b>
            <small className="mudo">{px.tem_termo ? `já registrado: ${h(px.horas_aula)} de aula · ${h(px.programadas_h || 0)} já lançadas${px.excedente_h > 0 ? ` (${h(px.excedente_h)} acima do termo)` : ""}` : `a fazer até ${dataBR(px.prazo)}${px.faltam_dias >= 0 ? ` (${px.faltam_dias === 0 ? "hoje" : `faltam ${px.faltam_dias} dia(s)`})` : ""}`}</small></div>
          {editavel && !px.tem_termo && <button className="btn btn-primario btn-pequeno" onClick={() => setEdit((e) => ({ ...e, [px.mes]: {
            horas_aula: px.sugestao.horas_aula || "", horas_outras: px.sugestao.horas_outras || 0, dias_semana: px.sugestao.dias_semana,
            agenda: px.sugestao.agenda || {} } }))}>Usar a sugestão</button>}
        </div>
        {(px.sugestao.motivos.length > 0 || !px.tem_termo) && <div className="termo-sugestao">
          {!px.tem_termo && <span>Sugestão: <b>{h(px.sugestao.horas_aula)}</b> de aula{px.sugestao.dias_semana.length ? <> · dias <b>{nomesDias(px.sugestao.dias_semana)}</b></> : ""}</span>}
          {px.sugestao.motivos.length > 0 && <ul className="lista-limpa">{px.sugestao.motivos.map((x: string) => <li key={x}><small>• {x}</small></li>)}</ul>}
          {px.pendente.length > 0 && <small className="alerta-txt">⚠ O termo de {px.rotulo} ainda não tem esse(s) dia(s): revise-o.</small>}
        </div>}
      </div>}
      <div className="termos-lista">
        {r.dados.meses.map((m: any) => {
          const sujo = !!edit[m.mes];
          const [tomSit, rotSit] = SIT_MES[m.situacao] || ["neutro", ""];
          return (
            <div key={m.mes} className={`termo-mes ${m.tem_termo ? "" : "sem"} ${m.situacao === "atual" ? "atual" : ""}`}>
              <div className="termo-cab"><b>{m.rotulo}</b><Badge tipo={tomSit}>{rotSit}</Badge>{!m.tem_termo && <Badge tipo="alerta">sem termo</Badge>}
                {m.excedente_h > 0 && <Badge tipo="alerta">{h(m.excedente_h)} acima do termo</Badge>}
                {m.dias_fora?.length > 0 && <Badge tipo="alerta">aula fora do termo: {nomesDias(m.dias_fora)}</Badge>}
                {editavel && m.situacao !== "passado" && <button className="btn-link termo-urg" onClick={() => setAjuste({ mes: m.mes, rotulo: m.rotulo, horas_aula: m.tem_termo ? m.horas_aula : "",
                  dias_termo: m.dias_semana || [], incluir_dias: [], incluir_turnos: [], grade: Object.keys(m.agenda || {}).length > 0, fora: m.fora || [],
                  motivo: "", concordancia: false })}>⚡ Ajuste por urgência</button>}</div>
              {somenteLeitura ? <div className="termo-leitura">
                {m.tem_termo ? <><span><b>{h(m.horas_aula)}</b> de aula{m.horas_outras ? ` + ${h(m.horas_outras)} de outras ocupações` : ""}</span>
                  <span>Dias: <b>{m.dias_semana?.length ? nomesDias(m.dias_semana) : "qualquer dia"}</b></span>
                  {m.observacao && <small className="mudo">{m.observacao}</small>}</> : <span className="mudo">Termo ainda não registrado.</span>}
                {m.tem_termo && Object.keys(m.agenda || {}).length > 0 && <GradeTermo mes={m.mes} agenda={m.agenda} aulas={m.aulas_por_data || {}} horarios={m.horarios_aulas} />}
              </div> : <div className="termo-campos">
                <label>Horas de aula no mês<input type="number" min={0} max={220} step={0.5} value={campo(m, "horas_aula")} disabled={!editavel}
                  onChange={(e) => mudar(m, "horas_aula", e.target.value)} /></label>
                <label>Outras ocupações (h)<input type="number" min={0} max={220} step={0.5} value={campo(m, "horas_outras")} disabled={!editavel}
                  onChange={(e) => mudar(m, "horas_outras", e.target.value)} /></label>
                <label className="termo-obs">Observação<input value={campo(m, "observacao")} disabled={!editavel} placeholder="ex.: turmas e UCs do termo"
                  onChange={(e) => mudar(m, "observacao", e.target.value)} /></label>
                {editavel && <button className={`btn ${sujo ? "btn-primario" : ""}`} disabled={!sujo} onClick={() => salvar(m)}>{m.tem_termo ? "Salvar alteração" : "Registrar termo"}</button>}
              </div>}
              {!somenteLeitura && <div className="termo-grade-bloco">
                <button className="btn-link" onClick={() => alternar(m)}>{aberto(m) ? "▾" : "▸"} 📅 Grade do mês por dia e turno
                  {Object.keys(agenda(m)).length ? ` (${resumoGrade(agenda(m)).turnosAula} turno(s) de aula · ${resumoGrade(agenda(m)).turnosPl} de PL)` : " (sem grade: vale qualquer dia)"}</button>
                {aberto(m) && <>
                  {!Object.keys(agenda(m)).length && m.dias_semana?.length > 0 && <small className="mudo">Termo antigo por dia da semana ({nomesDias(m.dias_semana)}). Marque a grade para definir dia e turno.</small>}
                  <GradeTermo mes={m.mes} agenda={agenda(m)} aulas={m.aulas_por_data || {}} horarios={m.horarios_aulas} mudar={editavel ? (ag) => mudar(m, "agenda", ag) : undefined} />
                  {editavel && Object.keys(agenda(m)).length > 0 && (() => { const r = resumoGrade(agenda(m)); return (
                    <div className="termo-grade-total"><span>Pela grade: <b>{h(r.horasAula)}</b> de aula ({r.turnosAula} turnos) · <b>{h(r.horasPl)}</b> de planejamento ({r.turnosPl} turnos)</span>
                      <button className="btn btn-pequeno" onClick={() => setEdit((e) => ({ ...e, [m.mes]: { ...e[m.mes], horas_aula: Math.round(r.horasAula * 10) / 10, horas_outras: Math.round(r.horasPl * 10) / 10 } }))}>
                        Usar estes totais nas horas do termo</button></div>); })()}
                </>}
              </div>}
              {m.programadas_h != null && <div className="termo-prog">
                {m.tem_termo && <BarraPct valor={m.pct} fina neutra />}
                <small className="mudo">{h(m.programadas_h)} de aula lançadas no mês{m.tem_termo ? ` · ${Number(m.pct).toLocaleString("pt-BR", { maximumFractionDigits: 1 })}% do termo` : ""}
                  {m.dias_com_aula?.length ? ` · aulas às ${nomesDias(m.dias_com_aula).toLowerCase()}` : ""}</small>
              </div>}
              {ajuste?.mes === m.mes && <div className="termo-ajuste">
                <b>⚡ Ajuste por urgência — {m.rotulo}</b>
                <div className="termo-campos">
                  <label>Novas horas de aula no mês<input type="number" min={0} max={220} step={0.5} value={ajuste.horas_aula}
                    onChange={(e) => setAjuste({ ...ajuste, horas_aula: e.target.value })} /></label>
                  {ajuste.grade && ajuste.fora.length > 0 && <fieldset className="termo-dias"><legend>Incluir no termo as aulas fora dele</legend>
                    {ajuste.fora.map((f: any) => { const k = `${f.data}|${f.turno}`; const on = ajuste.incluir_turnos.some((x: any) => `${x.data}|${x.turno}` === k);
                      return <label key={k} className="dia-chk"><input type="checkbox" checked={on} onChange={(e) => setAjuste({ ...ajuste, incluir_turnos: e.target.checked
                        ? [...ajuste.incluir_turnos, f] : ajuste.incluir_turnos.filter((x: any) => `${x.data}|${x.turno}` !== k) })} />{dataBR(f.data).slice(0, 5)} {NOME_TURNO[f.turno]}</label>; })}
                  </fieldset>}
                  {!ajuste.grade && ajuste.dias_termo.length > 0 && <fieldset className="termo-dias"><legend>Incluir dia(s) fora do termo</legend>
                    {DIAS_CURTOS.map((nome, k) => ajuste.dias_termo.includes(k) ? null : <label key={k} className="dia-chk"><input type="checkbox" checked={ajuste.incluir_dias.includes(k)}
                      onChange={(e) => setAjuste({ ...ajuste, incluir_dias: e.target.checked ? [...ajuste.incluir_dias, k] : ajuste.incluir_dias.filter((x: number) => x !== k) })} />{nome}</label>)}
                  </fieldset>}
                  <label className="termo-obs">Motivo (a urgência)<input value={ajuste.motivo} placeholder="ex.: substituição da turma HTC-ELT-12 em 12/11"
                    onChange={(e) => setAjuste({ ...ajuste, motivo: e.target.value })} /></label>
                </div>
                <label className="concorda"><input type="checkbox" checked={ajuste.concordancia} onChange={(e) => setAjuste({ ...ajuste, concordancia: e.target.checked })} />
                  {nome} concordou com o ajuste do termo</label>
                <small className="mudo">Lembre de incluir o dia também no termo do mês seguinte.</small>
                <div className="acoes-linha">
                  <button className="btn" onClick={() => setAjuste(null)}>Cancelar</button>
                  <button className="btn btn-primario" disabled={!ajuste.concordancia || ajuste.motivo.trim().length < 5} onClick={ajustar}>Ajustar o termo</button>
                </div>
              </div>}
            </div>
          );
        })}
      </div>
    </div>
  );
}

const TURNOS_SEMANA = ["M", "V", "N"];
const HORAS_TURNO: Record<string, number> = { M: 220 / 60, V: 220 / 60, N: 200 / 60, S: 220 / 60 };
// horários usuais de entrada e saída de cada turno (dependem do turno de entrada do instrutor e do curso)
const HORARIOS: Record<string, string[]> = { M: ["07:30-11:30", "08:00-12:00"], V: ["13:30-17:30", "13:00-17:30", "13:00-17:00"],
  N: ["18:30-22:00", "18:00-22:00"], S: ["09:00-13:00", "08:00-12:00"] };
const ROT_TURNO: Record<string, string> = { M: "Manhã", V: "Tarde", N: "Noite", S: "Sábado" };
const iso = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
type Cel = { tipo: string; ini?: string; fim?: string };
type Agenda = Record<string, Record<string, Cel | string>>;
const cel = (v: any): Cel | null => (!v ? null : typeof v === "string" ? { tipo: v } : v);
const minutos = (x: string) => { const [h, m] = x.split(":").map(Number); return h * 60 + m; };
const horasCel = (tn: string, c: Cel) => (c.ini && c.fim ? (minutos(c.fim) - minutos(c.ini)) / 60 : c.tipo === "aula" ? HORAS_TURNO[tn] : 4);
const curto = (x?: string) => (x ? x.replace(/^0/, "").replace(":00", "h").replace(":", "h") : "");

function resumoGrade(agenda: Agenda) {
  let turnosAula = 0, turnosPl = 0, horasAula = 0, horasPl = 0;
  for (const ts of Object.values(agenda)) for (const [tn, v] of Object.entries(ts)) {
    const c = cel(v); if (!c) continue;
    if (c.tipo === "aula") { turnosAula++; horasAula += horasCel(tn, c); } else if (c.tipo === "pl") { turnosPl++; horasPl += horasCel(tn, c); }
  }
  return { turnosAula, turnosPl, horasAula, horasPl };
}

/** Grade do termo no mês, separada por semanas (segunda a sábado): em cada dia, os turnos — manhã, tarde, noite e o turno de sábado —
 * com aula ou planejamento (PL) e o HORÁRIO de entrada e saída daquele dia (ex.: 07:30–11:30 ou 08:00–12:00; 13:30–17:30, 13:00–17:30
 * ou 13:00–17:00; 18:30–22:00 ou 18:00–22:00), que depende do turno de entrada do instrutor e do curso. As horas do termo são contadas
 * por esse horário. Edição com “pincel”: escolha o tipo e o horário de cada turno e clique nos dias (clicar de novo apaga); no
 * cabeçalho, aplica o pincel em todas as semanas daquele dia. Ponto = aula já lançada; vermelho = aula fora do termo. Sem `mudar`: só leitura. */
export function GradeTermo({ mes, agenda, aulas, horarios, mudar }: { mes: string; agenda: Agenda; aulas: Record<string, string[]>;
  horarios?: Record<string, Record<string, string[]>>; mudar?: (a: Agenda) => void }) {
  const [tipo, setTipo] = useState<"aula" | "pl" | "livre">("aula");
  const [hor, setHor] = useState<Record<string, string>>({ M: HORARIOS.M[0], V: HORARIOS.V[0], N: HORARIOS.N[0], S: HORARIOS.S[0] });
  const [outro, setOutro] = useState<Record<string, string>>({ M: "07:00-11:00", V: "13:00-17:00", N: "18:00-22:00", S: "08:00-12:00" });
  const [a, mm] = mes.split("-").map(Number);
  const primeiro = new Date(a, mm - 1, 1, 12);
  const ultimo = new Date(a, mm, 0, 12).getDate();
  const ini = new Date(primeiro); ini.setDate(1 - ((primeiro.getDay() + 6) % 7));
  const semanas: Date[][] = [];
  for (let d = new Date(ini); ; ) {
    const sem: Date[] = [];
    for (let k = 0; k < 7; k++) { sem.push(new Date(d)); d.setDate(d.getDate() + 1); }
    semanas.push(sem.slice(0, 6));
    if (d.getMonth() !== mm - 1 && d > primeiro) break;
  }
  const doMes = (d: Date) => d.getMonth() === mm - 1;
  const turnosDo = (d: Date) => (d.getDay() === 6 ? ["S"] : TURNOS_SEMANA);
  const pincel = (tn: string): Cel | null => {
    if (tipo === "livre") return null;
    const h = hor[tn] === "outro" ? outro[tn] : hor[tn];
    if (!h) return { tipo };
    const [i0, f0] = h.split("-");
    return { tipo, ini: i0, fim: f0 };
  };
  const igual = (x: Cel | null, y: Cel | null) => (!x && !y) || (!!x && !!y && x.tipo === y.tipo && (x.ini || "") === (y.ini || "") && (x.fim || "") === (y.fim || ""));
  const definir = (ag: Agenda, k: string, tn: string, v: Cel | null) => {
    const dia = { ...(ag[k] || {}) };
    if (v) dia[tn] = v; else delete dia[tn];
    const n = { ...ag };
    if (Object.keys(dia).length) n[k] = dia; else delete n[k];
    return n;
  };
  const clicar = (k: string, tn: string) => {
    if (!mudar) return;
    const p = pincel(tn);
    mudar(definir(agenda, k, tn, igual(cel(agenda[k]?.[tn]), p) ? null : p));
  };
  const coluna = (dow: number, tn: string) => {
    if (!mudar) return;
    const p = pincel(tn);
    const datas: string[] = [];
    for (let dd = 1; dd <= ultimo; dd++) { const d = new Date(a, mm - 1, dd, 12); if ((d.getDay() + 6) % 7 === dow) datas.push(iso(d)); }
    const todas = datas.every((k) => igual(cel(agenda[k]?.[tn]), p));
    let n = agenda;
    for (const k of datas) n = definir(n, k, tn, todas ? null : p);
    mudar(n);
  };
  const hoje = iso(new Date());
  return (
    <div className={`grade-termo ${mudar ? "editavel" : ""}`}>
      {mudar && <div className="gt-pincel">
        <div className="gt-pincel-tipo" role="radiogroup" aria-label="O que marcar">
          <span className="mudo">Marcar:</span>
          {([["aula", "Aula"], ["pl", "PL (planejamento)"], ["livre", "Apagar"]] as const).map(([v, r]) =>
            <button key={v} type="button" role="radio" aria-checked={tipo === v} className={`chip-filtro ${tipo === v ? "on" : ""}`} onClick={() => setTipo(v)}>{r}</button>)}
        </div>
        {tipo !== "livre" && <div className="gt-pincel-hor">
          {["M", "V", "N", "S"].map((tn) => <label key={tn}><span>{ROT_TURNO[tn]}</span>
            <select value={hor[tn]} onChange={(e) => setHor({ ...hor, [tn]: e.target.value })}>
              {HORARIOS[tn].map((x) => <option key={x} value={x}>{x.replace("-", "–")}</option>)}
              <option value="outro">outro…</option><option value="">sem horário</option>
            </select>
            {hor[tn] === "outro" && <span className="gt-outro">
              <input type="time" value={outro[tn].split("-")[0]} onChange={(e) => setOutro({ ...outro, [tn]: `${e.target.value}-${outro[tn].split("-")[1]}` })} />
              –<input type="time" value={outro[tn].split("-")[1]} onChange={(e) => setOutro({ ...outro, [tn]: `${outro[tn].split("-")[0]}-${e.target.value}` })} /></span>}
          </label>)}
        </div>}
        <small className="mudo">O horário depende do turno de entrada do instrutor e do curso: escolha o horário de cada turno e clique nos dias
          (clicar de novo apaga). As horas do termo são contadas por esse horário.</small>
      </div>}
      <div className="gt-cab">
        {DIAS_CURTOS.map((nome, dow) => <div key={nome} className="gt-cab-dia"><b>{nome}</b>
          {mudar && <span className="gt-cab-turnos">{(dow === 5 ? ["S"] : TURNOS_SEMANA).map((tn) =>
            <button key={tn} type="button" title={`Aplicar em ${ROT_TURNO[tn].toLowerCase()} de todas as ${nome.toLowerCase()}s do mês`} onClick={() => coluna(dow, tn)}>{tn === "S" ? "todos" : tn}</button>)}</span>}
        </div>)}
      </div>
      {semanas.filter((sem) => sem.some((d) => doMes(d))).map((sem, i) => (
        <div key={i} className="gt-semana">
          {sem.map((d) => {
            const k = iso(d);
            if (!doMes(d)) return <div key={k} className="gt-dia fora-mes" />;
            const lancadas = aulas[k] || [];
            return (
              <div key={k} className={`gt-dia ${k === hoje ? "hoje" : ""}`}>
                <span className="gt-num">{d.getDate()}</span>
                <div className="gt-turnos">
                  {turnosDo(d).map((tn) => {
                    const c = cel(agenda[k]?.[tn]);
                    const tem = lancadas.includes(tn);
                    const ha = horarios?.[k]?.[tn];  // horário das aulas lançadas: fora do horário do termo naquele dia também conta como fora
                    const cobre = c?.tipo === "aula" && (!c.ini || !c.fim || !ha || (minutos(c.ini) <= minutos(ha[0]) && minutos(ha[1]) <= minutos(c.fim)));
                    return <button key={tn} type="button" disabled={!mudar} onClick={() => clicar(k, tn)}
                      className={`gt-t ${c ? `v-${c.tipo}` : ""} ${tem ? (cobre ? "com-aula" : "fora") : ""}`}
                      title={`${ROT_TURNO[tn]}: ${c ? `${c.tipo === "aula" ? "aula" : "planejamento (PL)"}${c.ini ? ` ${c.ini}–${c.fim}` : ""}` : "livre"}${tem ? ` · aula lançada${ha ? ` ${ha[0]}–${ha[1]}` : ""}${cobre ? "" : " (fora do termo)"}` : ""}`}>
                      <span>{tn === "S" ? "Sáb" : tn}{c?.tipo === "pl" ? " PL" : ""}{tem && <i aria-hidden="true">•</i>}</span>
                      {c?.ini && <small>{curto(c.ini)}–{curto(c.fim)}</small>}</button>;
                  })}
                </div>
              </div>);
          })}
        </div>))}
      <div className="gt-legenda"><span className="gt-t v-aula"><span>M</span></span> aula <span className="gt-t v-pl"><span>M PL</span></span> planejamento
        <span className="gt-t"><span>M</span></span> livre <span className="gt-t v-aula com-aula"><span>M<i>•</i></span></span> aula lançada
        <span className="gt-t fora"><span>M<i>•</i></span></span> aula fora do termo (dia, turno ou horário)</div>
    </div>
  );
}
