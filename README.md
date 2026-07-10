# Auditoria Fiscal IA — Pré-auditoria para Simples Nacional

Motor de regras fiscais para análise de balancetes trimestrais de empresas optantes pelo Simples Nacional, com conjuntos para serviços, comércio e empresas mistas de comércio e serviços. O motor extrai métricas do balancete, aplica regras de risco configuráveis e produz um JSON resumido (schema v3.0.0) para geração de parecer técnico consultivo objetivo ou envio direto ao cliente.

## Esquema de saída (v3.0.0)

```json
{
  "identificacao_empresa": {
    "cnpj": "00.000.000/0001-00",
    "regime_tributario": "Simples Nacional",
    "periodo_analisado": "2026-T1"
  },
  "resumo_analise": {
    "empresa": "Cliente Exemplo",
    "base_analise": "JSON de auditoria trimestral",
    "total_regras_verificadas": 17,
    "total_regras_acionadas": 7,
    "risco_geral": "alto",
    "pontuacao_total": 62,
    "achados_por_severidade": { "alta": 3, "media": 3, "baixa": 0 },
    "principais_pontos": ["SN-004A: Distribuição de lucros acima do lucro disponível identificado."]
  },
  "principais_achados": [
    {
      "codigo": "SN-004A",
      "severidade": "alta",
      "achado": "Distribuição de lucros acima do lucro disponível identificado",
      "evidencia_identificada": "Lucros distribuídos: R$ 65.000,00; lucro apurado: R$ -35.000,00",
      "impacto_tecnico": "Risco societário e fiscal por distribuição sem lastro contábil suficiente.",
      "pontuacao": 32,
      "norma_fundamento": ["Lei Complementar nº 123/2006, art. 14", "NBC TG 1000 (R1)"]
    }
  ],
  "fundamentacao_tecnica_resumida": {
    "normas_aplicaveis": ["Resolução CFC n.º 1.244/2009", "NBC PG 100 (R1) de 2018", "Lei Complementar nº 123/2006"],
    "texto_resumido": "A fundamentação técnica considera as normas aplicáveis aos achados acionados pelo motor de regras.",
    "observacoes_tecnicas": ["Validar enquadramento, anexo aplicável, Fator R e escrituração com documentação fiscal."]
  },
  "conclusao_tecnica": {
    "risco_geral": "alto",
    "conclusao_sugerida": "adversa",
    "ressalva_base_json": true,
    "necessita_validacao_documental": true,
    "texto_conclusivo": "Com base exclusivamente no JSON de auditoria trimestral, os achados indicam risco técnico elevado."
  },
  "recomendacoes_tecnicas": [
    {
      "ordem": 1,
      "descricao": "Validar escrituração completa, lucros acumulados, reservas e documentação societária.",
      "area_relacionada": "societária",
      "prioridade": "alta"
    }
  ],
  "metadados": {
    "data_analise": "2026-05-26T10:30:00",
    "versao_schema": "3.0.0",
    "versao_regras": "1.x.x",
    "conjunto_regras": "simples_servicos"
  }
}
```

Conjuntos disponíveis em `metadados.conjunto_regras`: `simples_servicos`, `simples_comercio` e `simples_comercio_servicos`.

O JSON formal validado pelo schema é o contrato para pareceres e integrações. A resposta do endpoint `POST /api/auditorias` também inclui um bloco auxiliar `dashboard` com métricas completas, contexto tributário e totais operacionais usados apenas pela interface web. O botão **JSON** do dashboard remove esse bloco auxiliar e baixa somente o payload formal `v3.0.0`.

As tabelas estruturadas dos anexos usados pelo contexto tributário ficam em `config/simples_anexos.json`. O motor estima Anexo I para comércio, Anexo III ou V para serviços conforme Fator R trimestral, e exige segregação para empresas mistas. A estimativa não substitui RBT12 oficial, CNAE, PGDAS-D e validação documental.

Quando os quatro trimestres estão salvos no backend para o mesmo CNPJ/ano, o motor passa a usar o RBT12 consolidado pelo histórico para contexto tributário, regra de limite do Simples (`SN-001`) e sublimite de comércio (`SN-019`). Sem os quatro trimestres, ele mantém `receita x 4` apenas como alerta.

## Como rodar

Requisitos: Python 3.11+

Dependências:

```powershell
python -m pip install -r requirements.txt
```

O runtime atual usa apenas a biblioteca padrão do Python. O arquivo `requirements.txt` existe para deixar o onboarding e a CI explícitos. A leitura de `.xlsx` é feita por parser interno baseado em `zipfile`; `openpyxl`/`xlrd` não são obrigatórios no estado atual do projeto.

Para desenvolvimento local:

```powershell
python -m pip install -r requirements-dev.txt
python -m unittest discover -v
python -m mypy src/auditoria --config-file pyproject.toml
```

### Servidor web (recomendado)

```powershell
python -m src.auditoria.api --port 8000
```

Acesse `http://127.0.0.1:8000` — faça upload do balancete e veja o dashboard/JSON de saída. Botões **JSON** e **PDF** permitem baixar o JSON formal e salvar o dashboard em PDF pelo navegador.

Endpoint JSON:
```text
POST /api/auditorias
Content-Type: multipart/form-data
campos: cliente, cnpj, periodo, balancete
campo opcional: atividade = servicos | comercio | comercio_servicos
```

Schema de saída:
```text
GET /api/auditorias/schema            # JSON Schema trimestral v3.0.0
GET /api/auditorias/schema/trimestral # alias explícito do trimestral
GET /api/auditorias/schema/anual      # JSON Schema anual annual-1.0.0
```

Os schemas formais versionados ficam em `schemas/auditoria_trimestral.v3.schema.json`
e `schemas/auditoria_anual.v1.schema.json`. A CI valida esses arquivos com
`python -m json.tool` junto com as configurações do motor.

Persistência local:
```text
GET  /api/auditorias?cnpj=00.000.000/0001-00&ano=2026
POST /api/auditorias/anual?cnpj=00.000.000/0001-00&ano=2026
GET  /api/auditorias/anual?cnpj=00.000.000/0001-00&ano=2026
```

Cada upload trimestral salva automaticamente o JSON resumido e a fonte compacta para consolidação anual em SQLite. Por padrão, o banco fica em `data/auditoria.sqlite` e não deve ser versionado. Para alterar o caminho:

```powershell
python -m src.auditoria.api --port 8000 --db-path C:\dados\auditoria.sqlite
```

Ou use a variável de ambiente `AUDIT_DB_PATH`.

O SQLite possui versionamento interno por `PRAGMA user_version`. A versão atual do schema local é `1.1.0`; bancos antigos são migrados automaticamente para incluir a coluna `schema_version` nos registros trimestrais e anuais.

Autenticação opcional:
```powershell
$env:AUDIT_API_KEY = "dev-local-secret"
python -m src.auditoria.api --port 8000
```

CORS opcional:
```powershell
python -m src.auditoria.api --port 8000 --cors-origin http://127.0.0.1:8000
```

Também é possível usar a variável `AUDIT_CORS_ORIGIN`. Se não for informado, o servidor local usa `*`.

Regime tributário personalizado:
```powershell
python -m src.auditoria.api --regime-tributario "Simples Nacional"
```

Conjunto de regras/atividade:
```powershell
python -m src.auditoria.api --atividade comercio
python -m src.auditoria.api --atividade comercio_servicos
```

No Windows, também pode usar:
```powershell
.\iniciar_api.ps1
```

### CLI (gerar JSON ou Markdown em arquivo)

```powershell
python -m src.auditoria.main samples/balancete_simples_servicos.csv --periodo "2026-T1" --cliente "Cliente Exemplo" --saida resultado.json
```

Para empresas de comércio ou mistas:
```powershell
python -m src.auditoria.main balancete.csv --periodo "2026-T1" --cliente "Loja Exemplo" --atividade comercio --saida comercio.json
python -m src.auditoria.main balancete.csv --periodo "2026-T1" --cliente "Empresa Mista" --atividade comercio_servicos --saida misto.json
```

Para gerar o parecer consultivo em Markdown:

```powershell
python -m src.auditoria.main samples/balancete_simples_servicos.csv --periodo "2026-T1" --cliente "Cliente Exemplo" --cnpj "00.000.000/0001-00" --markdown --no-ai --saida parecer.md
```

### Parecer anual comparativo

Depois de gerar os JSONs trimestrais, consolide o exercício:

```powershell
python -m src.auditoria.main --anual t1.json t2.json t3.json t4.json --saida parecer_anual.json
```

Para gerar o parecer anual comparativo em Markdown:

```powershell
python -m src.auditoria.main --anual t1.json t2.json t3.json t4.json --markdown --saida parecer_anual.md
```

O JSON anual (`annual-1.0.0`) consolida receita, deduções, tributos registrados,
resultado, estoques, fornecedores, CMV/custos, serviços de terceiros/conta 325,
créditos fiscais, saldos finais relevantes, RBT12 consolidado, recorrência de achados,
tendência de risco e risco anual.

### Testes

```powershell
python -m unittest discover -v
```

## Formato esperado do balancete

CSV (ponto e vírgula), XLSX ou XLS do Domínio:

```csv
codigo;conta;grupo;saldo_anterior;debito;credito;saldo_atual
3.1.1;Receita de Servicos;receita;0;0;180000;180000
2.1.1;Simples Nacional a Recolher;tributos;0;0;9800;9800
```

Modelos disponíveis em `samples/`.

### Grupos usados nas regras

| Grupo | Descrição |
|-------|-----------|
| `receita` | Receitas operacionais de serviços, comércio ou atividade mista |
| `tributos` | Grupo legado para CSVs antigos sem separação tributária |
| `tributos_a_recolher` | Obrigações tributárias no passivo |
| `tributos_sobre_receita` | Deduções/impostos incidentes sobre a receita |
| `despesas_tributarias` | Despesas tributárias operacionais |
| `folha` | Pró-labore, salários e encargos |
| `despesas` / `custos` | Despesas operacionais, custos dos serviços ou CMV |
| Conta `325` ou descrição `serviços prestados por terceiros` | Monitorada pela regra `SN-025` quando relevante nas despesas |
| `socios` | Empréstimos, mútuos, contas correntes, contas 616/627 no ativo e 770 no passivo |
| `adiantamentos` / `adiantamentos_clientes` | Adiantamentos a fornecedores, clientes, empregados e terceiros |
| `caixa` / `bancos` | Disponibilidades |
| `lucros` | Distribuição de lucros |
| `resultado` | Lucro ou prejuízo apurado |
| `fornecedores`, `estoques`, `creditos_fiscais`, `emprestimos` | Métricas complementares e regras específicas de comércio |

### Mapa contábil configurável

O arquivo `config/plano_contas_map.json` permite ajustar o reconhecimento de contas por código exato, prefixo e descrição sem alterar o código Python. O parser usa esse mapa quando o grupo informado vem inválido ou como `outros`, mantendo os fallbacks internos para o layout Domínio e para CSVs simples.

O JSON trimestral inclui o bloco `classificacao_contas`, que resume quantas contas foram classificadas por grupo, origem e nível de confiança, além de listar contas que precisam revisão. Isso ajuda a validar o plano de contas antes de confiar integralmente nos achados do motor.

Esse mapa já inclui a conta `325`/`serviços prestados por terceiros`, contas de sócios/mútuos (`616`, `627` e `770`), bancos, caixa, clientes, estoques, fornecedores, tributos, folha, receitas, deduções e custos/CMV.

## Integração com IA

O motor de regras entrega o JSON trimestral resumido v3.0.0 e o CLI também pode gerar parecer consultivo em Markdown com `--markdown`. O relatório em linguagem natural usa o system prompt consultivo em `src/auditoria/report_ai.py`, com fallback local quando `--no-ai` é usado ou quando a IA não está disponível.

O cliente OpenRouter (`src/auditoria/ai_client.py`) pode ser usado para esse fim, mas é independente do motor de regras.

### Chats externos por JSON

Para uso em chats treinados ou assistentes externos, mantenha dois chats separados:

- **Parecer Trimestral via JSON** — recebe o JSON trimestral `v3.0.0` gerado pelo motor.
- **Parecer Anual Comparativo via JSON** — recebe o JSON anual `annual-1.0.0` gerado pela consolidação dos trimestres.

Os prompts completos para configurar esses chats estão em `docs/PROMPTS_IA.md`. Em ambos os casos, a orientação é enviar apenas o JSON gerado pelo sistema como entrada e solicitar a saída em Markdown.

## Estrutura do projeto

- `src/auditoria/models.py` — modelos de dados (RuleFinding, AuditResult, etc.)
- `src/auditoria/parser.py` — leitura e normalização do balancete (CSV, XLSX, XLS)
- `src/auditoria/rules/simples_servicos.py` — orquestração das regras fiscais para Simples Nacional serviços, comércio e misto
- `src/auditoria/rules/servicos.py` — checagens específicas de serviços, incluindo Fator R/folha
- `src/auditoria/rules/comercio.py` — checagens específicas de comércio, incluindo estoque, fornecedores, CMV, sublimite e ICMS-ST
- `src/auditoria/rules/misto.py` — checagens de empresas mistas com receitas de comércio e serviços
- `src/auditoria/rules/metricas.py` — cálculo de métricas contábeis usadas pelo motor de regras
- `src/auditoria/rules/compostas.py` — regras compostas que combinam achados correlacionados
- `src/auditoria/rules/rulesets.py` — normalização dos conjuntos de regras por atividade
- `src/auditoria/risk.py` — classificação de risco + `suggest_opinion_type`
- `src/auditoria/audit.py` — orquestração: métricas, contexto do regime, explicação do score
- `src/auditoria/annual.py` — consolidação anual dos JSONs trimestrais e parecer anual comparativo
- `src/auditoria/serializers.py` — serialização para JSON trimestral resumido v3.0.0
- `src/auditoria/evidence.py` — evidência estruturada por achado, com fonte, confiança e documentos recomendados
- `src/auditoria/storage.py` — persistência SQLite dos trimestres e consolidações anuais
- `src/auditoria/schema_loader.py` — carregamento dos JSON Schemas formais trimestral/anual
- `src/auditoria/schema_validator.py` — validação interna dos JSONs gerados contra os schemas formais
- `src/auditoria/api.py` — servidor HTTP com upload, schemas e rotas estáticas do dashboard
- `src/auditoria/static/` — frontend do dashboard, download JSON, filtros de achados e impressão em PDF
- `src/auditoria/report_ai.py` — system prompt para geração de parecer via IA
- `src/auditoria/ai_client.py` — cliente OpenRouter (stdlib, sem dependências)
- `src/auditoria/main.py` — CLI para processamento em lote (JSON por padrão, Markdown com `--markdown`)
- `config/rules.json` — configuração de pesos e limites das regras
- `config/simples_anexos.json` — tabelas dos Anexos I, III e V usadas na estimativa tributária
- `config/plano_contas_map.json` — mapa configurável de reconhecimento de contas contábeis
- `schemas/` — contratos JSON Schema versionados para integrações com chats/IA
- `requirements.txt` / `requirements-dev.txt` — dependências de runtime e ferramentas de desenvolvimento
- `.github/workflows/ci.yml` — pipeline de CI com validação de JSON, compile, testes e mypy
- `REGRAS.md` — tabela das regras fiscais configuradas
- `docs/PROMPTS_IA.md` — prompts para chats externos de parecer trimestral e anual
- `tests/` — suíte de testes unitários e de integração leve
