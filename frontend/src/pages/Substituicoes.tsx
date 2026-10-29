import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api, dataBR, qs } from "../api";
import { useApp } from "../contexto";
import { useOpcoes } from "../hooks";
import { semestreDe } from "../semestre";
import { CandidatosSubstituicao, SubstituicoesEmVigor } from "../components/Substituicao";
import { Badge, Campo, Erro, Modal, Pagina, useCarregar } from "../components/ui";

const DIAS = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"];
const iso = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
const somaDias = (s: string, n: number) => { const d = new Date(`${s}T12:00:00`); d.setDate(d.getDate() + n); return iso(d); };

/** Substituições: buscar o instrutor, ver o que ele estaria fazendo, escolher as aulas e indicar quem pode assumir
 * (pela disponibilidade no dia e no horário). Horista fora do termo de horas entra como opção, com a aprovação da
 * supervisão e a concordância dele. */
export default function Substituicoes() {
  const { cenarios, cenario, pode, aviso } = useApp();
  const [sp, setSp] = useSearchParams();
  const instrutores = useOpcoes("instrutores");
  const hoje = iso(new Date());
  const [busca, setBusca] = useState("");
  const [instrutorId, setInstrutorId] = useState<number | null>(Number(sp.get("instrutor")) || null);
  const [inicio, setInicio] = useState(sp.get("de") || hoje);
  const [fim, setFim] = useState(sp.get("ate") || somaDias(hoje, 13));
  const [aberta, setAberta] = useState<any>(null);  // aula clicada: abre o pop-up com quem pode assumir
  const [versao, setVersao] = useState(0);
  const podeEditar = pode("alocacoes.editar");

  // substituição é ajuste operacional: vale no horário publicado do semestre (ou na versão aberta, se ainda não houver)
  const alvo = useMemo(() => {
    const sem = semestreDe(cenario);
    return cenarios.find((c) => c.estado === "publicado" && c.tipo !== "simulacao" && semestreDe(c) === sem) || cenario;
  }, [cenarios, cenario]);
  useEffect(() => { setAberta(null); }, [instrutorId, inicio, fim, alvo?.id]);
  useEffect(() => {
    const p: Record<string, string> = {};
    if (instrutorId) p.instrutor = String(instrutorId);
    if (inicio !== hoje) p.de = inicio;
    setSp(p, { replace: true });
  }, [instrutorId, inicio]);

  const termo = busca.trim().toLowerCase();
  const achados = termo ? instrutores.filter((i) => i.rotulo.toLowerCase().includes(termo)).slice(0, 8) : [];
  const aulas = useCarregar<any>(() => instrutorId && alvo
    ? api.get(`/api/substituicoes/aulas-do-instrutor${qs({ cenario_id: alvo.id, instrutor_id: instrutorId, inicio, fim })}`)
    : Promise.resolve(null), [instrutorId, inicio, fim, alvo?.id, versao]);
  const pendentes = useCarregar<any[]>(() => pode("solicitacoes.aprovar") ? api.get("/api/solicitacoes-instrutores?status=pendente") : Promise.resolve([]), [versao]);
  const pedidosSub = (pendentes.dados || []).filter((s) => s.tipo === "substituicao" || s.tipo === "folga");

  const blocos: any[] = aulas.dados?.blocos || [];
  const livres = blocos.filter((b) => b.situacao === "programada" && !b.substituto);
  // agenda em semanas (segunda a sexta; sábado só se houver aula)
  const semanas = useMemo(() => {
    const m = new Map<string, Map<string, any[]>>();
    for (const b of blocos) {
      const seg = somaDias(b.data, -b.dia_semana);
      if (!m.has(seg)) m.set(seg, new Map());
      const dias = m.get(seg)!;
      dias.set(b.data, [...(dias.get(b.data) || []), b]);
    }
    return [...m.entries()].map(([seg, dias]) => {
      const sab = [...dias.keys()].some((d) => new Date(`${d}T12:00:00`).getDay() === 6);
      return { seg, dias: Array.from({ length: sab ? 6 : 5 }, (_, i) => { const d = somaDias(seg, i); return { data: d, aulas: dias.get(d) || [] }; }) };
    });
  }, [blocos]);
  const horas = (min: number) => `${(min / 60).toFixed(1).replace(".", ",")} h`;
  const nome = aulas.dados?.instrutor?.nome || instrutores.find((i) => Number(i.id) === instrutorId)?.rotulo;
  const nSubst = blocos.filter((b) => b.substituto).length;

  return (
    <Pagina titulo="Substituições" descricao="Busque o instrutor, veja o que ele estaria fazendo e escolha as aulas: o sistema indica quem pode assumir pela disponibilidade no dia e no horário (mensalista primeiro). Cada UC tem um só instrutor; a substituição é a exceção e fica registrada.">
      {!alvo && <div className="cur-vazio">Escolha um semestre no topo.</div>}
      {alvo && <>
        <div className="subs-topo">
          <div className="subs-busca">
            <label htmlFor="busca-inst" className="subs-rotulo">🔎 Instrutor</label>
            <input id="busca-inst" type="search" placeholder="Nome ou matrícula do instrutor" value={busca} autoComplete="off"
              onChange={(e) => setBusca(e.target.value)} />
            {achados.length > 0 && <ul className="subs-achados" role="listbox">
              {achados.map((i) => <li key={i.id}><button onClick={() => { setInstrutorId(Number(i.id)); setBusca(""); }}>{i.rotulo}</button></li>)}
            </ul>}
            {termo && !achados.length && <small className="mudo">Nenhum instrutor com “{busca}”.</small>}
          </div>
          <Campo rotulo="De"><input type="date" value={inicio} onChange={(e) => { setInicio(e.target.value); if (fim < e.target.value) setFim(e.target.value); }} /></Campo>
          <Campo rotulo="Até"><input type="date" value={fim} min={inicio} onChange={(e) => setFim(e.target.value)} /></Campo>
          <div className="subs-atalhos">
            {[["Hoje", 0], ["7 dias", 6], ["14 dias", 13], ["30 dias", 29]].map(([r, n]) =>
              <button key={r} className="chip-filtro" onClick={() => { setInicio(hoje); setFim(somaDias(hoje, n as number)); }}>{r}</button>)}
          </div>
        </div>
        <p className="sub">Semestre: <b>{alvo.nome}</b>{alvo.estado === "publicado" ? " (horário publicado: a troca vale na hora e os instrutores são avisados no portal)" : ` (${alvo.estado.replace(/_/g, " ")})`}.</p>

        {pedidosSub.length > 0 && <div className="subs-pedidos">
          <b>📝 Pedidos dos instrutores aguardando decisão:</b>
          {pedidosSub.map((s) => <button key={s.id} className="chip-area" onClick={() => { setInstrutorId(s.instrutor_id); setInicio(s.data_inicio); setFim(s.data_fim); }}
            title={s.justificativa}>{s.instrutor} · {s.tipo_rotulo} · {dataBR(s.data_inicio).slice(0, 5)}{s.data_fim !== s.data_inicio ? `–${dataBR(s.data_fim).slice(0, 5)}` : ""}</button>)}
          <small className="mudo">Clique para ver as aulas do período. A decisão do pedido fica em “Solicitações dos instrutores”.</small>
        </div>}

        {!instrutorId && <div className="cur-vazio">Busque um instrutor para ver as aulas dele no período e iniciar a substituição.</div>}
        {instrutorId && <section className="subs-agenda">
          <div className="subs-cab">
            <div className="subs-quem">
              <span className="subs-avatar" aria-hidden="true">{(nome || "?").split(" ").map((x: string) => x[0]).slice(0, 2).join("")}</span>
              <div><h3>{nome}</h3>
                <small className="mudo">{aulas.dados?.instrutor?.modalidade === "horista" ? "Horista" : "Mensalista"} · {dataBR(inicio)} a {dataBR(fim)}</small></div>
            </div>
            <div className="subs-kpis">
              <span><b>{blocos.length}</b><small>aulas de turno</small></span>
              <span><b>{horas(blocos.reduce((t, b) => t + b.minutos, 0))}</b><small>no período</small></span>
              <span><b>{livres.length}</b><small>a substituir</small></span>
              <span><b>{nSubst}</b><small>já com substituto</small></span>
            </div>
            <button className="btn-link" onClick={() => setInstrutorId(null)}>Trocar instrutor</button>
          </div>
          {podeEditar && livres.length > 0 && <p className="subs-dica">👆 Clique numa aula para ver quem pode assumir.</p>}
          {aulas.carregando && <p role="status">Carregando as aulas…</p>}
          {aulas.erro && <div className="erro-box">{aulas.erro}</div>}
          {aulas.dados && !blocos.length && <div className="cur-vazio">Nenhuma aula de {nome} neste período.</div>}
          {semanas.map((sem) => (
            <div key={sem.seg} className="subs-semana">
              <div className="subs-semana-rot">Semana de {dataBR(sem.seg).slice(0, 5)}</div>
              <div className="subs-grade" style={{ gridTemplateColumns: `repeat(${sem.dias.length}, minmax(0, 1fr))` }}>
                {sem.dias.map(({ data, aulas: xs }) => {
                  const d = new Date(`${data}T12:00:00`);
                  return (
                    <div key={data} className={`subs-col ${data === hoje ? "hoje" : ""} ${data < inicio || data > fim ? "fora" : ""}`}>
                      <div className="subs-col-cab"><b>{DIAS[(d.getDay() + 6) % 7]}</b><span>{dataBR(data).slice(0, 5)}</span>{data === hoje && <em>hoje</em>}</div>
                      {xs.map((b) => {
                        const clicavel = podeEditar && livres.includes(b);
                        const tom = b.situacao === "realizada" ? "realizada" : b.substituto ? "substituida" : b.substituindo ? "substituindo" : "programada";
                        return (
                          <button key={b.ids.join(",")} className={`subs-card t-${(b.turno || "").slice(0, 1).toLowerCase()} ${tom}`} disabled={!clicavel}
                            onClick={() => setAberta(b)} title={clicavel ? "Clique para substituir" : undefined}>
                            <span className="subs-card-hora">{b.inicio}–{b.fim}</span>
                            <b className="subs-card-turma">{b.turma}</b>
                            <span className="subs-card-uc">{b.uc}{b.grupo ? ` · G${b.grupo}` : ""}</span>
                            <span className="subs-card-rodape">🏫 {b.sala || "sem sala"}
                              {tom === "realizada" && <em>✓ realizada</em>}
                              {tom === "substituida" && <em>🔁 {b.substituto}</em>}
                              {tom === "substituindo" && <em>no lugar de {b.substituindo}</em>}
                              {tom === "programada" && clicavel && <em className="subs-card-acao">Substituir ›</em>}</span>
                          </button>);
                      })}
                      {!xs.length && <span className="subs-col-vazia">—</span>}
                    </div>);
                })}
              </div>
            </div>))}
        </section>}

        {aberta && alvo && <PopupSubstituicao cenarioId={alvo.id} aula={aberta} livres={livres} titular={nome || ""} fechar={() => setAberta(null)}
          pronto={() => { setAberta(null); setVersao((v) => v + 1); aviso("Substituição registrada. Os instrutores foram avisados no portal."); }} />}

        <SubstituicoesEmVigor cenarioId={alvo.id} podeEditar={podeEditar} versao={versao} mudou={() => setVersao((v) => v + 1)} />
      </>}
    </Pagina>
  );
}

/** Pop-up aberto ao clicar numa aula: o que vai para o substituto (só esta aula, o dia, a UC no período ou tudo) e quem pode assumir. */
function PopupSubstituicao({ cenarioId, aula, livres, titular, fechar, pronto }: { cenarioId: number; aula: any; livres: any[]; titular: string;
  fechar: () => void; pronto: () => void }) {
  const opcoes = [
    { k: "aula", rotulo: "Só esta aula", xs: [aula] },
    { k: "dia", rotulo: `O dia ${dataBR(aula.data).slice(0, 5)} todo`, xs: livres.filter((b) => b.data === aula.data) },
    { k: "uc", rotulo: `${aula.turma} · ${aula.uc.split(" – ")[0]} no período`, xs: livres.filter((b) => b.turma_uc_id === aula.turma_uc_id) },
    { k: "tudo", rotulo: "Todas as aulas do período", xs: livres },
  ].filter((o, i, arr) => i === 0 || (o.xs.length > 1 && o.xs.length !== arr[i - 1].xs.length));
  const [escopo, setEscopo] = useState("aula");
  const atual = opcoes.find((o) => o.k === escopo) || opcoes[0];
  const ids = atual.xs.flatMap((b) => b.ids);
  const d = new Date(`${aula.data}T12:00:00`);
  return (
    <Modal titulo="🔁 Substituir aula" aberto fechar={fechar} largo>
      <div className={`subs-pop-aula t-${(aula.turno || "").slice(0, 1).toLowerCase()}`}>
        <div className="subs-pop-data"><b>{DIAS[(d.getDay() + 6) % 7]}</b><span>{dataBR(aula.data).slice(0, 5)}</span></div>
        <div><span><b>{aula.turma}</b> · {aula.uc}{aula.grupo ? ` (grupo ${aula.grupo})` : ""}</span>
          <small className="mudo">{aula.inicio}–{aula.fim} · {aula.turno} · 🏫 {aula.sala || "sem sala"} · titular: {titular}</small></div>
      </div>
      {opcoes.length > 1 && <div className="subs-escopo" role="radiogroup" aria-label="O que vai para o substituto">
        <span className="mudo">Substituir:</span>
        {opcoes.map((o) => <button key={o.k} role="radio" aria-checked={escopo === o.k} className={`chip-filtro ${escopo === o.k ? "on" : ""}`}
          onClick={() => setEscopo(o.k)}>{o.rotulo}{o.xs.length > 1 ? ` (${o.xs.length})` : ""}</button>)}
      </div>}
      <IniciarSubstituicao key={ids.join(",")} cenarioId={cenarioId} ids={ids} titular={titular} resumo={atual.xs} pronto={pronto} />
    </Modal>
  );
}

/** Aulas escolhidas: substitutos possíveis (pela disponibilidade no dia e no horário), motivo, conferência e confirmação. */
function IniciarSubstituicao({ cenarioId, ids, titular, resumo, pronto }: { cenarioId: number; ids: number[]; titular: string; resumo: any[]; pronto: () => void }) {
  const [sub, setSub] = useState<any>(null);
  const [motivo, setMotivo] = useState("");
  const [aprovado, setAprovado] = useState(false);
  const [concorda, setConcorda] = useState(false);
  const [previa, setPrevia] = useState<any>(null);
  const [erro, setErro] = useState<any>(null);
  const alvo = { cenario_id: cenarioId, alocacao_ids: ids };
  const cand = useCarregar<any>(() => api.get(`/api/substituicoes/candidatos${qs({ cenario_id: cenarioId, alocacao_ids: ids.join(",") })}`), [ids.join(",")]);
  const precisaAprovacao = sub?.grupo === "aprovacao";
  const corpo = () => ({ ...alvo, substituto_id: sub.id, motivo, aprovado_supervisao: aprovado, concordancia: concorda });
  const ok = !!sub && motivo.trim().length >= 10 && (!precisaAprovacao || (aprovado && concorda));
  const conferir = async () => { setErro(null); try { setPrevia(await api.post("/api/substituicoes", { ...corpo(), somente_validar: true })); } catch (e) { setErro(e); } };
  const confirmar = async () => {
    setErro(null);
    try {
      const r = await api.post("/api/substituicoes", corpo());
      if (!r.substituidas) { setPrevia({ ...r, possiveis: 0 }); return; }
      pronto();
    } catch (e) { setErro(e); }
  };
  return (
    <section className="subs-painel">
      <h4 className="subs-painel-tit">Quem pode assumir <small className="mudo">— {resumo.length} aula(s) de {titular}{resumo.length > 1 ? `: ${resumo.slice(0, 4).map((b) => `${dataBR(b.data).slice(0, 5)} ${b.turma}`).join(", ")}${resumo.length > 4 ? "…" : ""}` : ""}</small></h4>
      <CandidatosSubstituicao dados={cand.dados} carregando={cand.carregando} erro={cand.erro} escolhido={sub?.id ?? null}
        escolher={(c) => { setSub(c); setPrevia(null); setAprovado(false); setConcorda(false); }} />
      {sub && <div className="subs-confirmar">
        <p>Substituto: <b>{sub.nome}</b> {sub.modalidade === "horista" ? <Badge tipo="info">horista</Badge> : <Badge tipo="ok">mensalista</Badge>}</p>
        {precisaAprovacao && <div className="aviso-inline">
          ⏱ {sub.nome} está <b>fora do termo de horas ou da disponibilidade cadastrada</b> nesse dia/horário. Pode assumir com:
          <label><input type="checkbox" checked={aprovado} onChange={(e) => { setAprovado(e.target.checked); setPrevia(null); }} /> a <b>aprovação da supervisão</b></label>
          <label><input type="checkbox" checked={concorda} onChange={(e) => { setConcorda(e.target.checked); setPrevia(null); }} /> a <b>concordância e a disponibilidade</b> do instrutor (confirmadas com ele)</label>
          <small>O termo de horas do mês é ajustado junto e fica registrado com o motivo.</small>
        </div>}
        <Campo rotulo="Motivo da substituição" obrigatorio ajuda="Fica registrado na aula, no histórico e no aviso aos instrutores.">
          <textarea rows={2} value={motivo} placeholder="Ex.: atestado médico do titular; curso externo do titular." onChange={(e) => { setMotivo(e.target.value); setPrevia(null); }} />
        </Campo>
        {previa && <div className={`previa-sub ${previa.falhas.length ? "tom-alerta" : "tom-ok"}`}>
          <b>{previa.possiveis ?? previa.substituidas} aula(s) podem ser trocadas para {sub.nome}.</b>
          {[...new Set<string>((previa.aulas || []).flatMap((a: any) => a.avisos))].slice(0, 4).map((x) => <div key={x}><small>{x}</small></div>)}
          {previa.falhas.length > 0 && <ul>{previa.falhas.map((f: any) => <li key={f.alocacao_id}>{dataBR(f.data)} {f.horario}: {f.motivos.join("; ")}</li>)}</ul>}
        </div>}
        <Erro erro={erro} />
        <div className="acoes-linha">
          <button className="btn" disabled={!ok} onClick={conferir}>Conferir</button>
          <button className="btn btn-primario" disabled={!ok || !previa || !previa.possiveis} onClick={confirmar}>Confirmar substituição</button>
          {!ok && <small className="mudo">{motivo.trim().length < 10 ? "Escreva o motivo (mínimo de 10 caracteres)." : precisaAprovacao ? "Marque a aprovação e a concordância." : ""}</small>}
        </div>
      </div>}
    </section>
  );
}
