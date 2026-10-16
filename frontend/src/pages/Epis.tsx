import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { ControleEpis, ListasPorCurso } from "../components/Epis";
import { Abas, Pagina } from "../components/ui";

/** EPIs: a lista de cada curso e o controle de entregas das turmas (cada turma nova entra sozinha). */
export default function Epis() {
  const [sp] = useSearchParams();
  const [aba, setAba] = useState(sp.get("aba") || "controle");
  return (
    <Pagina titulo="EPIs das turmas" descricao="Monte a lista de EPIs de cada curso; toda turma do curso entra automaticamente no controle de entregas, com quantidade, prazo e as marcações de comprado/separado e entregue.">
      <Abas abas={[{ id: "controle", rotulo: "✅ Controle de entregas" }, { id: "listas", rotulo: "📋 Lista de EPIs por curso" }]} ativa={aba} mudar={setAba} />
      {aba === "controle" ? <ControleEpis situacaoInicial={sp.get("situacao") || "abertos"} /> : <ListasPorCurso />}
    </Pagina>
  );
}
