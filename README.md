# Auditoria Fiscal IA — Pré-auditoria para Simples Nacional

Motor de regras fiscais para análise de balancetes trimestrais de empresas optantes pelo Simples Nacional (serviços). O motor extrai métricas do balancete, aplica regras de risco configuráveis e produz um JSON estruturado (schema v2.0.0) que pode ser consumido por uma IA para geração de parecer técnico consultivo ou enviado diretamente ao cliente.

## Esquema de saída (v2.0.0)

```json
{
  "_schema_version": "2.0.0",
  "meta": {
    "versao_schema": "2.0.0",
    "versao_regras": "1.x.x",
    "conjunto_regras": "simples_servicos",
    "data_analise": "2026-05-26T10:30:00",
    "total_contas_analisadas": 15,
    "total_regras_verificadas": 17,
    "total_regras_acionadas": 7
  },
  "identificacao": {
    "cliente": "Cliente Exemplo",
    "cnpj": "",
    "regime_tributario": "Simples Nacional",
    "periodo": "2026-T1"
  },
  "risco": {
    "nivel_geral": "alto",
    "pontuacao_total": 62,
    "modalidade_opiniao_sugerida": "adversa",
    "classificacao": { "achados_alto": 3, "achados_medio": 3, "achados_baixo": 0, "achados_compostos": 1 },
    "explicacao_pontuacao": ["..."]
  },
  "metricas": {
    "receita_servicos": { "valor": 180000.0, "formatado": "R$ 180.000,00" },
    "tributos_a_recolher": { "valor": 1000.0, "formatado": "R$ 1.000,00" },
    "indicadores_derivados": {
      "carga_tributaria_efetiva_percentual": "0,56%",
      "percentual_folha_sobre_receita": "11,11%"
    }
  },
  "achados": [{ "codigo": "SN-004A", "nivel": "alto", "normas_aplicaveis": ["art. 14° LC 123/2006", "NBC TG 1000"], ... }],
  "contexto_regime": {
    "regime": "Simples Nacional",
    "faixa_receita_estimada": "3ª faixa (R$ 360.000,01 a R$ 720.000,00/ano)",
    "aliquota_efetiva_esperada": "13,5%",
    "fator_r_calculado": "44,44%",
    "sublimite_risco": false,
    "observacoes": ["Fator R estimado de 44,44% está acima de 28%..."]
  }
}
```

## Como rodar

Requisitos: Python 3.11+

### Servidor web (recomendado)

```powershell
python -m src.auditoria.api --port 8000
```

Acesse `http://127.0.0.1:8000` — faça upload do balancete e veja o JSON de saída. Botão **⬇ JSON** para download do resultado.

Endpoint JSON:
```text
POST /api/auditorias
Content-Type: multipart/form-data
campos: cliente, cnpj, periodo, balancete
```

Schema de saída:
```text
GET /api/auditorias/schema
```

Autenticação opcional:
```powershell
$env:AUDIT_API_KEY = "dev-local-secret"
python -m src.auditoria.api --port 8000
```

Regime tributário personalizado:
```powershell
python -m src.auditoria.api --regime-tributario "Simples Nacional"
```

No Windows, também pode usar:
```powershell
.\iniciar_api.ps1
```

### CLI (gerar JSON ou Markdown em arquivo)

```powershell
python -m src.auditoria.main samples/balancete_simples_servicos.csv --periodo "2026-T1" --cliente "Cliente Exemplo" --saida resultado.json
```

Para gerar o parecer consultivo em Markdown:

```powershell
python -m src.auditoria.main samples/balancete_simples_servicos.csv --periodo "2026-T1" --cliente "Cliente Exemplo" --cnpj "00.000.000/0001-00" --markdown --no-ai --saida parecer.md
```

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
| `receita` | Receitas de serviços |
| `tributos` | DAS, Simples Nacional, ISS, INSS e outros |
| `folha` | Pro-labore, salários e encargos |
| `despesas` | Despesas operacionais |
| `socios` | Empréstimos, mútuos e contas correntes |
| `adiantamentos` | Adiantamentos a fornecedores, clientes, etc. |
| `caixa` / `bancos` | Disponibilidades |
| `lucros` | Distribuição de lucros |
| `resultado` | Lucro ou prejuízo apurado |

## Integração com IA

O motor de regras entrega o JSON v2.0.0 e o CLI também pode gerar parecer consultivo em Markdown com `--markdown`. O relatório em linguagem natural usa o system prompt consultivo em `src/auditoria/report_ai.py` (Parecer Técnico Consultivo Trimestral — 4 seções), com fallback local quando `--no-ai` é usado ou quando a IA não está disponível.

O cliente OpenRouter (`src/auditoria/ai_client.py`) pode ser usado para esse fim, mas é independente do motor de regras.

## Estrutura do projeto

- `src/auditoria/models.py` — modelos de dados (RuleFinding, AuditResult, etc.)
- `src/auditoria/parser.py` — leitura e normalização do balancete (CSV, XLSX, XLS)
- `src/auditoria/rules/simples_servicos.py` — 21+ regras fiscais com `normas_aplicaveis`
- `src/auditoria/risk.py` — classificação de risco + `suggest_opinion_type`
- `src/auditoria/audit.py` — orquestração: métricas, contexto do regime, explicação do score
- `src/auditoria/serializers.py` — serialização para JSON v2.0.0
- `src/auditoria/api.py` — servidor HTTP com upload, schema e download JSON
- `src/auditoria/report_ai.py` — system prompt para geração de parecer via IA
- `src/auditoria/ai_client.py` — cliente OpenRouter (stdlib, sem dependências)
- `src/auditoria/main.py` — CLI para processamento em lote (JSON por padrão, Markdown com `--markdown`)
- `config/rules.json` — configuração de pesos e limites das regras
- `REGRAS.md` — tabela das regras fiscais configuradas
- `tests/` — suíte de testes unitários e de integração leve
