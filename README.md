# Auditoria Fiscal IA - Protótipo

Protótipo inicial para ler um balancete, aplicar regras fiscais simples para empresas de serviços no Simples Nacional e gerar um relatório trimestral de risco.

O relatório é gerado por IA (OpenRouter/Nemotron 3 Super) por padrão. Se a IA falhar ou não estiver configurada, o modo padrão (Markdown local) é usado como fallback automático.

## Como rodar

Requisitos:

- Python 3.11+

Execute com o balancete CSV de exemplo:

```powershell
python -m src.auditoria.main samples/balancete_simples_servicos.csv --periodo "2026-T1" --cliente "Cliente Exemplo"
```

Tambem funciona com Excel `.xlsx`, desde que a primeira aba tenha o mesmo cabecalho:

```powershell
python -m src.auditoria.main caminho\do\balancete.xlsx --periodo "2026-T1" --cliente "Cliente Exemplo"
```

Arquivos `.xls` exportados pelo Domínio também são aceitos no Windows quando o Excel está instalado. O sistema abre o `.xls` em modo somente leitura, cria uma conversão temporária para `.xlsx` e analisa a cópia.

Subir a API local com tela de upload:

```powershell
python -m src.auditoria.api --port 8000
```

No Windows, tambem pode rodar pelo script:

```powershell
.\iniciar_api.ps1
```

Ou dar duplo clique em:

```text
iniciar_api.bat
```

Depois acesse:

```text
http://127.0.0.1:8000
```

Endpoint JSON:

```text
POST /api/auditorias
Content-Type: multipart/form-data

campos:
- cliente
- periodo
- balancete
```

Gerar relatório em arquivo:

```powershell
# Markdown
python -m src.auditoria.main samples/balancete_simples_servicos.csv --periodo "2026-T1" --cliente "Cliente Exemplo" --saida relatorio.md

# PDF
python -m src.auditoria.main samples/balancete_simples_servicos.csv --periodo "2026-T1" --cliente "Cliente Exemplo" --pdf relatorio.pdf
```

Nota: para exportar PDF, instale `fpdf2`:
```powershell
pip install fpdf2
```

### Configuração da IA (OpenRouter - Gratuito)

A IA já vem habilitada por padrão. Para usá-la:

```powershell
$env:OPENROUTER_API_KEY = "sk-or-..."
```

O modelo padrão é o **Nemotron 3 Super (120B)**, gratuito e de alta qualidade.

Para desabilitar a IA e usar o relatório local:
```powershell
python -m src.auditoria.main ... --no-ai
```

## Formato esperado do CSV, XLSX ou XLS

O CSV deve usar ponto e virgula. No Excel `.xlsx`, use a primeira aba com as mesmas colunas na primeira linha:

```csv
codigo;conta;grupo;saldo_anterior;debito;credito;saldo_atual
```

Exemplo:

```csv
3.1.1;Receita de Servicos;receita;0;0;180000;180000
2.1.1;Simples Nacional a Recolher;tributos;0;0;9800;9800
```

Modelos disponiveis:

- `samples/modelo_balancete_regras.csv`
- `samples/modelo_balancete_regras.xlsx`
- `samples/exemplo_balancete_todas_regras.csv`
- `samples/exemplo_balancete_todas_regras.xlsx`

Para arquivos `.xls` do Domínio, o parser reconhece automaticamente o layout com as colunas `Código`, `Classificação`, `Descrição da conta`, `Saldo Anterior`, `Débito`, `Crédito` e `Saldo Atual`.

## Estrutura

- `src/auditoria/models.py`: modelos de dados.
- `src/auditoria/parser.py`: leitura e normalização do balancete.
- `src/auditoria/rules/simples_servicos.py`: regras fiscais iniciais.
- `src/auditoria/risk.py`: cálculo do nível geral de risco.
- `src/auditoria/report_ai.py`: geração do relatório (com IA ou modo padrão).
- `src/auditoria/pdf_export.py`: exportação do relatório para PDF (requer fpdf2).
- `src/auditoria/ai_client.py`: cliente para chamada à API do OpenRouter (stdlib, sem dependências).
- `src/auditoria/api.py`: API local com upload de balancete.
- `src/auditoria/serializers.py`: conversão do resultado para JSON.
- `src/auditoria/audit.py`: orquestração da auditoria.
- `src/auditoria/main.py`: CLI para rodar o protótipo.
- `REGRAS.md`: tabela das regras fiscais configuradas.

## Grupos usados nas regras

Use estes valores na coluna `grupo` do CSV ou XLSX:

- `receita`: receitas de servicos.
- `tributos`: DAS, Simples Nacional, ISS, INSS e outros impostos.
- `folha`: pro-labore, salarios e encargos.
- `despesas`: despesas operacionais.
- `socios`: adiantamentos, emprestimos e contas correntes de socios.
- `caixa`: caixa.
- `bancos`: bancos e aplicacoes financeiras.
- `lucros`: distribuicao de lucros.
- `resultado`: lucro ou prejuizo apurado no periodo. Quando existir, esse grupo e usado na regra `SN-004A`.

## Como funciona a análise

### 1. Classificação das Contas
Se o seu arquivo já tiver a coluna **`grupo`**, o sistema usa ela diretamente. Caso contrário (formato Domínio), ele classifica automaticamente pelo código e nome da conta (ex: contas começando com `4.*` viram despesa, `3.1.1.*` viram receita).

### 2. Lógica de Debito vs Crédito
O sistema não usa sinais (+/-) para distinguir receita de despesa; ele usa as colunas:
- **Receitas:** Soma apenas os valores da coluna `credito`.
- **Despesas e Custos:** Soma apenas os valores da coluna `debito`.
- **Saldos (Balanço):** Usa a coluna `saldo_atual` para verificar caixa, bancos e tributos a recolher.

### 3. Exemplo: Empresa sem Receita
Se a coluna `credito` das contas de `receita` estiver zerada, mas houver valores em `despesas` ou movimentação em `bancos`, o sistema aciona um alerta de **Risco Alto**.
- **Interpretação:** A empresa tem custos operacionais, mas não declarou faturamento. Isso sugere possível sonegação ou erro de classificação contábil.
- **Atenção:** Se a receita foi lançada direto na conta de "Resultado do Período" (em vez de "Receita de Serviços"), a análise atual não captará esse valor como faturamento, resultando em um relatório mais conservador (pior).

## Próximos passos naturais

1. Validar o formato real dos balancetes usados pelos clientes.
2. Mapear contas contábeis comuns para categorias padronizadas.
3. Refinar pesos e limites das regras com um contador/fiscalista.
4. ~~Trocar o gerador mock de relatório por uma chamada de IA com os achados estruturados.~~ **Feito!**
5. Adicionar upload via API e armazenamento dos relatórios por cliente/trimestre.
