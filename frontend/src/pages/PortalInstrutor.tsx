import { useEffect, useMemo, useState } from "react";
import { addDias, api, baixar, dataBR, DIAS_CURTOS, iso, segundaDe } from "../api";
import { CompetenciasUCs, JornadaInstrutor } from "../components/CamposEspeciais";
import Perfil from "../components/Perfil";
import { Abas, Badge, Campo, Erro, useCarregar } from "../components/ui";
import { useApp } from "../contexto";
import { Aderencia, IndicesAderencia, JornadaMensalista, Ocupacao, Pdi } from "../components/PerfilInstrutor";
import { PainelTermo } from "../components/QuadroDisponibilidade";
import { MinhasImpressoes } from "../components/Impressoes";

const TIPOS: [string, string][] = [["sugestao", "Sugestão"], ["dificuldade", "Dificuldade"], ["recurso", "Recurso ou material"], ["horario", "Horário"], ["outro", "Outro"]];
const STATUS: Record<string, [string, string]> = { nova: ["info", "Enviada"], lida: ["alerta", "Lida pela coordenação"], resolvida: ["ok", "Resolvida"] };

/** Página exclusiva do perfil "instrutor": os próprios dados, as próprias turmas e as observações. */
export default function PortalInstrutor({ trocarSenha }: { trocarSenha: () => void }) {
  const { usuario } = useApp();
  const [aba, setAba] = useState("turmas");
  const eu = useCarregar<any>(() => api.get("/api/portal/eu"), []);
  const obs = useCarregar<any[]>(() => api.get("/api/portal/observacoes"), []);
  const respostas = (obs.dados || []).filter((o) => o.resposta).length;
  const notifs = useCarregar<any[]>(() => api.get("/api/portal/notificacoes"), []);
  const novas = (notifs.dados || []).filter((n) => !n.lida).length;
  const solic = useCarregar<any[]>(() => api.get("/api/portal/solicitacoes"), []);
  const aguardando = (solic.dados || []).filter((x) => x.status === "pendente").length;
  const irPara = (a: string) => { setAba(a); window.scrollTo({ top: 0 }); };
  return (
    <div className="portal">
      <header className="portal-topo">
        <img src="/icone.png" alt="" width={36} height={36} />
        <div className="portal-marca"><b>Portal do instrutor</b><small>Planejamento Acadêmico</small></div>
        <button className={`sino ${novas ? "com-novas" : ""}`} aria-label={`Notificações: ${novas} nova(s)`} onClick={() => irPara("notif")}>
          🔔{novas > 0 && <span className="sino-n">{novas}</span>}</button>
        <Perfil trocarSenha={trocarSenha} />
      </header>
      <main className="portal-main">
        {eu.erro ? <div className="card portal-aviso"><h2>Acesso ainda não liberado</h2><p>{eu.erro}</p></div> : <>
          <section className="portal-hero">
            <div>
              <h1>Olá, {(eu.dados?.nome || usuario?.nome || "").split(" ")[0]}!</h1>
              <p>Aqui você confere suas turmas e horários, mantém suas áreas, UCs e disponibilidade em dia e manda sugestões para a coordenação.</p>
            </div>
            {eu.dados && <div className="portal-status">
              {eu.dados.atualizado_pelo_instrutor_em
                ? <span className="chip-status ok">✔ Dados atualizados em {new Date(eu.dados.atualizado_pelo_instrutor_em).toLocaleDateString("pt-BR")}</span>
                : <button className="chip-status alerta" onClick={() => setAba("dados")}>! Confira e complete seus dados</button>}
              <span className="chip-status">{eu.dados.ucs_competencia.length} UC(s) que ministra</span>
              {novas > 0 && <button className="chip-status alerta" onClick={() => irPara("notif")}>🔔 {novas} novidade{novas > 1 ? "s" : ""}</button>}
            </div>}
          </section>
          <Abas abas={[{ id: "turmas", rotulo: "📅 Minhas turmas e horários" }, { id: "dados", rotulo: "🧑‍🏫 Meus dados e expertise" },
            { id: "desenv", rotulo: "📈 Meu desenvolvimento" },
            { id: "obs", rotulo: `💬 Minhas observações${respostas ? ` (${respostas} resposta${respostas > 1 ? "s" : ""})` : ""}` },
            { id: "solic", rotulo: `📝 Solicitações${aguardando ? ` (${aguardando} aguardando)` : ""}` },
            { id: "impressoes", rotulo: "🖨 Impressões" },
            { id: "notif", rotulo: `🔔 Notificações${novas ? ` (${novas})` : ""}` }]} ativa={aba} mudar={setAba} />
          {aba === "turmas" && <MinhasTurmas aoEnviar={obs.recarregar} />}
          {aba === "dados" && eu.dados && <MeusDados eu={eu.dados} salvo={eu.recarregar} />}
          {aba === "desenv" && <MeuDesenvolvimento registrado={() => { obs.recarregar(); eu.recarregar(); }} />}
          {aba === "obs" && <MinhasObservacoes lista={obs.dados} />}
          {aba === "impressoes" && <MinhasImpressoes />}
          {aba === "solic" && eu.dados && <MinhasSolicitacoes lista={solic.dados} turnos={eu.dados.turnos} mudou={solic.recarregar} />}
          {aba === "notif" && <Notificacoes lista={notifs.dados} mudou={notifs.recarregar} ir={(a) => { irPara(a); if (a === "dados") eu.recarregar(); if (a === "obs") obs.recarregar(); if (a === "solic") solic.recarregar(); }} />}
        </>}
      </main>
    </div>
  );
}

// ---------------------------------------------------------------------------- turmas e horários
function MinhasTurmas({ aoEnviar }: { aoEnviar: () => void }) {
  const r = useCarregar<any[]>(() => api.get("/api/portal/turmas"), []);
  const [semIdx, setSemIdx] = useState(0);
  if (r.carregando && !r.dados) return <p role="status">Carregando suas turmas…</p>;
  if (r.erro) return <div className="erro-box">{r.erro}</div>;
  const sems = r.dados || [];
  if (!sems.length) return <div className="card portal-aviso"><h2>Nenhuma turma atribuída ainda</h2>
    <p>Quando a coordenação montar a grade com você, suas turmas, UCs e horários aparecem aqui. Enquanto isso, mantenha seus dados e expertise atualizados.</p></div>;
  const s = sems[Math.min(semIdx, sems.length - 1)];
  return (
    <>
      <div className="portal-sem">
        {sems.length > 1 && <select aria-label="Semestre" value={semIdx} onChange={(e) => setSemIdx(Number(e.target.value))}>
          {sems.map((x, i) => <option key={x.cenario_id} value={i}>Semestre {x.semestre}</option>)}</select>}
        <b>Semestre {s.semestre}</b> <small className="mudo">{dataBR(s.inicio)} a {dataBR(s.fim)}</small>
        {s.publicado ? <Badge tipo="ok">Horário publicado</Badge> : <Badge tipo="alerta">Proposta em planejamento: pode mudar até a publicação</Badge>}
        <button className="btn" onClick={() => baixar(`/api/portal/agenda?cenario_id=${s.cenario_id}`, `minha_agenda_${s.semestre.replace("/", "-")}.xlsx`)}>⬇ Baixar minha agenda (Excel)</button>
      </div>
      <SemanaInstrutor aulas={s.aulas} reservas={s.reservas || []} inicio={s.inicio} />
      <h2 className="portal-sub">Turmas e UCs atribuídas ({s.turmas_ucs.length})</h2>
      <div className="portal-cards">{s.turmas_ucs.map((t: any) => <CartaoTurma key={t.turma_uc_id} t={t} aoEnviar={() => { aoEnviar(); r.recarregar(); }} />)}</div>
    </>
  );
}

function SemanaInstrutor({ aulas, reservas, inicio }: { aulas: any[]; reservas: any[]; inicio: string }) {
  const hoje = iso(new Date());
  const primeira = aulas.find((a) => a.data >= hoje)?.data || aulas[0]?.data || inicio;
  const [seg, setSeg] = useState(() => segundaDe(new Date(primeira + "T12:00:00")));
  useEffect(() => setSeg(segundaDe(new Date(primeira + "T12:00:00"))), [primeira]);
  const dias = Array.from({ length: 6 }, (_, i) => addDias(seg, i));
  const naSemana = aulas.filter((a) => a.data >= iso(dias[0]) && a.data <= iso(dias[5]));
  const usaSab = naSemana.some((a) => a.data === iso(dias[5]));
  const resSemana = reservas.filter((r) => r.data >= iso(dias[0]) && r.data <= iso(dias[5]));
  const turnos = [...new Set([...aulas.map((a) => a.turno || "—"), ...reservas.map(turnoDaHora)])].sort((a, b) => ordemTurno(a) - ordemTurno(b));
  const blocos = (turno: string, d: Date) => {
    const xs = naSemana.filter((a) => a.data === iso(d) && (a.turno || "—") === turno);
    const g = new Map<string, any>();
    for (const a of xs) {
      const k = `${a.turma}|${a.uc}`;
      const b = g.get(k) || { ...a, ini: a.inicio, fimB: a.fim };
      b.ini = a.inicio < b.ini ? a.inicio : b.ini; b.fimB = a.fim > b.fimB ? a.fim : b.fimB;
      g.set(k, b);
    }
    return [...g.values()];
  };
  return (
    <section className="card portal-semana">
      <div className="portal-semana-cab">
        <button className="btn" aria-label="Semana anterior" onClick={() => setSeg(addDias(seg, -7))}>‹</button>
        <b>Semana de {dataBR(iso(dias[0]))} a {dataBR(iso(dias[usaSab ? 5 : 4]))}</b>
        <button className="btn" aria-label="Próxima semana" onClick={() => setSeg(addDias(seg, 7))}>›</button>
        <button className="btn-link" onClick={() => setSeg(segundaDe(new Date()))}>esta semana</button>
        <small className="mudo">{naSemana.length ? `${new Set(naSemana.map((a) => a.data)).size} dia(s) com aula` : "sem aulas nesta semana"}
          {resSemana.length ? ` · ${resSemana.length} turno(s) de PL/PJ` : ""}</small>
      </div>
      <div className="tabela-wrap"><table className="tabela portal-grade">
        <thead><tr><th>Turno</th>{dias.slice(0, usaSab ? 6 : 5).map((d, i) => <th key={i} className={iso(d) === hoje ? "hoje" : ""}>{DIAS_CURTOS[i]} {dataBR(iso(d)).slice(0, 5)}</th>)}</tr></thead>
        <tbody>{turnos.map((t) => <tr key={t}><th>{t}</th>{dias.slice(0, usaSab ? 6 : 5).map((d, i) => (
          <td key={i}>{blocos(t, d).map((b) => <div key={b.turma + b.uc} className="bloco-aula" style={{ background: corDe(b.turma + b.uc) }}>
            <b>{b.turma}{b.substituindo ? " 🔁" : ""}</b><span>{b.uc} · {b.uc_nome}</span><small>{b.ini}–{b.fimB}{b.sala ? ` · ${b.sala}` : ""}</small>
            {b.substituindo && <small>substituindo {b.substituindo}</small>}</div>)}
            {resSemana.filter((r) => r.data === iso(d) && turnoDaHora(r) === t).map((r) => <div key={r.inicio} className="portal-reserva" title={r.descricao}>
              <b>{r.sigla}</b> {r.sigla === "PL" ? "Planejamento" : "Projeto / outra atividade"} <small>{r.inicio}–{r.fim}</small></div>)}</td>))}</tr>)}</tbody>
      </table></div>
    </section>
  );
}

function turnoDaHora(r: { inicio: string }) { return r.inicio < "12:00" ? "Manhã" : r.inicio < "18:00" ? "Tarde" : "Noite"; }
function ordemTurno(t: string) { return t.startsWith("Manh") ? 0 : t.startsWith("Tard") ? 1 : t.startsWith("Noit") ? 2 : 3; }
function corDe(k: string) {
  let h = 0;
  for (const ch of k) h = (h * 31 + ch.charCodeAt(0)) % 360;
  return `hsl(${h} 70% var(--cor-l))`;
}

function CartaoTurma({ t, aoEnviar }: { t: any; aoEnviar: () => void }) {
  const { aviso } = useApp();
  const [aberto, setAberto] = useState(false);
  const [tipo, setTipo] = useState("sugestao");
  const [texto, setTexto] = useState("");
  const [erro, setErro] = useState<any>(null);
  const enviar = async () => {
    setErro(null);
    try {
      await api.post("/api/portal/observacoes", { turma_uc_id: t.turma_uc_id, tipo, texto });
      aviso("Observação enviada para a coordenação."); setTexto(""); setAberto(false); aoEnviar();
    } catch (e) { setErro(e); }
  };
  const pct = t.ch_uc ? Math.min(100, Math.round(100 * t.horas_suas / t.ch_uc)) : 0;
  return (
    <article className="portal-cartao">
      <div className="portal-cartao-cab">
        <div><b>{t.turma_codigo}</b> <small className="mudo">{t.turno}{t.qtd_alunos ? ` · ${t.qtd_alunos} alunos` : ""}</small></div>
        {t.observacoes > 0 && <Badge tipo="info">{t.observacoes} observação(ões)</Badge>}
      </div>
      <div className="portal-uc">{t.uc_codigo} — {t.uc_nome}</div>
      {t.substituindo.length > 0 && <p className="aviso-inline">🔁 Substituindo {t.substituindo.join(", ")} em {t.dias_substituicao.map((d: string) => dataBR(d).slice(0, 5)).join(", ")}</p>}
      <div className="chips">{t.horarios.map((h: string) => <span key={h} className="chip">{h}</span>)}</div>
      <p className="sub">{dataBR(t.primeira)} a {dataBR(t.ultima)} · {t.dias_de_aula} dia(s) de aula{t.salas.length ? ` · ${t.salas.join(", ")}` : ""}</p>
      <div className="barra-ch" title={`${t.horas_suas} h com você de ${t.ch_uc} h da UC`}><span style={{ width: `${pct}%` }} /></div>
      <small className="mudo">{t.horas_suas} h com você · UC de {t.ch_uc} h</small>
      {!aberto ? <button className="btn" onClick={() => setAberto(true)}>💬 Enviar observação</button> : <div className="portal-obs-form">
        <select aria-label="Tipo de observação" value={tipo} onChange={(e) => setTipo(e.target.value)}>{TIPOS.map(([v, r]) => <option key={v} value={v}>{r}</option>)}</select>
        <textarea rows={3} maxLength={3000} placeholder="Ex.: sugiro trocar a sala para o laboratório de comandos nas aulas práticas…" value={texto} onChange={(e) => setTexto(e.target.value)} />
        <Erro erro={erro} />
        <div className="acoes"><button className="btn" onClick={() => setAberto(false)}>Cancelar</button>
          <button className="btn btn-primario" disabled={texto.trim().length < 3} onClick={enviar}>Enviar para a coordenação</button></div>
      </div>}
    </article>
  );
}

// ---------------------------------------------------------------------------- meus dados
function MeusDados({ eu, salvo }: { eu: any; salvo: () => void }) {
  const { aviso } = useApp();
  const [v, setV] = useState<any>(() => ({ ...eu }));
  const [nova, setNova] = useState("");
  const [erro, setErro] = useState<any>(null);
  const [salvando, setSalvando] = useState(false);
  useEffect(() => setV({ ...eu }), [eu]);
  const outras = eu.areas_unidade.filter((a: any) => a.id !== eu.area_principal?.id);
  const salvar = async () => {
    setErro(null); setSalvando(true);
    try {
      const corpo: any = { areas_ids: v.areas_ids, ucs_competencia: v.ucs_competencia, certificacoes: v.certificacoes, formacao: v.formacao };
      if (v.__disp) { corpo.jornada = v.jornada; corpo.disp_dias = v.disp_dias; }
      await api.put("/api/portal/eu", corpo);
      aviso("Dados salvos no seu cadastro. A coordenação já vê as alterações."); salvo();
    } catch (e) { setErro(e); } finally { setSalvando(false); }
  };
  const addCert = () => {
    const n = nova.trim();
    if (n && !v.certificacoes.some((c: string) => c.toLowerCase() === n.toLowerCase())) setV({ ...v, certificacoes: [...v.certificacoes, n] });
    setNova("");
  };
  return (
    <div className="portal-dados">
      <section className="card">
        <h2>Cadastro</h2>
        <dl className="portal-info">
          <dt>Nome</dt><dd>{eu.nome}</dd><dt>Matrícula</dt><dd>{eu.matricula}</dd><dt>Unidade</dt><dd>{eu.unidade}</dd>
          <dt>Área principal</dt><dd>{eu.todas_areas ? "Todas as áreas" : eu.area_principal?.nome || "—"}</dd>
          <dt>Modalidade</dt><dd>{eu.modalidade === "horista" ? "Horista (horas não garantidas)" : "Mensalista (horas garantidas: aula, planejamento ou projeto)"}</dd>
          <dt>Carga contratual</dt><dd>{eu.carga_horaria_contratual} h/semana · {eu.max_horas_dia} h de aula por dia</dd>
        </dl>
        <p className="sub">Esses dados são mantidos pela coordenação. Se algo estiver errado, avise por uma observação.</p>
      </section>

      {!eu.todas_areas && outras.length > 0 && <section className="card">
        <h2>Outras áreas em que também atua</h2>
        <div className="checks">{outras.map((a: any) => (
          <label key={a.id}><input type="checkbox" checked={v.areas_ids.includes(a.id)}
            onChange={(e) => setV({ ...v, areas_ids: e.target.checked ? [...v.areas_ids, a.id] : v.areas_ids.filter((x: number) => x !== a.id) })} /> {a.nome}</label>))}</div>
      </section>}

      <CompetenciasUCs valores={{ ...v, area_id: eu.area_principal?.id }} set={(c) => setV({ ...v, ucs_competencia: c })}
        fonte={(areas) => `/api/portal/ucs?areas=${areas.join(",")}`} />
      <JornadaInstrutor valores={v} setVarios={(o) => setV({ ...v, ...o })} />

      <section className="card">
        <h2>Certificações</h2>
        <div className="chips">{v.certificacoes.map((c: string) => <span key={c} className="chip">{c} <button className="btn-link" aria-label={`Remover ${c}`}
          onClick={() => setV({ ...v, certificacoes: v.certificacoes.filter((x: string) => x !== c) })}>✕</button></span>)}
          {!v.certificacoes.length && <span className="mudo">Nenhuma informada.</span>}</div>
        <div className="filtros"><input placeholder="Ex.: NR-10, NR-12, CREA…" value={nova} onChange={(e) => setNova(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); addCert(); } }} /><button className="btn" onClick={addCert}>+ Adicionar</button></div>
      </section>

      <section className="card">
        <h2>Formação e especialidades</h2>
        <textarea rows={4} placeholder="Formação, experiência na indústria, softwares, equipamentos que domina…" value={v.formacao || ""} onChange={(e) => setV({ ...v, formacao: e.target.value })} />
      </section>

      <Erro erro={erro} />
      <div className="portal-salvar"><button className="btn btn-primario btn-grande" disabled={salvando} onClick={salvar}>{salvando ? "Salvando…" : "Salvar meus dados"}</button></div>
    </div>
  );
}

// ---------------------------------------------------------------------------- notificações
const ICONE_NOTIF: Record<string, string> = { substituicao: "🔁", publicacao: "📅", cadastro: "🧑‍🏫", observacao: "💬", solicitacao: "📝" };

function Notificacoes({ lista, mudou, ir }: { lista: any[] | null; mudou: () => void; ir: (aba: string) => void }) {
  if (!lista) return <p role="status">Carregando…</p>;
  const novas = lista.filter((n) => !n.lida);
  const marcar = async (ids?: number[]) => { await api.post("/api/portal/notificacoes/lidas", ids ? { ids } : {}); mudou(); };
  if (!lista.length) return <div className="card portal-aviso"><p>Nenhuma notificação ainda. Aqui aparecem avisos de mudanças no seu cadastro, substituições,
    horários publicados e respostas da coordenação.</p></div>;
  return (
    <section className="card">
      <div className="portal-semana-cab"><b>{novas.length ? `${novas.length} nova(s)` : "Tudo lido"}</b>
        {novas.length > 0 && <button className="btn-link" onClick={() => marcar()}>Marcar todas como lidas</button>}</div>
      <ul className="lista-notif">{lista.map((n) => (
        <li key={n.id} className={n.lida ? "" : "nova"}>
          <span className="notif-ico" aria-hidden="true">{ICONE_NOTIF[n.tipo] || "🔔"}</span>
          <div><b>{n.titulo}</b>{n.texto && <p>{n.texto}</p>}<small className="mudo">{new Date(n.criado_em).toLocaleString("pt-BR")}</small></div>
          <div className="notif-acoes">
            {n.aba && <button className="btn-link" onClick={async () => { if (!n.lida) await marcar([n.id]); ir(n.aba); }}>Ver</button>}
            {!n.lida && <button className="btn-link" onClick={() => marcar([n.id])}>Marcar como lida</button>}
          </div>
        </li>))}</ul>
    </section>
  );
}

// ---------------------------------------------------------------------------- observações
function MinhasObservacoes({ lista }: { lista: any[] | null }) {
  if (!lista) return <p role="status">Carregando…</p>;
  if (!lista.length) return <div className="card portal-aviso"><p>Você ainda não enviou observações. Use o botão “Enviar observação” em cada turma.</p></div>;
  return (
    <div className="portal-obs">{lista.map((o) => (
      <article key={o.id} className={`portal-cartao obs-${o.status}`}>
        <div className="portal-cartao-cab"><div><b>{o.turma || "Geral"}</b> <small className="mudo">{o.uc}</small></div>
          <Badge tipo={STATUS[o.status]?.[0] || "info"}>{STATUS[o.status]?.[1] || o.status}</Badge></div>
        <small className="mudo">{o.tipo_rotulo} · {new Date(o.criado_em).toLocaleString("pt-BR")}</small>
        <p>{o.texto}</p>
        {o.resposta && <div className="portal-resposta"><b>Resposta{o.respondido_por ? ` de ${o.respondido_por}` : ""}:</b> {o.resposta}</div>}
      </article>))}</div>
  );
}

// ---------------------------------------------------------------------------- solicitações (folga e substituição)
const ST_SOLIC: Record<string, string> = { pendente: "alerta", aprovada: "ok", recusada: "bloqueio", cancelada: "info" };

function MinhasSolicitacoes({ lista, turnos, mudou }: { lista: any[] | null; turnos: any[]; mudou: () => void }) {
  const { aviso } = useApp();
  const amanha = iso(addDias(new Date(), 1));
  const [f, setF] = useState<any>({ tipo: "folga", data_inicio: amanha, data_fim: amanha, turnos: [], justificativa: "" });
  const [erro, setErro] = useState<any>(null);
  const [enviando, setEnviando] = useState(false);
  const enviar = async () => {
    setErro(null); setEnviando(true);
    try {
      const r = await api.post("/api/portal/solicitacoes", f);
      aviso(`Pedido enviado ao coordenador${r.aulas_afetadas ? ` (${r.aulas_afetadas} aula(s) no período)` : ""}.`);
      setF({ ...f, justificativa: "" }); mudou();
    } catch (e) { setErro(e); } finally { setEnviando(false); }
  };
  const cancelar = async (id: number) => { if (!confirm("Cancelar este pedido?")) return; await api.post(`/api/portal/solicitacoes/${id}/cancelar`, {}); mudou(); };
  const marcarTurno = (id: number, on: boolean) => setF({ ...f, turnos: on ? [...f.turnos, id] : f.turnos.filter((x: number) => x !== id) });
  return (
    <div className="portal-dados">
      <section className="card">
        <h2>Nova solicitação</h2>
        <p className="sub">Avise com antecedência quando precisar de <b>folga</b> (não vai estar disponível) ou de <b>substituição</b> (outra pessoa assume as suas aulas).
          O pedido vai para o coordenador, que aprova ou recusa; a resposta aparece aqui e nas notificações.</p>
        <div className="form-grid">
          <Campo rotulo="Tipo"><select value={f.tipo} onChange={(e) => setF({ ...f, tipo: e.target.value })}>
            <option value="folga">Folga</option><option value="substituicao">Substituição nas minhas aulas</option></select></Campo>
          <Campo rotulo="De"><input type="date" min={iso(new Date())} value={f.data_inicio} onChange={(e) => setF({ ...f, data_inicio: e.target.value, data_fim: f.data_fim < e.target.value ? e.target.value : f.data_fim })} /></Campo>
          <Campo rotulo="Até"><input type="date" min={f.data_inicio} value={f.data_fim} onChange={(e) => setF({ ...f, data_fim: e.target.value })} /></Campo>
        </div>
        <fieldset className="painel-campo"><legend>Turnos <small>(nenhum marcado = o dia todo)</small></legend>
          <div className="checks">{turnos.map((t: any) => <label key={t.id}><input type="checkbox" checked={f.turnos.includes(t.id)} onChange={(e) => marcarTurno(t.id, e.target.checked)} /> {t.nome} <small className="mudo">{t.inicio}–{t.fim}</small></label>)}</div>
        </fieldset>
        <Campo rotulo="Justificativa" obrigatorio ajuda="Mínimo de 10 caracteres. O coordenador lê antes de decidir.">
          <textarea rows={3} maxLength={3000} placeholder="Ex.: consulta médica agendada; participação em banca; curso de capacitação…" value={f.justificativa}
            onChange={(e) => setF({ ...f, justificativa: e.target.value })} /></Campo>
        <Erro erro={erro} />
        <div className="acoes"><button className="btn btn-primario" disabled={enviando || f.justificativa.trim().length < 10} onClick={enviar}>{enviando ? "Enviando…" : "Enviar ao coordenador"}</button></div>
      </section>
      <section className="card">
        <h2>Meus pedidos</h2>
        {!lista ? <p role="status">Carregando…</p> : !lista.length ? <p className="mudo">Nenhum pedido ainda.</p> :
          <ul className="lista-notif">{lista.map((x) => (
            <li key={x.id}>
              <span className="notif-ico" aria-hidden="true">{x.tipo === "folga" ? "🌴" : "🔁"}</span>
              <div><b>{x.tipo_rotulo}</b> · {dataBR(x.data_inicio)}{x.data_fim !== x.data_inicio ? ` a ${dataBR(x.data_fim)}` : ""} · {x.turnos.join(", ")}
                <p>{x.justificativa}</p>
                {x.resposta && <div className="portal-resposta"><b>Resposta:</b> {x.resposta}</div>}
                {x.status === "aprovada" && x.efeitos?.substituidas > 0 && <small className="mudo">{x.efeitos.substituidas} aula(s) com {x.efeitos.substituto}.</small>}</div>
              <div className="notif-acoes"><Badge tipo={ST_SOLIC[x.status] || "info"}>{x.status_rotulo}</Badge>
                {x.status === "pendente" && <button className="btn-link" onClick={() => cancelar(x.id)}>Cancelar</button>}</div>
            </li>))}</ul>}
      </section>
    </div>
  );
}

// ---------------------------------------------------------------------------- meu desenvolvimento
const TIPOS_FORMACAO: [string, string][] = [["curso", "Curso"], ["aperfeicoamento", "Aperfeiçoamento"], ["certificacao", "Certificação"],
  ["pos", "Pós-graduação / especialização"], ["outro", "Outra formação"]];

/** O instrutor acompanha o próprio índice de aderência (por área e geral), a ocupação, o PDI indicado pela coordenação
 * e registra as formações que concluir — as UCs são habilitadas na hora e a coordenação recebe uma observação. */
function MeuDesenvolvimento({ registrado }: { registrado: () => void }) {
  const p = useCarregar<any>(() => api.get("/api/portal/perfil"), []);
  const [sub, setSub] = useState("pdi");
  const d = p.dados;
  if (p.carregando && !d) return <p role="status">Carregando…</p>;
  if (p.erro) return <div className="erro-box">{p.erro}</div>;
  if (!d) return null;
  const abertos = d.pdi.filter((x: any) => x.situacao === "planejado" || x.situacao === "em_andamento");
  return (
    <div className="card meu-desenv">
      <div className="md-cab">
        <div>
          <h2>Meu índice de aderência</h2>
          <p className="sub">Quanto da carga horária das UCs técnicas dos cursos da sua área você já pode ministrar. O PDI traz as ações que a coordenação
            indicou para você chegar a 100%; ao concluir uma formação, registre aqui.</p>
          <div className="md-chips">
            <span className="chip-status">{abertos.length} ação(ões) do PDI em aberto</span>
            {d.semestre && <span className="chip-status">{d.semestre.media_semanal_h} h de aula por semana · {d.semestre.pct_contrato}% do contrato</span>}
          </div>
        </div>
        <IndicesAderencia ad={d.aderencia} />
      </div>
      <Abas abas={[{ id: "pdi", rotulo: `🎯 Meu PDI${abertos.length ? ` (${abertos.length})` : ""}` }, { id: "registrar", rotulo: "➕ Registrar formação" },
        { id: "aderencia", rotulo: "📊 Aderência por curso" }, { id: "ocupacao", rotulo: "⏱ Minha ocupação" },
        { id: "termo", rotulo: d.dados.modalidade === "horista" ? "🗓 Meu termo de horas" : "🗓 Minha jornada" }]} ativa={sub} mudar={setSub} />
      {sub === "pdi" && <Pdi id={d.dados.id} url="/api/portal/pdi" somenteLeitura mudou={p.recarregar} />}
      {sub === "registrar" && <RegistrarFormacao d={d} feito={() => { p.recarregar(); registrado(); setSub("pdi"); }} />}
      {sub === "aderencia" && <Aderencia ad={d.aderencia} />}
      {sub === "ocupacao" && <Ocupacao d={d} />}
      {sub === "termo" && (d.dados.modalidade === "horista" ? <PainelTermo instId={d.dados.id} nome={d.dados.nome} url="/api/portal/termos" somenteLeitura />
        : <JornadaMensalista d={d} portal />)}
    </div>
  );
}

function RegistrarFormacao({ d, feito }: { d: any; feito: () => void }) {
  const { aviso } = useApp();
  const [f, setF] = useState<any>({ tipo: "curso", titulo: "", instituicao: "", carga_h: "", concluido_em: iso(new Date()), pdi_item_id: "", ucs: [] as string[],
    certificacao: "", validade: "", observacao: "" });
  const [erro, setErro] = useState<any>(null);
  const [enviando, setEnviando] = useState(false);
  const abertos = d.pdi.filter((x: any) => x.situacao === "planejado" || x.situacao === "em_andamento");
  const faltam = d.aderencia.areas.flatMap((a: any) => a.cursos.map((c: any) => ({ ...c, ucs: c.ucs.filter((u: any) => u.situacao !== "sim") })))
    .filter((c: any) => c.ucs.length);
  const chave = (c: any, u: any) => `${c.curso_id}|${u.codigo}`;
  const marcar = (k: string, on: boolean) => setF({ ...f, ucs: on ? [...f.ucs, k] : f.ucs.filter((x: string) => x !== k) });
  const enviar = async () => {
    setErro(null); setEnviando(true);
    try {
      const r = await api.post("/api/portal/formacoes", { ...f, pdi_item_id: f.pdi_item_id || null,
        ucs: f.ucs.map((k: string) => { const [curso_id, uc_codigo] = k.split("|"); return { curso_id: Number(curso_id), uc_codigo }; }) });
      aviso(`Formação registrada. ${r.habilitadas.length ? `Habilitado em ${r.habilitadas.length} UC(s). ` : ""}Seu índice agora é ${String(r.geral).replace(".", ",")}%. A coordenação foi avisada.`);
      feito();
    } catch (e) { setErro(e); }
    setEnviando(false);
  };
  return (
    <div className="registrar-formacao">
      <p className="sub">Concluiu um curso, aperfeiçoamento ou certificação? Registre aqui: as UCs que você marcar passam a constar como <b>“Sim”</b> no seu
        perfil na hora (e entram no seu índice), a certificação é registrada e a coordenação recebe uma observação para conferir.</p>
      <div className="form-grid">
        <Campo rotulo="Tipo" obrigatorio><select value={f.tipo} onChange={(e) => setF({ ...f, tipo: e.target.value })}>
          {TIPOS_FORMACAO.map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></Campo>
        <Campo rotulo="Nome do curso ou da formação" obrigatorio><input value={f.titulo} onChange={(e) => setF({ ...f, titulo: e.target.value })} placeholder="ex.: Eletrônica Analógica Aplicada" /></Campo>
        <Campo rotulo="Instituição"><input value={f.instituicao} onChange={(e) => setF({ ...f, instituicao: e.target.value })} placeholder="ex.: SENAI-ES" /></Campo>
        <Campo rotulo="Carga horária (h)"><input type="number" min={1} value={f.carga_h} onChange={(e) => setF({ ...f, carga_h: e.target.value })} /></Campo>
        <Campo rotulo="Concluído em" obrigatorio><input type="date" value={f.concluido_em} max={iso(new Date())} onChange={(e) => setF({ ...f, concluido_em: e.target.value })} /></Campo>
        {abertos.length > 0 && <Campo rotulo="É de uma ação do meu PDI?" ajuda="O item é marcado como concluído (e a UC dele, habilitada).">
          <select value={f.pdi_item_id} onChange={(e) => setF({ ...f, pdi_item_id: e.target.value })}>
            <option value="">Não</option>
            {abertos.map((x: any) => <option key={x.id} value={x.id}>{x.uc_codigo} – {x.uc_nome}{x.prazo ? ` (prazo ${dataBR(x.prazo)})` : ""}</option>)}
          </select></Campo>}
        <Campo rotulo="Certificação obtida" ajuda="ex.: NR-10 (exigida por algumas UCs)"><input value={f.certificacao} onChange={(e) => setF({ ...f, certificacao: e.target.value })} /></Campo>
        {f.certificacao && <Campo rotulo="Validade da certificação"><input type="date" value={f.validade} onChange={(e) => setF({ ...f, validade: e.target.value })} /></Campo>}
      </div>
      <fieldset className="painel-campo">
        <legend>UCs que passo a ministrar com esta formação</legend>
        {!faltam.length && <p className="mudo">Você já ministra todas as UCs técnicas dos cursos da sua área. 🎉</p>}
        <div className="rf-cursos">
          {faltam.map((c: any) => (
            <div key={c.curso_id} className="rf-curso"><b>{c.codigo}</b> <small className="mudo">{c.nome}</small>
              {c.ucs.map((u: any) => (
                <label key={u.codigo} className="rf-uc"><input type="checkbox" checked={f.ucs.includes(chave(c, u))} onChange={(e) => marcar(chave(c, u), e.target.checked)} />
                  <span><b>{u.codigo}</b> {u.nome} <small className="mudo">· {u.ch} h{u.situacao === "em_partes" ? " · hoje em partes" : ""}{u.certificacao ? ` · exige ${u.certificacao}` : ""}</small></span></label>
              ))}
            </div>
          ))}
        </div>
      </fieldset>
      <Campo rotulo="Observação para a coordenação (opcional)"><textarea rows={2} value={f.observacao} onChange={(e) => setF({ ...f, observacao: e.target.value })} /></Campo>
      <Erro erro={erro} />
      <div className="rodape-modal"><button className="btn btn-primario" disabled={enviando || f.titulo.trim().length < 3 || (!f.ucs.length && !f.certificacao.trim() && !f.pdi_item_id)}
        onClick={enviar}>{enviando ? "Registrando…" : "Registrar formação"}</button></div>
    </div>
  );
}
