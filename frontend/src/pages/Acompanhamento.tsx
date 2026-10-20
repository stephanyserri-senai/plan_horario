import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { CabecalhoGrafico, Colunas, maior, pctBR } from "../components/Graficos";
import { api, dataBR, qs } from "../api";
import { Abas, Badge, Card, Modal, Pagina, Tabela, useCarregar } from "../components/ui";
import { ControleEpis } from "../components/Epis";
import { rotuloDe, useOpcoes } from "../hooks";
import { Periodo } from "./Consultas";
import { Anel, BarraCH, LegendaCH, Medidor, MiniSemana } from "../components/Visual";
import { BarraOcupacao, GraficoSerie, QuadroInstrutores } from "../components/Ocupacao";
import { useApp } from "../contexto";

const RISCO: Record<string, [string, string]> = {
  alto: ["bloqueio", "risco alto"], medio: ["alerta", "risco médio"], baixo: ["info", "risco baixo"], sem_risco: ["ok", "em dia"], ead: ["info", "EAD (fora da grade)"],
};
const n1 = (v: number) => (Number(v) || 0).toLocaleString("pt-BR", { maximumFractionDigits: 1 });

/** Ocupação e andamento num só lugar: taxas de ocupação (instrutores, salas, turnos, dias), quadro de instrutores
 * e o andamento da carga horária por turma, instrutor, UC e sala. Um único período vale para tudo. */
function PainelAcompanhamento() {
  const { cenario } = useApp();
  const [aba, setAba] = useState("geral");
  const [busca, setBusca] = useState("");
  const [soPendencias, setSoPendencias] = useState(false);
  const [inicio, setInicio] = useState("");
  const [fim, setFim] = useState("");
  const per = { cenario_id: cenario?.id, inicio, fim };
  const dep = [cenario?.id, inicio, fim];
  const tu = useCarregar<any>(() => cenario ? api.get(`/api/indicadores/turmas${qs({ cenario_id: cenario.id })}`) : Promise.resolve(null), [cenario?.id]);
  const ins = useCarregar<any>(() => cenario ? api.get(`/api/indicadores/instrutores${qs(per)}`) : Promise.resolve(null), dep);
  const amb = useCarregar<any>(() => cenario ? api.get(`/api/indicadores/ambientes${qs(per)}`) : Promise.resolve(null), dep);
  const inst = useCarregar<any>(() => cenario ? api.get(`/api/indicadores/institucionais${qs(per)}`) : Promise.resolve(null), dep);
  if (!cenario) return <p>Selecione um semestre no topo da página.</p>;
  const r = tu.dados?.resumo;
  const total = r?.ch_total_h || 0;
  const filtro = (txt: string) => !busca || txt.toLowerCase().includes(busca.toLowerCase());
  const d = inst.dados;
  return (
    <div className="acompanhamento">
      <Periodo inicio={inicio} fim={fim} setInicio={setInicio} setFim={setFim} />
      {d && <p className="sub">Ocupação de {dataBR(d.periodo.inicio)} a {dataBR(d.periodo.fim)}; o andamento da carga horária é do semestre inteiro.</p>}
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
          {d && <div className={d.turmas_programacao_incompleta ? "tom-alerta" : "tom-ok"}><b>{d.turmas_programacao_incompleta}</b> turma(s) com horário incompleto</div>}
          {d && <div className={d.bloqueios_ultima_validacao ? "tom-erro" : "tom-ok"}>
            {d.bloqueios_ultima_validacao == null ? "semestre ainda não validado" : <><b>{d.bloqueios_ultima_validacao}</b> bloqueio(s) na última validação · {d.alertas_pendentes} alerta(s)</>}</div>}
        </div>
      </div>}
      <Abas abas={[{ id: "geral", rotulo: "📈 Taxas de ocupação" }, { id: "quadro", rotulo: "👥 Quadro de instrutores" }, { id: "turmas", rotulo: "Por turma" },
        { id: "instrutores", rotulo: "Por instrutor" }, { id: "ucs", rotulo: "Por unidade curricular" }, { id: "salas", rotulo: "Salas e laboratórios" }]} ativa={aba} mudar={setAba} />
      {aba === "geral" && <TaxasDeOcupacao inicio={inicio} fim={fim} amb={amb.dados} inst={d} ins={ins.dados} />}
      {aba === "quadro" && <QuadroCard />}
      {!["geral", "quadro"].includes(aba) && <div className="filtros">
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

function QuadroCard() {
  const nav = useNavigate();
  return (
    <Card titulo="Quadro de instrutores: precisa contratar?" extra={<button className="btn-link" onClick={() => nav("/simulador")}>Simular nova turma →</button>}>
      <QuadroInstrutores />
    </Card>
  );
}


/** Taxas de ocupação no período: semana a semana, por turno, por dia da semana, maiores ocupações e ociosidade. */
function TaxasDeOcupacao({ inicio, fim, amb, inst, ins }: { inicio: string; fim: string; amb: any; inst: any; ins: any }) {
  const { cenario, unidade } = useApp();
  const nav = useNavigate();
  const p = { cenario_id: cenario?.id, inicio, fim };
  const se = useCarregar<any>(() => cenario ? api.get(`/api/consultas/serie${qs(p)}`) : Promise.resolve(null), [cenario?.id, inicio, fim]);
  const rk = useCarregar<any>(() => cenario ? api.get(`/api/consultas/ranking${qs(p)}`) : Promise.resolve(null), [cenario?.id, inicio, fim]);
  // um ponto por turno (somando as unidades): manhã, tarde, noite e sábado por último; a PFP conta na manhã ou na tarde
  const porTurno = useMemo(() => {
    const m = new Map<string, { turno: string; ocup: number; disp: number }>();
    for (const t of amb?.por_turno || []) {
      const nome = String(t.turno).split(" – ")[0];
      const x = m.get(nome) || { turno: nome, ocup: 0, disp: 0 };
      x.ocup += t.horas_ocupadas || 0; x.disp += t.horas_disponiveis || 0;
      m.set(nome, x);
    }
    const ordem = ["Manhã", "Tarde", "Noite", "Sábado"];
    return [...m.values()].filter((x) => x.disp > 0)
      .sort((a, b) => (ordem.indexOf(a.turno) + 99) % 99 - (ordem.indexOf(b.turno) + 99) % 99)
      .map((x) => ({ turno: x.turno, taxa_ocupacao_pct: Math.round((1000 * x.ocup) / x.disp) / 10 }));
  }, [amb]);
  return (
    <div className="ocupacao-quadro">
      <Card className="graf-card">
        <CabecalhoGrafico titulo="Ocupação semana a semana" sub="instrutores: % da jornada com aula · salas: % do horário com aula; à direita, a previsão pela grade gerada"
          destaque={se.dados?.pico && <><small>semana mais cheia</small><b>{pctBR(se.dados.pico.instrutores_pct)}</b><small>{se.dados.pico.rotulo}</small></>} />
        {se.dados ? <GraficoSerie dados={se.dados} altura={280} /> : <p role="status">Calculando…</p>}
      </Card>
      {amb && <div className="grid-2">
        <Card className="graf-card">
          <CabecalhoGrafico titulo="Salas: ocupação por turno" sub={!unidade ? "Beira Mar e Porto somadas · a PFP conta na manhã ou na tarde" : "a PFP conta na manhã ou na tarde"}
            destaque={maior(porTurno, "turno", "taxa_ocupacao_pct")} />
          <Colunas dados={porTurno} x="turno" y="taxa_ocupacao_pct" nome="Ocupação do horário" />
        </Card>
        <Card className="graf-card">
          <CabecalhoGrafico titulo="Salas: ocupação por dia da semana" sub="horas com aula ÷ horas disponíveis das salas"
            destaque={maior(amb.por_dia_semana, "dia", "taxa_ocupacao_pct")} />
          <Colunas dados={amb.por_dia_semana} x="dia" y="taxa_ocupacao_pct" nome="Ocupação do horário"
            extraTooltip={(l: any) => <div className="tt-nota">{Math.round(l.horas_ocupadas)} de {Math.round(l.horas_disponiveis)} h</div>} />
        </Card>
      </div>}
      {rk.dados && <Card className="graf-card">
        <CabecalhoGrafico titulo="Ocupação por área" sub="o instrutor conta na área principal; as horas dadas em turmas de outra área contam nela" />
        <div className="grid-2">
          <div>
            <div className="graf-sub"><span className="graf-marca" style={{ background: "var(--grafico-1)" }} /> Instrutores <small className="mudo">% da jornada com aula</small>
              <span className="graf-destaque-mini">{maior(rk.dados.areas, "area", "ocupacao_pct")}</span></div>
            <Colunas dados={rk.dados.areas} x="area" y="ocupacao_pct" nome="Ocupação da jornada" altura={270}
              extraTooltip={(l: any) => <div className="tt-nota">{l.instrutores} instrutor(es){l.instrutores_outras_areas ? ` +${l.instrutores_outras_areas} de outras áreas` : ""} · {l.aula_media_semana_h} de {l.capacidade_semana_h} h/sem</div>} />
            <details className="tabela-dados"><summary>Ver os números (tabela)</summary>
            <Tabela colunas={[{ chave: "area", rotulo: "Área" },
              { chave: "instrutores", rotulo: "Instrutores", alinhar: "dir", render: (l: any) => <>{l.instrutores}{l.instrutores_outras_areas > 0 &&
                <small className="mudo" title="instrutores de outra área com aulas em turmas desta área"> +{l.instrutores_outras_areas} de outras</small>}</> },
              { chave: "aula_media_semana_h", rotulo: "Aula (h/sem)", alinhar: "dir" }, { chave: "capacidade_semana_h", rotulo: "Jornada (h/sem)", alinhar: "dir" },
              { chave: "ocupacao_pct", rotulo: "Ocupação", render: (l: any) => <BarraOcupacao pct={l.ocupacao_pct} /> }]}
              linhas={rk.dados.areas} chave={(l: any) => l.area} /></details>
          </div>
          <div>
            <div className="graf-sub"><span className="graf-marca" style={{ background: "var(--grafico-2)" }} /> Salas e laboratórios <small className="mudo">% do horário com aula</small>
              <span className="graf-destaque-mini">{maior(rk.dados.areas_salas || [], "area", "ocupacao_pct")}</span></div>
            <Colunas dados={rk.dados.areas_salas || []} x="area" y="ocupacao_pct" nome="Ocupação do horário" cor="var(--grafico-2)" altura={270}
              extraTooltip={(l: any) => <div className="tt-nota">{l.salas} sala(s) · {Math.round(l.horas_ocupadas)} h ocupadas{l.area === "Uso comum" ? " · salas de todas as áreas" : ""}</div>} />
            <details className="tabela-dados"><summary>Ver os números (tabela)</summary>
            <Tabela colunas={[{ chave: "area", rotulo: "Área", render: (l: any) => l.area === "Uso comum" ? <span title="salas que atendem todas as áreas">Uso comum (todas as áreas)</span> : l.area }, { chave: "salas", rotulo: "Salas", alinhar: "dir" },
              { chave: "horas_ocupadas", rotulo: "Ocupadas (h)", alinhar: "dir", render: (l: any) => Math.round(l.horas_ocupadas) },
              { chave: "ocupacao_pct", rotulo: "Ocupação", render: (l: any) => <BarraOcupacao pct={l.ocupacao_pct} /> }]}
              linhas={rk.dados.areas_salas || []} chave={(l: any) => l.area} /></details>
          </div>
        </div>
      </Card>}
      {rk.dados && <div className="grid-2">
        <Card titulo="Instrutores mais ocupados" extra={<button className="btn-link" onClick={() => nav("/consultas")}>Ranking completo →</button>}>
          <Tabela colunas={[{ chave: "nome", rotulo: "Instrutor", render: (l: any) => <><b>{l.nome}</b><small className="mudo"> {l.area}</small></> },
            { chave: "ocupacao_pct", rotulo: "Ocupação da jornada", render: (l: any) => <BarraOcupacao pct={l.ocupacao_pct} /> },
            { chave: "pico_pct", rotulo: "Semana mais cheia", alinhar: "dir", render: (l: any) => `${l.pico_pct}%` }]} linhas={rk.dados.instrutores_mais.slice(0, 8)} chave={(l: any) => l.id} />
          {ins && ins.resumo.criticos > 0 && <p className="sub">{ins.resumo.criticos} instrutor(es) acima do limite em alguma semana.</p>}
        </Card>
        <Card titulo="Instrutores com mais folga">
          <Tabela colunas={[{ chave: "nome", rotulo: "Instrutor", render: (l: any) => <><b>{l.nome}</b><small className="mudo"> {l.area}</small></> },
            { chave: "ocupacao_pct", rotulo: "Ocupação da jornada", render: (l: any) => <BarraOcupacao pct={l.ocupacao_pct} /> }]}
            linhas={rk.dados.instrutores_menos.slice(0, 8)} chave={(l: any) => l.id} />
        </Card>
        <Card titulo="Salas mais ocupadas">
          <Tabela colunas={[{ chave: "codigo", rotulo: "Sala", render: (l: any) => <><b>{l.codigo}</b><small className="mudo"> {l.tipo}</small></> },
            { chave: "ocupacao_pct", rotulo: "Ocupação", render: (l: any) => <BarraOcupacao pct={l.ocupacao_pct} /> }]} linhas={rk.dados.salas_mais.slice(0, 8)} chave={(l: any) => l.id} />
        </Card>
        <Card titulo="Salas mais ociosas">
          <Tabela colunas={[{ chave: "codigo", rotulo: "Sala", render: (l: any) => <><b>{l.codigo}</b><small className="mudo"> {l.tipo}</small></> },
            { chave: "ocupacao_pct", rotulo: "Ocupação", render: (l: any) => <BarraOcupacao pct={l.ocupacao_pct} /> }]} linhas={rk.dados.salas_menos.slice(0, 8)} chave={(l: any) => l.id} />
        </Card>
      </div>}
      {inst?.evolucao_versoes?.length >= 2 && <Card className="graf-card">
        <CabecalhoGrafico titulo="Evolução por versão do semestre" sub="ocupação das salas em cada versão aprovada ou publicada" />
        <Colunas dados={inst.evolucao_versoes.map((v: any) => ({ versao: `v${v.versao}`, ocupacao: v.indicadores?.taxa_ocupacao_ambientes_pct || 0, horas: v.indicadores?.horas_programadas }))}
          x="versao" y="ocupacao" nome="Ocupação das salas" referencias={false} altura={200}
          extraTooltip={(l: any) => l.horas != null && <div className="tt-nota">{Math.round(l.horas)} h programadas</div>} />
      </Card>}
      {amb && ins && <p className="sub">{amb.formula}. {ins.formula}.</p>}
    </div>
  );
}

export default function Acompanhamento() {
  return (
    <Pagina titulo="Ocupação e andamento" descricao="Taxas de ocupação de instrutores e salas (por semana, turno e dia), o quadro de instrutores e o andamento da carga horária de cada turma, instrutor, UC e sala.">
      <PainelAcompanhamento />
    </Pagina>
  );
}

function PorTurma({ itens, filtro, so }: { itens: any[]; filtro: (t: string) => boolean; so: boolean }) {
  const nav = useNavigate();
  const [aberta, setAberta] = useState<any | null>(null);
  const epis = useCarregar<any>(() => api.get("/api/epis-turmas").catch(() => null), [aberta ? 0 : 1]);
  const episDe = (id: number) => (epis.dados?.itens || []).filter((e: any) => e.turma_id === id);
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
        <Card key={t.id} className="card-turma" titulo={<button className="titulo-link" onClick={() => setAberta(t)}>{t.codigo} <small className="mudo">{t.nome}</small></button>}
          extra={<span className="acoes-linha"><button className="btn btn-pequeno" onClick={() => setAberta(t)}>Detalhes</button>
            <button className="btn-link" onClick={() => nav(`/grade?turma=${t.id}`)}>Ver grade ›</button></span>}>
          <BarraCH total={t.total} realizada={t.realizada} programada={t.programada} />
          <div className="chips-status">
            <span>{t.ucs.length} UC(s)</span>
            {t.riscoAlto > 0 && <Badge tipo="bloqueio">{t.riscoAlto} em risco alto</Badge>}
            {t.riscoMedio > 0 && <Badge tipo="alerta">{t.riscoMedio} em risco médio</Badge>}
            <ChipEpis itens={episDe(t.id)} />
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
      <Modal titulo={aberta ? `${aberta.codigo} — ${aberta.nome}` : ""} aberto={!!aberta} fechar={() => setAberta(null)} largo>
        {aberta && <DetalheTurma t={aberta} />}
      </Modal>
    </div>
  );
}

/** Resumo dos EPIs da turma no cartão: entregues ou o que falta (com prazo vencido em destaque). */
function ChipEpis({ itens }: { itens: any[] }) {
  if (!itens.length) return null;
  const falta = itens.filter((e) => !e.entregue);
  const atraso = falta.filter((e) => e.situacao === "atrasado").length;
  if (!falta.length) return <Badge tipo="ok">🦺 EPIs entregues</Badge>;
  return <Badge tipo={atraso ? "bloqueio" : "alerta"}>🦺 {falta.length} EPI(s) a entregar{atraso ? ` · ${atraso} atrasado(s)` : ""}</Badge>;
}

const DIAS_TXT = ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"];

/** Tudo da turma num lugar: dados gerais, andamento das UCs, instrutores e EPIs (com o controle de entrega). */
function DetalheTurma({ t }: { t: any }) {
  const nav = useNavigate();
  const [aba, setAba] = useState("ucs");
  const cad = useCarregar<any>(() => api.get(`/api/cadastros/turmas/${t.id}`), [t.id]);
  const turnos = useOpcoes("turnos");
  const cursos = useOpcoes("cursos");
  const epis = useCarregar<any>(() => api.get(`/api/epis-turmas?turma_id=${t.id}`), [t.id, aba]);
  const d = cad.dados;
  const instrutores = useMemo(() => {
    const m = new Map<string, string[]>();
    for (const u of t.ucs) for (const n of u.instrutores || []) m.set(n, [...(m.get(n) || []), u.uc_codigo]);
    return [...m.entries()].map(([nome, ucs]) => ({ nome, ucs }));
  }, [t]);
  const semInstrutor = t.ucs.filter((u: any) => !u.instrutores?.length);
  const ep = epis.dados?.itens || [];
  const epFalta = ep.filter((e: any) => !e.entregue);
  const pct = t.total ? Math.round((100 * (t.realizada + t.programada)) / t.total) : 0;
  return (
    <div className="detalhe-turma">
      {d && <div className="dt-dados">
        <div><small>Curso</small><b>{rotuloDe(cursos, d.curso_id)}</b></div>
        <div><small>Turno</small><b>{rotuloDe(turnos, d.turno_id)}</b></div>
        <div><small>Dias de aula</small><b>{(d.dias_possiveis || []).map((x: number) => DIAS_TXT[x]).join(", ")}{d.dias_ead?.length ? ` · EAD ${d.dias_ead.map((x: number) => DIAS_TXT[x]).join(", ")}` : ""}</b></div>
        <div><small>Período</small><b>{dataBR(d.data_inicio)} a {dataBR(d.data_fim)}</b></div>
        <div><small>Alunos</small><b>{d.qtd_alunos}</b></div>
      </div>}
      <div className="dt-kpis">
        <div><b>{n1(t.realizada)} h</b><small>já realizadas</small></div>
        <div><b>{pct}%</b><small>da carga com horário</small></div>
        <div className={t.restante > 0.01 ? "tom-alerta" : "tom-ok"}><b>{n1(t.restante)} h</b><small>sem horário</small></div>
        <div className={t.riscoAlto ? "tom-erro" : t.riscoMedio ? "tom-alerta" : "tom-ok"}><b>{t.riscoAlto + t.riscoMedio}</b><small>UC(s) em risco de prazo</small></div>
        <div className={epFalta.some((e: any) => e.situacao === "atrasado") ? "tom-erro" : epFalta.length ? "tom-alerta" : "tom-ok"}>
          <b>{ep.length ? `${ep.length - epFalta.length}/${ep.length}` : "—"}</b><small>EPIs entregues</small></div>
      </div>
      <BarraCH total={t.total} realizada={t.realizada} programada={t.programada} />
      <Abas abas={[{ id: "ucs", rotulo: `Unidades curriculares (${t.ucs.length})` }, { id: "instrutores", rotulo: `Instrutores (${instrutores.length})` },
        { id: "epis", rotulo: `🦺 EPIs (${ep.length})` }]} ativa={aba} mudar={setAba} />
      {aba === "ucs" && <Tabela linhas={t.ucs} chave={(u: any) => u.turma_uc_id} colunas={[
        { chave: "uc", rotulo: "UC", render: (u: any) => <><b>{u.uc_codigo}</b> {u.uc_nome}</> },
        { chave: "and", rotulo: "Andamento", render: (u: any) => <BarraCH compacta total={u.total_h} realizada={u.realizada_h} programada={u.programada_h} /> },
        { chave: "falta", rotulo: "Falta", alinhar: "dir", render: (u: any) => u.restante_h > 0.01 ? <b className="falta-txt">{n1(u.restante_h)} h</b> : "✔" },
        { chave: "inst", rotulo: "Instrutor(es)", render: (u: any) => u.instrutores?.length ? u.instrutores.join(", ")
          : u.sem_instrutor_elegivel ? <span className="falta-txt">sem instrutor habilitado</span> : <span className="mudo">a definir</span> },
        { chave: "prazo", rotulo: "Prazo", render: (u: any) => dataBR(u.data_limite) },
        { chave: "risco", rotulo: "Situação", render: (u: any) => <Badge tipo={RISCO[u.risco_atraso]?.[0] || "info"}>{RISCO[u.risco_atraso]?.[1] || u.risco_atraso}</Badge> },
      ]} />}
      {aba === "instrutores" && <>
        <Tabela linhas={instrutores} chave={(i: any) => i.nome} vazio="Nenhum instrutor com aula nesta turma ainda." colunas={[
          { chave: "nome", rotulo: "Instrutor", render: (i: any) => <b>{i.nome}</b> },
          { chave: "ucs", rotulo: "UCs nesta turma", render: (i: any) => <span className="chips">{i.ucs.map((c: string) => <span key={c} className="chip chip-neutro">{c}</span>)}</span> },
        ]} />
        {semInstrutor.length > 0 && <p className="sub">Sem instrutor definido: {semInstrutor.map((u: any) => u.uc_codigo).join(", ")}.</p>}
      </>}
      {aba === "epis" && <ControleEpis turmaId={t.id} />}
      <div className="rodape-modal">
        <button className="btn" onClick={() => nav(`/cadastros/turmas?id=${t.id}`)}>Cadastro da turma</button>
        <button className="btn btn-primario" onClick={() => nav(`/grade?turma=${t.id}`)}>Ver a grade da turma ›</button>
      </div>
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
