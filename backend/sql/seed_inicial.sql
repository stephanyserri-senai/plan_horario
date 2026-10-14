-- Dados iniciais da Plataforma de Planejamento Acadêmico (gerado por scripts/gerar_seed_sql.py).
-- Aplique DEPOIS de schema_completo.sql. Pode ser executado mais de uma vez (idempotente).
BEGIN;

-- Permissões padrão de cada perfil
INSERT INTO permissoes_perfil (perfil, acao) VALUES ('administrador', 'cadastros.ler') ON CONFLICT DO NOTHING;
INSERT INTO permissoes_perfil (perfil, acao) VALUES ('administrador', 'cadastros.editar') ON CONFLICT DO NOTHING;
INSERT INTO permissoes_perfil (perfil, acao) VALUES ('administrador', 'alocacoes.ler') ON CONFLICT DO NOTHING;
INSERT INTO permissoes_perfil (perfil, acao) VALUES ('administrador', 'alocacoes.editar') ON CONFLICT DO NOTHING;
INSERT INTO permissoes_perfil (perfil, acao) VALUES ('administrador', 'cenarios.criar') ON CONFLICT DO NOTHING;
INSERT INTO permissoes_perfil (perfil, acao) VALUES ('administrador', 'cenarios.editar') ON CONFLICT DO NOTHING;
INSERT INTO permissoes_perfil (perfil, acao) VALUES ('administrador', 'cenarios.aprovar') ON CONFLICT DO NOTHING;
INSERT INTO permissoes_perfil (perfil, acao) VALUES ('administrador', 'cenarios.publicar') ON CONFLICT DO NOTHING;
INSERT INTO permissoes_perfil (perfil, acao) VALUES ('administrador', 'cenarios.restaurar') ON CONFLICT DO NOTHING;
INSERT INTO permissoes_perfil (perfil, acao) VALUES ('administrador', 'otimizacao.executar') ON CONFLICT DO NOTHING;
INSERT INTO permissoes_perfil (perfil, acao) VALUES ('administrador', 'simulacao.executar') ON CONFLICT DO NOTHING;
INSERT INTO permissoes_perfil (perfil, acao) VALUES ('administrador', 'indicadores.ler') ON CONFLICT DO NOTHING;
INSERT INTO permissoes_perfil (perfil, acao) VALUES ('administrador', 'importacao.executar') ON CONFLICT DO NOTHING;
INSERT INTO permissoes_perfil (perfil, acao) VALUES ('administrador', 'exportacao.executar') ON CONFLICT DO NOTHING;
INSERT INTO permissoes_perfil (perfil, acao) VALUES ('administrador', 'usuarios.gerenciar') ON CONFLICT DO NOTHING;
INSERT INTO permissoes_perfil (perfil, acao) VALUES ('administrador', 'configuracoes.editar') ON CONFLICT DO NOTHING;
INSERT INTO permissoes_perfil (perfil, acao) VALUES ('administrador', 'auditoria.ler') ON CONFLICT DO NOTHING;
INSERT INTO permissoes_perfil (perfil, acao) VALUES ('administrador', 'dados_pessoais.ler') ON CONFLICT DO NOTHING;
INSERT INTO permissoes_perfil (perfil, acao) VALUES ('administrador', 'excecoes.autorizar') ON CONFLICT DO NOTHING;
INSERT INTO permissoes_perfil (perfil, acao) VALUES ('administrador', 'aprendizado.gerenciar') ON CONFLICT DO NOTHING;
INSERT INTO permissoes_perfil (perfil, acao) VALUES ('planejador', 'cadastros.ler') ON CONFLICT DO NOTHING;
INSERT INTO permissoes_perfil (perfil, acao) VALUES ('planejador', 'cadastros.editar') ON CONFLICT DO NOTHING;
INSERT INTO permissoes_perfil (perfil, acao) VALUES ('planejador', 'alocacoes.ler') ON CONFLICT DO NOTHING;
INSERT INTO permissoes_perfil (perfil, acao) VALUES ('planejador', 'alocacoes.editar') ON CONFLICT DO NOTHING;
INSERT INTO permissoes_perfil (perfil, acao) VALUES ('planejador', 'cenarios.criar') ON CONFLICT DO NOTHING;
INSERT INTO permissoes_perfil (perfil, acao) VALUES ('planejador', 'cenarios.editar') ON CONFLICT DO NOTHING;
INSERT INTO permissoes_perfil (perfil, acao) VALUES ('planejador', 'otimizacao.executar') ON CONFLICT DO NOTHING;
INSERT INTO permissoes_perfil (perfil, acao) VALUES ('planejador', 'simulacao.executar') ON CONFLICT DO NOTHING;
INSERT INTO permissoes_perfil (perfil, acao) VALUES ('planejador', 'indicadores.ler') ON CONFLICT DO NOTHING;
INSERT INTO permissoes_perfil (perfil, acao) VALUES ('planejador', 'importacao.executar') ON CONFLICT DO NOTHING;
INSERT INTO permissoes_perfil (perfil, acao) VALUES ('planejador', 'exportacao.executar') ON CONFLICT DO NOTHING;
INSERT INTO permissoes_perfil (perfil, acao) VALUES ('planejador', 'dados_pessoais.ler') ON CONFLICT DO NOTHING;
INSERT INTO permissoes_perfil (perfil, acao) VALUES ('coordenador', 'cadastros.ler') ON CONFLICT DO NOTHING;
INSERT INTO permissoes_perfil (perfil, acao) VALUES ('coordenador', 'alocacoes.ler') ON CONFLICT DO NOTHING;
INSERT INTO permissoes_perfil (perfil, acao) VALUES ('coordenador', 'alocacoes.editar') ON CONFLICT DO NOTHING;
INSERT INTO permissoes_perfil (perfil, acao) VALUES ('coordenador', 'cenarios.criar') ON CONFLICT DO NOTHING;
INSERT INTO permissoes_perfil (perfil, acao) VALUES ('coordenador', 'cenarios.editar') ON CONFLICT DO NOTHING;
INSERT INTO permissoes_perfil (perfil, acao) VALUES ('coordenador', 'cenarios.aprovar') ON CONFLICT DO NOTHING;
INSERT INTO permissoes_perfil (perfil, acao) VALUES ('coordenador', 'cenarios.publicar') ON CONFLICT DO NOTHING;
INSERT INTO permissoes_perfil (perfil, acao) VALUES ('coordenador', 'cenarios.restaurar') ON CONFLICT DO NOTHING;
INSERT INTO permissoes_perfil (perfil, acao) VALUES ('coordenador', 'simulacao.executar') ON CONFLICT DO NOTHING;
INSERT INTO permissoes_perfil (perfil, acao) VALUES ('coordenador', 'indicadores.ler') ON CONFLICT DO NOTHING;
INSERT INTO permissoes_perfil (perfil, acao) VALUES ('coordenador', 'exportacao.executar') ON CONFLICT DO NOTHING;
INSERT INTO permissoes_perfil (perfil, acao) VALUES ('coordenador', 'auditoria.ler') ON CONFLICT DO NOTHING;
INSERT INTO permissoes_perfil (perfil, acao) VALUES ('coordenador', 'dados_pessoais.ler') ON CONFLICT DO NOTHING;
INSERT INTO permissoes_perfil (perfil, acao) VALUES ('coordenador', 'excecoes.autorizar') ON CONFLICT DO NOTHING;
INSERT INTO permissoes_perfil (perfil, acao) VALUES ('gestor', 'cadastros.ler') ON CONFLICT DO NOTHING;
INSERT INTO permissoes_perfil (perfil, acao) VALUES ('gestor', 'alocacoes.ler') ON CONFLICT DO NOTHING;
INSERT INTO permissoes_perfil (perfil, acao) VALUES ('gestor', 'indicadores.ler') ON CONFLICT DO NOTHING;
INSERT INTO permissoes_perfil (perfil, acao) VALUES ('gestor', 'simulacao.executar') ON CONFLICT DO NOTHING;
INSERT INTO permissoes_perfil (perfil, acao) VALUES ('gestor', 'exportacao.executar') ON CONFLICT DO NOTHING;
INSERT INTO permissoes_perfil (perfil, acao) VALUES ('gestor', 'auditoria.ler') ON CONFLICT DO NOTHING;
INSERT INTO permissoes_perfil (perfil, acao) VALUES ('consulta', 'cadastros.ler') ON CONFLICT DO NOTHING;
INSERT INTO permissoes_perfil (perfil, acao) VALUES ('consulta', 'alocacoes.ler') ON CONFLICT DO NOTHING;
INSERT INTO permissoes_perfil (perfil, acao) VALUES ('consulta', 'indicadores.ler') ON CONFLICT DO NOTHING;

-- Conjunto de pesos padrão do otimizador
INSERT INTO parametros_otimizacao (nome, pesos, limite_tempo_s, padrao, versao, ativo) VALUES ('Padrão', '{"demanda_nao_atendida": 1000.0, "prazos": 200.0, "janelas_instrutores": 10.0, "janelas_turmas": 15.0, "ocupacao_inadequada": 0.2, "deslocamentos": 30.0, "equilibrio_carga": 2.0, "concentracao_dias": 20.0, "preferencia_turno": 5.0, "aulas_isoladas": 10.0, "especializado_desnecessario": 8.0, "horarios_excepcionais": 15.0, "mudancas_vigente": 25.0, "preservar_aprovados": 40.0, "min_periodos_dia": 2}'::jsonb, 30, true, 1, true) ON CONFLICT (nome) DO NOTHING;

-- Configurações
INSERT INTO configuracoes (chave, valor, descricao) VALUES ('limiares_ocupacao', '{"subutilizado_pct": 30.0, "demanda_excessiva_pct": 85.0, "instrutor_critico_pct": 90.0}'::jsonb, 'Limiares para classificar ambientes subutilizados/sobrecarregados e instrutores críticos.') ON CONFLICT (chave) DO NOTHING;
INSERT INTO configuracoes (chave, valor, descricao) VALUES ('geral', '{"nome_instituicao": "", "fuso_horario": "America/Sao_Paulo"}'::jsonb, 'Parâmetros gerais da instituição.') ON CONFLICT (chave) DO NOTHING;

-- USUÁRIO DE TESTE (login: admin / senha: admin@123) — SOMENTE homologação.
-- Remova antes da produção: DELETE FROM usuarios WHERE email = 'admin' AND nome LIKE 'Administrador de TESTE%';
INSERT INTO usuarios (nome, email, senha_hash, perfil, acesso_global, ativo) VALUES ('Administrador de TESTE (remover antes da produção)', 'admin', '$2b$12$q4eiqN1koTX3FKXxJ/RS1Oe/ovSrXMFxMgJvKyfE6pAWupjF/57Ei', 'administrador', true, true) ON CONFLICT (email) DO NOTHING;

COMMIT;
