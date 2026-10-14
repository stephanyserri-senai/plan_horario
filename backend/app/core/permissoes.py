"""Catálogo de ações e perfis padrão. Os vínculos perfil→ação ficam na tabela
`permissoes_perfil` e podem ser alterados pelo administrador."""

ACOES = {
    "cadastros.ler": "Consultar cadastros",
    "cadastros.editar": "Incluir/alterar/inativar cadastros",
    "alocacoes.ler": "Consultar grade horária",
    "alocacoes.editar": "Alocar e alterar aulas",
    "cenarios.criar": "Criar cenários e propostas",
    "cenarios.editar": "Alterar cenários e mudar para validação",
    "cenarios.aprovar": "Aprovar ou reprovar cenários",
    "cenarios.publicar": "Publicar cenários aprovados",
    "cenarios.restaurar": "Restaurar versões anteriores",
    "otimizacao.executar": "Executar o gerador de horários",
    "simulacao.executar": "Executar simulações de capacidade",
    "indicadores.ler": "Consultar dashboard, capacidade e gargalos",
    "importacao.executar": "Importar planilhas",
    "exportacao.executar": "Exportar grades e relatórios",
    "usuarios.gerenciar": "Gerenciar usuários, perfis e escopos",
    "configuracoes.editar": "Alterar regras, pesos e parâmetros",
    "auditoria.ler": "Consultar auditoria",
    "dados_pessoais.ler": "Ver dados pessoais de instrutores",
    "excecoes.autorizar": "Autorizar exceções documentadas",
    "aprendizado.gerenciar": "Revisar registros de decisão para treinamento",
    "observacoes.gerenciar": "Ler e responder observações enviadas pelos instrutores",
    "portal.instrutor": "Portal do instrutor: atualizar os próprios dados e ver as próprias turmas",
}

PERFIS = ["administrador", "planejador", "coordenador", "gestor", "consulta", "instrutor"]

PADRAO = {
    "administrador": [a for a in ACOES if a != "portal.instrutor"],
    "planejador": [
        "cadastros.ler", "cadastros.editar", "alocacoes.ler", "alocacoes.editar", "cenarios.criar",
        "cenarios.editar", "otimizacao.executar", "simulacao.executar", "indicadores.ler",
        "importacao.executar", "exportacao.executar", "dados_pessoais.ler", "observacoes.gerenciar",
    ],
    "coordenador": [
        "cadastros.ler", "alocacoes.ler", "alocacoes.editar", "cenarios.criar", "cenarios.editar",
        "cenarios.aprovar", "cenarios.publicar", "cenarios.restaurar", "simulacao.executar",
        "indicadores.ler", "exportacao.executar", "auditoria.ler", "dados_pessoais.ler", "excecoes.autorizar",
        "observacoes.gerenciar",
    ],
    "gestor": ["cadastros.ler", "alocacoes.ler", "indicadores.ler", "simulacao.executar", "exportacao.executar", "auditoria.ler"],
    "consulta": ["cadastros.ler", "alocacoes.ler", "indicadores.ler"],
    # O instrutor só acessa o portal: os próprios dados, as próprias turmas e as próprias observações.
    "instrutor": ["portal.instrutor"],
}
