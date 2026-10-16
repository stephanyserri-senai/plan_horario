import { Link } from "react-router-dom";
import { api } from "../api";
import { Badge, Card, Pagina, Tabela, useCarregar } from "../components/ui";

const TIPO: Record<string, [string, string]> = { obrigatoria: ["bloqueio", "obrigatória"], preferencia: ["info", "preferência"], aviso: ["alerta", "aviso"] };
const DECISOES: Record<string, string> = { sugestao: "sugestões aceitas/recusadas", selecao: "aulas criadas", alteracao_manual: "alterações manuais",
  aprovacao: "aprovações de semestre", reprovacao: "reprovações", resultado_cenario: "gerações de horário", preferencia: "preferências", rejeicao: "rejeições" };

/** Memória do algoritmo: as regras que o sistema aplica (de onde vêm as decisões do gerador e da validação). */
export default function Regras() {
  const r = useCarregar<any>(() => api.get("/api/regras"), []);
  const d = r.dados;
  const grupos: [string, any[]][] = [];
  (d?.regras || []).forEach((x: any) => { const g = grupos.find(([n]) => n === x.grupo); g ? g[1].push(x) : grupos.push([x.grupo, [x]]); });
  return (
    <Pagina titulo="Regras do sistema" descricao="A memória do algoritmo: tudo o que o gerador de horários, a validação e as análises seguem, num lugar só.">
      {r.erro && <div className="erro-box">{r.erro}</div>}
      {!d && !r.erro && <p role="status">Carregando…</p>}
      {d && <>
        <p className="sub">Obrigatória = a grade não aceita o que viola; preferência = o gerador busca, mas pode ceder; aviso = aparece nas análises para apoiar a decisão.
          As decisões tomadas sobre as sugestões do sistema ficam registradas para calibrar pesos e preferências
          ({Object.entries(d.decisoes_registradas || {}).map(([k, n]) => `${n} ${DECISOES[k] || k}`).join(" · ") || "nenhuma ainda"}).</p>
        {d.conformidade.length > 0 && <Card titulo={<>Turmas fora do padrão de dias <Badge tipo="alerta">{d.conformidade.length}</Badge></>}>
          <Tabela colunas={[{ chave: "turma", rotulo: "Turma", render: (t: any) => <Link to={`/cadastros/turmas?id=${t.turma_id}`}>{t.turma}</Link> },
            { chave: "dias", rotulo: "Dias presenciais" }, { chave: "ead", rotulo: "EAD" }, { chave: "problema", rotulo: "O que ajustar" }]}
            linhas={d.conformidade} chave={(t: any) => t.turma_id} />
        </Card>}
        {grupos.map(([g, lista]) => (
          <Card key={g} titulo={g}>
            <ul className="lista-regras">{lista.map((x) => (
              <li key={x.codigo}><div><b>{x.titulo}</b> <Badge tipo={TIPO[x.tipo]?.[0] || "info"}>{TIPO[x.tipo]?.[1] || x.tipo}</Badge></div>
                <p>{x.descricao}</p><small className="mudo">Onde vale: {x.onde.join(", ")} · código {x.codigo}</small></li>))}</ul>
          </Card>))}
      </>}
    </Pagina>
  );
}
