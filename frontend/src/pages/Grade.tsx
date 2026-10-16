import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { addDias, api, baixar, dataBR, DIAS_CURTOS, iso, qs, segundaDe } from "../api";
import { Alternativas, Badge, Campo, Erro, Modal, OcorrenciasLista, Pagina, Selecao, Tabela, useCarregar } from "../components/ui";
import { AvisoSomenteLeitura } from "../components/AvisoSomenteLeitura";
import { useApp } from "../contexto";
import Substituicao, { ESTADOS_SUBSTITUICAO, SubstituicoesEmVigor } from "../components/Substituicao";
import AgendaInstrutor from "../components/AgendaInstrutor";
import { useOpcoes } from "../hooks";
import { Diferenca } from "./Cadastro";

type Aula = { turno_id?: number; unidade_id?: number; id: number; versao: number; data: string; inicio: string; fim: string; turma_id: number; turma: string; turma_uc_id: number; uc: string;
  uc_nome: string; grupo: number | null; instrutor_id: number | null; instrutor: string | null; instrutor_titular?: string | null; instrutor_titular_id?: number | null; ambiente_id: number | null; ambiente: string | null;
  fixa: boolean; origem: string; observacao: string | null; status: string; minutos_aula: number };
type Periodo = { id: number; turno_id: number; turno: string; turno_codigo?: string; ordem: number; inicio: string; fim: string; dias_semana: number[]; excepcional: boolean };

const MODOS = [{ id: "turma", rotulo: "Por turma" }, { id: "instrutor", rotulo: "Por instrutor" }, { id: "ambiente", rotulo: "Por ambiente" },
  { id: "turno", rotulo: "Por turno" }, { id: "curso", rotulo: "Por curso" }];
const ENT: Record<string, string> = { turma: "turmas", instrutor: "instrutores", ambiente: "ambientes", turno: "turnos", curso: "cursos", unidade: "unidades" };

function corDe(id: number) {
  return `hsl(${(id * 67) % 360} 55% var(--cor-l))`;
}

export default function Grade() {
  const { cenario, pode, aviso, unidade: unidadeTopo, setUnidade: setUnidadeTopo } = useApp();
  const [sp, setSp] = useSearchParams();
  const modoInicial = MODOS.find((m) => sp.get(m.id))?.id || "turma";
  const [modo, setModo] = useState(modoInicial);
  const [alvo, setAlvo] = useState<string>(sp.get(modoInicial) || "");
  const [q, setQ] = useState("");
  const [semana, setSemana] = useState<Date>(() => segundaDe(cenario?.periodo_inicio ? new Date(cenario.periodo_inicio + "T12:00") : new Date()));
  // a grade sempre mostra uma unidade: a do filtro do topo (se houver) ou a última usada aqui
  const [unidade, setUnidadeEstado] = useState<string>(() => { try { return unidadeTopo || localStorage.getItem("grade_unidade") || ""; } catch { return unidadeTopo; } });
  const setUnidade = (u: string) => {
    setUnidadeEstado(u);
    try { localStorage.setItem("grade_unidade", u); } catch { /* sem armazenamento */ }
    if (unidadeTopo && u !== unidadeTopo) setUnidadeTopo(u);  // com filtro no topo, trocar aqui troca o filtro também
  };
  const [mostrarLivres, setMostrarLivres] = useState(false);
  const [form, setForm] = useState<any | null>(null);
  const [aulaSel, setAulaSel] = useState<Aula | null>(null);
  const [copiar, setCopiar] = useState(false);
  const [substituir, setSubstituir] = useState<{ aula: Aula | null } | null>(null);
  const [versaoSub, setVersaoSub] = useState(0);
  const [soltar, setSoltar] = useState("");
  const unidades = useOpcoes("unidades");
  const todasOpcoes = useOpcoes(ENT[modo]) as any[];
  // as listas de turma, instrutor, sala, turno e curso mostram só o que é da unidade escolhida
  const opsAlvo = todasOpcoes.filter((o) => !unidade || o.unidade_id == null || String(o.unidade_id) === unidade);
  useEffect(() => { if (cenario?.periodo_inicio) setSemana(segundaDe(new Date(cenario.periodo_inicio + "T12:00"))); }, [cenario?.id]);
  // unidade inicial: a do semestre; senão a última usada; senão a primeira
  useEffect(() => {
    if (!unidades.length) return;
    const doCenario = (cenario as any)?.unidade_id ? String((cenario as any).unidade_id) : "";
    const valida = (u: string) => unidades.some((x) => String(x.id) === u);
    const escolhida = (valida(unidadeTopo) ? unidadeTopo : "") || doCenario || (valida(unidade) ? unidade : String(unidades[0].id));
    if (escolhida !== unidade) setUnidade(escolhida);
  }, [unidades, cenario?.id]);
  // escolheu (ou abriu pelo link) uma turma/instrutor/sala de outra unidade: muda a unidade junto
  useEffect(() => {
    if (!alvo) return;
    const o = todasOpcoes.find((x) => String(x.id) === String(alvo));
    if (o?.unidade_id && String(o.unidade_id) !== unidade) setUnidade(String(o.unidade_id));
  }, [alvo, todasOpcoes]);
  const trocarUnidade = (u: string) => {
    if (u === unidade) return;
    const o = todasOpcoes.find((x) => String(x.id) === String(alvo));
    if (alvo && o?.unidade_id && String(o.unidade_id) !== u) { setAlvo(""); setSp({}); }
    setUnidade(u);
  };

  const fimSemana = addDias(semana, 6);
  const filtro: any = { cenario_id: cenario?.id, inicio: iso(semana), fim: iso(fimSemana), q, unidade_id: unidade };
  if (alvo) filtro[`${modo}_id`] = alvo;
  const aulas = useCarregar<Aula[]>(() => cenario && unidade ? api.get(`/api/grade${qs(filtro)}`) : Promise.resolve([]), [cenario?.id, modo, alvo, iso(semana), q, unidade]);
  // aulas da semana em cada unidade (para os botões de unidade)
  const contagem = useCarregar<Record<string, number>>(async () => {
    if (!cenario) return {};
    const r: Record<string, number> = {};
    await Promise.all(unidades.map(async (u) => {
      r[u.id] = (await api.get(`/api/grade${qs({ cenario_id: cenario.id, inicio: iso(semana), fim: iso(fimSemana), unidade_id: u.id })}`, { semUnidade: true })).length;
    }));
    return r;
  }, [cenario?.id, iso(semana), unidades.length, versaoSub]);
  const periodos = useCarregar<Periodo[]>(() => unidade ? api.get(`/api/periodos?unidade_id=${unidade}`) : Promise.resolve([]), [unidade]);
  const livres = useCarregar<any[]>(() => cenario && mostrarLivres && alvo && ["turma", "instrutor", "ambiente"].includes(modo)
    ? api.get(`/api/grade/livres${qs({ cenario_id: cenario.id, semana: iso(semana), [`${modo}_id`]: alvo, unidade_id: unidade })}`) : Promise.resolve([]),
    [cenario?.id, mostrarLivres, modo, alvo, iso(semana), unidade]);
  const editavel = pode("alocacoes.editar") && cenario && ["em_elaboracao", "em_validacao"].includes(cenario.estado);
  // substituição de instrutor por imprevisto: vale também com o horário aprovado ou publicado
  const podeSubstituir = pode("alocacoes.editar") && cenario && ESTADOS_SUBSTITUICAO.includes(cenario.estado);

  // turnos especiais (sábado e integral das turmas PFP) só aparecem quando há aula neles ou a turma/turno escolhido é deles
  const linhas = useMemo(() => {
    const comAula = new Set((aulas.dados || []).map((a) => String(a.turno_id)));
    const turmaAlvo = modo === "turma" && alvo ? (todasOpcoes.find((o: any) => String(o.id) === alvo) as any)?.turno_id : null;
    // PFP (manhã e tarde) não tem linhas próprias: as aulas dela caem nas linhas da manhã e da tarde
    return (periodos.dados || []).filter((p) => p.turno_codigo !== "I" && (p.turno_codigo !== "S" || comAula.has(String(p.turno_id))
      || String(turmaAlvo) === String(p.turno_id) || (modo === "turno" && alvo === String(p.turno_id))));
  }, [periodos.dados, aulas.dados, modo, alvo, todasOpcoes]);
  const dias = useMemo(() => {
    const ds = new Set<number>();
    linhas.forEach((p) => p.dias_semana.forEach((d) => ds.add(d)));
    return [...ds].sort();
  }, [linhas]);
  const porCelula = useMemo(() => {
    const m: Record<string, Aula[]> = {};
    (aulas.dados || []).forEach((a) => {
      const p = periodoDaAula(linhas, a);
      const k = `${a.data}|${p?.id ?? "fora"}`;
      (m[k] = m[k] || []).push(a);
    });
    return m;
  }, [aulas.dados, linhas]);
  // Aulas de várias aulas seguidas ocupam as linhas correspondentes (um único bloco por turno).
  const { span, coberta } = useMemo(() => {
    const span: Record<string, number> = {}, coberta = new Set<string>();
    for (const d of dias) {
      const data = iso(addDias(semana, d));
      linhas.forEach((p, i) => {
        const lista = porCelula[`${data}|${p.id}`] || [];
        if (!lista.length || coberta.has(`${data}|${i}`)) return;
        const fimMax = lista.reduce((m, a) => (a.fim > m ? a.fim : m), "");
        let n = 1;
        while (i + n < linhas.length && linhas[i + n].turno_id === p.turno_id && linhas[i + n].inicio < fimMax && !(porCelula[`${data}|${linhas[i + n].id}`] || []).length) {
          coberta.add(`${data}|${i + n}`); n++;
        }
        span[`${data}|${i}`] = n;
      });
    }
    return { span, coberta };
  }, [porCelula, linhas, dias, iso(semana)]);
  // Visão geral (sem turma/instrutor/sala filtrados): uma linha por turno, todas as aulas em cartões do mesmo tamanho.
  const visaoGeral = !alvo || modo === "turno" || modo === "curso";
  // dias EAD (turmas 80-20): etiqueta no turno da turma, nas visões por turma, turno e curso
  const [versaoEad, setVersaoEad] = useState(0);
  const turmasEad = useCarregar<any[]>(() => api.get("/api/cadastros/turmas/opcoes?limite=2000").catch(() => []), [versaoEad, unidade]);
  const eadNoDia = (d: number, data: string, turnoId: any) => !["turma", "turno", "curso"].includes(modo) ? [] : (turmasEad.dados || []).filter((t) =>
    (t.dias_ead || []).includes(d) && String(t.turno_id) === String(turnoId) && t.data_inicio <= data && data <= t.data_fim &&
    (!unidade || String(t.unidade_id) === unidade) && (!alvo || (modo === "turma" ? String(t.id) === alvo : modo === "turno" ? String(t.turno_id) === alvo : String(t.curso_id) === alvo)));
  const tagEad = (lista: any[]) => lista.length > 0 && <div className="tags-ead">{lista.map((t) => (
    <span key={t.id} className="tag-ead" title={`${t.rotulo}: dia de atividades a distância (turma 80-20), sem aula presencial`}>
      EAD{modo !== "turma" || !alvo ? ` · ${String(t.rotulo).split(" – ")[0]}` : " · atividades a distância"}</span>))}</div>;
  const turmaSel = modo === "turma" && alvo ? (turmasEad.dados || []).find((t) => String(t.id) === alvo) : null;
  const alternarEad = async () => {
    if (!turmaSel) return;
    const sextaEad = (turmaSel.dias_ead || []).includes(4);
    const novo = sextaEad ? (turmaSel.dias_ead || []).filter((x: number) => x !== 4) : [...(turmaSel.dias_ead || []), 4];
    if (!confirm(sextaEad ? `Desmarcar a sexta como EAD na ${String(turmaSel.rotulo).split(" – ")[0]}? A sexta volta a ser dia de aula presencial.`
      : `Marcar a sexta como EAD na ${String(turmaSel.rotulo).split(" – ")[0]} (turma 80-20)? A sexta deixa de ser dia de aula presencial; aulas já marcadas nas sextas passam a acusar conflito na validação.`)) return;
    try { await api.put(`/api/cadastros/turmas/${turmaSel.id}`, { dias_ead: novo }); aviso(sextaEad ? "Sexta voltou a ser presencial." : "Sexta marcada como EAD."); setVersaoEad((v) => v + 1); aulas.recarregar(); }
    catch (e: any) { aviso(e?.message || String(e), "erro"); }
  };
  const turnosLinhas = useMemo(() => {
    const m = new Map<number, { turno_id: number; turno: string; inicio: string; fim: string; primeiro: Periodo; dias: Set<number> }>();
    for (const p of linhas) {
      const t = m.get(p.turno_id);
      if (!t) m.set(p.turno_id, { turno_id: p.turno_id, turno: p.turno, inicio: p.inicio, fim: p.fim, primeiro: p, dias: new Set(p.dias_semana) });
      else { t.fim = p.fim > t.fim ? p.fim : t.fim; p.dias_semana.forEach((d) => t.dias.add(d)); }
    }
    const todos = [...m.values()];
    // filtro "Por turno": mostra só a linha do turno escolhido
    return modo === "turno" && alvo ? todos.filter((t) => String(t.turno_id) === String(alvo)) : todos;
  }, [linhas, modo, alvo]);
  const porTurnoDia = useMemo(() => {
    const m: Record<string, Aula[]> = {};
    (aulas.dados || []).forEach((a) => {
      const p = periodoDaAula(linhas, a);
      const k = `${a.data}|${p?.turno_id ?? "fora"}`;
      (m[k] = m[k] || []).push(a);
    });
    Object.values(m).forEach((l) => l.sort((x, y) => x.turma.localeCompare(y.turma) || x.inicio.localeCompare(y.inicio)));
    return m;
  }, [aulas.dados, linhas]);
  // cartão da aula: <div role="button"> porque alguns navegadores (Firefox) não deixam arrastar <button>
  const cartao = (a: Aula) => (
    <div key={a.id} role="button" tabIndex={0} className="aula" style={{ ["--cor" as any]: corDe(a.turma_uc_id) }} draggable={!!editavel && !a.fixa}
      onDragStart={(e) => { e.dataTransfer.setData("text/aula", String(a.id)); e.dataTransfer.effectAllowed = "move"; }}
      onDragEnd={() => setSoltar("")} onClick={() => setAulaSel(a)}
      onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); setAulaSel(a); } }}
      title={`${a.turma} · ${a.uc} ${a.uc_nome} · ${a.instrutor || "sem instrutor"}${a.instrutor_titular ? ` (substituindo ${a.instrutor_titular})` : ""} · ${a.ambiente || "sem ambiente"}`}>
      <b>{a.turma}{a.grupo ? ` G${a.grupo}` : ""}</b> {a.uc}<br />
      <small>{a.inicio}–{a.fim} · {a.instrutor_titular && <span title={`substituindo ${a.instrutor_titular}`}>🔁 </span>}{a.instrutor || <i>sem instrutor</i>} · {a.ambiente || <i>sem sala</i>}</small>
      {a.fixa && <span className="tag-fixa" aria-label="aula fixa"> 📌</span>}
    </div>
  );
  // célula que recebe a aula arrastada (destaque enquanto passa por cima)
  const alvoSoltar = (chave: string, data: string, p: Periodo) => editavel ? {
    onDragOver: (e: React.DragEvent) => { e.preventDefault(); e.dataTransfer.dropEffect = "move"; if (soltar !== chave) setSoltar(chave); },
    onDragLeave: (e: React.DragEvent) => { if (!(e.currentTarget as Node).contains(e.relatedTarget as Node)) setSoltar(""); },
    onDrop: (e: React.DragEvent) => { e.preventDefault(); setSoltar(""); const id = Number(e.dataTransfer.getData("text/aula")); if (id) mover(id, data, p); },
  } : {};
  const continuacao = (data: string, p: Periodo) => (aulas.dados || []).some((a) => a.data === data && a.inicio < p.inicio && a.fim > p.inicio
    && (a.turno_id == null || String(a.turno_id) === String(p.turno_id)));
  const livre = (data: string, p: Periodo) => (livres.dados || []).some((l) => l.data === data && l.periodo_id === p.id);

  const mover = async (aulaId: number, data: string, p: Periodo) => {
    const a = (aulas.dados || []).find((x) => x.id === aulaId);
    if (!a) return;
    // mantém a mesma quantidade de aulas (períodos) que a aula ocupava
    const n = Math.max(1, linhas.filter((x) => x.inicio >= a.inicio && x.fim <= a.fim).length);
    try {
      await api.put(`/api/alocacoes/${a.id}`, { versao: a.versao, data, periodo_inicio_id: p.id, num_periodos: n, motivo: "arrastar e soltar" });
      aviso("Aula movida.");
    } catch (e: any) {
      setForm({ __erro: e, turma_uc_id: a.turma_uc_id, turma_id: a.turma_id, data, periodo_inicio_id: p.id, num_periodos: n, instrutor_id: a.instrutor_id,
        ambiente_id: a.ambiente_id, grupo: a.grupo, alocacao_id: a.id, versao: a.versao });
    }
    aulas.recarregar();
  };

  if (!cenario) return <Pagina titulo="Grade horária"><p>Escolha ou crie o semestre no topo da página.</p></Pagina>;
  return (
    <Pagina titulo="Grade horária" descricao="Todas as formas de alocação (formulário, arrastar e soltar, cópia, importação e gerador) usam o mesmo serviço central de validação."
      acoes={<>
        {editavel && <button className="btn btn-primario" onClick={() => setForm({ data: iso(semana), turma_id: modo === "turma" ? alvo : "" })}>+ Nova aula</button>}
        {editavel && modo === "turma" && alvo && <button className="btn" onClick={() => setCopiar(true)}>Copiar semana</button>}
        {turmaSel && pode("cadastros.editar") && !linhas.some((p) => p.turno_id === turmaSel.turno_id && !p.dias_semana.some((x) => x < 5)) && <button className="btn" onClick={alternarEad} title="Turmas 80-20: a sexta fica para atividades a distância">
          {(turmaSel.dias_ead || []).includes(4) ? "Sexta EAD ✓ (desmarcar)" : "Marcar sexta como EAD"}</button>}
        {podeSubstituir && <button className="btn" onClick={() => setSubstituir({ aula: null })}>🔁 Substituir instrutor</button>}
        {pode("exportacao.executar") && <button className="btn" onClick={() => baixar(`/api/exportar/grade${qs({ cenario_id: cenario.id, formato: "pdf", semana: iso(semana),
          filtro: alvo && ["turma", "instrutor", "ambiente", "turno"].includes(modo) ? modo : "", filtro_id: alvo })}`, "grade_semana.pdf")}>PDF da semana</button>}
      </>}>
      {!editavel && <AvisoSomenteLeitura />}
      <SubstituicoesEmVigor cenarioId={cenario.id} podeEditar={!!podeSubstituir} versao={versaoSub} mudou={() => aulas.recarregar()} />
      {!unidadeTopo && <div className="seletor-unidade" role="group" aria-label="Unidade">
        {unidades.map((u) => (
          <button key={u.id} className={String(u.id) === unidade ? "ativo" : ""} aria-pressed={String(u.id) === unidade} onClick={() => trocarUnidade(String(u.id))}>
            🏫 {u.rotulo}{contagem.dados && <small> · {contagem.dados[u.id] ?? 0} aula(s) na semana</small>}
          </button>))}
      </div>}
      <div className="filtros">
        <select aria-label="Visualização" value={modo} onChange={(e) => { setModo(e.target.value); setAlvo(""); setSp({}); setMostrarLivres(false); }}>
          {MODOS.map((m) => <option key={m.id} value={m.id}>{m.rotulo}</option>)}
        </select>
        <Selecao rotulo="Filtrar" valor={alvo} mudar={setAlvo} opcoes={opsAlvo} vazio="(todos)" />
        <input type="search" aria-label="Pesquisa rápida" placeholder="Pesquisa rápida" value={q} onChange={(e) => setQ(e.target.value)} />
        <button className="btn" aria-label="Semana anterior" onClick={() => setSemana(addDias(semana, -7))}>‹</button>
        <input type="date" aria-label="Semana" value={iso(semana)} onChange={(e) => e.target.value && setSemana(segundaDe(new Date(e.target.value + "T12:00")))} />
        <button className="btn" aria-label="Próxima semana" onClick={() => setSemana(addDias(semana, 7))}>›</button>
        {["turma", "instrutor", "ambiente"].includes(modo) && <label><input type="checkbox" checked={mostrarLivres} disabled={!alvo} onChange={(e) => setMostrarLivres(e.target.checked)} /> Destacar horários livres</label>}
      </div>
      <p className="sub">Semana de {dataBR(iso(semana))} a {dataBR(iso(fimSemana))} · {aulas.dados?.length ?? 0} aula(s)</p>
      {(() => {
        const foraDoPeriodo = cenario.periodo_inicio && (iso(fimSemana) < cenario.periodo_inicio || (cenario.periodo_fim && iso(semana) > cenario.periodo_fim));
        return <>
          {foraDoPeriodo && <p className="aviso-inline">Esta semana está fora do período do semestre ({dataBR(cenario.periodo_inicio)} a {dataBR(cenario.periodo_fim)}).{" "}
            <button className="btn-link" onClick={() => setSemana(segundaDe(new Date(cenario.periodo_inicio + "T12:00")))}>Ir para a primeira semana</button></p>}
        </>;
      })()}
      {aulas.erro && <div className="erro-box">{aulas.erro}</div>}
      <div className="grade-wrap">
        {visaoGeral ? (
          <table className="grade grade-geral">
            <thead><tr><th>Turno</th>{dias.map((d) => <th key={d}>{DIAS_CURTOS[d]} {dataBR(iso(addDias(semana, d))).slice(0, 5)}</th>)}</tr></thead>
            <tbody>
              {turnosLinhas.map((t) => (
                <tr key={t.turno_id}>
                  <th className="periodo"><span>{t.turno}</span>{t.inicio}–{t.fim}</th>
                  {dias.map((d) => {
                    const data = iso(addDias(semana, d));
                    const lista = t.dias.has(d) ? porTurnoDia[`${data}|${t.turno_id}`] || [] : [];
                    return (
                      <td key={d} className={`${!t.dias.has(d) ? "indisp" : ""} ${soltar === `${data}|t${t.turno_id}` ? "soltar" : ""}`}
                          {...alvoSoltar(`${data}|t${t.turno_id}`, data, t.primeiro)}
                          onDoubleClick={() => editavel && setForm({ data, periodo_inicio_id: t.primeiro.id, turma_id: modo === "turma" ? alvo : "" })}>
                        {tagEad(eadNoDia(d, data, t.turno_id))}
                        <div className="aulas-turno">{lista.map(cartao)}</div>
                        {lista.length === 0 && t.dias.has(d) && <span className="sr">sem aulas</span>}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
        <table className="grade">
            <thead><tr><th>Período</th>{dias.map((d) => <th key={d}>{DIAS_CURTOS[d]} {dataBR(iso(addDias(semana, d))).slice(0, 5)}</th>)}</tr></thead>
            <tbody>
              {linhas.map((p, i) => (
                <tr key={p.id} className={i > 0 && linhas[i - 1].turno_id !== p.turno_id ? "novo-turno" : ""}>
                  <th className="periodo"><span>{p.turno}</span>{p.ordem}º {p.inicio}–{p.fim}{p.excepcional && <Badge tipo="alerta">excepcional</Badge>}</th>
                  {dias.map((d) => {
                    const data = iso(addDias(semana, d));
                    if (coberta.has(`${data}|${i}`)) return null;
                    const n = span[`${data}|${i}`] || 1;
                    const lista = p.dias_semana.includes(d) ? porCelula[`${data}|${p.id}`] || [] : [];
                    const ehLivre = mostrarLivres && livre(data, p);
                    return (
                      <td key={d} rowSpan={n} style={n > 1 ? { ["--n" as any]: n } : undefined}
                          className={`${n > 1 ? "bloco" : ""} ${ehLivre ? "livre" : ""} ${!p.dias_semana.includes(d) ? "indisp" : ""} ${soltar === `${data}|${p.id}` ? "soltar" : ""}`}
                          {...alvoSoltar(`${data}|${p.id}`, data, p)}
                          onDoubleClick={() => editavel && setForm({ data, periodo_inicio_id: p.id, turma_id: modo === "turma" ? alvo : "", instrutor_id: modo === "instrutor" ? alvo : "", ambiente_id: modo === "ambiente" ? alvo : "" })}>
                        {(i === 0 || linhas[i - 1].turno_id !== p.turno_id) && tagEad(eadNoDia(d, data, p.turno_id))}
                        {lista.map(cartao)}
                        {lista.length === 0 && p.dias_semana.includes(d) && continuacao(data, p) && <span className="cont" aria-hidden="true">┆</span>}
                        {ehLivre && lista.length === 0 && <span className="sr">livre</span>}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {linhas.length === 0 && !periodos.carregando && <div className="vazio-grade">
          <p><b>A unidade selecionada ainda não tem horários de aula cadastrados</b>, por isso a grade não pode ser desenhada.</p>
          <p>Escolha outra unidade no seletor acima ou cadastre os turnos e os horários de cada aula em <Link to="/cadastros/turnos">Cadastros → Turnos e horários</Link>.</p>
        </div>}
      </div>
      {modo === "instrutor" && alvo && <AgendaInstrutor cenarioId={cenario.id} instrutorId={alvo} semana={iso(semana)} fimSemestre={cenario.periodo_fim}
        editavel={!!pode("alocacoes.editar")} versao={aulas.dados} />}
      {editavel
        ? <p className="sub">Dica: clique duas vezes em uma célula para alocar; arraste uma aula para outro dia ou turno para movê-la (a validação é refeita no servidor;
            se houver conflito, o formulário abre com o motivo). Aulas fixas (📌) não se movem. Área verde = livre para todos os recursos filtrados.</p>
        : <p className="sub">Esta versão está <b>{cenario.estado === "publicado" ? "publicada" : cenario.estado.replace(/_/g, " ")}</b>: a grade não pode ser editada
            direto aqui (nem arrastar aulas). Para mudar, use <b>Substituir instrutor</b> ou crie uma <b>proposta de alteração</b> em Semestres e aprovação.
            Legenda: 📌 fixa.</p>}
      {form && <FormAula inicial={form} cenarioId={cenario.id} unidadeId={unidade} periodos={linhas} fechar={(ok) => { setForm(null); if (ok) aulas.recarregar(); }} />}
      {aulaSel && <DetalheAula aula={aulaSel} editavel={!!editavel} substituir={podeSubstituir ? () => { const a = aulaSel; setAulaSel(null); setSubstituir({ aula: a }); } : undefined}
        fechar={(ok) => { setAulaSel(null); if (ok) { aulas.recarregar(); setVersaoSub((v) => v + 1); } }}
        editar={() => { const a = aulaSel; setAulaSel(null); setForm({ alocacao_id: a.id, versao: a.versao, turma_id: a.turma_id, turma_uc_id: a.turma_uc_id, grupo: a.grupo,
          instrutor_id: a.instrutor_id, ambiente_id: a.ambiente_id, data: a.data, hora_inicio: a.inicio, hora_fim: a.fim, fixa: a.fixa, observacao: a.observacao }); }} />}
      {substituir && <Substituicao cenarioId={cenario.id} publicado={cenario.estado === "publicado"} aula={substituir.aula}
        fechar={(ok) => { setSubstituir(null); if (ok) { aulas.recarregar(); setVersaoSub((v) => v + 1); } }} />}
      <Modal titulo="Copiar aulas da turma para outra semana" aberto={copiar} fechar={() => setCopiar(false)}>
        <CopiarSemana cenarioId={cenario.id} turmaId={alvo} origem={iso(semana)} fechar={(ok) => { setCopiar(false); if (ok) aulas.recarregar(); }} />
      </Modal>
    </Pagina>
  );
}

/** Linha da grade em que a aula começa. O limiar aceita até 45 min antes do 1º horário do turno, para as turmas PFP
 *  (manhã 08:00–12:00 cai na manhã; tarde 13:00–17:00 cai na tarde). */
function periodoDaAula(linhas: Periodo[], a: { inicio: string }) {
  return linhas.find((x) => x.inicio === a.inicio) || linhas.find((x) => x.inicio <= a.inicio && a.inicio < x.fim)
    || linhas.find((x) => x.inicio > a.inicio && minutos(x.inicio) - minutos(a.inicio) <= 45);
}

function minutos(h: string) {
  const [a, b] = h.split(":").map(Number);
  return a * 60 + b;
}

function CopiarSemana({ cenarioId, turmaId, origem, fechar }: { cenarioId: number; turmaId: string; origem: string; fechar: (ok: boolean) => void }) {
  const [destino, setDestino] = useState(iso(addDias(new Date(origem + "T12:00"), 7)));
  const [erro, setErro] = useState<any>(null);
  const { aviso } = useApp();
  return <>
    <p>Origem: semana de {dataBR(origem)}. Operação atômica: se qualquer aula violar uma restrição, nada é gravado.</p>
    <Campo rotulo="Semana de destino"><input type="date" value={destino} onChange={(e) => setDestino(e.target.value)} /></Campo>
    <Erro erro={erro} />
    <div className="rodape-modal"><button className="btn btn-primario" onClick={async () => {
      try { const r = await api.post("/api/alocacoes/copiar_semana", { cenario_id: cenarioId, turma_id: turmaId, semana_origem: origem, semana_destino: destino });
        aviso(`${r.aulas_criadas} aula(s) copiada(s).`); fechar(true); } catch (e) { setErro(e); }
    }}>Copiar</button></div>
  </>;
}

function DetalheAula({ aula, editavel, fechar, editar, substituir }: { aula: Aula; editavel: boolean; fechar: (ok: boolean) => void; editar: () => void; substituir?: () => void }) {
  const hist = useCarregar(() => api.get(`/api/alocacoes/${aula.id}/historico`), [aula.id]);
  const { aviso } = useApp();
  return (
    <Modal titulo={`${aula.turma} · ${aula.uc} – ${aula.uc_nome}`} aberto fechar={() => fechar(false)} largo>
      <dl className="dl">
        <dt>Data</dt><dd>{dataBR(aula.data)} {aula.inicio}–{aula.fim} ({(aula.minutos_aula / 60).toFixed(2)} h-aula)</dd>
        <dt>Grupo</dt><dd>{aula.grupo ? `Grupo ${aula.grupo}` : "Turma inteira"}</dd>
        <dt>Instrutor</dt><dd>{aula.instrutor || "pendente"}{aula.instrutor_titular && <> <Badge tipo="alerta">🔁 substituindo {aula.instrutor_titular}</Badge></>}</dd>
        <dt>Ambiente</dt><dd>{aula.ambiente || "pendente"}</dd>
        <dt>Origem</dt><dd>{aula.origem}{aula.fixa ? " · fixa (preservada pelo gerador)" : ""}</dd>
        <dt>Observação</dt><dd>{aula.observacao || "—"}</dd>
      </dl>
      {substituir && <div className="acoes">
        <button className="btn" onClick={substituir}>🔁 Substituir instrutor</button>
        {aula.instrutor_titular_id && <button className="btn" onClick={async () => {
          if (!confirm(`Devolver a aula para ${aula.instrutor_titular}?`)) return;
          try { const r = await api.post("/api/substituicoes/desfazer", { alocacao_ids: [aula.id] });
            if (r.desfeitas) { aviso("Aula devolvida ao titular."); fechar(true); } else aviso(r.falhas[0]?.motivos.join("; ") || "Não foi possível desfazer.", "erro"); }
          catch (e: any) { aviso(e.message, "erro"); }
        }}>Desfazer substituição</button>}
      </div>}
      {editavel && <div className="acoes">
        <button className="btn btn-primario" onClick={editar}>Editar</button>
        <button className="btn" onClick={async () => {
          try { await api.put(`/api/alocacoes/${aula.id}`, { versao: aula.versao, fixa: !aula.fixa, motivo: aula.fixa ? "liberada" : "fixada" }); aviso(aula.fixa ? "Aula liberada para o gerador." : "Aula fixada."); fechar(true); }
          catch (e: any) { aviso(e.message, "erro"); }
        }}>{aula.fixa ? "Desfixar" : "Fixar"}</button>
        <button className="btn btn-perigo" onClick={async () => {
          const motivo = prompt("Motivo da remoção:");
          if (motivo === null) return;
          try { await api.del(`/api/alocacoes/${aula.id}${qs({ versao: aula.versao, motivo })}`); aviso("Aula removida."); fechar(true); } catch (e: any) { aviso(e.message, "erro"); }
        }}>Remover</button>
      </div>}
      <h3>Histórico</h3>
      <Tabela colunas={[{ chave: "em", rotulo: "Quando", render: (h: any) => new Date(h.em).toLocaleString("pt-BR") }, { chave: "usuario", rotulo: "Usuário" },
        { chave: "acao", rotulo: "Ação" }, { chave: "motivo", rotulo: "Motivo" }, { chave: "d", rotulo: "Alterações", render: (h: any) => <Diferenca antes={h.antes} depois={h.depois} /> }]}
        linhas={hist.dados || []} chave={(_h, i) => i} />
    </Modal>
  );
}

export function FormAula({ inicial, cenarioId, unidadeId, periodos, fechar }: { inicial: any; cenarioId: number; unidadeId: string; periodos: Periodo[]; fechar: (ok: boolean) => void }) {
  const { aviso } = useApp();
  const [f, setF] = useState<any>({ num_periodos: 2, recursos: [], ...inicial });
  const [erro, setErro] = useState<any>(inicial.__erro || null);
  const [validacao, setValidacao] = useState<any[] | null>(null);
  const turmas = useOpcoes("turmas");
  const recursos = useOpcoes("recursos");
  const oferta = useCarregar<any[]>(() => f.turma_id ? api.get(`/api/planejamento/oferta${qs({ cenario_id: cenarioId, turma_id: f.turma_id })}`) : Promise.resolve([]), [f.turma_id]);
  const excecoes = useCarregar<any[]>(() => api.get("/api/excecoes"), []);
  const tuc = (oferta.dados || []).find((o) => String(o.turma_uc_id) === String(f.turma_uc_id));
  // sugestões avaliadas pela validação central para o horário escolhido
  const podeSugerir = f.turma_uc_id && f.data && f.periodo_inicio_id && f.num_periodos;
  const sug = useCarregar<any>(() => podeSugerir ? api.get(`/api/sugestoes/aula${qs({ cenario_id: cenarioId, turma_uc_id: f.turma_uc_id, data: f.data,
    periodo_inicio_id: f.periodo_inicio_id, num_periodos: f.num_periodos, grupo: f.grupo, alocacao_id: f.alocacao_id })}`) : Promise.resolve(null),
    [f.turma_uc_id, f.data, f.periodo_inicio_id, f.num_periodos, f.grupo]);
  const [justificativa, setJustificativa] = useState("");
  const instSel = sug.dados?.instrutores?.find((i: any) => String(i.id) === String(f.instrutor_id));
  const ambSel = sug.dados?.ambientes?.find((a: any) => String(a.id) === String(f.ambiente_id));
  const regrasErro: string[] = (erro?.detalhes?.ocorrencias || []).filter((o: any) => o.severidade === "bloqueio").map((o: any) => o.regra);
  const precisaExcecao = (instSel?.grupo === "excecao" || ambSel?.grupo === "excecao" ||
    (regrasErro.length > 0 && regrasErro.every((r) => EXCECIONAVEIS.includes(r)))) && !f.excecao_id;
  useEffect(() => { if (tuc && !inicial.num_periodos && !inicial.hora_inicio) setF((x: any) => ({ ...x, num_periodos: tuc.periodos_sugeridos || tuc.periodos_por_encontro || tuc.duracao_bloco_periodos || x.num_periodos })); }, [tuc?.turma_uc_id]);
  const set = (k: string, v: any) => setF((x: any) => ({ ...x, [k]: v }));
  const corpoBase = () => {
    const c: any = { ...f, cenario_id: cenarioId };
    if (c.periodo_inicio_id) { delete c.hora_inicio; delete c.hora_fim; }
    if (c.recorrente) { c.dia_semana = (new Date(c.data + "T12:00").getDay() + 6) % 7; }
    return c;
  };
  const enviar = async (somenteValidar: boolean, extra: any = {}) => {
    setErro(null);
    setValidacao(null);
    const corpo = () => ({ ...corpoBase(), ...extra });
    try {
      if (f.alocacao_id) {
        const r = await api.put(`/api/alocacoes/${f.alocacao_id}`, { ...corpo(), versao: f.versao, motivo: f.motivo });
        aviso("Aula alterada."); if (r.ocorrencias?.length) aviso(`${r.ocorrencias.length} alerta(s): ${r.ocorrencias.map((o: any) => o.regra).join(", ")}`, "info");
        fechar(true);
      } else {
        const r = await api.post("/api/alocacoes", { ...corpo(), somente_validar: somenteValidar });
        if (somenteValidar) { setValidacao(r.ocorrencias); return; }
        if (r.aulas_criadas !== undefined) aviso(`${r.aulas_criadas} aula(s) criada(s); ${r.datas_puladas.length} data(s) não letiva(s) pulada(s).`);
        else aviso("Aula gravada.");
        fechar(true);
      }
    } catch (e) { setErro(e); }
  };
  const salvarComExcecao = async () => {
    if (justificativa.trim().length < 10) return setErro(new Error("Escreva a justificativa (mínimo de 10 caracteres)."));
    try {
      const e = await api.post("/api/excecoes", { tipo: "regra_academica", justificativa: justificativa.trim() });
      setF((x: any) => ({ ...x, excecao_id: e.id }));
      excecoes.recarregar();
      await enviar(false, { excecao_id: e.id });
    } catch (e) { setErro(e); }
  };
  const aplicarAlternativa = (alt: any) => setF((x: any) => ({ ...x, ...alt, ...(alt.periodo_inicio_id ? { hora_inicio: undefined, hora_fim: undefined } : {}) }));
  return (
    <Modal titulo={f.alocacao_id ? "Editar aula" : "Nova aula"} aberto fechar={() => fechar(false)} largo>
      <div className="form-grid">
        <Campo rotulo="Turma" obrigatorio><Selecao valor={f.turma_id} mudar={(v) => setF({ ...f, turma_id: v, turma_uc_id: "" })} opcoes={turmas} /></Campo>
        <Campo rotulo="Unidade curricular" obrigatorio ajuda={tuc ? `Restam ${tuc.restante_h} h de ${tuc.total_h} h · ${tuc.estado_planejamento}` : undefined}>
          <Selecao valor={f.turma_uc_id} mudar={(v) => set("turma_uc_id", v)} opcoes={(oferta.dados || []).map((o) => ({ id: o.turma_uc_id, rotulo: `${o.uc_codigo} – ${o.uc_nome} (${o.restante_h} h restantes)` }))} />
        </Campo>
        {tuc?.divide_grupos && <Campo rotulo="Grupo"><select value={f.grupo ?? ""} onChange={(e) => set("grupo", e.target.value)}><option value="">Turma inteira</option>
          {Array.from({ length: tuc.num_grupos }, (_, i) => <option key={i} value={i + 1}>Grupo {i + 1}</option>)}</select></Campo>}
        <Campo rotulo="Instrutor" ajuda={sug.dados ? `Ordenados por aderência à turma (área ${sug.dados.area_turma || "não definida"}): competência, área e carga da semana.`
            : "Escolha UC, data e período para ver as sugestões avaliadas pelas regras."}>
          {sug.dados ? <SelecaoSugerida valor={f.instrutor_id} mudar={(v) => set("instrutor_id", v)} itens={sug.dados.instrutores}
              rotulo={(i: any) => `${i.nome}${i.area ? ` · ${i.area}` : ""}${i.competencia ? ` · ${i.competencia}` : " · sem competência"} · ${i.carga_semana_h}/${i.limite_h} h na semana`} />
            : <Selecao valor={f.instrutor_id} mudar={(v) => set("instrutor_id", v)} vazio="(pendente)"
              opcoes={(tuc?.instrutores_elegiveis || []).map((i: any) => ({ id: i.id, rotulo: `${i.nome}${i.nivel !== "pleno" ? ` (${i.nivel})` : ""}` }))} />}
          {instSel && instSel.grupo !== "recomendado" && <small className={instSel.grupo === "indisponivel" ? "faixa-erro" : "faixa-alerta"}>{instSel.motivos.join(" ")}</small>}
        </Campo>
        <Campo rotulo="Sala / laboratório" ajuda={sug.dados ? "Ordenados por aderência: área, compatibilidade e capacidade." : "Somente ambientes tecnicamente compatíveis (tipo, capacidade, acessibilidade, equipamentos)."}>
          {sug.dados ? <SelecaoSugerida valor={f.ambiente_id} mudar={(v) => set("ambiente_id", v)} itens={sug.dados.ambientes}
              rotulo={(a: any) => `${a.codigo} – ${a.nome}${a.area ? ` · ${a.area}` : ""} · cap. ${a.capacidade}`} />
            : <Selecao valor={f.ambiente_id} mudar={(v) => set("ambiente_id", v)} vazio="(pendente)"
              opcoes={(tuc?.ambientes_compativeis || []).map((a: any) => ({ id: a.id, rotulo: `${a.codigo} – cap. ${a.capacidade_operacional}/${a.capacidade_fisica}${Object.keys(a.requer_recursos_moveis || {}).length ? " (requer reserva de equipamento)" : ""}` }))} />}
          {ambSel && ambSel.grupo !== "recomendado" && <small className={ambSel.grupo === "indisponivel" ? "faixa-erro" : "faixa-alerta"}>{ambSel.motivos.join(" ")}</small>}
        </Campo>
        <Campo rotulo="Data" obrigatorio><input type="date" value={f.data || ""} onChange={(e) => set("data", e.target.value)} /></Campo>
        <Campo rotulo="Período inicial"><select value={f.periodo_inicio_id ?? ""} onChange={(e) => setF({ ...f, periodo_inicio_id: e.target.value, hora_inicio: undefined, hora_fim: undefined })}>
          <option value="">{f.hora_inicio ? `${f.hora_inicio}–${f.hora_fim} (horário atual)` : "—"}</option>
          {periodos.map((p) => <option key={p.id} value={p.id}>{p.turno} {p.ordem}º {p.inicio}</option>)}</select></Campo>
        <Campo rotulo="Nº de aulas (períodos)" ajuda={tuc ? (tuc.periodos_sugeridos < tuc.periodos_por_encontro ? `Fechamento da carga horária: faltam ${tuc.restante_h} h, use ${tuc.periodos_sugeridos} aula(s). O restante do turno pode ficar com outra UC que também esteja fechando.` : `Regra da instituição: a UC ocupa o turno inteiro (${tuc.periodos_por_encontro} aulas).`) : undefined}><input type="number" min={1} value={f.num_periodos ?? ""} onChange={(e) => set("num_periodos", e.target.value)} /></Campo>
        <Campo rotulo="Equipamento móvel reservado" ajuda="Necessário quando a UC exige equipamento que o ambiente não possui instalado.">
          <div className="linha">
            <Selecao valor={f.recursos?.[0]?.recurso_id ?? ""} mudar={(v) => set("recursos", v ? [{ recurso_id: v, quantidade: f.recursos?.[0]?.quantidade || 1 }] : [])} opcoes={recursos} vazio="(nenhum)" />
            <input type="number" min={1} aria-label="Quantidade" style={{ width: 70 }} value={f.recursos?.[0]?.quantidade ?? 1} disabled={!f.recursos?.length}
              onChange={(e) => set("recursos", [{ ...f.recursos[0], quantidade: e.target.value }])} />
          </div>
        </Campo>
        <Campo rotulo="Exceção autorizada" ajuda="Para feriado/bloqueio ou carga horária excedente, com justificativa documentada.">
          <Selecao valor={f.excecao_id} mudar={(v) => set("excecao_id", v)} vazio="(nenhuma)" opcoes={(excecoes.dados || []).map((e: any) => ({ id: e.id, rotulo: `#${e.id} ${e.tipo}: ${e.justificativa.slice(0, 40)}` }))} />
        </Campo>
        <Campo rotulo="Observação"><input value={f.observacao ?? ""} onChange={(e) => set("observacao", e.target.value)} /></Campo>
        {f.alocacao_id && <Campo rotulo="Motivo da alteração"><input value={f.motivo ?? ""} onChange={(e) => set("motivo", e.target.value)} /></Campo>}
        <Campo rotulo="Opções">
          <label><input type="checkbox" checked={!!f.fixa} onChange={(e) => set("fixa", e.target.checked)} /> Aula fixa (o gerador não altera)</label>
          {!f.alocacao_id && <label><input type="checkbox" checked={!!f.recorrente} onChange={(e) => set("recorrente", e.target.checked)} /> Repetir semanalmente</label>}
        </Campo>
        {f.recorrente && <>
          <Campo rotulo="Repetir de"><input type="date" value={f.data_inicio ?? f.data ?? ""} onChange={(e) => set("data_inicio", e.target.value)} /></Campo>
          <Campo rotulo="até" ajuda="Para quando a carga horária da UC for atingida."><input type="date" value={f.data_fim ?? ""} onChange={(e) => set("data_fim", e.target.value)} /></Campo>
        </>}
      </div>
      {validacao && (validacao.length ? <OcorrenciasLista ocorrencias={validacao} /> : <p><Badge tipo="ok">Sem conflitos</Badge> A aula pode ser gravada.</p>)}
      <Erro erro={erro} ocultarAlternativas />
      {precisaExcecao && <div className="excecao-box">
        <b>Esta escolha foge da regra acadêmica</b> (outra área ou sem competência cadastrada). Se for realmente necessária, registre a justificativa:
        a aula fica marcada como exceção, aparece em "Conferir conflitos" e no histórico (auditoria).
        <textarea rows={2} placeholder="Ex.: instrutor titular afastado; substituição combinada com a coordenação até 30/09." value={justificativa} onChange={(e) => setJustificativa(e.target.value)} />
        <button className="btn" onClick={salvarComExcecao}>Registrar exceção e salvar</button>
      </div>}
      {erro?.detalhes?.alternativas && <Alternativas alt={erro.detalhes.alternativas} aplicar={aplicarAlternativa}
        aceitar={async (alt: any) => { aplicarAlternativa(alt); await enviar(false, { ...alt, ...(alt.periodo_inicio_id ? { hora_inicio: undefined, hora_fim: undefined } : {}) });}} />}
      <div className="rodape-modal">
        <button className="btn" onClick={() => fechar(false)}>Cancelar</button>
        {!f.alocacao_id && !f.recorrente && <button className="btn" onClick={() => enviar(true)}>Validar</button>}
        <button className="btn btn-primario" onClick={() => enviar(false)}>Salvar</button>
      </div>
    </Modal>
  );
}

const EXCECIONAVEIS = ["INSTRUTOR_OUTRA_AREA", "INSTRUTOR_NAO_HABILITADO", "AMBIENTE_OUTRA_AREA"];

/** Lista em 3 grupos: recomendados, só com exceção justificada, indisponíveis (desabilitados, com o motivo). */
function SelecaoSugerida({ valor, mudar, itens, rotulo }: { valor: any; mudar: (v: string) => void; itens: any[]; rotulo: (i: any) => string }) {
  const grupo = (g: string) => itens.filter((i) => i.grupo === g);
  return (
    <select value={valor ?? ""} onChange={(e) => mudar(e.target.value)}>
      <option value="">(pendente)</option>
      {grupo("recomendado").length > 0 && <optgroup label="✔ Recomendados">{grupo("recomendado").map((i) => <option key={i.id} value={i.id}>{rotulo(i)}</option>)}</optgroup>}
      {grupo("excecao").length > 0 && <optgroup label="⚠ Só com exceção justificada">{grupo("excecao").map((i) => <option key={i.id} value={i.id}>{rotulo(i)}</option>)}</optgroup>}
      {grupo("indisponivel").length > 0 && <optgroup label="⛔ Indisponíveis neste horário">{grupo("indisponivel").map((i) => (
        <option key={i.id} value={i.id} disabled>{rotulo(i)} — {(i.motivos[0] || "").slice(0, 70)}</option>))}</optgroup>}
    </select>
  );
}
