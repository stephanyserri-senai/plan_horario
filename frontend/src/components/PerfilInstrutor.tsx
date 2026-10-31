import { PainelTermo } from "./QuadroDisponibilidade";
import { type ReactNode, useState } from "react";
import { api, dataBR, qs } from "../api";
import { useApp } from "../contexto";
import { Abas, Badge, Modal, useCarregar } from "./ui";
import { Colunas } from "./Graficos";

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
export function BarraPct({ valor, fina, neutra, distribuicao }: { valor: number; fina?: boolean; neutra?: boolean; distribuicao?: boolean }) {
  const tom = distribuicao ? "neutro" : neutra ? (valor > 90 ? "erro" : "neutro") : tomAderencia(valor);
  return <span className={`barra-pct ${fina ? "fina" : ""}`}><span className={`barra-pct-v bp-${tom}`} style={{ width: `${Math.min(100, valor)}%` }} /></span>;
}

/** Cartão do instrutor na lista: quem é (unidade, áreas, nível, modalidade), como está no semestre (aulas, turmas, próxima aula),
 * o que sabe (UCs, certificações, aderência por curso), o PDI, os alertas e as ações do cadastro. Clique abre o perfil completo. */
export function CartaoInstrutor({ l, ad, r, abrir, acoes }: { l: any; ad?: any; r?: any; abrir: () => void; acoes?: ReactNode }) {
  const horista = l.modalidade === "horista";
  const s = r?.semestre;
  return (
    <article className={`cartao-inst ${l.ativo === false ? "inativo" : ""} ${r?.alertas?.some((a: any) => a.tipo === "bloqueio") ? "com-bloqueio" : ""}`}>
      <button className="ci-cab" onClick={abrir} aria-label={`Abrir o perfil de ${l.nome}`}>
        <Avatar nome={l.nome} />
        <span className="ci-id">
          <b>{l.nome}</b>
          <small className="mudo">{l.matricula}{r?.unidade ? ` · ${r.unidade.replace(/^Unidade\s+/i, "")}` : ""}</small>
          <span className="ci-tags">
            <span className={`modalidade modalidade-${l.modalidade}`}>{horista ? "Horista" : "Mensalista"}</span>
            <span className="chip-area">{NIVEL[l.nivel] || l.nivel}</span>
            <span className="chip-area">{Number(l.carga_horaria_contratual)} h/sem</span>
            {l._acesso_portal && <span className="chip-area ca-portal">portal ✓</span>}
          </span>
        </span>
        <span className="ci-anel">{ad ? <Anel valor={ad.geral} tamanho={56} rotulo="Aderência geral" /> : <span className="ader-vazio" />}<small>aderência</small></span>
      </button>
      <div className="cartao-inst-areas">
        {(ad?.areas || []).map((a: any) => <span key={a.area_id} className={`chip-area ${a.principal ? "ca-principal" : ""}`}>{a.area} · {pct(a.pct)}</span>)}
        {!ad?.areas?.length && <span className="chip-area">sem área</span>}
      </div>
      <div className="ci-numeros">
        <div><small>Aulas/semana</small><b>{s ? `${s.media_semanal_h} h` : "—"}</b>
          {s && <><BarraPct valor={s.pct_contrato} fina neutra /><small className="mudo">{pct(s.pct_contrato)} do contrato</small></>}</div>
        <div><small>Turmas</small><b>{s ? s.turmas : "—"}</b><small className="mudo">{s?.proxima_aula ? `próxima ${dataBR(s.proxima_aula).slice(0, 5)}` : "sem aula futura"}</small></div>
        <div><small>UCs</small><b>{r ? r.ucs_sim : "—"}</b><small className="mudo">{r?.ucs_em_partes ? `+ ${r.ucs_em_partes} em partes` : "que ministra"}</small></div>
        <div><small>{horista ? `Termo ${r?.termo?.rotulo?.split("/")[0] || ""}` : "PDI"}</small>
          {horista ? <><b>{r?.termo?.horas_aula != null ? `${r.termo.horas_aula} h` : "—"}</b><small className="mudo">{r?.termo?.horas_aula != null ? "de aula no mês" : "sem termo"}</small></>
            : <><b>{r ? r.pdi.abertos : "—"}</b><small className="mudo">{r?.pdi.concluidos ? `${r.pdi.concluidos} concluído(s)` : "item(ns) em aberto"}</small></>}</div>
      </div>
      <div className="cartao-inst-cursos">
        {(ad?.cursos || []).slice(0, 4).map((c: any) => (
          <div key={c.codigo} className="mini-curso"><span>{c.codigo}</span><BarraPct valor={c.pct} fina /><small>{Math.round(c.pct)}%</small></div>
        ))}
        {!ad?.cursos?.length && <small className="mudo">Sem cursos com UCs técnicas na área.</small>}
      </div>
      {(r?.certificacoes?.length > 0 || (horista && r?.pdi.abertos > 0)) && <div className="ci-certs">
        {r.certificacoes.map((c: any) => <span key={c.nome} className={`chip-area ${c.vencida ? "ca-vencida" : c.vence_em_30 ? "ca-vence" : "ca-cert"}`}
          title={c.vencida ? "vencida" : c.vence_em_30 ? "vence em até 30 dias" : "válida"}>🎓 {c.nome}</span>)}
        {horista && r?.pdi.abertos > 0 && <span className="chip-area">PDI: {r.pdi.abertos} em aberto</span>}
      </div>}
      {r?.alertas?.length > 0 && <div className="ci-alertas">{r.alertas.map((a: any) => <Badge key={a.texto} tipo={a.tipo}>{a.texto}</Badge>)}</div>}
      <div className="ci-acoes" onClick={(e) => e.stopPropagation()}>
        <button className="btn btn-primario btn-pequeno" onClick={abrir}>Ver perfil</button>
        {acoes}
      </div>
    </article>
  );
}

/** Perfil do instrutor: visão geral (dados, semestre, agenda), aderência por área e curso, e PDI. */
export function PerfilInstrutor({ id, fechar, editar, abaInicial }: { id: number | null; fechar: () => void; editar?: () => void; abaInicial?: string }) {
  const { cenario } = useApp();
  const [aba, setAba] = useState(abaInicial || "geral");
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
          <IndicesAderencia ad={d.aderencia} />
          {editar && <button className="btn" onClick={editar}>Editar cadastro</button>}
        </div>
        <Abas abas={[{ id: "geral", rotulo: "Visão geral" }, { id: "ocupacao", rotulo: "Ocupação" },
          { id: "termo", rotulo: d.dados.modalidade === "horista" ? `⏱ Termo de horas${d.termos && !d.termos.atual?.tem_termo ? " ⚠" : ""}` : "⏱ Jornada / termo" },
          { id: "competencias", rotulo: "Competências e certificações" },
          { id: "aderencia", rotulo: "Aderência aos cursos" }, { id: "pdi", rotulo: "PDI" }]} ativa={aba} mudar={setAba} />
        {aba === "geral" && <VisaoGeral d={d} />}
        {aba === "ocupacao" && <Ocupacao d={d} />}
        {aba === "termo" && (d.dados.modalidade === "horista" ? <PainelTermo instId={d.dados.id} nome={d.dados.nome} /> : <JornadaMensalista d={d} />)}
        {aba === "competencias" && <Competencias d={d} mudou={p.recarregar} />}
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

export function Aderencia({ ad }: { ad: any }) {
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

export function Pdi({ id, mudou, url, somenteLeitura }: { id: number; mudou: () => void; url?: string; somenteLeitura?: boolean }) {
  const { pode, aviso } = useApp();
  const r = useCarregar<any>(() => api.get(url || `/api/instrutores/${id}/pdi`), [id, url]);
  const [sel, setSel] = useState<Record<string, boolean>>({});
  const [ocupado, setOcupado] = useState(false);
  const editavel = pode("cadastros.editar") && !somenteLeitura;
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
              {editavel ? <>
                <label className="mudo">prazo <input type="date" value={p.prazo || ""} disabled={p.situacao === "concluido"} onChange={(e) => atualizar(p.id, { prazo: e.target.value || null })} /></label>
                <select aria-label="Situação do item" value={p.situacao} disabled={p.situacao === "concluido"} onChange={(e) => atualizar(p.id, { situacao: e.target.value })}>
                  {Object.entries(SITUACAO_PDI).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                </select></> : <>
                {p.prazo && <small className="mudo">prazo {dataBR(p.prazo)}</small>}
                {p.situacao !== "concluido" && <Badge tipo={p.situacao === "em_andamento" ? "alerta" : p.situacao === "cancelado" ? "neutro" : "info"}>{SITUACAO_PDI[p.situacao]}</Badge>}</>}
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

const NIVEL_COMP: [string, string][] = [["pleno", "Sim"], ["parcial", "Em partes"], ["nenhum", "Não"]];

/** Matriz de competências e certificações do instrutor, editáveis no próprio perfil (antes eram abas separadas). */
function Competencias({ d, mudou }: { d: any; mudou: () => void }) {
  const { pode, aviso } = useApp();
  const editavel = pode("cadastros.editar");
  const id = d.dados.id;
  const [ocupado, setOcupado] = useState<string | null>(null);
  const [nova, setNova] = useState({ nome: "", valido_ate: "" });
  const [filtro, setFiltro] = useState("");
  const certs: any[] = d.dados.certificacoes;
  const temCert = new Set(certs.filter((c) => !c.vencida).map((c) => c.nome.trim().toLowerCase()));
  const exigidas = Array.from(new Set(d.aderencia.areas.flatMap((a: any) => a.cursos.flatMap((c: any) => c.ucs.map((u: any) => u.certificacao)))
    .filter((x: any) => x && !temCert.has(String(x).toLowerCase())))) as string[];
  const marcar = async (curso_id: number, u: any, nivel: string) => {
    setOcupado(`${curso_id}-${u.codigo}`);
    try {
      const r = await api.put(`/api/instrutores/${id}/competencias`, { curso_id, uc_codigo: u.codigo, nivel });
      aviso(`${u.codigo}: ${r.rotulo}. Aderência geral agora: ${pct(r.geral)}.`);
      mudou();
    } catch (e: any) { aviso(e.message, "erro"); }
    setOcupado(null);
  };
  const salvarCert = async (nome: string, valido_ate: string) => {
    try {
      const r = await api.put(`/api/instrutores/${id}/certificacoes`, { nome, valido_ate: valido_ate || null });
      aviso(`Certificação ${r.nome} registrada. Aderência geral: ${pct(r.geral)}.`);
      setNova({ nome: "", valido_ate: "" });
      mudou();
    } catch (e: any) { aviso(e.message, "erro"); }
  };
  const retirar = async (c: any) => {
    if (!confirm(`Retirar a certificação ${c.nome} do perfil? (fica no histórico)`)) return;
    try { await api.post(`/api/instrutores/${id}/certificacoes/${c.id}/retirar`); aviso(`${c.nome} retirada.`); mudou(); }
    catch (e: any) { aviso(e.message, "erro"); }
  };
  const f = filtro.trim().toLowerCase();
  return (
    <div className="comp-perfil">
      <section className="perfil-bloco">
        <h4>Certificações e habilitações</h4>
        {!certs.length && <p className="mudo">Nenhuma certificação registrada.</p>}
        <ul className="lista-limpa cert-lista">
          {certs.map((c) => (
            <li key={c.id}>
              <Badge tipo={c.vencida ? "bloqueio" : "ok"}>{c.nome}</Badge>
              {editavel ? <label className="mudo">validade <input type="date" defaultValue={c.valido_ate || ""} onBlur={(e) => {
                if ((e.target.value || null) !== (c.valido_ate || null)) salvarCert(c.nome, e.target.value);
              }} /></label> : <small className="mudo">{c.valido_ate ? `até ${dataBR(c.valido_ate)}` : "sem validade"}</small>}
              {c.vencida && <small className="falta-txt">vencida: as UCs que a exigem não contam</small>}
              {editavel && <button className="btn-link" onClick={() => retirar(c)}>Retirar</button>}
            </li>
          ))}
        </ul>
        {exigidas.length > 0 && <p className="sub">Exigidas por UCs das áreas dele e ainda não registradas: {exigidas.map((x) =>
          editavel ? <button key={x} className="chip" onClick={() => setNova({ nome: x, valido_ate: "" })}>+ {x}</button> : <b key={x}>{x} </b>)}</p>}
        {editavel && <div className="cert-nova">
          <input placeholder="Nova certificação (ex.: NR-10)" aria-label="Nome da certificação" value={nova.nome} onChange={(e) => setNova({ ...nova, nome: e.target.value })} />
          <label className="mudo">validade <input type="date" value={nova.valido_ate} onChange={(e) => setNova({ ...nova, valido_ate: e.target.value })} /></label>
          <button className="btn btn-primario" disabled={nova.nome.trim().length < 2} onClick={() => salvarCert(nova.nome.trim(), nova.valido_ate)}>Registrar</button>
        </div>}
      </section>
      <section className="perfil-bloco">
        <div className="comp-cab"><h4>Matriz de competências <small className="mudo">— UCs técnicas dos cursos da(s) área(s) dele</small></h4>
          <input type="search" placeholder="Filtrar UC ou curso" aria-label="Filtrar UCs" value={filtro} onChange={(e) => setFiltro(e.target.value)} /></div>
        <p className="sub">Sim = ministra a UC; Em partes = ministra com alerta (vale metade no índice); Não = não ministra. Vale para todas as versões da
          matriz do curso. UCs transversais não precisam de marcação (qualquer instrutor pode dar).</p>
        {!d.aderencia.areas.length && <p className="mudo">Cadastre a área do instrutor para ver as UCs.</p>}
        {d.aderencia.areas.map((a: any) => (
          <div key={a.area_id} className="comp-area">
            <h5>{a.area} {a.principal && <small className="mudo">· área principal</small>}</h5>
            {a.cursos.map((c: any) => {
              const ucs = c.ucs.filter((u: any) => !f || `${c.codigo} ${c.nome} ${u.codigo} ${u.nome}`.toLowerCase().includes(f));
              if (!ucs.length) return null;
              return (
                <div key={c.curso_id} className="comp-curso">
                  <div className="comp-curso-cab"><b>{c.codigo}</b> <small className="mudo">{c.nome}</small> <span className="mudo">· {c.ucs_sim}/{c.ucs_total} UCs · {pct(c.pct)}</span></div>
                  <ul className="lista-limpa">
                    {ucs.map((u: any) => {
                      const atual = u.marcado || "nenhum";
                      return (
                        <li key={u.codigo} className="comp-uc">
                          <span><b>{u.codigo}</b> {u.nome} <small className="mudo">· {u.ch} h{u.certificacao ? ` · exige ${u.certificacao}` : ""}</small>
                            {u.situacao === "sem_certificacao" && <small className="falta-txt"> · falta a certificação {u.certificacao}</small>}</span>
                          <span className="seg" role="group" aria-label={`Competência em ${u.codigo}`}>
                            {NIVEL_COMP.map(([k, rot]) => (
                              <button key={k} className={`seg-op ${atual === k ? `on on-${k}` : ""}`} disabled={!editavel || ocupado === `${c.curso_id}-${u.codigo}` || atual === k}
                                aria-pressed={atual === k} onClick={() => marcar(c.curso_id, u, k)}>{rot}</button>
                            ))}
                          </span>
                        </li>
                      );
                    })}
                  </ul>
                </div>
              );
            })}
            {a.fora_do_nivel?.length > 0 && <p className="sub">Fora do nível do instrutor (básico): {a.fora_do_nivel.join(", ")}.</p>}
          </div>
        ))}
      </section>
    </div>
  );
}

/** Índice de aderência no cabeçalho: um anel por área em que o instrutor atua e o geral (todas as áreas, pela carga horária). */
export function IndicesAderencia({ ad }: { ad: any }) {
  return (
    <div className="indices-ader">
      {ad.areas.length > 1 && ad.areas.map((a: any) => (
        <div key={a.area_id} className="ia-area"><Anel valor={a.pct} tamanho={54} rotulo={`Aderência em ${a.area}`} /><small>{capitalizarArea(a.area)}</small></div>
      ))}
      <div className="ia-geral"><Anel valor={ad.geral} tamanho={84} rotulo="Aderência geral" />
        <small>{ad.areas.length > 1 ? "geral (todas as áreas)" : ad.areas.length ? `aderência · ${capitalizarArea(ad.areas[0].area)}` : "aderência geral"}</small></div>
    </div>
  );
}

const capitalizarArea = (t: string) => (t && t === t.toUpperCase() && !t.includes("/") ? t.charAt(0) + t.slice(1).toLowerCase() : t);

/** Ocupação do instrutor no semestre: semana a semana sobre o contrato, pico, turnos e o que fica fora de sala. */
export function Ocupacao({ d }: { d: any }) {
  const s = d.semestre;
  if (!s?.ocupacao) return <p className="mudo">Sem semestre com aulas para mostrar a ocupação.</p>;
  const o = s.ocupacao;
  const ag = s.agenda_h || {};
  const totalTurno = Object.values(o.por_turno).reduce((a: number, b: any) => a + Number(b), 0) as number;
  const tetoPct = o.carga_semanal ? Math.round((100 * o.limite_letivo) / o.carga_semanal) : 90;
  return (
    <div className="ocup-perfil">
      <div className="perfil-kpis">
        <div className="pk"><small>Média semanal</small><b>{s.media_semanal_h} h</b><BarraPct valor={s.pct_contrato} fina neutra />
          <span className="mudo">{pct(s.pct_contrato)} do contrato ({o.carga_semanal} h)</span></div>
        <div className="pk"><small>Semana mais cheia</small><b>{o.pico ? `${o.pico.horas} h` : "—"}</b>
          <span className="mudo">{o.pico ? `semana de ${o.pico.semana} · ${pct(o.pico.pct)} do contrato` : ""}</span></div>
        <div className="pk"><small>Limite de aulas</small><b>{o.limite_letivo} h</b>
          <span className={o.semanas_acima_teto ? "falta-txt" : "mudo"}>{o.semanas_acima_teto ? `${o.semanas_acima_teto} semana(s) acima` : "nenhuma semana acima"}</span></div>
        <div className="pk"><small>Fora de sala</small><b>{(ag.PL || 0) + (ag.PJ || 0) + (ag.TR || 0)} h</b>
          <span className="mudo">PL {ag.PL || 0} · PJ {ag.PJ || 0} · TR {ag.TR || 0}</span></div>
      </div>
      <section className="perfil-bloco">
        <h4>Ocupação semana a semana <small className="mudo">— horas de aula sobre a carga do contrato ({o.carga_semanal} h); limite de aulas do instrutor: {o.limite_letivo} h ({tetoPct}%)</small></h4>
        <Colunas dados={o.semanas} x="semana" y="pct" nome="% do contrato" altura={220}
          extraTooltip={(l: any) => <div className="tt-linha"><span className="tt-rotulo">horas de aula</span><b>{l.horas} h</b></div>} />
      </section>
      <section className="perfil-bloco">
        <h4>Aulas por turno</h4>
        {!totalTurno && <p className="mudo">Sem aulas no semestre.</p>}
        <div className="ocup-turnos">
          {Object.entries(o.por_turno).map(([t, hh]: any) => (
            <div key={t} className="mini-curso ocup-turno"><span>{t}</span><BarraPct valor={totalTurno ? (100 * hh) / totalTurno : 0} distribuicao /><small>{hh} h</small></div>
          ))}
        </div>
        {d.termos && <p className="sub">Horista: termo de {d.termos.atual?.rotulo} {d.termos.atual?.tem_termo ? `com ${d.termos.atual.horas_aula} h de aula` : "ainda não registrado"} (ajustável numa urgência, com a concordância do instrutor).</p>}
      </section>
    </div>
  );
}

/** Mensalista: não tem termo de horas (é do horista); a jornada semanal é fixa, com aulas até 90% dela e no máximo 44 h por semana. */
export function JornadaMensalista({ d, portal }: { d: any; portal?: boolean }) {
  const c = Number(d.dados.carga_contratual || 0), l = Number(d.dados.limite_letivo || 0);
  return (
    <div className="termo-proximo feito">
      <div className="termo-proximo-cab"><span className="termo-proximo-ico" aria-hidden="true">🗓</span>
        <div><b>Mensalista: jornada semanal fixa de {c} h</b>
          <small className="mudo">Aulas até {l} h por semana (limite cadastrado, no máximo 90% da jornada); o restante é planejamento (PL) e projeto (PJ). Ninguém passa de 44 h por semana.</small></div></div>
      <p className="sub">O termo de horas é do <b>horista</b>: é ele que recebe todo mês as horas pagas (aula, planejamento, projeto e urgência) na grade por dia e turno.
        {!portal && " Para lançar um termo para este instrutor, mude a modalidade dele para horista no cadastro."}</p>
      {d.semestre && <p className="sub">No semestre: {d.semestre.media_semanal_h} h de aula por semana em média ({d.semestre.pct_contrato}% do contrato).</p>}
    </div>
  );
}
