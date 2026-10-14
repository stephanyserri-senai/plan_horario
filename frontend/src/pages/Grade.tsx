import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { addDias, api, baixar, dataBR, DIAS_CURTOS, iso, qs, segundaDe } from "../api";
import { Alternativas, Badge, Campo, Erro, Modal, OcorrenciasLista, Pagina, Selecao, Tabela, useCarregar } from "../components/ui";
import { useApp } from "../contexto";
import { useOpcoes } from "../hooks";
import { Diferenca } from "./Cadastro";

type Aula = { unidade_id?: number; id: number; versao: number; data: string; inicio: string; fim: string; turma_id: number; turma: string; turma_uc_id: number; uc: string;
  uc_nome: string; grupo: number | null; instrutor_id: number | null; instrutor: string | null; ambiente_id: number | null; ambiente: string | null;
  fixa: boolean; origem: string; observacao: string | null; status: string; minutos_aula: number };
type Periodo = { id: number; turno_id: number; turno: string; ordem: number; inicio: string; fim: string; dias_semana: number[]; excepcional: boolean };

const MODOS = [{ id: "turma", rotulo: "Por turma" }, { id: "instrutor", rotulo: "Por instrutor" }, { id: "ambiente", rotulo: "Por ambiente" },
  { id: "turno", rotulo: "Por turno" }, { id: "curso", rotulo: "Por curso" }, { id: "unidade", rotulo: "Por unidade" }];
const ENT: Record<string, string> = { turma: "turmas", instrutor: "instrutores", ambiente: "ambientes", turno: "turnos", curso: "cursos", unidade: "unidades" };

function corDe(id: number) {
  return `hsl(${(id * 67) % 360} 55% var(--cor-l))`;
}

export default function Grade() {
  const { cenario, pode, aviso } = useApp();
  const [sp, setSp] = useSearchParams();
  const modoInicial = MODOS.find((m) => sp.get(m.id))?.id || "turma";
  const [modo, setModo] = useState(modoInicial);
  const [alvo, setAlvo] = useState<string>(sp.get(modoInicial) || "");
  const [q, setQ] = useState("");
  const [semana, setSemana] = useState<Date>(() => segundaDe(cenario?.periodo_inicio ? new Date(cenario.periodo_inicio + "T12:00") : new Date()));
  const [unidade, setUnidade] = useState<string>("");
  const [mostrarLivres, setMostrarLivres] = useState(false);
  const [form, setForm] = useState<any | null>(null);
  const [aulaSel, setAulaSel] = useState<Aula | null>(null);
  const [copiar, setCopiar] = useState(false);
  const unidades = useOpcoes("unidades");
  const opsAlvo = useOpcoes(ENT[modo]);
  const [unidadeManual, setUnidadeManual] = useState(false);
  useEffect(() => { setUnidadeManual(false); }, [cenario?.id]);
  useEffect(() => { if (cenario?.periodo_inicio) setSemana(segundaDe(new Date(cenario.periodo_inicio + "T12:00"))); }, [cenario?.id]);

  const fimSemana = addDias(semana, 6);
  const filtro: any = { cenario_id: cenario?.id, inicio: iso(semana), fim: iso(fimSemana), q };
  if (alvo) filtro[`${modo}_id`] = alvo;
  const aulas = useCarregar<Aula[]>(() => cenario ? api.get(`/api/grade${qs(filtro)}`) : Promise.resolve([]), [cenario?.id, modo, alvo, iso(semana), q]);
  // Unidade da grade de horários escolhida automaticamente (a menos que o usuário escolha):
  // unidade do cenário → unidade das aulas exibidas → primeira unidade cadastrada.
  useEffect(() => {
    if (unidadeManual || !unidades.length) return;
    const contagem: Record<string, number> = {};
    (aulas.dados || []).forEach((a) => { if (a.unidade_id) contagem[a.unidade_id] = (contagem[a.unidade_id] || 0) + 1; });
    const daAulas = Object.entries(contagem).sort((x, y) => y[1] - x[1])[0]?.[0];
    const escolhida = (cenario as any)?.unidade_id ? String((cenario as any).unidade_id) : daAulas || unidade || String(unidades[0].id);
    if (escolhida !== unidade) setUnidade(escolhida);
  }, [unidades, aulas.dados, cenario?.id, unidadeManual]);
  const periodos = useCarregar<Periodo[]>(() => unidade ? api.get(`/api/periodos?unidade_id=${unidade}`) : Promise.resolve([]), [unidade]);
  const livres = useCarregar<any[]>(() => cenario && mostrarLivres && alvo && ["turma", "instrutor", "ambiente"].includes(modo)
    ? api.get(`/api/grade/livres${qs({ cenario_id: cenario.id, semana: iso(semana), [`${modo}_id`]: alvo, unidade_id: unidade })}`) : Promise.resolve([]),
    [cenario?.id, mostrarLivres, modo, alvo, iso(semana), unidade]);
  const editavel = pode("alocacoes.editar") && cenario && ["em_elaboracao", "em_validacao"].includes(cenario.estado);

  const dias = useMemo(() => {
    const ds = new Set<number>();
    (periodos.dados || []).forEach((p) => p.dias_semana.forEach((d) => ds.add(d)));
    return [...ds].sort();
  }, [periodos.dados]);
  const linhas = periodos.dados || [];
  const porCelula = useMemo(() => {
    const m: Record<string, Aula[]> = {};
    (aulas.dados || []).forEach((a) => {
      const p = linhas.find((x) => x.inicio === a.inicio) || linhas.find((x) => x.inicio <= a.inicio && a.inicio < x.fim);
      const k = `${a.data}|${p?.id ?? "fora"}`;
      (m[k] = m[k] || []).push(a);
    });
    return m;
  }, [aulas.dados, linhas]);
  const continuacao = (data: string, p: Periodo) => (aulas.dados || []).some((a) => a.data === data && a.inicio < p.inicio && a.fim > p.inicio);
  const livre = (data: string, p: Periodo) => (livres.dados || []).some((l) => l.data === data && l.periodo_id === p.id);

  const mover = async (aulaId: number, data: string, p: Periodo) => {
    const a = (aulas.dados || []).find((x) => x.id === aulaId);
    if (!a) return;
    const seq = linhas.filter((x) => x.turno_id === p.turno_id && x.ordem >= p.ordem);
    let acum = 0, n = 0;
    while (n < seq.length && acum < a.minutos_aula) { const s = seq[n]; acum += minutos(s.fim) - minutos(s.inicio); n++; }
    try {
      await api.put(`/api/alocacoes/${a.id}`, { versao: a.versao, data, periodo_inicio_id: p.id, num_periodos: n, motivo: "arrastar e soltar" });
      aviso("Aula movida.");
    } catch (e: any) {
      setForm({ __erro: e, turma_uc_id: a.turma_uc_id, turma_id: a.turma_id, data, periodo_inicio_id: p.id, num_periodos: n, instrutor_id: a.instrutor_id,
        ambiente_id: a.ambiente_id, grupo: a.grupo, alocacao_id: a.id, versao: a.versao });
    }
    aulas.recarregar();
  };

  if (!cenario) return <Pagina titulo="Grade horária"><p>Selecione ou crie um cenário.</p></Pagina>;
  return (
    <Pagina titulo="Grade horária" descricao="Todas as formas de alocação (formulário, arrastar e soltar, cópia, importação e gerador) usam o mesmo serviço central de validação."
      acoes={<>
        {editavel && <button className="btn btn-primario" onClick={() => setForm({ data: iso(semana), turma_id: modo === "turma" ? alvo : "" })}>+ Nova aula</button>}
        {editavel && modo === "turma" && alvo && <button className="btn" onClick={() => setCopiar(true)}>Copiar semana</button>}
        {pode("exportacao.executar") && <button className="btn" onClick={() => baixar(`/api/exportar/grade${qs({ cenario_id: cenario.id, formato: "pdf", semana: iso(semana),
          filtro: alvo && ["turma", "instrutor", "ambiente", "turno"].includes(modo) ? modo : "", filtro_id: alvo })}`, "grade_semana.pdf")}>PDF da semana</button>}
      </>}>
      {!editavel && <p className="aviso-inline"><Badge tipo="info">Somente leitura</Badge> O cenário está “{cenario.estado}”. Alterações em horários publicados exigem uma proposta de alteração (Planejamento).</p>}
      <div className="filtros">
        <select aria-label="Visualização" value={modo} onChange={(e) => { setModo(e.target.value); setAlvo(""); setSp({}); }}>
          {MODOS.map((m) => <option key={m.id} value={m.id}>{m.rotulo}</option>)}
        </select>
        <Selecao rotulo="Filtrar" valor={alvo} mudar={setAlvo} opcoes={opsAlvo} vazio="(todos)" />
        <Selecao rotulo="Unidade (grade de períodos)" valor={unidade} mudar={(v) => { setUnidade(v); setUnidadeManual(true); }} opcoes={unidades} vazio="Unidade" />
        <input type="search" aria-label="Pesquisa rápida" placeholder="Pesquisa rápida" value={q} onChange={(e) => setQ(e.target.value)} />
        <button className="btn" aria-label="Semana anterior" onClick={() => setSemana(addDias(semana, -7))}>‹</button>
        <input type="date" aria-label="Semana" value={iso(semana)} onChange={(e) => e.target.value && setSemana(segundaDe(new Date(e.target.value + "T12:00")))} />
        <button className="btn" aria-label="Próxima semana" onClick={() => setSemana(addDias(semana, 7))}>›</button>
        {["turma", "instrutor", "ambiente"].includes(modo) && <label><input type="checkbox" checked={mostrarLivres} disabled={!alvo} onChange={(e) => setMostrarLivres(e.target.checked)} /> Destacar horários livres</label>}
      </div>
      <p className="sub">Semana de {dataBR(iso(semana))} a {dataBR(iso(fimSemana))} · {aulas.dados?.length ?? 0} aula(s)</p>
      {(() => {
        const outras = (aulas.dados || []).filter((a) => a.unidade_id && String(a.unidade_id) !== unidade);
        const foraDoPeriodo = cenario.periodo_inicio && (iso(fimSemana) < cenario.periodo_inicio || (cenario.periodo_fim && iso(semana) > cenario.periodo_fim));
        return <>
          {outras.length > 0 && <p className="aviso-inline">{outras.length} aula(s) desta semana são de outra unidade e não aparecem nesta grade.{" "}
            <button className="btn-link" onClick={() => { setUnidade(String(outras[0].unidade_id)); setUnidadeManual(true); }}>Mostrar a unidade {unidades.find((u) => String(u.id) === String(outras[0].unidade_id))?.rotulo || ""}</button></p>}
          {foraDoPeriodo && <p className="aviso-inline">Esta semana está fora do período do cenário ({dataBR(cenario.periodo_inicio)} a {dataBR(cenario.periodo_fim)}).{" "}
            <button className="btn-link" onClick={() => setSemana(segundaDe(new Date(cenario.periodo_inicio + "T12:00")))}>Ir para a primeira semana</button></p>}
        </>;
      })()}
      {aulas.erro && <div className="erro-box">{aulas.erro}</div>}
      <div className="grade-wrap">
        <table className="grade">
          <thead><tr><th>Período</th>{dias.map((d) => <th key={d}>{DIAS_CURTOS[d]} {dataBR(iso(addDias(semana, d))).slice(0, 5)}</th>)}</tr></thead>
          <tbody>
            {linhas.map((p) => (
              <tr key={p.id}>
                <th className="periodo"><span>{p.turno}</span>{p.ordem}º {p.inicio}–{p.fim}{p.excepcional && <Badge tipo="alerta">excepcional</Badge>}</th>
                {dias.map((d) => {
                  const data = iso(addDias(semana, d));
                  const lista = p.dias_semana.includes(d) ? porCelula[`${data}|${p.id}`] || [] : [];
                  const ehLivre = mostrarLivres && livre(data, p);
                  return (
                    <td key={d} className={`${ehLivre ? "livre" : ""} ${!p.dias_semana.includes(d) ? "indisp" : ""}`}
                        onDragOver={(e) => editavel && e.preventDefault()}
                        onDrop={(e) => { e.preventDefault(); const id = Number(e.dataTransfer.getData("text/aula")); if (id) mover(id, data, p); }}
                        onDoubleClick={() => editavel && setForm({ data, periodo_inicio_id: p.id, turma_id: modo === "turma" ? alvo : "", instrutor_id: modo === "instrutor" ? alvo : "", ambiente_id: modo === "ambiente" ? alvo : "" })}>
                      {lista.map((a) => (
                        <button key={a.id} className="aula" style={{ ["--cor" as any]: corDe(a.turma_uc_id) }} draggable={!!editavel && !a.fixa}
                          onDragStart={(e) => e.dataTransfer.setData("text/aula", String(a.id))} onClick={() => setAulaSel(a)}
                          title={`${a.turma} · ${a.uc} ${a.uc_nome} · ${a.instrutor || "sem instrutor"} · ${a.ambiente || "sem ambiente"}`}>
                          <b>{a.turma}{a.grupo ? ` G${a.grupo}` : ""}</b> {a.uc}<br />
                          <small>{a.inicio}–{a.fim} · {a.instrutor || <i>sem instrutor</i>} · {a.ambiente || <i>sem sala</i>}</small>
                          {a.fixa && <span className="tag-fixa" aria-label="aula fixa"> 📌</span>}
                        </button>
                      ))}
                      {lista.length === 0 && continuacao(data, p) && <span className="cont" aria-hidden="true">┆</span>}
                      {ehLivre && lista.length === 0 && <span className="sr">livre</span>}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
        {linhas.length === 0 && !periodos.carregando && <div className="vazio-grade">
          <p><b>A unidade selecionada ainda não tem horários de aula cadastrados</b>, por isso a grade não pode ser desenhada.</p>
          <p>Escolha outra unidade no seletor acima ou cadastre os turnos e os horários de cada aula em <Link to="/cadastros/turnos">Cadastros → Turnos e horários</Link>.</p>
        </div>}
      </div>
      <p className="sub">Dica: clique duas vezes em uma célula para alocar; arraste uma aula para movê-la (a validação é refeita no servidor). Legenda: 📌 fixa · área verde = livre para todos os recursos filtrados.</p>
      {form && <FormAula inicial={form} cenarioId={cenario.id} unidadeId={unidade} periodos={linhas} fechar={(ok) => { setForm(null); if (ok) aulas.recarregar(); }} />}
      {aulaSel && <DetalheAula aula={aulaSel} editavel={!!editavel} fechar={(ok) => { setAulaSel(null); if (ok) aulas.recarregar(); }}
        editar={() => { const a = aulaSel; setAulaSel(null); setForm({ alocacao_id: a.id, versao: a.versao, turma_id: a.turma_id, turma_uc_id: a.turma_uc_id, grupo: a.grupo,
          instrutor_id: a.instrutor_id, ambiente_id: a.ambiente_id, data: a.data, hora_inicio: a.inicio, hora_fim: a.fim, fixa: a.fixa, observacao: a.observacao }); }} />}
      <Modal titulo="Copiar aulas da turma para outra semana" aberto={copiar} fechar={() => setCopiar(false)}>
        <CopiarSemana cenarioId={cenario.id} turmaId={alvo} origem={iso(semana)} fechar={(ok) => { setCopiar(false); if (ok) aulas.recarregar(); }} />
      </Modal>
    </Pagina>
  );
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

function DetalheAula({ aula, editavel, fechar, editar }: { aula: Aula; editavel: boolean; fechar: (ok: boolean) => void; editar: () => void }) {
  const hist = useCarregar(() => api.get(`/api/alocacoes/${aula.id}/historico`), [aula.id]);
  const { aviso } = useApp();
  return (
    <Modal titulo={`${aula.turma} · ${aula.uc} – ${aula.uc_nome}`} aberto fechar={() => fechar(false)} largo>
      <dl className="dl">
        <dt>Data</dt><dd>{dataBR(aula.data)} {aula.inicio}–{aula.fim} ({(aula.minutos_aula / 60).toFixed(2)} h-aula)</dd>
        <dt>Grupo</dt><dd>{aula.grupo ? `Grupo ${aula.grupo}` : "Turma inteira"}</dd>
        <dt>Instrutor</dt><dd>{aula.instrutor || "pendente"}</dd>
        <dt>Ambiente</dt><dd>{aula.ambiente || "pendente"}</dd>
        <dt>Origem</dt><dd>{aula.origem}{aula.fixa ? " · fixa (preservada pelo gerador)" : ""}</dd>
        <dt>Observação</dt><dd>{aula.observacao || "—"}</dd>
      </dl>
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
  useEffect(() => { if (tuc && !inicial.num_periodos && !inicial.hora_inicio) setF((x: any) => ({ ...x, num_periodos: tuc.duracao_bloco_periodos || x.num_periodos })); }, [tuc?.turma_uc_id]);
  const set = (k: string, v: any) => setF((x: any) => ({ ...x, [k]: v }));
  const corpo = () => {
    const c: any = { ...f, cenario_id: cenarioId };
    if (c.periodo_inicio_id) { delete c.hora_inicio; delete c.hora_fim; }
    if (c.recorrente) { c.dia_semana = (new Date(c.data + "T12:00").getDay() + 6) % 7; }
    return c;
  };
  const enviar = async (somenteValidar: boolean) => {
    setErro(null);
    setValidacao(null);
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
        <Campo rotulo="Instrutor" ajuda="Somente instrutores habilitados pela matriz de competências.">
          <Selecao valor={f.instrutor_id} mudar={(v) => set("instrutor_id", v)} vazio="(pendente)"
            opcoes={(tuc?.instrutores_elegiveis || []).map((i: any) => ({ id: i.id, rotulo: `${i.nome}${i.nivel !== "pleno" ? ` (${i.nivel})` : ""}` }))} />
        </Campo>
        <Campo rotulo="Ambiente" ajuda="Somente ambientes tecnicamente compatíveis (tipo, capacidade, acessibilidade, equipamentos).">
          <Selecao valor={f.ambiente_id} mudar={(v) => set("ambiente_id", v)} vazio="(pendente)"
            opcoes={(tuc?.ambientes_compativeis || []).map((a: any) => ({ id: a.id, rotulo: `${a.codigo} – cap. ${a.capacidade_operacional}/${a.capacidade_fisica}${Object.keys(a.requer_recursos_moveis || {}).length ? " (requer reserva de equipamento)" : ""}` }))} />
        </Campo>
        <Campo rotulo="Data" obrigatorio><input type="date" value={f.data || ""} onChange={(e) => set("data", e.target.value)} /></Campo>
        <Campo rotulo="Período inicial"><select value={f.periodo_inicio_id ?? ""} onChange={(e) => setF({ ...f, periodo_inicio_id: e.target.value, hora_inicio: undefined, hora_fim: undefined })}>
          <option value="">{f.hora_inicio ? `${f.hora_inicio}–${f.hora_fim} (horário atual)` : "—"}</option>
          {periodos.map((p) => <option key={p.id} value={p.id}>{p.turno} {p.ordem}º {p.inicio}</option>)}</select></Campo>
        <Campo rotulo="Nº de períodos"><input type="number" min={1} value={f.num_periodos ?? ""} onChange={(e) => set("num_periodos", e.target.value)} /></Campo>
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
      {erro?.detalhes?.alternativas && <Alternativas alt={erro.detalhes.alternativas} aplicar={aplicarAlternativa} />}
      <div className="rodape-modal">
        <button className="btn" onClick={() => fechar(false)}>Cancelar</button>
        {!f.alocacao_id && !f.recorrente && <button className="btn" onClick={() => enviar(true)}>Validar</button>}
        <button className="btn btn-primario" onClick={() => enviar(false)}>Salvar</button>
      </div>
    </Modal>
  );
}
