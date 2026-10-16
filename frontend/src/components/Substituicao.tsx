import { useState } from "react";
import { api, dataBR, qs } from "../api";
import { useApp } from "../contexto";
import { useOpcoes } from "../hooks";
import { Sugestao } from "./Sugestao";
import { Badge, Campo, Erro, Modal, useCarregar } from "./ui";

export const ESTADOS_SUBSTITUICAO = ["em_elaboracao", "em_validacao", "aguardando_aprovacao", "aprovado", "publicado"];
const GRUPOS: [string, string, string][] = [
  ["recomendado", "Livres, da área e com a UC", "ok"],
  ["excecao", "Livres, mas de outra área ou sem a UC cadastrada (fica registrado como exceção)", "alerta"],
  ["parcial", "Livres só em parte dos dias", "info"],
  ["indisponivel", "Não podem (já têm aula, fora da jornada, turno vazio sem antecedência…)", "bloqueio"],
];

type Aula = { id: number; data: string; inicio: string; fim: string; turma: string; uc: string; instrutor_id: number | null; instrutor: string | null; turma_uc_id: number };

/** Substituição de instrutor por imprevisto: uma aula ou todas as aulas de um instrutor num período. */
export default function Substituicao({ cenarioId, publicado, aula, fechar }: { cenarioId: number; publicado: boolean; aula?: Aula | null; fechar: (ok: boolean) => void }) {
  const { aviso } = useApp();
  const instrutores = useOpcoes("instrutores");
  const [escopo, setEscopo] = useState(aula ? "aula" : "periodo");
  const [ausente, setAusente] = useState<string>(aula?.instrutor_id ? String(aula.instrutor_id) : "");
  const [inicio, setInicio] = useState(aula?.data || "");
  const [fim, setFim] = useState(aula?.data || "");
  const [soTurma, setSoTurma] = useState(false);
  const [sub, setSub] = useState<number | null>(null);
  const [motivo, setMotivo] = useState("");
  const [previa, setPrevia] = useState<any>(null);
  const [erro, setErro] = useState<any>(null);
  const [verTodos, setVerTodos] = useState(false);
  const alvo = escopo === "aula" && aula ? { cenario_id: cenarioId, alocacao_id: aula.id }
    : { cenario_id: cenarioId, instrutor_id: ausente, inicio, fim: fim || inicio, turma_uc_id: soTurma && aula ? aula.turma_uc_id : undefined };
  const pronto = escopo === "aula" ? !!aula : !!(ausente && inicio);
  const cand = useCarregar<any>(() => pronto ? api.get(`/api/substituicoes/candidatos${qs(alvo)}`) : Promise.resolve(null),
    [escopo, ausente, inicio, fim, soTurma, pronto]);
  const enviar = async (somente: boolean) => {
    setErro(null);
    try {
      const r = await api.post("/api/substituicoes", { ...alvo, substituto_id: sub, motivo, somente_validar: somente });
      if (somente) { setPrevia(r); return; }
      aviso(`${r.substituidas} aula(s) substituída(s).${r.falhas.length ? ` ${r.falhas.length} não puderam ser trocadas.` : ""} Os instrutores foram avisados no portal.`);
      fechar(true);
    } catch (e) { setErro(e); }
  };
  const lista: any[] = cand.dados?.instrutores || [];
  const melhor = lista.find((i) => i.grupo === "recomendado") || lista.find((i) => i.grupo === "excecao");
  const escolhido = lista.find((i) => i.id === sub) || (sub ? { nome: instrutores.find((i) => Number(i.id) === sub)?.rotulo } : null);
  const SITUACAO: Record<string, string> = { recomendado: "✓ livre, da área", excecao: "⚠ livre, outra área/sem a UC", parcial: "◐ livre só em parte", indisponivel: "✗ não pode" };
  const situacao = (id: number) => { const c = lista.find((i) => i.id === id); return c ? ` — ${c.na_escola ? "📍 " : ""}${SITUACAO[c.grupo]}` : ""; };
  const titularId = escopo === "aula" ? aula?.instrutor_id : Number(ausente) || null;
  const campoSubstituto = (
    <Campo rotulo="Instrutor substituto" obrigatorio ajuda={pronto ? "A situação de cada um na(s) aula(s) aparece ao lado do nome; as sugestões estão logo abaixo." : undefined}>
      <select aria-label="Instrutor substituto" value={sub ?? ""} onChange={(e) => { setSub(e.target.value ? Number(e.target.value) : null); setPrevia(null); }}>
        <option value="">— escolha quem vai assumir —</option>
        {instrutores.filter((i) => Number(i.id) !== titularId).map((i) => <option key={i.id} value={i.id}>{i.rotulo}{situacao(Number(i.id))}</option>)}
      </select>
    </Campo>);
  return (
    <Modal titulo="🔁 Substituir instrutor" aberto fechar={() => fechar(false)} largo>
      <p className="sub">Para imprevistos (falta, afastamento, ninguém da área disponível). O substituto pode ser de outra área ou não ter a UC cadastrada:
        isso fica registrado com o motivo. Escolha o substituto direto no campo ou pelas sugestões; se ele já tiver aula no mesmo horário,
        o botão Conferir mostra quais aulas não podem ser trocadas. A aula fica fixa e pode ser desfeita depois.</p>
      <ul className="sub-regras">
        <li><b>📍 Em PL ou PJ</b> no horário: está na escola e pode assumir <b>até no mesmo dia</b>. O PL/PJ daquele turno vira a aula.</li>
        <li><b>🎓 Em TR (treinamento)</b>: está liberado das aulas e não entra como substituto naquele turno.</li>
        <li><b>🏠 Turno vazio</b>: pode ser acionado, desde que a substituição seja planejada com <b>pelo menos 1 dia de antecedência</b>.</li>
      </ul>
      {publicado && <p className="aviso-inline">⚠ Este horário já está <b>publicado</b>: a troca vale imediatamente e os instrutores recebem um aviso no portal.</p>}
      <div className="sub-escopo">
        {aula && <label><input type="radio" checked={escopo === "aula"} onChange={() => { setEscopo("aula"); setPrevia(null); }} />
          Só esta aula ({aula.turma} · {aula.uc}, {dataBR(aula.data)} {aula.inicio}–{aula.fim})</label>}
        <label><input type="radio" checked={escopo === "periodo"} onChange={() => { setEscopo("periodo"); setPrevia(null); }} /> Todas as aulas de um instrutor num período</label>
      </div>
      {escopo === "periodo" && <div className="form-grid">
        <Campo rotulo="Instrutor ausente" obrigatorio><select value={ausente} onChange={(e) => { setAusente(e.target.value); setSub(null); setPrevia(null); }}>
          <option value="">—</option>{instrutores.map((i) => <option key={i.id} value={i.id}>{i.rotulo}</option>)}</select></Campo>
        <Campo rotulo="De" obrigatorio><input type="date" value={inicio} onChange={(e) => { setInicio(e.target.value); if (!fim || fim < e.target.value) setFim(e.target.value); setPrevia(null); }} /></Campo>
        <Campo rotulo="Até"><input type="date" value={fim} min={inicio} onChange={(e) => { setFim(e.target.value); setPrevia(null); }} /></Campo>
        {campoSubstituto}
        {aula && <Campo rotulo="Turma"><label><input type="checkbox" checked={soTurma} onChange={(e) => { setSoTurma(e.target.checked); setPrevia(null); }} /> Só {aula.turma} · {aula.uc}</label></Campo>}
      </div>}
      {escopo === "aula" && <div className="form-grid">{campoSubstituto}</div>}

      {pronto && <fieldset className="painel-campo">
        <legend>Sugestões: quem pode assumir {cand.dados ? <small>({cand.dados.aulas} aula(s) em {cand.dados.dias} dia(s){cand.dados.dias > cand.dados.dias_avaliados ? `; avaliados os primeiros ${cand.dados.dias_avaliados} dias` : ""})</small> : null}</legend>
        {cand.carregando && <p role="status">Verificando a agenda de cada instrutor…</p>}
        {cand.erro && <div className="erro-box">{cand.erro}</div>}
        {cand.dados && cand.dados.aulas === 0 && <p className="sub">Nenhuma aula desse instrutor no período escolhido.</p>}
        {cand.dados && cand.dados.aulas > 0 && GRUPOS.map(([g, titulo, tom]) => {
          const xs = lista.filter((i) => i.grupo === g);
          if (!xs.length || (g === "indisponivel" && !verTodos)) return null;
          return <div key={g} className="sub-grupo"><Badge tipo={tom}>{titulo}</Badge>
            {xs.map((i) => (
              <label key={i.id} className={`sub-cand ${sub === i.id ? "marcada" : ""} ${g === "indisponivel" ? "desabilitado" : ""}`}>
                <input type="radio" name="substituto" checked={sub === i.id} onChange={() => { setSub(i.id); setPrevia(null); }} />
                <span><b>{i.nome}</b> {presenca(i)} <small className="mudo">{i.area || "sem área"}{i.ministra_uc ? " · ministra a UC" : ""}{i.outra_unidade ? " · outra unidade" : ""}
                  {g === "parcial" ? ` · livre em ${i.dias_livres} de ${i.dias_avaliados} dias` : ""}</small>
                  {i.motivos.length > 0 && <small className="sub-motivos">{i.motivos.join(" · ")}</small>}</span>
              </label>))}
          </div>;
        })}
        {cand.dados && lista.some((i) => i.grupo === "indisponivel") && <button className="btn-link" onClick={() => setVerTodos(!verTodos)}>
          {verTodos ? "Ocultar" : "Mostrar"} os sem horário ({lista.filter((i) => i.grupo === "indisponivel").length})</button>}
      </fieldset>}

      <Campo rotulo="Motivo da substituição" obrigatorio ajuda="Fica registrado na aula, no histórico e no aviso aos instrutores.">
        <textarea rows={2} value={motivo} placeholder="Ex.: falta do titular por motivo de saúde; ninguém de Energias livre neste turno." onChange={(e) => { setMotivo(e.target.value); setPrevia(null); }} /></Campo>

      {melhor && cand.dados?.aulas > 0 && <Sugestao
        texto={<><b>{melhor.nome}</b> assume {cand.dados.aulas > 1 ? `as ${cand.dados.aulas} aulas` : "a aula"}{melhor.na_escola ? " (está na escola: PL/PJ)" : ""}</>}
        detalhe={melhor.grupo === "recomendado" ? "Livre em todas as aulas, da área e com a UC." : "Livre, mas de outra área ou sem a UC: fica registrado como exceção com o motivo."}
        rotulo="Aceitar e substituir" desabilitada={motivo.trim().length < 10}
        aplicar={async () => {
          if (motivo.trim().length < 10) throw new Error("Escreva o motivo da substituição (mínimo de 10 caracteres).");
          const r = await api.post("/api/substituicoes", { ...alvo, substituto_id: melhor.id, motivo });
          aviso(`${r.substituidas} aula(s) substituída(s)${r.falhas.length ? `; ${r.falhas.length} não puderam` : ""}.`);
          fechar(true); return r;
        }} />}
      {melhor && cand.dados?.aulas > 0 && motivo.trim().length < 10 && <small className="mudo">Para aceitar a sugestão, escreva o motivo abaixo.</small>}
      {previa && <div className={`previa-sub ${previa.falhas.length ? "tom-alerta" : "tom-ok"}`}>
        <b>{previa.possiveis} aula(s) podem ser trocadas para {escolhido?.nome}.</b>
        {[...new Set<string>(previa.aulas.flatMap((a: any) => a.avisos))].slice(0, 4).map((x) => <div key={x}><small>{x}</small></div>)}
        {previa.falhas.length > 0 && <ul>{previa.falhas.map((f: any) => <li key={f.alocacao_id}>{dataBR(f.data)} {f.horario}: {f.motivos.join("; ")}</li>)}</ul>}
      </div>}
      <Erro erro={erro} />
      <div className="rodape-modal">
        <button className="btn" onClick={() => fechar(false)}>Cancelar</button>
        <button className="btn" disabled={!sub || motivo.trim().length < 10} onClick={() => enviar(true)}>Conferir</button>
        <button className="btn btn-primario" disabled={!sub || motivo.trim().length < 10 || !previa || previa.possiveis === 0} onClick={() => enviar(false)}>Confirmar substituição</button>
      </div>
    </Modal>
  );
}

function presenca(i: { presenca?: string[]; na_escola?: boolean }) {
  if (!i.presenca?.length) return null;
  if (i.na_escola) return <span className="tag-presenca na-escola" title="Em planejamento/projeto no horário: está na escola">📍 em {i.presenca.join("/")} – na escola</span>;
  const reservas = i.presenca.filter((p) => p !== "vazio");
  return <span className="tag-presenca vazio" title="Turno vazio: acionar com pelo menos 1 dia de antecedência">
    {reservas.length ? `📍 ${reservas.join("/")} em parte dos dias · 🏠 vazio nos demais` : "🏠 turno vazio"} – acionar com antecedência</span>;
}

/** Substituições em vigor no semestre, com opção de desfazer. */
export function SubstituicoesEmVigor({ cenarioId, podeEditar, versao, mudou }: { cenarioId: number; podeEditar: boolean; versao: number; mudou: () => void }) {
  const { aviso } = useApp();
  const r = useCarregar<any[]>(() => api.get(`/api/substituicoes?cenario_id=${cenarioId}`), [cenarioId, versao]);
  if (!r.dados?.length) return null;
  return (
    <details className="sub-vigor">
      <summary>🔁 Substituições em vigor ({r.dados.length})</summary>
      <ul>{r.dados.map((g, i) => (
        <li key={i}><b>{g.substituto}</b> no lugar de <b>{g.titular}</b> · {g.turma} · {g.uc} · {g.datas.map((d: string) => dataBR(d).slice(0, 5)).join(", ")}
          {g.motivo && <small className="mudo"> — {g.motivo}</small>}
          {podeEditar && <button className="btn-link" onClick={async () => {
            if (!confirm(`Devolver estas aulas para ${g.titular}?`)) return;
            try {
              const x = await api.post("/api/substituicoes/desfazer", { alocacao_ids: g.alocacao_ids, motivo: "substituição desfeita" });
              aviso(`${x.desfeitas} aula(s) devolvida(s) para ${g.titular}.${x.falhas.length ? ` ${x.falhas.length} não (o titular já tem outra aula no horário).` : ""}`);
              r.recarregar(); mudou();
            } catch (e: any) { aviso(e.message, "erro"); }
          }}>Desfazer</button>}
        </li>))}</ul>
    </details>
  );
}
