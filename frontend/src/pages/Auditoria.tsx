import { useState } from "react";
import { api, qs } from "../api";
import { Pagina, Paginacao, Tabela, useCarregar } from "../components/ui";
import { Diferenca } from "./Cadastro";

export default function Auditoria() {
  const [f, setF] = useState<any>({ acao: "", entidade: "", inicio: "", fim: "" });
  const [pagina, setPagina] = useState(1);
  const d = useCarregar<any>(() => api.get(`/api/auditoria${qs({ ...f, pagina, por_pagina: 50 })}`), [JSON.stringify(f), pagina]);
  return (
    <Pagina titulo="Auditoria" descricao="Cadastros, importações, alocações, pesos, execuções do otimizador, aprovações, publicações, exportações e acessos.">
      <div className="filtros">
        <select aria-label="Ação" value={f.acao} onChange={(e) => { setF({ ...f, acao: e.target.value }); setPagina(1); }}>
          <option value="">Todas as ações</option>{["cadastro", "alocacao", "atividade", "cenario", "otimizacao", "importacao", "exportacao", "pesos", "configuracao", "simulacao", "usuario", "perfil", "excecao", "auth", "aprendizado"].map((a) => <option key={a}>{a}</option>)}</select>
        <input placeholder="Entidade (tabela)" aria-label="Entidade" value={f.entidade} onChange={(e) => setF({ ...f, entidade: e.target.value })} />
        <label>De <input type="date" value={f.inicio} onChange={(e) => setF({ ...f, inicio: e.target.value })} /></label>
        <label>Até <input type="date" value={f.fim} onChange={(e) => setF({ ...f, fim: e.target.value })} /></label>
      </div>
      <Tabela colunas={[{ chave: "em", rotulo: "Quando", render: (h: any) => new Date(h.em).toLocaleString("pt-BR") }, { chave: "usuario_nome", rotulo: "Usuário" },
        { chave: "acao", rotulo: "Ação" }, { chave: "entidade", rotulo: "Entidade" }, { chave: "entidade_id", rotulo: "ID" }, { chave: "origem", rotulo: "Origem" },
        { chave: "motivo", rotulo: "Motivo" }, { chave: "d", rotulo: "Detalhe", render: (h: any) => <Diferenca antes={h.antes} depois={h.depois} /> }]} linhas={d.dados?.itens || []} />
      {d.dados && <Paginacao pagina={pagina} total={d.dados.total} porPagina={50} mudar={setPagina} />}
    </Pagina>
  );
}
