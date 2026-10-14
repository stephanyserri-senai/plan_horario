import { useEffect } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, dataBR } from "../api";
import { Pagina, useCarregar } from "../components/ui";
import { Anel } from "../components/Visual";
import { useApp } from "../contexto";
import { semestreDe } from "../semestre";

const ICONE: Record<string, string> = { ok: "✔", atencao: "!", andamento: "…", pendente: "", futuro: "" };
const ROTULO: Record<string, string> = { ok: "Concluído", atencao: "Requer atenção", andamento: "Em andamento", pendente: "A fazer", futuro: "Depois" };

/** Início: o semestre como fluxo de trabalho + visão geral + o que precisa de atenção. */
export default function Inicio() {
  const { cenario, pode } = useApp();
  const nav = useNavigate();
  const p = useCarregar<any>(() => cenario ? api.get(`/api/painel?cenario_id=${cenario.id}`) : Promise.resolve(null), [cenario?.id]);
  const gerando = p.dados?.etapas?.some((e: any) => e.chave === "gerar" && e.status === "andamento");
  useEffect(() => {
    if (!gerando) return;
    const t = setInterval(p.recarregar, 10000);
    return () => clearInterval(t);
  }, [gerando]);

  if (!cenario) return (
    <Pagina titulo="Bem-vindo(a)">
      <div className="card inicio-vazio">
        <h2>Comece criando o semestre a planejar</h2>
        <p>Unidades, áreas e turnos da instituição já estão cadastrados. Crie o semestre e depois cadastre cursos, instrutores, salas e turmas.</p>
        {pode("cenarios.criar") && <button className="btn btn-primario btn-grande" onClick={() => nav("/planejamento")}>+ Novo semestre</button>}
      </div>
    </Pagina>
  );
  const d = p.dados;
  const ind = d?.indicadores;
  const sem = d?.semestre;
  return (
    <Pagina titulo={`Semestre ${semestreDe(cenario)}`}
      descricao={sem ? `${sem.nome} · ${dataBR(sem.inicio)} a ${dataBR(sem.fim)}` : undefined}>
      {p.carregando && !d && <p role="status">Carregando o semestre…</p>}
      {p.erro && <div className="erro-box">{p.erro}</div>}
      {d && <>
        <section aria-label="Fluxo do semestre" className="fluxo-trabalho">
          {d.etapas.map((e: any, i: number) => {
            const proximo = d.proximo === e.chave;
            return (
              <div key={e.chave} className={`etapa etapa-${e.status} ${proximo ? "etapa-proxima" : ""}`}>
                <div className="etapa-cab">
                  <span className="etapa-num" aria-hidden="true">{ICONE[e.status] || i + 1}</span>
                  <div>
                    <div className="etapa-titulo">{e.titulo}</div>
                    <div className="etapa-status">{proximo ? "Próximo passo" : ROTULO[e.status]}</div>
                  </div>
                </div>
                <p className="etapa-detalhe">{e.detalhe}</p>
                {e.acao && e.link && <button className={`btn ${proximo ? "btn-primario" : ""}`} onClick={() => nav(e.link)}>{e.acao}</button>}
              </div>
            );
          })}
        </section>

        <div className="inicio-grid">
          <section className="card" aria-label="Visão geral">
            <h2>Visão geral</h2>
            <div className="inicio-visao">
              <Anel pct={ind.pct_com_horario} rotulo="Carga horária com horário" detalhe={`${ind.ch_com_horario_h} de ${ind.ch_total_h} h`} />
              <div className="inicio-numeros">
                <div><b>{ind.aulas}</b><span>aulas na grade</span></div>
                <div><b>{ind.turmas}</b><span>turmas · {ind.ucs} UCs</span></div>
                <div className={ind.turmas_atrasadas ? "tom-erro" : ind.turmas_em_risco ? "tom-alerta" : "tom-ok"}>
                  <b>{ind.turmas_atrasadas + ind.turmas_em_risco}</b><span>turma(s) atrasada(s) ou em risco</span></div>
                <div className={sem?.fim && ind.termino_previsto > sem.fim ? "tom-erro" : "tom-ok"}>
                  <b>{dataBR(ind.termino_previsto)}</b><span>término previsto (fim do semestre {dataBR(sem?.fim)})</span></div>
              </div>
            </div>
          </section>

          <section className="card" aria-label="Precisa de atenção">
            <h2>Precisa de atenção</h2>
            {d.atencao.length === 0 ? <p className="ok-txt">✔ Nada precisa de atenção agora.</p> :
              <ul className="lista-atencao">
                {d.atencao.map((a: any, i: number) => (
                  <li key={i} className={`tom-${a.tipo === "bloqueio" ? "erro" : a.tipo === "alerta" ? "alerta" : "ok"}`}>
                    <Link to={a.link}>{a.texto}</Link>
                  </li>
                ))}
              </ul>}
          </section>
        </div>

        <section aria-label="Atalhos" className="atalhos">
          {[["/grade", "▤", "Grade horária", "Ver e ajustar as aulas da semana"], ["/cronograma", "▬", "Cronograma (Gantt)", "Prazos e caminho crítico"],
            ["/acompanhamento", "📊", "Acompanhamento", "Turmas, instrutores e salas"], ["/indicadores", "📈", "Indicadores", "Ocupação por turno, dia e sala"]].map(([to, ic, t, sub]) => (
            <Link key={to} to={to} className="atalho"><span aria-hidden="true">{ic}</span><b>{t}</b><small>{sub}</small></Link>
          ))}
        </section>
      </>}
    </Pagina>
  );
}
