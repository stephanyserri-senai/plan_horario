import { useEffect } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, dataBR } from "../api";
import { Pagina, useCarregar } from "../components/ui";
import { useOpcoes } from "../hooks";
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

  if (!cenario) return <BoasVindas criar={pode("cenarios.criar") ? () => nav("/planejamento") : undefined} />;
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
            ["/acompanhamento", "📊", "Ocupação e andamento", "Taxas de ocupação, turmas, instrutores e salas"]].map(([to, ic, t, sub]) => (
            <Link key={to} to={to} className="atalho"><span aria-hidden="true">{ic}</span><b>{t}</b><small>{sub}</small></Link>
          ))}
        </section>
      </>}
    </Pagina>
  );
}

const PASSOS: [string, string, string][] = [
  ["🗓️", "Crie o semestre", "Defina o período letivo que será planejado."],
  ["📥", "Cadastre ou importe", "Cursos e UCs, salas e laboratórios, instrutores e turmas — por planilha ou formulário."],
  ["⚙️", "Gere a grade", "O sistema distribui as aulas respeitando turnos, áreas, disponibilidade e pré-requisitos."],
  ["✅", "Ajuste, acompanhe e publique", "Revise conflitos, acompanhe o Gantt e publique o horário."],
];
const TURNOS: [string, string, string, string][] = [
  ["☀️", "Manhã", "4 aulas de 55 min", "intervalo 9h20–9h40"],
  ["🌤️", "Tarde", "4 aulas de 55 min", "intervalo 15h20–15h40"],
  ["🌙", "Noite", "4 aulas de 50 min", "intervalo 20h00–20h10"],
];

/** Tela de boas-vindas quando ainda não há semestre: apresenta o fluxo, a estrutura fixa e o andamento dos cadastros. */
function BoasVindas({ criar }: { criar?: () => void }) {
  const unidades = useOpcoes("unidades");
  const areas = useOpcoes("areas");
  const cadastros: [string, string, string, any[]][] = [
    ["📚", "Cursos", "/cadastros/cursos", useOpcoes("cursos")],
    ["🏫", "Salas e laboratórios", "/cadastros/ambientes", useOpcoes("ambientes")],
    ["👩‍🏫", "Instrutores", "/cadastros/instrutores", useOpcoes("instrutores")],
    ["👥", "Turmas", "/cadastros/turmas", useOpcoes("turmas")],
  ];
  return (
    <div className="boas-vindas">
      <section className="hero">
        <div className="hero-texto">
          <span className="hero-selo">Planejamento Acadêmico</span>
          <h1>Bem-vindo(a)! Vamos montar o próximo semestre.</h1>
          <p>Unidades, áreas e turnos da instituição já estão prontos. Crie o semestre e, em seguida, cadastre ou importe cursos, salas, instrutores e turmas — o sistema cuida da grade.</p>
          <div className="acoes">
            {criar && <button className="btn btn-primario btn-grande" onClick={criar}>+ Novo semestre</button>}
            <Link className="btn btn-grande btn-claro" to="/importacao">📥 Importar planilhas</Link>
          </div>
        </div>
        <img className="hero-icone" src="/icone.png" alt="" width={168} height={168} />
      </section>

      <section aria-label="Como funciona" className="passos">
        {PASSOS.map(([ic, t, d], i) => (
          <div key={t} className="passo">
            <div className="passo-ico" aria-hidden="true">{ic}</div>
            <div className="passo-num">Passo {i + 1}</div>
            <b>{t}</b>
            <p>{d}</p>
          </div>
        ))}
      </section>

      <div className="bv-grid">
        <section className="card">
          <h2>Seus cadastros</h2>
          <p className="sub">Comece pela estrutura curricular; depois salas, instrutores e turmas.</p>
          <div className="bv-cadastros">
            {cadastros.map(([ic, t, to, ops]) => (
              <Link key={to} to={to} className={`bv-cad ${ops.length ? "tem" : ""}`}>
                <span aria-hidden="true">{ic}</span><b>{ops.length}</b><small>{t}</small>
              </Link>
            ))}
          </div>
        </section>
        <section className="card">
          <h2>Turnos oficiais</h2>
          <p className="sub">Cada UC ocupa o turno inteiro do dia; só divide o dia ao fechar a carga horária.</p>
          <ul className="bv-turnos">
            {TURNOS.map(([ic, t, a, i]) => <li key={t}><span aria-hidden="true">{ic}</span><b>{t}</b><span>{a}</span><small>{i}</small></li>)}
          </ul>
        </section>
      </div>

      <section className="card">
        <h2>Unidades e áreas tecnológicas</h2>
        <div className="bv-unidades">
          {unidades.map((u: any) => (
            <div key={u.id} className="bv-unidade">
              <h3>📍 {u.rotulo}</h3>
              <div className="chips">{areas.filter((a: any) => a.unidade_id === u.id).map((a: any) => <span key={a.id} className="chip">{a.rotulo}</span>)}</div>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
