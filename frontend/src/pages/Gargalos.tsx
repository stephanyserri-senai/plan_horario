import { Link } from "react-router-dom";
import { api, dataBR, qs } from "../api";
import { Badge, Card, Kpi, Pagina, Tabela, useCarregar } from "../components/ui";
import { useApp } from "../contexto";

const GRAV: Record<string, [string, string]> = { alta: ["bloqueio", "gravidade alta"], media: ["alerta", "gravidade média"], baixa: ["info", "gravidade baixa"] };
const COLUNAS: Record<string, string> = {
  data: "Data", horario: "Horário", turma: "Turma", uc: "UC", instrutor: "Instrutor", sala: "Sala", motivo: "Motivo", falta: "Falta",
  falta_h: "Falta (h)", cabe_h: "Cabe até o prazo (h)", prazo: "Prazo", risco: "Risco", habilitados: "Habilitado(s)", media_pct: "Ocupação média (%)",
  pico_pct: "Semana mais cheia (%)", maior_semana_h: "Maior semana (h)", tipo: "Tipo", recurso: "Recurso", falta_h_semana: "Falta (h/semana)",
  descricao: "Descrição", pedido: "Pedido", de: "De", ate: "Até", justificativa: "Justificativa", dias: "Dias presenciais", ead: "EAD", problema: "O que ajustar",
};
const DATAS = new Set(["data", "prazo", "de", "ate"]);

/** Riscos ao desenvolvimento: o que pode atrapalhar as turmas daqui até o fim do semestre, com gravidade e o que fazer. */
export default function Gargalos() {
  const { cenario } = useApp();
  const r = useCarregar<any>(() => cenario ? api.get(`/api/riscos${qs({ cenario_id: cenario.id })}`) : Promise.resolve(null), [cenario?.id]);
  if (!cenario) return <Pagina titulo="Riscos e gargalos"><p>Escolha o semestre no topo da página.</p></Pagina>;
  const d = r.dados;
  const ativos = (d?.riscos || []).filter((x: any) => x.quantidade > 0);
  const ok = (d?.riscos || []).filter((x: any) => x.quantidade === 0);
  return (
    <Pagina titulo="Riscos e gargalos" descricao="O que pode atrapalhar o andamento das turmas daqui até o fim do semestre: prazos, aulas sem recurso, ausências, salas indisponíveis, dependência de um só instrutor, sobrecarga e falta de capacidade.">
      {r.carregando && <p role="status">Analisando o semestre…</p>}
      {r.erro && <div className="erro-box">{r.erro}</div>}
      {d && <>
        <div className="kpis">
          <Kpi rotulo="Riscos de gravidade alta" valor={d.resumo.alta} tom={d.resumo.alta ? "erro" : "ok"} detalhe="resolver primeiro" />
          <Kpi rotulo="Gravidade média" valor={d.resumo.media} tom={d.resumo.media ? "alerta" : "ok"} />
          <Kpi rotulo="Casos encontrados" valor={d.resumo.casos} detalhe={`em ${d.resumo.aulas_futuras} aulas futuras`} />
          <Kpi rotulo="Período analisado" valor={`${dataBR(d.referencia).slice(0, 5)} a ${dataBR(d.fim).slice(0, 5)}`} detalhe="de hoje ao fim do semestre" />
        </div>
        {ativos.length === 0 && <Card><p><Badge tipo="ok">Nenhum risco encontrado</Badge> Nada no horizonte ameaça o andamento das turmas.</p></Card>}
        {ativos.map((x: any) => <CartaoRisco key={x.codigo} x={x} gargalos={x.codigo === "capacidade" ? d.gargalos : null} />)}
        {ok.length > 0 && <Card titulo="Sem ocorrência">
          <ul className="lista-ok">{ok.map((x: any) => <li key={x.codigo}><Badge tipo="ok">ok</Badge> {x.titulo}</li>)}</ul>
        </Card>}
      </>}
    </Pagina>
  );
}

function CartaoRisco({ x, gargalos }: { x: any; gargalos: any[] | null }) {
  const [tom, rot] = GRAV[x.gravidade] || ["info", x.gravidade];
  const cols = Object.keys(x.itens[0] || {}).map((c) => ({ chave: c, rotulo: COLUNAS[c] || c,
    render: DATAS.has(c) ? (l: any) => dataBR(l[c]) : undefined }));
  return (
    <Card titulo={<><Badge tipo={tom}>{rot}</Badge> {x.titulo} <small className="mudo">· {x.quantidade} caso(s)</small></>}
      extra={x.link ? <Link className="btn" to={x.link}>Resolver →</Link> : undefined}>
      <p>{x.descricao}</p>
      <p className="sub"><b>O que fazer:</b> {x.o_que_fazer}</p>
      {gargalos ? gargalos.map((g: any, i: number) => (
        <div key={i} className="gargalo-item"><b>{g.recurso}</b>{g.turno ? ` · ${g.turno}` : ""}: {g.descricao}
          {g.alternativas?.length > 0 && <ul>{g.alternativas.map((a: string, k: number) => <li key={k}>{a}</li>)}</ul>}</div>))
        : <details open={x.quantidade <= 5}><summary>Ver os casos ({x.quantidade}{x.quantidade > x.itens.length ? `; mostrando ${x.itens.length}` : ""})</summary>
          <Tabela colunas={cols} linhas={x.itens} chave={(_l: any, k: number) => k} /></details>}
    </Card>
  );
}
