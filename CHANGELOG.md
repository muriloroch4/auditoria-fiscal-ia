# Changelog

Todas as mudancas relevantes deste projeto devem ser registradas aqui.

O formato segue uma versao simplificada de "Keep a Changelog": novas mudancas entram em "Nao publicado" e podem ser agrupadas por versao quando houver release formal.

## Nao publicado

### Adicionado

- Teste automatizado para garantir que os codigos documentados em `REGRAS.md` e configurados em `config/rules.json` tenham cobertura consultiva em `config/consultivo_por_regra.json`.
- Validacao automatizada de sintaxe dos arquivos `src/auditoria/static/app*.js`.
- Medicao de cobertura Python no CI com `coverage.py`.
- Configuracao de cobertura no `pyproject.toml`.
- Campo `conclusao_tecnica.orientacao_consultiva` no JSON trimestral v3.2.0 para orientar relatórios consultivos sem depender de termos formais como "adversa" ou "com ressalva".
- Módulos `annual_consultivo.py` e `annual_report.py` para separar consolidação anual, camada consultiva e renderização Markdown.
- Módulos `annual_metrics.py` e `annual_findings.py` para separar métricas/RBT12 e achados anuais.
- Arquivos `app-utils.js`, `app-dashboard.js`, `app-print.js` e `app-annual.js` para reduzir o arquivo principal do dashboard sem etapa de build.
- Teste Playwright opcional para validar upload no dashboard, ausência de overflow horizontal, HTML de impressão e screenshots não vazios.

### Alterado

- Autenticacao da API passou a comparar a chave enviada com `hmac.compare_digest`.
- Dashboard, relatório local, prompts e documentação passaram a priorizar linguagem consultiva de orientação técnica.
- Validação de JSON Schema passou a usar `jsonschema` quando disponível, mantendo fallback interno para ambientes sem dependência instalada.
- Consolidação anual passou a validar JSONs trimestrais formais contra o schema antes de montar o anual, preservando compatibilidade com payload legado.
- API exposta em host não local passou a exigir API key e CORS restrito, salvo override explícito de laboratório.

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
