import { useState } from "react";
import { api, dataBR, qs } from "../api";
import { useApp } from "../contexto";
import { Erro, useCarregar } from "./ui";

type Celula = { data: string; dia: number; turno_id: number; turno: string; horario: string; estado: string; horas?: number; descricao?: string;
  aulas?: { id: number; turma: string; uc: string }[] };
type Agenda = {
  instrutor: { id: number; nome: string; modalidade: string; carga_semanal_h: number };
  dias: { dia: number; data: string; rotulo: string }[];
  turnos: { id: number; nome: string; horario: string }[];
  celulas: Celula[];
  resumo: { aula_h: number; pl_h: number; pj_h: number; tr_h?: number; ocupadas_h: number; vazios: number; sem_atribuicao_h: number; dispensa_h: number; excede_carga: boolean };
};

const ROTULO: Record<string, string> = { PL: "PL · Planejamento", PJ: "PJ · Projeto / outra atividade", TR: "TR · Treinamento", vazio: "Vazio", indisponivel: "Indisponível", nao_letivo: "Não letivo" };

/** Semana do instrutor turno a turno: aula, PL, PJ ou vazio — e o saldo da carga conforme a modalidade (mensalista ou horista). */
export default function AgendaInstrutor({ cenarioId, instrutorId, semana, fimSemestre, editavel, versao }: {
  cenarioId: number; instrutorId: string; semana: string; fimSemestre?: string | null; editavel: boolean; versao?: unknown;
}) {
  const { aviso } = useApp();
  const [repetir, setRepetir] = useState(true);
  const [erro, setErro] = useState<any>(null);
  const [salvando, setSalvando] = useState(false);
  const ag = useCarregar<Agenda>(() => api.get(`/api/grade/agenda-instrutor${qs({ cenario_id: cenarioId, instrutor_id: instrutorId, semana })}`),
    [cenarioId, instrutorId, semana, versao]);
  const a = ag.dados;
  if (!a) return ag.erro ? <p className="aviso-inline">{ag.erro}</p> : null;
  const mensalista = a.instrutor.modalidade !== "horista";
  const cel = (dia: number, turno: number) => a.celulas.find((c) => c.dia === dia && c.turno_id === turno);

  const marcar = async (c: Celula, sigla: string) => {
    setErro(null); setSalvando(true);
    try {
      const r = await api.post(`/api/instrutores/${instrutorId}/agenda`, {
        cenario_id: cenarioId, data: c.data, turno_id: c.turno_id, sigla: sigla === "vazio" ? null : sigla,
        repetir_ate: repetir && fimSemestre ? fimSemestre : null,
      });
      const comAula = r.com_aula?.length ? ` ${r.com_aula.length} data(s) com aula ficaram como estão.` : "";
      aviso(sigla === "vazio" ? `Turno liberado em ${r.removidos} data(s).${comAula}` : `${sigla} marcado em ${r.marcados} data(s).${comAula}`);
      ag.recarregar();
    } catch (e) { setErro(e); } finally { setSalvando(false); }
  };

  const r = a.resumo;
  const carga = a.instrutor.carga_semanal_h;
  const pct = (h: number) => `${Math.min(100, (h / Math.max(carga, 1)) * 100)}%`;
  return (
    <section className="agenda-instrutor" aria-label="Agenda do instrutor na semana">
      <div className="agenda-topo">
        <h3>Agenda de {a.instrutor.nome} na semana</h3>
        <span className={`modalidade modalidade-${a.instrutor.modalidade}`}>{mensalista ? "Mensalista" : "Horista"} · {carga} h/sem</span>
      </div>
      <p className="sub">
        {mensalista
          ? "Mensalista: as horas são garantidas. Todo turno da jornada deve ter aula, planejamento (PL), projeto/outra atividade (PJ) ou treinamento (TR); turno vazio é hora paga sem atribuição."
          : "Horista: as horas não são garantidas. Turno sem aula pode ficar vazio (dispensa); PL, PJ e TR são opcionais."}
        {" "}O gerador de horários não coloca aula nos turnos marcados como PL, PJ ou TR. Em TR o instrutor está liberado para treinamento: não entra como substituto.
      </p>
      <div className="barra-carga" role="img" aria-label={`Aula ${r.aula_h} h, PL ${r.pl_h} h, PJ ${r.pj_h} h, TR ${r.tr_h ?? 0} h de ${carga} h`}>
        <span className="seg-aula" style={{ width: pct(r.aula_h) }} />
        <span className="seg-pl" style={{ width: pct(r.pl_h) }} />
        <span className="seg-pj" style={{ width: pct(r.pj_h) }} />
        <span className="seg-tr" style={{ width: pct(r.tr_h ?? 0) }} />
      </div>
      <ul className="resumo-carga">
        <li><i className="seg-aula" /> Aula: <b>{r.aula_h} h</b></li>
        <li><i className="seg-pl" /> PL: <b>{r.pl_h} h</b></li>
        <li><i className="seg-pj" /> PJ: <b>{r.pj_h} h</b></li>
        <li><i className="seg-tr" /> TR: <b>{r.tr_h ?? 0} h</b></li>
        {mensalista
          ? <li className={r.sem_atribuicao_h ? "alerta" : ""}><i className="seg-vazio" /> Sem atribuição: <b>{r.sem_atribuicao_h} h</b></li>
          : <li><i className="seg-vazio" /> Dispensa: <b>{r.dispensa_h} h</b></li>}
        <li>Total: <b>{r.ocupadas_h} / {carga} h</b>{r.excede_carga && <span className="alerta"> · acima da carga</span>}</li>
      </ul>
      {editavel && <label className="repetir">
        <input type="checkbox" checked={repetir} onChange={(e) => setRepetir(e.target.checked)} disabled={!fimSemestre} />
        {" "}Aplicar toda semana até o fim do semestre{fimSemestre ? ` (${dataBR(fimSemestre)})` : ""}
      </label>}
      <Erro erro={erro} />
      <div className="tabela-rolagem">
        <table className="agenda-tabela">
          <thead><tr><th>Turno</th>{a.dias.map((d) => <th key={d.dia}>{d.rotulo} {dataBR(d.data).slice(0, 5)}</th>)}</tr></thead>
          <tbody>
            {a.turnos.map((t) => (
              <tr key={t.id}>
                <th scope="row">{t.nome}<small>{t.horario}</small></th>
                {a.dias.map((d) => {
                  const c = cel(d.dia, t.id);
                  if (!c) return <td key={d.dia} />;
                  const livre = ["PL", "PJ", "TR", "vazio"].includes(c.estado);
                  return (
                    <td key={d.dia} className={`ag-${c.estado}`}>
                      {c.estado === "aula" && c.aulas?.map((x) => <div key={x.id}><b>{x.turma}</b> · {x.uc}</div>)}
                      {c.estado === "aula" && <small>{c.horas} h de aula</small>}
                      {livre && editavel ? (
                        <select aria-label={`${d.rotulo} ${t.nome}`} value={c.estado} disabled={salvando} onChange={(e) => marcar(c, e.target.value)}>
                          <option value="vazio">{mensalista ? "Vazio (sem atribuição)" : "Vazio (dispensa)"}</option>
                          <option value="PL">PL · Planejamento</option>
                          <option value="PJ">PJ · Projeto / outra</option>
                          <option value="TR">TR · Treinamento</option>
                        </select>
                      ) : livre && <span>{ROTULO[c.estado]}</span>}
                      {!livre && c.estado !== "aula" && <span title={c.descricao}>{ROTULO[c.estado]}</span>}
                      {c.descricao && ["PL", "PJ", "TR"].includes(c.estado) && !c.descricao.startsWith(({ PL: "Planejamento", PJ: "Projeto", TR: "Treinamento" } as any)[c.estado]) &&
                        <small>{c.descricao}</small>}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
