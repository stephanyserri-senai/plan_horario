import { useEffect, useMemo, useState } from "react";
import { api, DIAS, qs } from "../api";
import { useOpcoes } from "../hooks";

type Comp = { uc_id: number; nivel: string };
type Grupo = { curso_id: number; curso: string; area: string; ucs: { id: number; codigo: string; nome: string; ch: number; certificacao?: string }[] };

/** UCs dos cursos das áreas do instrutor, para marcar o que ele ministra (e se é sob supervisão). */
export function CompetenciasUCs({ valores, set, fonte }: { valores: any; set: (v: Comp[]) => void; fonte?: (areas: number[]) => string }) {
  const [grupos, setGrupos] = useState<Grupo[] | null>(null);
  const [filtro, setFiltro] = useState("");
  const areas = [valores.area_id, ...(valores.areas_ids || [])].filter(Boolean).map(Number);
  const chave = `${areas.join(",")}|${valores.todas_areas ? 1 : 0}|${valores.unidade_id || ""}`;
  useEffect(() => {
    if (!areas.length && !valores.todas_areas) { setGrupos([]); return; }
    api.get(fonte ? fonte(areas) : `/api/cadastros-apoio/ucs-por-area${qs({ areas: areas.join(","), todas: valores.todas_areas ? "true" : "", unidade_id: valores.unidade_id })}`)
      .then(setGrupos).catch(() => setGrupos([]));
  }, [chave]);
  const sel: Comp[] = valores.ucs_competencia || [];
  const mapa = useMemo(() => new Map(sel.map((c) => [Number(c.uc_id), c.nivel])), [sel]);
  const visiveis = new Set((grupos || []).flatMap((g) => g.ucs.map((u) => u.id)));
  const foraDasAreas = sel.filter((c) => !visiveis.has(Number(c.uc_id))).length;
  const marcar = (id: number, nivel: string | null) => set([...sel.filter((c) => Number(c.uc_id) !== id), ...(nivel ? [{ uc_id: id, nivel }] : [])]);
  const marcarCurso = (g: Grupo, on: boolean) => {
    const ids = new Set(g.ucs.map((u) => u.id));
    set([...sel.filter((c) => !ids.has(Number(c.uc_id))), ...(on ? g.ucs.map((u) => ({ uc_id: u.id, nivel: mapa.get(u.id) || "pleno" })) : [])]);
  };
  const f = filtro.trim().toLowerCase();
  return (
    <fieldset className="painel-campo">
      <legend>UCs que ministra <small>({sel.length} marcada{sel.length === 1 ? "" : "s"})</small></legend>
      {!areas.length && !valores.todas_areas ? <p className="sub">Escolha a área do instrutor para ver as UCs dos cursos dela.</p> : grupos === null ? <p className="sub">Carregando UCs…</p> :
        grupos.length === 0 ? <p className="sub">Nenhum curso com UCs cadastrado nesta(s) área(s) ainda.</p> : <>
          {grupos.reduce((n, g) => n + g.ucs.length, 0) > 12 && <input type="search" placeholder="Filtrar UC por código ou nome" aria-label="Filtrar UCs" value={filtro} onChange={(e) => setFiltro(e.target.value)} />}
          {grupos.map((g) => {
            const ucs = g.ucs.filter((u) => !f || `${u.codigo} ${u.nome}`.toLowerCase().includes(f));
            if (!ucs.length) return null;
            const todas = g.ucs.every((u) => mapa.has(u.id));
            return (
              <div key={g.curso + g.curso_id} className="grupo-ucs">
                <div className="grupo-ucs-cab"><b>{g.curso}</b> <small className="mudo">{g.area}</small>
                  <button type="button" className="btn-link" onClick={() => marcarCurso(g, !todas)}>{todas ? "Desmarcar todas" : "Marcar todas"}</button></div>
                {ucs.map((u) => {
                  const nivel = mapa.get(u.id);
                  return (
                    <div key={u.id} className={`linha-uc ${nivel ? "marcada" : ""}`}>
                      <label><input type="checkbox" checked={!!nivel} onChange={(e) => marcar(u.id, e.target.checked ? "pleno" : null)} />
                        <span><b>{u.codigo}</b> {u.nome} <small className="mudo">· {u.ch} h{u.certificacao ? ` · exige ${u.certificacao}` : ""}</small></span></label>
                      {nivel && <select aria-label={`Nível em ${u.codigo}`} value={nivel} onChange={(e) => marcar(u.id, e.target.value)}>
                        <option value="pleno">Ministra sozinho</option><option value="supervisionado">Sob supervisão</option><option value="em_formacao">Em formação</option></select>}
                    </div>
                  );
                })}
              </div>
            );
          })}
        </>}
      {foraDasAreas > 0 && <p className="sub">+ {foraDasAreas} UC(s) de outras áreas já habilitada(s) (mantidas).</p>}
    </fieldset>
  );
}

/** Turnos × dias em que o instrutor pode dar aula (substitui a disponibilidade cadastrada). */
export function DisponibilidadeTurnos({ valores, setVarios, turnosFixos }: { valores: any; setVarios: (v: Record<string, any>) => void; turnosFixos?: { id: number; rotulo: string }[] }) {
  const todosTurnos = useOpcoes(turnosFixos ? null : "turnos");
  const turnos = turnosFixos || todosTurnos.filter((t: any) => !valores.unidade_id || String(t.unidade_id) === String(valores.unidade_id));
  const sel: number[] = (valores.disp_turnos || []).map(Number);
  const dias: number[] = valores.disp_dias ?? [0, 1, 2, 3, 4];
  const mudar = (t: number[], d: number[]) => setVarios({ disp_turnos: t, disp_dias: d, __disp: true });
  const horas = Number(valores.max_horas_dia) || 8;
  const limite = Math.max(1, Math.floor(horas / 4));  // cada turno = 4 aulas
  return (
    <fieldset className="painel-campo">
      <legend>Quando pode dar aula</legend>
      {!valores.unidade_id ? <p className="sub">Escolha a unidade para ver os turnos.</p> : <>
        <p className="sub">Com <b>{horas} h de aula por dia</b> o instrutor pode ter até <b>{limite} turno{limite > 1 ? "s" : ""}</b> por dia.</p>
        <div className="checks"><span className="mudo">Turnos:</span>{turnos.map((t: any) => {
          const marcado = sel.includes(Number(t.id));
          const bloqueado = !marcado && sel.length >= limite;
          return <label key={t.id} className={bloqueado ? "desabilitado" : ""} title={bloqueado ? "Aumente as horas por dia para marcar mais turnos" : undefined}>
            <input type="checkbox" checked={marcado} disabled={bloqueado}
              onChange={(e) => mudar(e.target.checked ? [...sel, Number(t.id)] : sel.filter((x) => x !== Number(t.id)), dias)} /> {t.rotulo}</label>;
        })}</div>
        {sel.length > limite && <p className="sub tom-erro">⚠ {sel.length} turnos marcados, mas {horas} h por dia permitem {limite}. Desmarque um turno ou aumente as horas por dia.</p>}
        <div className="checks"><span className="mudo">Dias:</span>{DIAS.slice(0, 6).map((d, i) => (
          <label key={i}><input type="checkbox" checked={dias.includes(i)}
            onChange={(e) => mudar(sel, e.target.checked ? [...dias, i].sort() : dias.filter((x) => x !== i))} /> {d.slice(0, 3)}</label>))}</div>
        {valores.disp_personalizada && !valores.__disp && <p className="sub">Há horários personalizados cadastrados. Marcar turnos aqui substitui esses horários.</p>}
        {sel.length === 0 && !valores.disp_personalizada && <p className="sub">⚠ Sem turno marcado o instrutor não é escalado.</p>}
      </>}
    </fieldset>
  );
}

/** Mostra o código que a turma vai receber (sigla do curso + número + tipo). */
export function PreviaCodigoTurma({ valores }: { valores: any }) {
  const [p, setP] = useState<any>(null);
  useEffect(() => {
    if (!valores.curso_id) { setP(null); return; }
    const t = setTimeout(() => api.get(`/api/cadastros-apoio/codigo-turma${qs({ curso_id: valores.curso_id, numero: valores._numero || "", tipo: valores._tipo_oferta || "" })}`)
      .then(setP).catch(() => setP(null)), 250);
    return () => clearTimeout(t);
  }, [valores.curso_id, valores._numero, valores._tipo_oferta]);
  if (!valores.curso_id) return <p className="previa-codigo mudo">Escolha o curso: a área, a unidade e a matriz vêm dele.</p>;
  if (!p) return null;
  const repetido = p.existe && p.codigo !== valores.codigo;
  return (
    <p className={`previa-codigo ${repetido ? "tom-erro" : ""}`}>
      {p.codigo ? <>Código da turma: <b>{p.codigo}</b>{repetido && " — já existe uma turma com este código"}</> : <>Sigla do curso: <b>{p.sigla}</b> · digite o número da turma</>}
      {p.matriz ? <small className="mudo"> · matriz {p.matriz}</small> : <small className="tom-erro"> · o curso ainda não tem matriz</small>}
    </p>
  );
}

const JORNADAS: Record<string, string> = { M: "M – Manhã", V: "V – Tarde (vespertino)", N: "N – Noite", MV: "MV – Manhã e tarde", VN: "VN – Tarde e noite" };

export function horasPorDia(valores: any): number {
  const h = Number(valores.max_horas_dia);
  if (h > 0) return h;
  const c = Number(valores.carga_horaria_contratual);
  return c > 0 ? Math.min(12, Math.max(1, Math.round(c / 5))) : 8;
}

/** Turnos de trabalho do instrutor: 8 h por dia (40 h/semana) = dois turnos (MV ou VN); menos = um turno (M, V ou N). */
export function JornadaInstrutor({ valores, setVarios }: { valores: any; setVarios: (v: Record<string, any>) => void }) {
  const horas = horasPorDia(valores);
  const dois = horas >= 8;
  const opcoes = dois ? ["MV", "VN"] : ["M", "V", "N"];
  const dias: number[] = valores.disp_dias ?? [0, 1, 2, 3, 4];
  const atual = valores.jornada || "";
  const invalida = atual && !opcoes.includes(atual);
  const mudar = (j: string, d: number[]) => setVarios({ jornada: j, disp_dias: d, __disp: true });
  return (
    <fieldset className="painel-campo">
      <legend>Turnos de trabalho</legend>
      <p className="sub">{dois ? <>Com <b>{horas} h de aula por dia</b> o instrutor trabalha <b>dois turnos</b>: manhã e tarde (MV) ou tarde e noite (VN).</>
        : <>Com <b>{horas} h de aula por dia</b> o instrutor trabalha <b>um turno</b>: manhã (M), tarde (V) ou noite (N).</>}</p>
      <div className="jornadas" role="radiogroup" aria-label="Turnos de trabalho">
        {opcoes.map((j) => <label key={j} className={atual === j ? "marcada" : ""}>
          <input type="radio" name="jornada" checked={atual === j} onChange={() => mudar(j, dias)} /> {JORNADAS[j]}</label>)}
      </div>
      {invalida && <p className="sub tom-erro">⚠ "{JORNADAS[atual] || atual}" não combina com {horas} h por dia. Escolha uma das opções acima.</p>}
      {!atual && <p className="sub">⚠ Sem turnos de trabalho o instrutor não é escalado.</p>}
      {valores.disp_personalizada && !valores.__disp && <p className="sub">Há horários personalizados cadastrados; escolher os turnos aqui substitui esses horários.</p>}
      <div className="checks"><span className="mudo">Dias:</span>{DIAS.slice(0, 6).map((d, i) => (
        <label key={i}><input type="checkbox" checked={dias.includes(i)}
          onChange={(e) => mudar(atual, e.target.checked ? [...dias, i].sort() : dias.filter((x) => x !== i))} /> {d.slice(0, 3)}</label>))}</div>
    </fieldset>
  );
}
