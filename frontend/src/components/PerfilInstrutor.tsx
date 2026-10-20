import { useState } from "react";
import { api, dataBR, qs } from "../api";
import { useApp } from "../contexto";
import { Abas, Badge, Modal, useCarregar } from "./ui";

/** Índice de aderência do instrutor: cores e componentes visuais (anel, barra, avatar) e o perfil com visão geral, aderência e PDI. */

export const tomAderencia = (p: number) => (p >= 80 ? "ok" : p >= 50 ? "alerta" : "erro");
const pct = (v: number) => `${Number(v || 0).toLocaleString("pt-BR", { maximumFractionDigits: 1 })}%`;
const NIVEL: Record<string, string> = { tecnico: "Técnico", basico: "Básico" };
const PRIORIDADE: Record<string, [string, string]> = { alta: ["bloqueio", "prioridade alta"], media: ["alerta", "prioridade média"], baixa: ["info", "prioridade baixa"] };
const TIPO_PDI: Record<string, string> = { uc: "Aprender a UC", completar: "Completar a UC", certificacao: "Certificação" };
const SITUACAO_PDI: Record<string, string> = { planejado: "Planejado", em_andamento: "Em andamento", concluido: "Concluído", cancelado: "Cancelado" };
const STATUS_UC: Record<string, string> = { sim: "uc-sim", em_partes: "uc-partes", sem_certificacao: "uc-cert", nao: "uc-nao" };

export function iniciais(nome: string) {
  const p = (nome || "?").trim().split(/\s+/);
  return ((p[0]?.[0] || "") + (p.length > 1 ? p[p.length - 1][0] : "")).toUpperCase();
}

export function Avatar({ nome, grande }: { nome: string; grande?: boolean }) {
  return <span className={`inst-avatar ${grande ? "inst-avatar-g" : ""}`} aria-hidden="true">{iniciais(nome)}</span>;
}

/** Anel com o percentual no meio (aderência geral ou de uma área). */
export function Anel({ valor, tamanho = 64, rotulo }: { valor: number; tamanho?: number; rotulo?: string }) {
  const r = (tamanho - 8) / 2, c = 2 * Math.PI * r, v = Math.max(0, Math.min(100, valor || 0));
  return (
    <span className={`ader-anel ader-${tomAderencia(v)}`} style={{ width: tamanho, height: tamanho }} role="img" aria-label={`${rotulo || "Aderência"}: ${pct(v)}`}>
      <svg width={tamanho} height={tamanho} viewBox={`0 0 ${tamanho} ${tamanho}`}>
        <circle cx={tamanho / 2} cy={tamanho / 2} r={r} className="ader-trilho" strokeWidth={7} fill="none" />
        <circle cx={tamanho / 2} cy={tamanho / 2} r={r} className="ader-valor" strokeWidth={7} fill="none" strokeLinecap="round"
          strokeDasharray={`${(c * v) / 100} ${c}`} transform={`rotate(-90 ${tamanho / 2} ${tamanho / 2})`} />
      </svg>
      <b style={{ fontSize: tamanho < 56 ? 11 : 14 }}>{Math.round(v)}%</b>
    </span>
  );
}

/** Barra de percentual: na aderência a cor segue o índice; "neutra" para progresso e ocupação (vermelha só acima do teto de 90%). */
export function BarraPct({ valor, fina, neutra }: { valor: number; fina?: boolean; neutra?: boolean }) {
  const tom = neutra ? (valor > 90 ? "erro" : "neutro") : tomAderencia(valor);
  return <span className={`barra-pct ${fina ? "fina" : ""}`}><span className={`barra-pct-v bp-${tom}`} style={{ width: `${Math.min(100, valor)}%` }} /></span>;
}

/** Cartão do instrutor na lista: avatar, áreas, aderência geral e por curso. */
export function CartaoInstrutor({ l, ad, abrir }: { l: any; ad?: any; abrir: () => void }) {
  return (
    <button className="cartao-inst" onClick={abrir} aria-label={`Abrir o perfil de ${l.nome}`}>
      <div className="cartao-inst-topo">
        <Avatar nome={l.nome} />
        <div className="cartao-inst-nome">
          <b>{l.nome}</b>
          <small className="mudo">{l.matricula} · {NIVEL[l.nivel] || l.nivel} · {l.modalidade === "horista" ? "Horista" : "Mensalista"} · {Number(l.carga_horaria_contratual)} h</small>
        </div>
        {ad ? <Anel valor={ad.geral} tamanho={52} rotulo="Aderência geral" /> : <span className="ader-vazio" />}
      </div>
      <div className="cartao-inst-areas">
        {(ad?.areas || []).map((a: any) => <span key={a.area_id} className={`chip-area ${a.principal ? "ca-principal" : ""}`}>{a.area} · {pct(a.pct)}</span>)}
        {l._acesso_portal && <span className="chip-area ca-portal">portal ✓</span>}
      </div>
      <div className="cartao-inst-cursos">
        {(ad?.cursos || []).slice(0, 4).map((c: any) => (
          <div key={c.codigo} className="mini-curso"><span>{c.codigo}</span><BarraPct valor={c.pct} fina /><small>{Math.round(c.pct)}%</small></div>
        ))}
        {!ad?.cursos?.length && <small className="mudo">Sem cursos com UCs técnicas na área.</small>}
      </div>
    </button>
  );
}

/** Perfil do instrutor: visão geral (dados, semestre, agenda), aderência por área e curso, e PDI. */
export function PerfilInstrutor({ id, fechar, editar }: { id: number | null; fechar: () => void; editar?: () => void }) {
  const { cenario } = useApp();
  const [aba, setAba] = useState("geral");
  const p = useCarregar<any>(() => (id ? api.get(`/api/instrutores/${id}/perfil${qs({ cenario_id: cenario?.id })}`) : Promise.resolve(null)), [id, cenario?.id]);
  const d = p.dados;
  return (
    <Modal titulo={d ? `Perfil — ${d.dados.nome}` : "Perfil do instrutor"} aberto={id != null} fechar={() => { setAba("geral"); fechar(); }} largo>
      {p.carregando && !d && <p role="status">Carregando o perfil…</p>}
      {p.erro && <div className="erro-box">{p.erro}</div>}
      {d && <>
        <div className="perfil-cab">
          <Avatar nome={d.dados.nome} grande />
          <div className="perfil-id">
            <h3>{d.dados.nome}</h3>
            <p className="mudo">{d.dados.matricula}{d.dados.email ? ` · ${d.dados.email}` : ""} · {d.dados.unidade}{d.dados.outras_unidades.length ? ` (+ ${d.dados.outras_unidades.join(", ")})` : ""}</p>
            <div className="perfil-chips">
              {d.dados.areas.map((a: string) => <span key={a} className={`chip-area ${a === d.dados.area ? "ca-principal" : ""}`}>{a}</span>)}
              {d.dados.todas_areas && <span className="chip-area">atende todas as áreas</span>}
              <span className="chip-area">{NIVEL[d.dados.nivel] || d.dados.nivel}</span>
              <span className={`modalidade modalidade-${d.dados.modalidade}`}>{d.dados.modalidade === "horista" ? "Horista" : "Mensalista"}</span>
              {d.dados.portal ? <Badge tipo="ok">portal ativo</Badge> : <Badge tipo="info">sem acesso ao portal</Badge>}
            </div>
          </div>
          <div className="perfil-anel"><Anel valor={d.aderencia.geral} tamanho={84} rotulo="Aderência geral" /><small>aderência geral</small></div>
          {editar && <button className="btn" onClick={editar}>Editar cadastro</button>}
        </div>
        <Abas abas={[{ id: "geral", rotulo: "Visão geral" }, { id: "aderencia", rotulo: "Aderência aos cursos" }, { id: "pdi", rotulo: "PDI" }]} ativa={aba} mudar={setAba} />
        {aba === "geral" && <VisaoGeral d={d} />}
        {aba === "aderencia" && <Aderencia ad={d.aderencia} />}
        {aba === "pdi" && <Pdi id={d.dados.id} mudou={p.recarregar} />}
      </>}
    </Modal>
  );
}

function VisaoGeral({ d }: { d: any }) {
  const s = d.semestre;
  const ag = s?.agenda_h || {};
  return (
    <div className="perfil-geral">
      <div className="perfil-kpis">
        <div className="pk"><small>Aulas no semestre</small><b>{s ? s.aulas : "—"}</b><span className="mudo">{s ? `${s.realizadas} dadas · ${s.horas} h` : "escolha o semestre"}</span></div>
        {d.termos ? <div className="pk"><small>Termo de {d.termos.atual?.rotulo || "—"}</small>
          {d.termos.atual?.tem_termo ? <><b>{d.termos.atual.horas_aula} h</b>
            {d.termos.atual.programadas_h != null && <><BarraPct valor={d.termos.atual.pct} fina neutra />
              <span className="mudo">{d.termos.atual.programadas_h} h de aula programadas ({pct(d.termos.atual.pct)})</span></>}</>
            : <><b>—</b><span className="mudo">sem termo neste mês: vale o limite semanal ({d.dados.limite_letivo} h)</span></>}</div>
          : <div className="pk"><small>Média semanal</small><b>{s ? `${s.media_semanal_h} h` : "—"}</b>
          {s && <><BarraPct valor={s.pct_limite} fina neutra /><span className="mudo">{pct(s.pct_limite)} do limite letivo ({d.dados.limite_letivo} h)</span></>}</div>}
        <div className="pk"><small>Turmas</small><b>{s ? s.turmas : "—"}</b><span className="mudo">{s ? `${s.por_turma.length} UC(s) em andamento` : ""}</span></div>
        <div className="pk"><small>UCs que ministra</small><b>{d.dados.ucs_sim}</b><span className="mudo">{d.dados.ucs_em_partes ? `+ ${d.dados.ucs_em_partes} em partes` : "marcadas no perfil"}</span></div>
      </div>
      <div className="perfil-colunas">
        <section className="perfil-bloco">
          <h4>Turmas e UCs no semestre</h4>
          {!s?.por_turma?.length && <p className="mudo">Sem aulas neste semestre.</p>}
          <ul className="lista-limpa">
            {(s?.por_turma || []).map((x: any) => (
              <li key={`${x.turma_id}-${x.uc_id}`} className="linha-turma">
                <div><b>{x.turma}</b> · {x.uc} <small className="mudo">{x.uc_nome}</small></div>
                <div className="linha-turma-prog"><BarraPct valor={x.aulas ? (100 * x.realizadas) / x.aulas : 0} fina neutra />
                  <small className="mudo">{x.realizadas}/{x.aulas} aulas · {x.horas} h{x.proxima ? ` · próxima ${dataBR(x.proxima).slice(0, 5)}` : " · concluídas"}</small></div>
              </li>
            ))}
          </ul>
        </section>
        <section className="perfil-bloco">
          <h4>Próximas aulas</h4>
          {!s?.proximas?.length && <p className="mudo">Nenhuma aula futura.</p>}
          <ul className="lista-limpa proximas">
            {(s?.proximas || []).map((a: any, k: number) => (
              <li key={k}><span className="dia">{dataBR(a.data).slice(0, 5)}</span><span>{a.inicio}–{a.fim}</span><b>{a.turma}</b><span>{a.uc}</span><small className="mudo">{a.sala || "sem sala"}</small></li>
            ))}
          </ul>
          <h4>Agenda fora de sala</h4>
          <div className="agenda-chips">
            <span className="chip-ag pl">PL {ag.PL || 0} h</span><span className="chip-ag pj">PJ {ag.PJ || 0} h</span><span className="chip-ag tr">TR {ag.TR || 0} h</span>
          </div>
        </section>
        <section className="perfil-bloco">
          <h4>Disponibilidade</h4>
          {!d.dados.disponibilidade.length && <p className="mudo">Sem disponibilidade cadastrada.</p>}
          <ul className="lista-limpa disp">
            {d.dados.disponibilidade.map((x: any) => <li key={x.dia}><b>{x.dia}</b> <small className="mudo">{Array.from(new Set(x.janelas)).join(" · ")}</small></li>)}
          </ul>
          <h4>Certificações</h4>
          {!d.dados.certificacoes.length && <p className="mudo">Nenhuma certificação cadastrada.</p>}
          <div className="agenda-chips">
            {d.dados.certificacoes.map((c: any) => <Badge key={c.nome} tipo={c.vencida ? "erro" : "ok"}>{c.nome}{c.valido_ate ? ` até ${dataBR(c.valido_ate)}` : ""}</Badge>)}
          </div>
          {d.termos ? <>
            <h4>Termos de horas (horista)</h4>
            <ul className="lista-limpa disp">
              {d.termos.meses.map((m: any) => <li key={m.mes}><b className="cap">{m.rotulo}</b>{" "}
                {m.tem_termo ? <small>{m.horas_aula} h de aula{m.horas_outras ? ` + ${m.horas_outras} h outras` : ""}{m.programadas_h != null ? ` · ${m.programadas_h} h programadas` : ""}</small>
                  : <Badge tipo="alerta">sem termo</Badge>}{m.excedente_h > 0 && <> <Badge tipo="alerta">{m.excedente_h} h acima (ajustável)</Badge></>}</li>)}
            </ul>
            <p className="sub">Horista: as horas de aula de cada mês vêm do termo, ajustável numa urgência com a concordância do instrutor. O limite real é a carga do contrato.</p>
          </> : <p className="sub">Mensalista: jornada fixa de {d.dados.carga_contratual} h/semana · aulas até {d.dados.limite_letivo} h (teto de 90%)</p>}
        </section>
      </div>
    </div>
  );
}

function Aderencia({ ad }: { ad: any }) {
  const [aberto, setAberto] = useState<number | null>(null);
  if (!ad.areas.length) return <p className="mudo">O instrutor não tem área definida nem UCs marcadas: cadastre a área para calcular a aderência.</p>;
  return (
    <div className="aderencia">
      <p className="sub">{ad.metodo}</p>
      {ad.multiarea && <p className="sub"><b>Índice geral {pct(ad.geral)}</b>: soma de todas as áreas em que o instrutor atua, pela carga horária.</p>}
      {ad.areas.map((a: any) => (
        <section key={a.area_id} className="ad-area">
          <div className="ad-area-cab">
            <Anel valor={a.pct} tamanho={58} rotulo={`Aderência em ${a.area}`} />
            <div><h4>{a.area} {a.principal && <small className="mudo">· área principal</small>}</h4>
              <small className="mudo">{a.cursos.length} curso(s) · {a.cursos_100} com 100%</small></div>
          </div>
          {a.fora_do_nivel?.length > 0 && <p className="sub">Fora do índice: {a.fora_do_nivel.join(", ")} — curso(s) técnico(s), e o instrutor é de nível básico
            (só AIB e qualificações). Passar a técnico é decisão da coordenação, não item de PDI.</p>}
          <ul className="lista-limpa ad-cursos">
            {a.cursos.map((c: any) => (
              <li key={c.curso_id}>
                <button className="ad-curso" aria-expanded={aberto === c.curso_id} onClick={() => setAberto(aberto === c.curso_id ? null : c.curso_id)}>
                  <span className="ad-curso-nome"><b>{c.codigo}</b> <small className="mudo">{c.nome}</small></span>
                  <BarraPct valor={c.pct} />
                  <b className={`tom-txt-${tomAderencia(c.pct)}`}>{pct(c.pct)}</b>
                  <small className="mudo">{c.ucs_sim}/{c.ucs_total} UCs{c.ucs_em_partes ? ` · ${c.ucs_em_partes} em partes` : ""}</small>
                </button>
                {aberto === c.curso_id && <div className="ad-ucs">
                  {c.ucs.map((u: any) => <span key={u.codigo} className={`uc-pilula ${STATUS_UC[u.situacao]}`} title={`${u.nome} · ${u.ch} h · ${u.rotulo}${u.certificacao ? ` · exige ${u.certificacao}` : ""}`}>
                    {u.codigo} <small>{u.rotulo} · {u.ch} h</small></span>)}
                  {c.transversais > 0 && <small className="mudo">+ {c.transversais} UC(s) transversal(is), que qualquer instrutor pode dar (fora do índice).</small>}
                </div>}
              </li>
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
}

function Pdi({ id, mudou }: { id: number; mudou: () => void }) {
  const { pode, aviso } = useApp();
  const r = useCarregar<any>(() => api.get(`/api/instrutores/${id}/pdi`), [id]);
  const [sel, setSel] = useState<Record<string, boolean>>({});
  const [ocupado, setOcupado] = useState(false);
  const editavel = pode("cadastros.editar");
  const d = r.dados;
  if (r.carregando && !d) return <p role="status">Montando as propostas de PDI…</p>;
  if (r.erro) return <div className="erro-box">{r.erro}</div>;
  if (!d) return null;
  const chave = (i: any) => `${i.curso_id}|${i.uc_codigo}|${i.tipo}`;
  const marcados = d.itens.filter((i: any) => sel[chave(i)] && !i.no_pdi);
  const incluir = async (itens: any[]) => {
    setOcupado(true);
    try {
      const x = await api.post(`/api/instrutores/${id}/pdi`, { itens: itens.map((i) => ({ curso_id: i.curso_id, uc_codigo: i.uc_codigo, tipo: i.tipo, prazo: i.prazo_sugerido, prioridade: i.prioridade })) });
      aviso(`${x.incluidos} item(ns) incluído(s) no PDI.`);
      setSel({});
      r.recarregar(); mudou();
    } catch (e: any) { aviso(e.message, "erro"); }
    setOcupado(false);
  };
  const atualizar = async (pid: number, corpo: any, msg?: string) => {
    try {
      const x = await api.put(`/api/pdi/${pid}`, corpo);
      aviso(msg ? `${msg}${x.habilitou?.length ? ` Aderência geral agora: ${pct(x.geral)}.` : ""}` : "PDI atualizado.");
      r.recarregar(); mudou();
    } catch (e: any) { aviso(e.message, "erro"); }
  };
  const altas = d.itens.filter((i: any) => i.prioridade === "alta" && !i.no_pdi);
  return (
    <div className="pdi">
      <div className="pdi-proj">
        {d.projecao.map((p: any) => (
          <div key={p.area_id} className="pdi-proj-area">
            <small className="mudo">{p.area}</small>
            <div className="pdi-degraus">
              <span><Anel valor={p.hoje} tamanho={46} /><small>hoje</small></span><span className="seta">→</span>
              <span><Anel valor={p.com_alta} tamanho={46} /><small>com a prioridade alta</small></span><span className="seta">→</span>
              <span><Anel valor={p.com_todas} tamanho={46} /><small>com o PDI completo</small></span>
            </div>
            <small className="mudo">{p.ch_a_desenvolver} h de UCs a desenvolver</small>
          </div>
        ))}
      </div>
      <h4>PDI do instrutor</h4>
      {!d.salvo.length && <p className="mudo">Nenhum item no PDI ainda. Escolha abaixo as propostas e inclua.</p>}
      {d.salvo.length > 0 && <ul className="lista-limpa pdi-salvo">
        {d.salvo.map((p: any) => (
          <li key={p.id} className={`pdi-item sit-${p.situacao}`}>
            <div><b>{p.uc_codigo}</b> {p.uc_nome} <small className="mudo">· {p.curso} · {TIPO_PDI[p.tipo]}{p.certificacao ? ` (${p.certificacao})` : ""}</small>
              {p.prioridade && <> <Badge tipo={PRIORIDADE[p.prioridade]?.[0] || "info"}>{PRIORIDADE[p.prioridade]?.[1]}</Badge></>}
              {p.atrasado && <> <Badge tipo="bloqueio">prazo vencido</Badge></>}</div>
            <div className="pdi-ctrl">
              <label className="mudo">prazo <input type="date" value={p.prazo || ""} disabled={!editavel || p.situacao === "concluido"} onChange={(e) => atualizar(p.id, { prazo: e.target.value || null })} /></label>
              <select aria-label="Situação do item" value={p.situacao} disabled={!editavel || p.situacao === "concluido"} onChange={(e) => atualizar(p.id, { situacao: e.target.value })}>
                {Object.entries(SITUACAO_PDI).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
              </select>
              {editavel && p.situacao !== "concluido" && p.situacao !== "cancelado" && <button className="btn btn-primario" onClick={() => {
                if (confirm(p.tipo === "certificacao" ? `Concluir e registrar a certificação ${p.certificacao} no perfil do instrutor?` : `Concluir e marcar ${p.uc_codigo} como "sim" no perfil do instrutor?`))
                  atualizar(p.id, { situacao: "concluido", habilitar: true }, "Item concluído e perfil atualizado.");
              }}>✓ Concluir e habilitar</button>}
              {p.situacao === "concluido" && <Badge tipo="ok">concluído {p.concluido_em ? dataBR(p.concluido_em) : ""}</Badge>}
            </div>
          </li>
        ))}
      </ul>}
      <div className="pdi-prop-cab">
        <h4>Propostas para chegar a 100% <small className="mudo">({d.resumo.total} · {d.resumo.alta} de prioridade alta)</small></h4>
        {editavel && <div className="acoes-linha">
          {altas.length > 0 && <button className="btn" disabled={ocupado} onClick={() => incluir(altas)}>Incluir as de prioridade alta ({altas.length})</button>}
          <button className="btn btn-primario" disabled={ocupado || !marcados.length} onClick={() => incluir(marcados)}>Incluir selecionadas no PDI ({marcados.length})</button>
        </div>}
      </div>
      {!d.itens.length && <p><Badge tipo="ok">100% de aderência</Badge> O instrutor já dá todas as UCs técnicas dos cursos da(s) área(s).</p>}
      <ul className="lista-limpa pdi-props">
        {d.itens.map((i: any) => (
          <li key={chave(i)} className={`pdi-prop ${i.no_pdi ? "no-pdi" : ""}`}>
            {editavel && <input type="checkbox" aria-label={`Selecionar ${i.uc_codigo}`} disabled={i.no_pdi} checked={!!sel[chave(i)] || i.no_pdi}
              onChange={(e) => setSel({ ...sel, [chave(i)]: e.target.checked })} />}
            <div className="pdi-prop-txt">
              <div><Badge tipo={PRIORIDADE[i.prioridade][0]}>{PRIORIDADE[i.prioridade][1]}</Badge> <b>{i.acao}</b></div>
              <small className="mudo">{i.curso} · {i.area} · {i.ch} h · {i.porque.join(" · ")}</small>
            </div>
            <div className="pdi-ganho"><b>+{i.ganho_curso_pp.toLocaleString("pt-BR")} pp</b><small className="mudo">em {i.curso}</small></div>
            <div className="pdi-ganho">{i.no_pdi ? <Badge tipo="ok">no PDI</Badge> : <><small className="mudo">prazo sugerido</small><small>{dataBR(i.prazo_sugerido)}</small></>}</div>
          </li>
        ))}
      </ul>
    </div>
  );
}
