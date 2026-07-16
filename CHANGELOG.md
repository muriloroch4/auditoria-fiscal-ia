# Changelog

Todas as mudancas relevantes deste projeto devem ser registradas aqui.

O formato segue uma versao simplificada de "Keep a Changelog": novas mudancas entram em "Nao publicado" e podem ser agrupadas por versao quando houver release formal.

## Nao publicado

### Adicionado

- Campos `pontuacao_bruta`, `pontuacao_maxima_aplicavel` e `escala_pontuacao` no JSON trimestral v3.3.0 e no JSON anual `annual-1.2.0`.
- Regras `SN-027` para contas patrimoniais com natureza inversa e `SN-028` para empréstimos sem evidência de juros/encargos por competência.
- Teste automatizado para garantir que os codigos documentados em `REGRAS.md` e configurados em `config/rules.json` tenham cobertura consultiva em `config/consultivo_por_regra.json`.
- Validacao automatizada de sintaxe dos arquivos `src/auditoria/static/app*.js`.
- Medicao de cobertura Python no CI com `coverage.py`.
- Configuracao de cobertura no `pyproject.toml`.
- Campo `conclusao_tecnica.orientacao_consultiva` no JSON trimestral para orientar relatórios consultivos sem depender de termos formais como "adversa" ou "com ressalva".
- Módulos `annual_consultivo.py` e `annual_report.py` para separar consolidação anual, camada consultiva e renderização Markdown.
- Módulos `annual_metrics.py` e `annual_findings.py` para separar métricas/RBT12 e achados anuais.
- Arquivos `app-utils.js`, `app-dashboard.js`, `app-print.js` e `app-annual.js` para reduzir o arquivo principal do dashboard sem etapa de build.
- Teste Playwright opcional para validar upload no dashboard, ausência de overflow horizontal, HTML de impressão e screenshots não vazios.

### Alterado

- Defaults internos de regras, mapa contábil e anexos foram movidos para `config_defaults.py`, deixando `config_loader.py` focado em leitura/cache.
- Pontuação executiva trimestral e anual passou a ser normalizada em escala de 0 a 100, mantendo a pontuação bruta apenas como trilha técnica.
- Mapa contábil passou a reconhecer empréstimos/financiamentos e contas de juros/encargos financeiros por descrição.
- Autenticacao da API passou a comparar a chave enviada com `hmac.compare_digest`.
- Dashboard, relatório local, prompts e documentação passaram a priorizar linguagem consultiva de orientação técnica.
- Validação de JSON Schema passou a usar `jsonschema` quando disponível, mantendo fallback interno para ambientes sem dependência instalada.
- Consolidação anual passou a validar JSONs trimestrais formais contra o schema antes de montar o anual, preservando compatibilidade com payload legado.
- API exposta em host não local passou a exigir API key e CORS restrito, salvo override explícito de laboratório.

- Evidencias com listas de contas passaram a priorizar materialidade antes de truncar a exibicao, evitando ocultar contas relevantes quando ha muitos itens no mesmo achado.
- Evidencia da regra `SN-011A` passou a separar o percentual de relevancia do limite calculado em reais, evitando rotulo de percentual com valor monetario.
- Validador interno de JSON Schema passou a cobrir combinadores, limites de arrays/textos, padroes e referencias invalidas quando `jsonschema` nao esta disponivel.
- CLI passou a oferecer `--ascii-output` para gerar arquivos sem acentos/caracteres especiais em integracoes legadas.
- Relatorio consultivo local ganhou testes dedicados de estrutura/fallback e `report_ai.py` teve helpers legados sem uso removidos para reduzir manutencao.
- Renderizacao Markdown local foi movida para `report_local.py` e a montagem do payload de prompt para `report_payload.py`, deixando `report_ai.py` focado na decisao IA/fallback.
- Serializacao trimestral foi separada em `serializer_common.py`, `serializer_sections.py` e `serializer_consultivo.py`, deixando `serializers.py` focado na orquestracao do schema.
- Payloads auxiliares da API foram movidos para `api_payloads.py`, deixando `api.py` mais focado no servidor HTTP.
- Estilos de impressao/PDF foram separados de `styles.css` para `static/print.css`, reduzindo o CSS principal do dashboard.
- Renderizadores internos do documento de impressao/PDF foram separados em `app-print-sections.js`, mantendo `app-print.js` como composicao e acionamento da impressao.
- Refinamentos visuais do dashboard foram separados para `static/dashboard.css`, deixando `styles.css` como base visual.
- Renderizadores do dashboard trimestral foram separados em `app-dashboard-summary.js` e `app-dashboard-sections.js`, deixando `app-dashboard.js` apenas como composição da tela.
- Parser de multipart da API e leitor baixo nivel de XLSX foram movidos para modulos dedicados, reduzindo `api.py` e `parser.py`.
- Classificacao de contas foi movida para `account_classifier.py`, deixando `parser.py` focado na leitura dos arquivos.
- Contexto tributario do Simples Nacional foi movido para `tax_context.py`, deixando `audit.py` mais focado na orquestracao da auditoria.
- Regras financeiras de caixa, recebiveis e adiantamentos foram movidas para `rules/financeiro.py`, reduzindo o orquestrador do Simples Nacional.
- Regras patrimoniais `SN-027` e `SN-028` foram movidas para `rules/patrimonial.py`, reduzindo o tamanho de `simples_servicos.py`.
- Regras fiscais gerais, societarias e de resultado/despesas foram movidas para `rules/fiscal.py`, `rules/societario.py` e `rules/resultado.py`, deixando `simples_servicos.py` como orquestrador.
- Helpers de entrada, JSON, RBT12 salvo e runtime da API foram movidos para `api_helpers.py` e `api_runtime.py`, reduzindo o tamanho de `api.py`.
- Parser de balancetes foi separado em fachada (`parser.py`), parser Domínio (`dominio_parser.py`), normalização tabular (`parser_records.py`/`parser_tables.py`) e conversor XLS (`xls_converter.py`).

## Historico consolidado

### Adicionado

- Motor de pre-auditoria fiscal/contabil trimestral para empresas do Simples Nacional.
- Regras especificas para servicos, comercio e empresas mistas.
- Consolidador anual com base nos quatro trimestres salvos.
- Persistencia local em SQLite para auditorias trimestrais e consolidacoes anuais.
- Dashboard web com upload de balancete, leitura consultiva, achados, recomendacoes, classificacao de contas e impressao em PDF pelo navegador.
- Schemas JSON formais para auditoria trimestral e anual.
- Prompts consultivos para geracao de relatorios trimestrais e anuais a partir do JSON.
- Testes automatizados para parser, motor de regras, serializacao, API, schemas e qualidade textual.

### Alterado

- Saida trimestral ajustada para schema resumido e consultivo, com foco em orientacao ao contador e ao cliente.
- Relatorios passaram de parecer tecnico formal para relatorio consultivo de pre-auditoria fiscal/contabil.
- Regras de Simples Nacional foram ampliadas com Fator R, anexos, RBT12 real quando disponivel, margem, caixa, clientes, fornecedores, estoque, socios, mutuos, IOF, servicos de terceiros e adiantamento de clientes.
- Layout do dashboard e da impressao foi refinado para leitura mais profissional.

### Corrigido

- Serializacao de `Decimal` para JSON.
- Inconsistencias de encoding e mojibake em textos do projeto.
- Compatibilidade entre JSON gerado, prompts consultivos e schemas formais.
