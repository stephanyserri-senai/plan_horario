import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api, dataBR, qs } from "../api";
import { useApp } from "../contexto";
import { useOpcoes } from "../hooks";
import { semestreDe } from "../semestre";
import { CandidatosSubstituicao, SubstituicoesEmVigor } from "../components/Substituicao";
import { Badge, Campo, Erro, Pagina, useCarregar } from "../components/ui";

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
  const [marcadas, setMarcadas] = useState<Set<string>>(new Set());
  const [versao, setVersao] = useState(0);
  const podeEditar = pode("alocacoes.editar");

  // substituição é ajuste operacional: vale no horário publicado do semestre (ou na versão aberta, se ainda não houver)
  const alvo = useMemo(() => {
    const sem = semestreDe(cenario);
    return cenarios.find((c) => c.estado === "publicado" && c.tipo !== "simulacao" && semestreDe(c) === sem) || cenario;
  }, [cenarios, cenario]);
  useEffect(() => { setMarcadas(new Set()); }, [instrutorId, inicio, fim, alvo?.id]);
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
  const chave = (b: any) => b.ids.join(",");
  const livres = blocos.filter((b) => b.situacao === "programada" && !b.substituto);
  const porDia = useMemo(() => {
    const m = new Map<string, any[]>();
    for (const b of blocos) m.set(b.data, [...(m.get(b.data) || []), b]);
    return [...m.entries()];
  }, [blocos]);
  const escolhidas = livres.filter((b) => marcadas.has(chave(b)));
  const ids = escolhidas.flatMap((b) => b.ids);
  const alternar = (b: any) => setMarcadas((s) => { const n = new Set(s); n.has(chave(b)) ? n.delete(chave(b)) : n.add(chave(b)); return n; });
  const marcarDia = (xs: any[]) => setMarcadas((s) => {
    const n = new Set(s); const ks = xs.filter((b) => livres.includes(b)).map(chave);
    const todos = ks.every((k) => n.has(k)); ks.forEach((k) => (todos ? n.delete(k) : n.add(k))); return n;
  });
  const horas = (min: number) => `${(min / 60).toFixed(1).replace(".", ",")} h`;
  const nome = aulas.dados?.instrutor?.nome || instrutores.find((i) => Number(i.id) === instrutorId)?.rotulo;

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
            <div><h3>{nome}</h3>
              <small className="mudo">{aulas.dados?.instrutor?.modalidade === "horista" ? "Horista" : "Mensalista"} · {dataBR(inicio)} a {dataBR(fim)} ·{" "}
                {blocos.length} aula(s) de turno · {horas(blocos.reduce((t, b) => t + b.minutos, 0))}</small></div>
            <button className="btn-link" onClick={() => setInstrutorId(null)}>Trocar instrutor</button>
          </div>
          {aulas.carregando && <p role="status">Carregando as aulas…</p>}
          {aulas.erro && <div className="erro-box">{aulas.erro}</div>}
          {aulas.dados && !blocos.length && <div className="cur-vazio">Nenhuma aula de {nome} neste período.</div>}
          {porDia.map(([dia, xs]) => {
            const d = new Date(`${dia}T12:00:00`);
            const selecionaveis = xs.filter((b) => livres.includes(b));
            return (
              <div key={dia} className="subs-dia">
                <div className="subs-dia-cab">
                  <span className="subs-data"><b>{DIAS[(d.getDay() + 6) % 7]}</b> {dataBR(dia).slice(0, 5)}</span>
                  {podeEditar && selecionaveis.length > 1 && <button className="btn-link" onClick={() => marcarDia(xs)}>marcar o dia todo</button>}
                </div>
                {xs.map((b) => {
                  const pode_ = podeEditar && livres.includes(b);
                  return (
                    <label key={chave(b)} className={`subs-aula ${marcadas.has(chave(b)) ? "marcada" : ""} ${!pode_ ? "travada" : ""}`}>
                      <input type="checkbox" disabled={!pode_} checked={marcadas.has(chave(b))} onChange={() => alternar(b)} />
                      <span className="subs-hora">{b.inicio}–{b.fim}<small>{b.turno}</small></span>
                      <span className="subs-o-que"><span><b>{b.turma}</b> · {b.uc}{b.grupo ? ` (grupo ${b.grupo})` : ""}</span>
                        <small className="mudo">🏫 {b.sala || "sem sala"} · {b.aulas} aula(s)</small></span>
                      <span className="subs-sit">
                        {b.situacao === "realizada" ? <Badge tipo="neutro">realizada</Badge>
                          : b.substituto ? <Badge tipo="info">🔁 com {b.substituto}</Badge>
                            : b.substituindo ? <Badge tipo="alerta">substituindo {b.substituindo}</Badge>
                              : <Badge tipo="ok">programada</Badge>}
                      </span>
                    </label>);
                })}
              </div>);
          })}
        </section>}

        {instrutorId && podeEditar && escolhidas.length > 0 &&
          <IniciarSubstituicao key={ids.join(",")} cenarioId={alvo.id} ids={ids} titular={nome || ""} resumo={escolhidas}
            pronto={() => { setMarcadas(new Set()); setVersao((v) => v + 1); aviso("Substituição registrada. Os instrutores foram avisados no portal."); }} />}
        {instrutorId && podeEditar && blocos.length > 0 && !escolhidas.length &&
          <p className="sub">Marque as aulas que precisam de substituto (uma a uma ou o dia todo) para ver quem pode assumir.</p>}

        <SubstituicoesEmVigor cenarioId={alvo.id} podeEditar={podeEditar} versao={versao} mudou={() => setVersao((v) => v + 1)} />
      </>}
    </Pagina>
  );
}

/** Painel das aulas escolhidas: substitutos possíveis (pela disponibilidade no dia e no horário), motivo, conferência e confirmação. */
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
      <h3>🔁 Quem pode assumir <small className="mudo">— {resumo.length} aula(s) de {titular}: {resumo.slice(0, 4).map((b) => `${dataBR(b.data).slice(0, 5)} ${b.turma}`).join(", ")}{resumo.length > 4 ? "…" : ""}</small></h3>
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
