import { api } from "../api";
import { useApp } from "../contexto";

/** Semestre publicado/aprovado: explica e oferece criar a proposta de alteração com um clique. */
export function AvisoSomenteLeitura() {
  const { cenario, pode, recarregarCenarios, setCenarioId, aviso } = useApp();
  if (!cenario || ["em_elaboracao", "em_validacao"].includes(cenario.estado)) return null;
  const podeProposta = ["publicado", "aprovado"].includes(cenario.estado) && pode("cenarios.criar");
  return (
    <p className="aviso-inline">
      Esta versão do semestre está “{cenario.estado.replace(/_/g, " ")}” e não pode ser alterada diretamente.{" "}
      {podeProposta ? <button className="btn" onClick={async () => {
        try {
          const n = await api.post(`/api/cenarios/${cenario.id}/proposta`, { nome: `Proposta – ${cenario.nome}` });
          await recarregarCenarios(); setCenarioId(n.id);
          aviso("Proposta de alteração criada e aberta: faça os ajustes e envie para aprovação.");
        } catch (e: any) { aviso(e.message, "erro"); }
      }}>Criar proposta de alteração</button> : "Peça a quem pode criar planejamentos para abrir uma proposta de alteração."}
    </p>
  );
}
