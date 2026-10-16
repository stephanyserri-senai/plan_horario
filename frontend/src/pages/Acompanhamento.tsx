import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, dataBR, qs } from "../api";
import { Abas, Badge, Card, Pagina, Tabela, useCarregar } from "../components/ui";
import { Anel, BarraCH, LegendaCH, Medidor, MiniSemana } from "../components/Visual";
import { BarraOcupacao, GraficoSerie, QuadroInstrutores } from "../components/Ocupacao";
import { useApp } from "../contexto";

const RISCO: Record<string, [string, string]> = {
  alto: ["bloqueio", "risco alto"], medio: ["alerta", "risco médio"], baixo: ["info", "risco baixo"], sem_risco: ["ok", "em dia"],
};
const n1 = (v: number) => (Number(v) || 0).toLocaleString("pt-BR", { maximumFractionDigits: 1 });

/** Acompanhamento macro: turmas e suas UCs, instrutores e ocupação, quanto falta por UC, salas. */
export function PainelAcompanhamento() {
  const { cenario } = useApp();
  const [aba, setAba] = useState("ocupacao");
  const [busca, setBusca] = useState("");
  const [soPendencias, setSoPendencias] = useState(false);
  const tu = useCarregar<any>(() => cenario ? api.get(`/api/indicadores/turmas${qs({ cenario_id: cenario.id })}`) : Promise.resolve(null), [cenario?.id]);
  const ins = useCarregar<any>(() => cenario ? api.get(`/api/indicadores/instrutores${qs({ cenario_id: cenario.id })}`) : Promise.resolve(null), [cenario?.id]);
  const amb = useCarregar<any>(() => cenario ? api.get(`/api/indicadores/ambientes${qs({ cenario_id: cenario.id })}`) : Promise.resolve(null), [cenario?.id]);
  if (!cenario) return <p>Selecione um cenário no topo da página.</p>;
  const r = tu.dados?.resumo;
  const total = r?.ch_total_h || 0;
  const filtro = (txt: string) => !busca || txt.toLowerCase().includes(busca.toLowerCase());
  return (
    <div className="acompanhamento">
      {(tu.carregando && !tu.dados) && <p role="status">Calculando…</p>}
      {(tu.erro || ins.erro) && <div className="erro-box">{tu.erro || ins.erro}</div>}
      {r && <div className="aneis">
        <Anel pct={total ? (100 * r.ch_realizada_h) / total : 0} rotulo="Carga horária já realizada" detalhe={`${n1(r.ch_realizada_h)} de ${n1(total)} h`} />
        <Anel pct={total ? (100 * (r.ch_realizada_h + r.ch_programada_h)) / total : 0} rotulo="Carga horária com horário definido" detalhe={`faltam ${n1(r.ch_pendente_h)} h sem horário`} />
        {ins.dados && <Anel pct={ins.dados.resumo.ocupacao_media_pct} rotulo="Ocupação média dos instrutores" detalhe={`${ins.dados.resumo.criticos} sobrecarregado(s) · ${ins.dados.resumo.sem_aulas} sem aulas`} />}
        {amb.dados && <Anel pct={amb.dados.resumo.taxa_ocupacao_pct} rotulo="Ocupação das salas" detalhe={`${amb.dados.resumo.subutilizados} pouco usada(s)`} />}
        <div className="alertas-resumo">
          <div className={r.em_risco_alto ? "tom-erro" : "tom-ok"}><b>{r.em_risco_alto}</b> UC(s) com risco alto de não terminar no prazo</div>
          <div className={r.em_risco_medio ? "tom-alerta" : "tom-ok"}><b>{r.em_risco_medio}</b> com risco médio</div>
          <div className={r.sem_instrutor_elegivel ? "tom-erro" : "tom-ok"}><b>{r.sem_instrutor_elegivel}</b> sem nenhum instrutor habilitado</div>
        </div>
      </div>}
      <Abas abas={[{ id: "ocupacao", rotulo: "Ocupação e quadro de instrutores" }, { id: "turmas", rotulo: "Por turma" }, { id: "instrutores", rotulo: "Por instrutor" }, { id: "ucs", rotulo: "Por unidade curricular" }, { id: "salas", rotulo: "Salas e laboratórios" }]} ativa={aba} mudar={setAba} />
      {aba === "ocupacao" && <OcupacaoEQuadro />}
      {aba !== "ocupacao" && <div className="filtros">
        <input type="search" placeholder="Filtrar por nome ou código…" aria-label="Filtrar" value={busca} onChange={(e) => setBusca(e.target.value)} />
        {aba !== "salas" && <label><input type="checkbox" checked={soPendencias} onChange={(e) => setSoPendencias(e.target.checked)} /> Mostrar só o que precisa de atenção</label>}
        {(aba === "turmas" || aba === "ucs") && <LegendaCH />}
      </div>}
      {aba === "turmas" && tu.dados && <PorTurma itens={tu.dados.itens} filtro={filtro} so={soPendencias} />}
      {aba === "instrutores" && ins.dados && <PorInstrutor dados={ins.dados} filtro={filtro} so={soPendencias} />}
      {aba === "ucs" && tu.dados && <PorUC itens={tu.dados.itens} filtro={filtro} so={soPendencias} />}
      {aba === "salas" && amb.dados && <PorSala dados={amb.dados} filtro={filtro} />}
    </div>
  );
}

/** O que o sistema sabe sobre ocupação: série no tempo, maiores ocupações e o quadro de instrutores (precisa contratar?). */
function OcupacaoEQuadro() {
  const { cenario } = useApp();
  const nav = useNavigate();
  const se = useCarregar<any>(() => cenario ? api.get(`/api/consultas/serie${qs({ cenario_id: cenario.id })}`) : Promise.resolve(null), [cenario?.id]);
  const rk = useCarregar<any>(() => cenario ? api.get(`/api/consultas/ranking${qs({ cenario_id: cenario.id })}`) : Promise.resolve(null), [cenario?.id]);
  return (
    <div className="ocupacao-quadro">
      <Card titulo="Quadro de instrutores: precisa contratar?" extra={<button className="btn-link" onClick={() => nav("/simulador")}>Simular nova turma →</button>}>
        <QuadroInstrutores />
      </Card>
      <Card titulo="Ocupação semana a semana" extra={<button className="btn-link" onClick={() => nav("/consultas")}>Consultar outro intervalo →</button>}>
        {se.dados ? <GraficoSerie dados={se.dados} /> : <p role="status">Calculando…</p>}
      </Card>
      {rk.dados && <div className="grid-2">
        <Card titulo="Instrutores mais ocupados" extra={<button className="btn-link" onClick={() => nav("/consultas")}>Ranking completo →</button>}>
          <Tabela colunas={[{ chave: "nome", rotulo: "Instrutor", render: (l: any) => <><b>{l.nome}</b><small className="mudo"> {l.area}</small></> },
            { chave: "ocupacao_pct", rotulo: "Ocupação da jornada", render: (l: any) => <BarraOcupacao pct={l.ocupacao_pct} /> },
            { chave: "pico_pct", rotulo: "Pico", alinhar: "dir", render: (l: any) => `${l.pico_pct}%` }]} linhas={rk.dados.instrutores_mais.slice(0, 6)} chave={(l: any) => l.id} />
        </Card>
        <Card titulo="Salas mais ocupadas">
          <Tabela colunas={[{ chave: "codigo", rotulo: "Sala", render: (l: any) => <><b>{l.codigo}</b><small className="mudo"> {l.tipo}</small></> },
            { chave: "ocupacao_pct", rotulo: "Ocupação", render: (l: any) => <BarraOcupacao pct={l.ocupacao_pct} /> }]} linhas={rk.dados.salas_mais.slice(0, 6)} chave={(l: any) => l.id} />
        </Card>
      </div>}
    </div>
  );
}

export default function Acompanhamento() {
  return (
    <Pagina titulo="Acompanhamento" descricao="Visão geral do andamento: quanto de cada turma e disciplina já tem horário, quanto falta, e como está a carga de cada instrutor e sala.">
      <PainelAcompanhamento />
    </Pagina>
  );
}

function PorTurma({ itens, filtro, so }: { itens: any[]; filtro: (t: string) => boolean; so: boolean }) {
  const nav = useNavigate();
  const turmas = useMemo(() => {
    const m = new Map<number, any>();
    for (const i of itens) {
      const t = m.get(i.turma_id) || { id: i.turma_id, codigo: i.turma_codigo, nome: i.turma_nome, ucs: [], total: 0, realizada: 0, programada: 0, restante: 0, riscoAlto: 0, riscoMedio: 0 };
      t.ucs.push(i); t.total += i.total_h; t.realizada += i.realizada_h; t.programada += i.programada_h; t.restante += i.restante_h;
      if (i.risco_atraso === "alto") t.riscoAlto++; if (i.risco_atraso === "medio") t.riscoMedio++;
      m.set(i.turma_id, t);
    }
    return [...m.values()];
  }, [itens]);
  const lista = turmas.filter((t) => filtro(`${t.codigo} ${t.nome}`) && (!so || t.restante > 0.01 || t.riscoAlto || t.riscoMedio));
  if (!lista.length) return <p className="mudo">Nenhuma turma {so ? "com pendências" : "encontrada"}.</p>;
  return (
    <div className="grade-cards">
      {lista.map((t) => (
        <Card key={t.id} className="card-turma" titulo={<>{t.codigo} <small className="mudo">{t.nome}</small></>}
          extra={<button className="btn-link" onClick={() => nav(`/grade?turma=${t.id}`)}>Ver grade ›</button>}>
          <BarraCH total={t.total} realizada={t.realizada} programada={t.programada} />
          <div className="chips-status">
            <span>{t.ucs.length} UC(s)</span>
            {t.riscoAlto > 0 && <Badge tipo="bloqueio">{t.riscoAlto} em risco alto</Badge>}
            {t.riscoMedio > 0 && <Badge tipo="alerta">{t.riscoMedio} em risco médio</Badge>}
          </div>
          <details open={t.ucs.length <= 6}>
            <summary>Unidades curriculares</summary>
            <ul className="lista-ucs">
              {t.ucs.map((u: any) => (
                <li key={u.turma_uc_id}>
                  <div className="uc-cab"><span><b>{u.uc_codigo}</b> {u.uc_nome}</span><Badge tipo={RISCO[u.risco_atraso]?.[0] || "info"}>{RISCO[u.risco_atraso]?.[1] || u.risco_atraso}</Badge></div>
                  <BarraCH compacta total={u.total_h} realizada={u.realizada_h} programada={u.programada_h} />
                  <small className="mudo">
                    {u.restante_h > 0.01 ? <b className="falta-txt">faltam {n1(u.restante_h)} h</b> : "✔ completa"} de {n1(u.total_h)} h
                    {" · "}{u.instrutores?.length ? u.instrutores.join(", ") : u.sem_instrutor_elegivel ? <span className="falta-txt">sem instrutor habilitado</span> : "instrutor a definir"}
                    {" · prazo "}{dataBR(u.data_limite)}
                  </small>
                </li>
              ))}
            </ul>
          </details>
        </Card>
      ))}
    </div>
  );
}

function PorInstrutor({ dados, filtro, so }: { dados: any; filtro: (t: string) => boolean; so: boolean }) {
  const nav = useNavigate();
  const lista = [...dados.instrutores].sort((a, b) => b.ocupacao_pct - a.ocupacao_pct)
    .filter((i) => filtro(`${i.nome} ${i.matricula || ""}`) && (!so || i.critico || i.alocada_total_h === 0));
  if (!lista.length) return <p className="mudo">Nenhum instrutor {so ? "sobrecarregado ou sem aulas" : "encontrado"}.</p>;
  return (
    <>
      <p className="sub">Ocupação = horas de aula por semana ÷ horas que o instrutor pode dar aula (limite letivo e disponibilidade). A linha vertical marca o limite de atenção.</p>
      <div className="grade-cards">
        {lista.map((i) => (
          <Card key={i.instrutor_id} className="card-instrutor" titulo={i.nome}
            extra={<button className="btn-link" onClick={() => nav(`/grade?instrutor=${i.instrutor_id}`)}>Ver agenda ›</button>}>
            <Medidor pct={i.ocupacao_pct} alerta={dados.limiares?.instrutor_critico_pct || 90} detalhe={`${n1(i.alocada_media_semanal_h)} de ${n1(i.capacidade_efetiva_h)} h/semana`} />
            <div className="inst-corpo">
              <div>
                <div><b>{n1(i.alocada_media_semanal_h)} h</b> de aula por semana <span className="mudo">(pode até {n1(i.capacidade_efetiva_h)} h)</span></div>
                {i.alocada_total_h === 0 && <Badge tipo="alerta">sem aulas no período</Badge>}
                {i.semanas_acima_limite > 0 && <Badge tipo="bloqueio">{i.semanas_acima_limite} semana(s) acima do limite</Badge>}
                {i.janelas_h > 0 && <div className="mudo">{n1(i.janelas_h)} h de intervalos vagos entre aulas no período</div>}
              </div>
              <MiniSemana horas={i.por_dia_semana_h || {}} />
            </div>
            {i.turmas_lista?.length > 0 && <div className="chips"><small className="mudo">Turmas:</small> {i.turmas_lista.map((t: string) => <span key={t} className="chip">{t}</span>)}</div>}
            {i.ucs_lista?.length > 0 && <div className="chips"><small className="mudo">UCs:</small> {i.ucs_lista.map((t: string) => <span key={t} className="chip chip-neutro">{t}</span>)}</div>}
          </Card>
        ))}
      </div>
    </>
  );
}

function PorUC({ itens, filtro, so }: { itens: any[]; filtro: (t: string) => boolean; so: boolean }) {
  const ucs = useMemo(() => {
    const m = new Map<number, any>();
    for (const i of itens) {
      const u = m.get(i.uc_id) || { uc_id: i.uc_id, codigo: i.uc_codigo, nome: i.uc_nome, turmas: [], total: 0, realizada: 0, programada: 0, restante: 0, riscoAlto: 0, semInstrutor: false };
      u.turmas.push(i.turma_codigo); u.total += i.total_h; u.realizada += i.realizada_h; u.programada += i.programada_h; u.restante += i.restante_h;
      if (i.risco_atraso === "alto") u.riscoAlto++; if (i.sem_instrutor_elegivel) u.semInstrutor = true;
      m.set(i.uc_id, u);
    }
    return [...m.values()].sort((a, b) => b.restante - a.restante);
  }, [itens]);
  const lista = ucs.filter((u) => filtro(`${u.codigo} ${u.nome}`) && (!so || u.restante > 0.01 || u.riscoAlto));
  return (
    <Tabela colunas={[
      { chave: "uc", rotulo: "Unidade curricular", render: (u: any) => <><b>{u.codigo}</b> {u.nome}{u.semInstrutor && <div><Badge tipo="bloqueio">sem instrutor habilitado</Badge></div>}</> },
      { chave: "turmas", rotulo: "Turmas", render: (u: any) => <span title={u.turmas.join(", ")}>{u.turmas.length}</span>, alinhar: "dir" },
      { chave: "barra", rotulo: "Andamento", render: (u: any) => <BarraCH total={u.total} realizada={u.realizada} programada={u.programada} /> },
      { chave: "restante", rotulo: "Falta (h)", alinhar: "dir", render: (u: any) => u.restante > 0.01 ? <b className="falta-txt">{n1(u.restante)}</b> : "✔" },
      { chave: "risco", rotulo: "Risco de atraso", render: (u: any) => u.riscoAlto ? <Badge tipo="bloqueio">{u.riscoAlto} turma(s)</Badge> : <Badge tipo="ok">ok</Badge> },
    ]} linhas={lista} chave={(u) => u.uc_id} vazio="Nenhuma unidade curricular encontrada." />
  );
}

function PorSala({ dados, filtro }: { dados: any; filtro: (t: string) => boolean }) {
  const lista = [...dados.ambientes].sort((a, b) => b.taxa_ocupacao_pct - a.taxa_ocupacao_pct).filter((a) => filtro(`${a.codigo} ${a.nome || ""} ${a.tipo || ""}`));
  return (
    <Tabela colunas={[
      { chave: "codigo", rotulo: "Sala / laboratório", render: (a: any) => <><b>{a.codigo}</b> <small className="mudo">{a.tipo}</small></> },
      { chave: "oc", rotulo: "Ocupação", render: (a: any) => <Medidor pct={a.taxa_ocupacao_pct} alerta={dados.limiares?.demanda_excessiva_pct || 85} /> },
      { chave: "horas_ocupadas", rotulo: "Usada (h)", alinhar: "dir" }, { chave: "horas_ociosas", rotulo: "Livre (h)", alinhar: "dir" },
    ]} linhas={lista} chave={(a) => a.ambiente_id} />
  );
}
