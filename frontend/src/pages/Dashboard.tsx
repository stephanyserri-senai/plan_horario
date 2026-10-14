import { useState } from "react";
import { Bar, BarChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api, dataBR, qs } from "../api";
import { Badge, Card, Kpi, Modal, Pagina, Tabela, useCarregar } from "../components/ui";
import { useApp } from "../contexto";
import { PrimeirosPassos } from "../components/PrimeirosPassos";
import { Medidor } from "../components/Visual";
import { useNavigate } from "react-router-dom";

const COR = "var(--grafico-1)";

export default function Dashboard() {
  const { cenario } = useApp();
  const nav = useNavigate();
  const [inicio, setInicio] = useState("");
  const [fim, setFim] = useState("");
  const [detalhe, setDetalhe] = useState<{ titulo: string; linhas: any[]; colunas: any[] } | null>(null);
  const p = { cenario_id: cenario?.id, inicio, fim };
  const inst = useCarregar(() => cenario ? api.get(`/api/indicadores/institucionais${qs(p)}`) : Promise.resolve(null), [cenario?.id, inicio, fim]);
  const amb = useCarregar(() => cenario ? api.get(`/api/indicadores/ambientes${qs(p)}`) : Promise.resolve(null), [cenario?.id, inicio, fim]);
  const ins = useCarregar(() => cenario ? api.get(`/api/indicadores/instrutores${qs(p)}`) : Promise.resolve(null), [cenario?.id, inicio, fim]);
  if (!cenario) return <Pagina titulo="Início"><PrimeirosPassos /><p>Nenhum semestre cadastrado. Crie o semestre a planejar em <b>Semestres e aprovação → + Novo semestre</b>.</p></Pagina>;
  const d = inst.dados;
  const a = amb.dados;
  const i = ins.dados;
  const colAmb = [{ chave: "codigo", rotulo: "Ambiente" }, { chave: "tipo", rotulo: "Tipo" }, { chave: "horas_disponiveis", rotulo: "Disp. (h)", alinhar: "dir" as const },
    { chave: "horas_ocupadas", rotulo: "Ocup. (h)", alinhar: "dir" as const }, { chave: "horas_ociosas", rotulo: "Ociosas (h)", alinhar: "dir" as const },
    { chave: "taxa_ocupacao_pct", rotulo: "Ocupação", render: (l: any) => <Medidor pct={l.taxa_ocupacao_pct} /> }, { chave: "utilizacao_capacidade_fisica_pct", rotulo: "Uso cap. física %", alinhar: "dir" as const },
    { chave: "classificacao", rotulo: "Situação", render: (l: any) => <Badge tipo={l.classificacao === "adequado" ? "ok" : l.classificacao === "demanda_excessiva" ? "bloqueio" : "alerta"}>{l.classificacao.replace("_", " ")}</Badge> }];
  const colIns = [{ chave: "nome", rotulo: "Instrutor" }, { chave: "capacidade_efetiva_h", rotulo: "Capacidade p/ ensino (h/sem)", alinhar: "dir" as const },
    { chave: "alocada_media_semanal_h", rotulo: "Alocada (h/sem)", alinhar: "dir" as const }, { chave: "ocupacao_pct", rotulo: "Ocupação", render: (l: any) => <Medidor pct={l.ocupacao_pct} alerta={90} /> },
    { chave: "ucs", rotulo: "UCs", alinhar: "dir" as const }, { chave: "turmas", rotulo: "Turmas", alinhar: "dir" as const }, { chave: "janelas_h", rotulo: "Janelas (h)", alinhar: "dir" as const },
    { chave: "critico", rotulo: "Crítico", render: (l: any) => l.critico ? <Badge tipo="alerta">sim</Badge> : "não" }];
  const colUc = [{ chave: "turma_codigo", rotulo: "Turma" }, { chave: "uc_codigo", rotulo: "UC" }, { chave: "restante_h", rotulo: "Restante (h)", alinhar: "dir" as const },
    { chave: "capacidade_restante_estimada_h", rotulo: "Capacidade até o prazo (h)", alinhar: "dir" as const }, { chave: "data_limite", rotulo: "Prazo", render: (l: any) => dataBR(l.data_limite) },
    { chave: "risco_atraso", rotulo: "Risco", render: (l: any) => <Badge tipo={l.risco_atraso === "alto" ? "bloqueio" : "alerta"}>{l.risco_atraso}</Badge> }];
  return (
    <Pagina titulo="Início" descricao={`Visão geral do cenário “${cenario.nome}”. Clique em um indicador para ver os detalhes.`}
      acoes={<div className="filtros">
        <label>Início <input type="date" value={inicio} onChange={(e) => setInicio(e.target.value)} /></label>
        <label>Fim <input type="date" value={fim} onChange={(e) => setFim(e.target.value)} /></label>
      </div>}>
      <PrimeirosPassos />
      {(inst.erro || amb.erro) && <div className="erro-box">{inst.erro || amb.erro}</div>}
      {(inst.carregando && !d) && <p role="status">Calculando indicadores…</p>}
      {d && a && i && <>
        <p className="sub">Período: {dataBR(d.periodo.inicio)} a {dataBR(d.periodo.fim)}</p>
        <div className="kpis">
          <Kpi rotulo="Carga horária alocada" valor={`${d.percentual_aulas_alocadas}%`} detalhe={`${d.turmas_ucs.ch_programada_h + d.turmas_ucs.ch_realizada_h} de ${d.turmas_ucs.ch_total_h} h`} />
          <Kpi rotulo="Turmas com programação incompleta" valor={d.turmas_programacao_incompleta} tom={d.turmas_programacao_incompleta ? "alerta" : "ok"} detalhe="clique para acompanhar" onClick={() => nav("/acompanhamento")} />
          <Kpi rotulo="Ocupação temporal dos ambientes" valor={`${a.resumo.taxa_ocupacao_pct}%`} detalhe={`${a.resumo.horas_ocupadas} h de ${a.resumo.horas_disponiveis} h disponíveis`}
            onClick={() => setDetalhe({ titulo: "Ocupação por ambiente", linhas: a.ambientes, colunas: colAmb })} />
          <Kpi rotulo="Ocupação média dos instrutores" valor={`${i.resumo.ocupacao_media_pct}%`} detalhe={`${i.resumo.criticos} crítico(s)`}
            tom={i.resumo.criticos ? "alerta" : undefined} onClick={() => setDetalhe({ titulo: "Ocupação por instrutor", linhas: i.instrutores, colunas: colIns })} />
          <Kpi rotulo="UCs em risco de atraso" valor={d.ucs_em_risco.length} tom={d.ucs_em_risco.length ? "erro" : "ok"}
            onClick={() => setDetalhe({ titulo: "UCs em risco", linhas: d.ucs_em_risco, colunas: colUc })} />
          <Kpi rotulo="Conflitos bloqueados no período" valor={d.conflitos_bloqueados} detalhe="tentativas impedidas pela validação" />
          <Kpi rotulo="Última validação" valor={d.bloqueios_ultima_validacao == null ? "—" : `${d.bloqueios_ultima_validacao} bloqueio(s)`}
            detalhe={d.alertas_pendentes == null ? "cenário ainda não validado" : `${d.alertas_pendentes} alerta(s)`} tom={d.bloqueios_ultima_validacao ? "erro" : undefined} />
          <Kpi rotulo="Ambientes" valor={a.resumo.total_ambientes} detalhe={`${a.resumo.disponiveis} disponíveis · ${a.resumo.bloqueados_ou_manutencao} em manutenção · ${a.resumo.subutilizados} subutilizados`}
            onClick={() => setDetalhe({ titulo: "Ambientes", linhas: a.ambientes, colunas: colAmb })} />
        </div>
        <div className="grid-2">
          <Card titulo="Ocupação por turno (%)">
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={a.por_turno}><CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="turno" /><YAxis unit="%" /><Tooltip /><Bar dataKey="taxa_ocupacao_pct" name="Ocupação %" fill={COR} /></BarChart>
            </ResponsiveContainer>
            <Tabela colunas={[{ chave: "turno", rotulo: "Turno" }, { chave: "horas_ocupadas", rotulo: "Ocupadas (h)", alinhar: "dir" }, { chave: "horas_disponiveis", rotulo: "Disponíveis (h)", alinhar: "dir" }, { chave: "taxa_ocupacao_pct", rotulo: "%", alinhar: "dir" }]} linhas={a.por_turno} chave={(l) => l.turno_id} />
          </Card>
          <Card titulo="Ocupação por dia da semana (%)">
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={a.por_dia_semana}><CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="dia" /><YAxis unit="%" /><Tooltip /><Bar dataKey="taxa_ocupacao_pct" name="Ocupação %" fill={COR} /></BarChart>
            </ResponsiveContainer>
          </Card>
          <Card titulo="Ambientes com maior ocupação">
            <Tabela colunas={colAmb.slice(0, 6)} linhas={d.ambientes_maior_ocupacao} chave={(l) => l.ambiente_id} />
          </Card>
          <Card titulo="Ambientes com maior ociosidade">
            <Tabela colunas={colAmb.slice(0, 6)} linhas={d.ambientes_maior_ociosidade} chave={(l) => l.ambiente_id} />
          </Card>
          <Card titulo="Instrutores com disponibilidade crítica">
            <Tabela colunas={colIns} linhas={d.instrutores_criticos} vazio="Nenhum instrutor acima do limiar configurado." chave={(l) => l.instrutor_id} />
          </Card>
          <Card titulo="Evolução por versão do cenário">
            {d.evolucao_versoes.length < 2 ? <p className="mudo">Versões são registradas a cada mudança de estado do cenário.</p> :
              <ResponsiveContainer width="100%" height={220}>
                <LineChart data={d.evolucao_versoes.map((v: any) => ({ versao: `v${v.versao}`, ocupacao: v.indicadores?.taxa_ocupacao_ambientes_pct, horas: v.indicadores?.horas_programadas }))}>
                  <CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="versao" /><YAxis /><Tooltip />
                  <Line dataKey="ocupacao" name="Ocupação ambientes %" stroke="var(--grafico-1)" /><Line dataKey="horas" name="Horas programadas" stroke="var(--grafico-2)" />
                </LineChart>
              </ResponsiveContainer>}
          </Card>
        </div>
        <p className="sub">{a.formula}. {i.formula}.</p>
      </>}
      <Modal titulo={detalhe?.titulo || ""} aberto={!!detalhe} fechar={() => setDetalhe(null)} largo>
        {detalhe && <Tabela colunas={detalhe.colunas} linhas={detalhe.linhas} chave={(_l, k) => k} />}
      </Modal>
    </Pagina>
  );
}
