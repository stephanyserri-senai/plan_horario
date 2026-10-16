import { useState } from "react";
import { Link } from "react-router-dom";
import { api, dataBR, qs } from "../api";
import { Badge, Kpi, Pagina, Tabela, useCarregar } from "../components/ui";
import { useApp } from "../contexto";

const GRAV: Record<string, [string, string]> = { alta: ["bloqueio", "gravidade alta"], media: ["alerta", "gravidade média"], baixa: ["info", "gravidade baixa"] };
const COLUNAS: Record<string, string> = {
  data: "Data", horario: "Horário", turma: "Turma", uc: "UC", instrutor: "Instrutor", sala: "Sala", motivo: "Motivo", falta: "Falta",
  falta_h: "Falta (h)", cabe_h: "Cabe até o prazo (h)", prazo: "Prazo", risco: "Risco", habilitados: "Habilitado(s)", media_pct: "Ocupação média (%)",
  pico_pct: "Semana mais cheia (%)", maior_semana_h: "Maior semana (h)", tipo: "Tipo", recurso: "Recurso", falta_h_semana: "Falta (h/semana)",
  descricao: "Descrição", pedido: "Pedido", de: "De", ate: "Até", justificativa: "Justificativa", dias: "Dias presenciais", ead: "EAD", problema: "O que ajustar",
  epi: "EPI", quantidade: "Quantidade", estado: "Situação",
};
const DATAS = new Set(["data", "prazo", "de", "ate"]);
// riscos que o sistema resolve sugerindo uma correção por caso; os outros levam à página certa
const RESOLVIVEIS = new Set(["sem_recurso", "instrutor_ausente", "sala_indisponivel", "nao_letivo", "dependencia", "prazo", "capacidade"]);
const PAGINA: Record<string, [string, string]> = {
  solicitacoes: ["/solicitacoes", "Abrir as solicitações"], epis: ["/epis", "Abrir o controle de EPIs"],
  sobrecarga: ["/consultas", "Ver o ranking de ocupação"], padrao_dias: ["/cadastros/turmas", "Abrir o cadastro de turmas"],
};

/** Riscos ao desenvolvimento: o que pode atrapalhar as turmas daqui até o fim do semestre, com sugestões para aceitar. */
export default function Gargalos() {
  const { cenario } = useApp();
  const r = useCarregar<any>(() => cenario ? api.get(`/api/riscos${qs({ cenario_id: cenario.id })}`) : Promise.resolve(null), [cenario?.id]);
  const [aberto, setAberto] = useState<string | null>(null);
  if (!cenario) return <Pagina titulo="Riscos e gargalos"><p>Escolha o semestre no topo da página.</p></Pagina>;
  const d = r.dados;
  const ativos = (d?.riscos || []).filter((x: any) => x.quantidade > 0);
  const ok = (d?.riscos || []).filter((x: any) => x.quantidade === 0);
  return (
    <Pagina titulo="Riscos e gargalos" descricao="O que pode atrapalhar o andamento das turmas daqui até o fim do semestre. Abra cada risco para ver os casos e a sugestão do sistema para cada um; aceite e ela é aplicada (sempre pela validação central).">
      {r.carregando && !d && <p role="status">Analisando o semestre…</p>}
      {r.erro && <div className="erro-box">{r.erro}</div>}
      {d && <>
        <div className="kpis">
          <Kpi rotulo="Riscos de gravidade alta" valor={d.resumo.alta} tom={d.resumo.alta ? "erro" : "ok"} detalhe="resolver primeiro" />
          <Kpi rotulo="Gravidade média" valor={d.resumo.media} tom={d.resumo.media ? "alerta" : "ok"} />
          <Kpi rotulo="Casos encontrados" valor={d.resumo.casos} detalhe={`em ${d.resumo.aulas_futuras} aulas futuras`} />
          <Kpi rotulo="Período analisado" valor={`${dataBR(d.referencia).slice(0, 5)} a ${dataBR(d.fim).slice(0, 5)}`} detalhe="de hoje ao fim do semestre" />
        </div>
        {ativos.length === 0 && <div className="risco"><div className="risco-cab"><Badge tipo="ok">Nenhum risco encontrado</Badge> Nada no horizonte ameaça o andamento das turmas.</div></div>}
        <div className="riscos">
          {ativos.map((x: any) => <Risco key={x.codigo} x={x} aberto={aberto === x.codigo} alternar={() => setAberto(aberto === x.codigo ? null : x.codigo)}
            mudou={r.recarregar} cenarioId={cenario.id} />)}
        </div>
        {ok.length > 0 && <details className="risco risco-ok">
          <summary className="risco-cab"><span className="risco-seta" aria-hidden="true">▸</span><Badge tipo="ok">ok</Badge>
            <b>Sem ocorrência</b> <small className="mudo">· {ok.length} verificação(ões)</small></summary>
          <ul className="lista-ok">{ok.map((x: any) => <li key={x.codigo}>✔ {x.titulo}</li>)}</ul>
        </details>}
      </>}
    </Pagina>
  );
}

/** Um risco: cabeçalho sempre igual (gravidade, título, casos) e, ao abrir, explicação + casos com a sugestão de cada um. */
function Risco({ x, aberto, alternar, mudou, cenarioId }: { x: any; aberto: boolean; alternar: () => void; mudou: () => void; cenarioId: number }) {
  const [tom, rot] = GRAV[x.gravidade] || ["info", x.gravidade];
  const resolvivel = RESOLVIVEIS.has(x.codigo);
  return (
    <section className={`risco risco-${x.gravidade} ${aberto ? "aberto" : ""}`}>
      <button className="risco-cab" aria-expanded={aberto} onClick={alternar}>
        <span className="risco-seta" aria-hidden="true">{aberto ? "▾" : "▸"}</span>
        <Badge tipo={tom}>{rot}</Badge>
        <b className="risco-titulo">{x.titulo}</b>
        <small className="mudo">{x.quantidade} caso(s)</small>
        <span className="risco-acao-dica">{resolvivel ? "💡 ver sugestões" : PAGINA[x.codigo] ? "↗ resolver na página" : "ver casos"}</span>
      </button>
      {aberto && <div className="risco-corpo">
        <p>{x.descricao}</p>
        <p className="sub"><b>O que fazer:</b> {x.o_que_fazer}</p>
        {resolvivel ? <Sugestoes codigo={x.codigo} cenarioId={cenarioId} mudou={mudou} /> : <>
          <Tabela colunas={Object.keys(x.itens[0] || {}).map((c) => ({ chave: c, rotulo: COLUNAS[c] || c, render: DATAS.has(c) ? (l: any) => dataBR(l[c]) : undefined }))}
            linhas={x.itens} chave={(_l: any, k: number) => k} />
          {x.quantidade > x.itens.length && <p className="sub">Mostrando {x.itens.length} de {x.quantidade}.</p>}
          {PAGINA[x.codigo] && <Link className="btn btn-primario" to={PAGINA[x.codigo][0]}>{PAGINA[x.codigo][1]} →</Link>}
        </>}
      </div>}
    </section>
  );
}

/** Sugestões do sistema para cada caso, no mesmo formato: situação → sugestão → aceitar. */
function Sugestoes({ codigo, cenarioId, mudou }: { codigo: string; cenarioId: number; mudou: () => void }) {
  const { pode, aviso } = useApp();
  const s = useCarregar<any>(() => api.get(`/api/riscos/${codigo}/sugestoes${qs({ cenario_id: cenarioId })}`), [codigo, cenarioId]);
  const [estado, setEstado] = useState<Record<string, { ok: boolean; msg: string }>>({});
  const [ocupado, setOcupado] = useState(false);
  const podeAceitar = pode("alocacoes.editar");
  const aceitar = async (it: any, acao: any = it.acao) => {
    try {
      const r = await api.post("/api/sugestoes/aplicar", { cenario_id: cenarioId, acao, gerar: false });
      setEstado((e) => ({ ...e, [it.id]: { ok: true, msg: r.mensagem || "Aplicada." } }));
      return true;
    } catch (e: any) {
      setEstado((x) => ({ ...x, [it.id]: { ok: false, msg: e.message } }));
      return false;
    }
  };
  const pendentes = (s.dados?.itens || []).filter((i: any) => i.acao && !estado[i.id]?.ok);
  const aceitarTodas = async () => {
    setOcupado(true);
    let n = 0;
    for (const it of pendentes) if (await aceitar(it)) n++;
    setOcupado(false);
    aviso(`${n} de ${pendentes.length} sugestão(ões) aplicada(s).`, n === pendentes.length ? undefined : "erro");
    mudou();
  };
  if (s.carregando && !s.dados) return <p role="status">Calculando as sugestões… (o sistema testa cada caso na validação)</p>;
  if (s.erro) return <div className="erro-box">{s.erro}</div>;
  const d = s.dados;
  if (!d) return null;
  return (
    <div className="sugestoes-risco">
      <div className="sugestoes-cab">
        <span><b>{d.com_sugestao}</b> de {d.mostrando} caso(s) com sugestão automática{d.total > d.mostrando ? ` (mostrando ${d.mostrando} de ${d.total}; aceite e reabra para ver os próximos)` : ""}</span>
        {podeAceitar && pendentes.length > 1 && <button className="btn btn-primario" disabled={ocupado} onClick={aceitarTodas}>
          {ocupado ? "Aplicando…" : `✓ Aceitar todas (${pendentes.length})`}</button>}
      </div>
      <ul className="lista-sugestoes">
        {d.itens.map((it: any) => {
          const st = estado[it.id];
          // mais de uma correção possível (ex.: habilitar outro instrutor ou remanejar o habilitado): cada uma com seu botão
          const extras = (it.opcoes || []).slice(1);
          return (
            <li key={it.id} className={`sugestao ${st?.ok ? "feita" : ""}`}>
              <div className="sug-caso"><b>{it.caso}</b><small className="mudo">{it.detalhe}</small></div>
              <div className="sug-texto">
                {it.acao ? <span>💡 {extras.length ? "Opção 1: " : ""}{it.sugestao}</span> : <span className="mudo">⚠ {it.motivo_sem}</span>}
                {it.alternativas?.length > 0 && <small className="mudo">{it.acao ? "outras opções" : "alternativas"}: {it.alternativas.join(" · ")}</small>}
                {!st?.ok && extras.map((o: any, k: number) => <div key={k} className="sug-opcao">
                  <span>💡 Opção {k + 2}: {o.sugestao}</span>
                  {podeAceitar && <button className="btn" disabled={ocupado} onClick={async () => { if (await aceitar(it, o.acao)) mudou(); }}>✓ Aceitar opção {k + 2}</button>}
                </div>)}
                {st && <small className={st.ok ? "ok-txt" : "falta-txt"}>{st.ok ? "✔ " : "✖ "}{st.msg}</small>}
              </div>
              <div className="sug-botao">
                {it.acao && podeAceitar && !st?.ok && <button className="btn" disabled={ocupado} onClick={async () => { if (await aceitar(it)) mudou(); }}>✓ Aceitar{extras.length ? " opção 1" : ""}</button>}
                {st?.ok && <Badge tipo="ok">aplicada</Badge>}
              </div>
            </li>
          );
        })}
      </ul>
      {!podeAceitar && <p className="sub">Seu perfil só consulta: peça a um planejador ou à coordenação para aceitar as sugestões.</p>}
    </div>
  );
}
