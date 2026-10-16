import { useSearchParams } from "react-router-dom";
import { ControleEpis } from "../components/Epis";
import { Pagina } from "../components/ui";

/** Controle de EPIs das turmas: o que comprar/separar e entregar, com prazo. */
export default function Epis() {
  const [sp] = useSearchParams();
  return (
    <Pagina titulo="EPIs das turmas" descricao="EPIs que cada curso exige, por turma: quantidade, prazo e as marcações de comprado/separado e entregue. Os EPIs de cada curso são cadastrados em Cadastros → Cursos, matrizes e UCs.">
      <ControleEpis situacaoInicial={sp.get("situacao") || "abertos"} />
    </Pagina>
  );
}
