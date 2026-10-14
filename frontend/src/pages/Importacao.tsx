import { useState } from "react";
import { api, baixar } from "../api";
import { Badge, Campo, Card, Erro, Pagina, Tabela, useCarregar } from "../components/ui";
import { useApp } from "../contexto";

const TIPOS = ["unidades", "cursos", "matrizes", "ucs", "turmas", "turma_ucs", "instrutores", "competencias", "ambientes", "disponibilidade_instrutores", "aulas"];

export default function Importacao() {
  const { cenarios, cenario, aviso } = useApp();
  const [arquivo, setArquivo] = useState<File | null>(null);
  const [tipo, setTipo] = useState("");
  const [cen, setCen] = useState<string>("");
  const [previa, setPrevia] = useState<any | null>(null);
  const [mapa, setMapa] = useState<Record<string, string | null>>({});
  const [erro, setErro] = useState<any>(null);
  const [rel, setRel] = useState<any | null>(null);
  const [filtroAcao, setFiltroAcao] = useState("");
  const hist = useCarregar<any[]>(() => api.get("/api/importacao"), []);
  const enviar = async () => {
    if (!arquivo) return;
    setErro(null); setRel(null);
    const f = new FormData();
    f.append("arquivo", arquivo);
    if (tipo) f.append("tipo", tipo);
    if (cen || cenario) f.append("cenario_id", cen || String(cenario?.id));
    try { const p = await api.upload("/api/importacao/previa", f); setPrevia(p); setMapa(p.mapeamento); setTipo(p.tipo); } catch (e) { setErro(e); }
  };
  const remapear = async (extra: any = {}) => {
    try { const p = await api.post(`/api/importacao/${previa.id}/remapear`, { mapeamento: mapa, tipo, planilha: previa.planilha, ...extra }); setPrevia(p); setMapa(p.mapeamento); } catch (e) { setErro(e); }
  };
  const confirmar = async (ignorar: boolean) => {
    setErro(null);
    try { const r = await api.post(`/api/importacao/${previa.id}/confirmar`, { ignorar_erros: ignorar }); setRel(r); aviso("Importação gravada."); setPrevia(null); hist.recarregar(); } catch (e) { setErro(e); }
  };
  const itens = (previa?.itens || []).filter((i: any) => !filtroAcao || i.acao === filtroAcao);
  return (
    <Pagina titulo="Importação de planilhas" descricao="XLSX ou CSV: identificação da estrutura, mapeamento revisável de colunas, validação de relacionamentos, prévia, correção e confirmação.">
      <Card titulo="1. Selecionar arquivo">
        <div className="form-grid">
          <Campo rotulo="Arquivo (.xlsx, .csv)"><input type="file" accept=".xlsx,.xlsm,.csv,.txt" onChange={(e) => setArquivo(e.target.files?.[0] || null)} /></Campo>
          <Campo rotulo="Tipo de dados" ajuda="Vazio = identificar pelos cabeçalhos"><select value={tipo} onChange={(e) => setTipo(e.target.value)}><option value="">Detectar automaticamente</option>{TIPOS.map((t) => <option key={t}>{t}</option>)}</select></Campo>
          <Campo rotulo="Cenário de destino (aulas)" ajuda="Somente cenários em elaboração; horários publicados nunca são sobrescritos.">
            <select value={cen} onChange={(e) => setCen(e.target.value)}><option value="">Cenário atual</option>{cenarios.filter((c) => c.estado === "em_elaboracao").map((c) => <option key={c.id} value={c.id}>{c.nome}</option>)}</select></Campo>
        </div>
        <div className="acoes"><button className="btn btn-primario" disabled={!arquivo} onClick={enviar}>Gerar prévia</button>
          {tipo && <button className="btn" onClick={() => baixar(`/api/importacao/modelo/${tipo}`, `modelo_${tipo}.xlsx`)}>Baixar modelo de “{tipo}”</button>}</div>
        <Erro erro={erro} />
      </Card>
      {previa && <>
        <Card titulo={`2. Mapeamento de colunas — tipo “${previa.tipo}”`}>
          {previa.arquivo_ja_processado && <p className="aviso-inline"><Badge tipo="alerta">Arquivo já importado</Badge> Este arquivo (mesmo conteúdo) foi confirmado na importação #{previa.arquivo_ja_processado.importacao_id}. Registros existentes serão reconhecidos pela chave e não duplicados.</p>}
          {previa.planilhas.length > 1 && <Campo rotulo="Planilha"><select value={previa.planilha} onChange={(e) => remapear({ planilha: e.target.value })}>{previa.planilhas.map((p: string) => <option key={p}>{p}</option>)}</select></Campo>}
          <div className="form-grid">{Object.entries(previa.campos).map(([campo, info]: any) => (
            <Campo key={campo} rotulo={campo} obrigatorio={info.obrigatorio}><select value={mapa[campo] ?? ""} onChange={(e) => setMapa({ ...mapa, [campo]: e.target.value || null })}>
              <option value="">(não importar)</option>{previa.cabecalhos.map((c: string) => <option key={c}>{c}</option>)}</select></Campo>))}</div>
          <button className="btn" onClick={() => remapear()}>Aplicar mapeamento e revalidar</button>
        </Card>
        <Card titulo="3. Prévia e validação">
          <p>{Object.entries(previa.resumo).map(([k, v]) => <Badge key={k} tipo={k === "erro" ? "bloqueio" : k === "criar" ? "ok" : "info"}>{k}: {String(v)}</Badge>)}</p>
          <select aria-label="Filtrar ação" value={filtroAcao} onChange={(e) => setFiltroAcao(e.target.value)}><option value="">Todas as linhas</option>{["criar", "atualizar", "sem_alteracao", "erro"].map((a) => <option key={a}>{a}</option>)}</select>
          <Tabela colunas={[{ chave: "linha", rotulo: "Linha" }, { chave: "acao", rotulo: "Ação", render: (i: any) => <Badge tipo={i.acao === "erro" ? "bloqueio" : i.acao === "criar" ? "ok" : "info"}>{i.acao}</Badge> },
            { chave: "valores", rotulo: "Valores", render: (i: any) => <small>{Object.entries(i.valores).filter(([, v]) => v != null).map(([k, v]) => `${k}=${v}`).join(" · ")}</small> },
            { chave: "erros", rotulo: "Erros / avisos", render: (i: any) => <small>{[...i.erros, ...i.avisos].join("; ")}</small> }]} linhas={itens.slice(0, 500)} chave={(i) => i.linha} />
          <p className="sub">Corrija o arquivo e gere nova prévia, ajuste o mapeamento, ou confirme ignorando as linhas com erro (elas constarão no relatório).</p>
          <div className="acoes"><button className="btn btn-primario" disabled={previa.resumo.erro > 0} onClick={() => confirmar(false)}>Confirmar importação</button>
            {previa.resumo.erro > 0 && <button className="btn" onClick={() => confirmar(true)}>Confirmar ignorando {previa.resumo.erro} linha(s) com erro</button>}
            <button className="btn" onClick={async () => { await api.post(`/api/importacao/${previa.id}/descartar`); setPrevia(null); hist.recarregar(); }}>Descartar</button></div>
        </Card>
      </>}
      {rel && <Card titulo="Resultado"><p>Criados: {rel.criados} · Atualizados: {rel.atualizados} · Sem alteração: {rel.sem_alteracao} · Ignorados por erro: {rel.ignorados_por_erro}</p>
        {rel.aulas_bloqueadas?.length > 0 && <><h3>Aulas bloqueadas pela validação</h3><ul>{rel.aulas_bloqueadas.map((b: any, i: number) => <li key={i}>Linha {b.linha}: {b.motivo} {(b.ocorrencias || []).map((o: any) => o.descricao).join("; ")}</li>)}</ul></>}</Card>}
      <Card titulo="Histórico de importações">
        <Tabela colunas={[{ chave: "id", rotulo: "#" }, { chave: "arquivo", rotulo: "Arquivo" }, { chave: "tipo", rotulo: "Tipo" }, { chave: "status", rotulo: "Status" },
          { chave: "criado_em", rotulo: "Enviado", render: (i: any) => new Date(i.criado_em).toLocaleString("pt-BR") }, { chave: "hash", rotulo: "SHA-256", render: (i: any) => <code>{i.hash.slice(0, 12)}…</code> },
          { chave: "r", rotulo: "Relatório", render: (i: any) => <button className="btn-link" onClick={() => baixar(`/api/importacao/${i.id}/relatorio?formato=xlsx`, `importacao_${i.id}.xlsx`)}>XLSX</button> }]}
          linhas={hist.dados || []} />
      </Card>
    </Pagina>
  );
}
