# Regras fiscais do protótipo

Motor para empresas enquadradas no Simples Nacional, com conjuntos para serviços, comércio e atividades mistas de comércio e serviços.

## Conjuntos de regras

| Conjunto | Uso recomendado |
|---|---|
| `simples_servicos` | Empresas predominantemente prestadoras de serviços |
| `simples_comercio` | Empresas predominantemente comerciais, com estoques, fornecedores e CMV |
| `simples_comercio_servicos` | Empresas que combinam venda de mercadorias e prestação de serviços |

| Código | Regra | Critério | Risco | Peso |
|---|---|---|---|---|
| SN-001A | Receita trimestral anualizada em atenção | Receita do trimestre x 4 acima de 70% do limite anual do Simples Nacional | Médio | 18 |
| SN-001B | Receita trimestral anualizada próxima ao limite | Receita do trimestre x 4 acima de 90% do limite anual do Simples Nacional | Alto | 35 |
| SN-002A | Carga tributária sobre receita | Tributos registrados / receita abaixo de 5,5% | Médio | 15 |
| SN-002B | Carga tributária sobre receita | Tributos registrados / receita abaixo de 3% | Alto | 20 |
| SN-003 | Folha e pró-labore trimestrais baixos | Folha + pró-labore abaixo de 8% da receita trimestral | Médio | 14 |
| SN-004A | Distribuição de lucros | Distribuição maior que lucro do período e lucros/reservas identificados | Alto | 32 |
| SN-004B | Distribuição de lucros | Distribuição maior que 30% da receita | Médio | 16 |
| SN-005 | Saldos em contas de sócios | Saldo em contas 616/627 no ativo, 770 no passivo ou demais contas relacionadas a sócios/mútuo; baixo se imaterial, médio se >= R$ 10.000 ou >= 5% da receita | Baixo/Médio | 6/18 |
| SN-006A | Caixa e bancos | Saldo menor que zero | Alto | 28 |
| SN-006B | Caixa e bancos | Saldo acima de 60% da receita | Médio | 12 |
| SN-007 | Despesas operacionais elevadas | Custos e despesas operacionais acima de 70% da receita | Médio | 16 |
| SN-008A | Receita versus movimentação | Receita igual a zero com movimentação bancária acima de R$ 10.000 | Alto | 20 |
| SN-008B | Receita versus movimentação | Receita abaixo de 5% da movimentação operacional | Alto | 20 |
| SN-009A | Prejuízo contábil | Prejuízo contábil sem receita declarada | Alto | 25 |
| SN-009B | Prejuízo contábil | Prejuízo contábil acima de 10% da receita | Alto | 25 |
| SN-009C | Prejuízo contábil | Prejuízo contábil leve | Médio | 12 |
| SN-010A | Clientes e recebíveis sem movimentação | Saldo de clientes sem débito/crédito no período | Médio | 12 |
| SN-010B | Clientes e recebíveis elevados | Saldo final acima de 100% da receita trimestral | Médio | 12 |
| SN-010C | Clientes e recebíveis muito elevados | Saldo final acima de 200% da receita trimestral | Alto | 20 |
| SN-011A | Adiantamentos relevantes | Adiantamentos acima da maior referência entre 10% da receita trimestral e R$ 10.000 | Médio | 12 |
| SN-012 | Passivo tributário crescente | Tributos a recolher cresceram mais de 50% em relação ao período anterior | Médio | 14 |
| SN-013A | Despesas de representação elevadas | Despesas de representação acima de 15% das despesas totais | Médio | 10 |
| SN-013B | Despesas de veículos elevadas | Despesas de veículos acima de 10% das despesas totais | Médio | 10 |
| SN-014 | Ausência de provisões com folha significativa | Folha acima de 10% da receita sem provisões trabalhistas | Médio | 12 |
| SN-015A | Estoque relevante sem receita | Estoques acima de R$ 10.000 sem receita registrada | Alto | 24 |
| SN-015B | Estoque elevado | Estoques acima de 100% da receita trimestral | Médio | 14 |
| SN-015C | Estoque muito elevado | Estoques acima de 200% da receita trimestral | Alto | 24 |
| SN-016A | Fornecedores relevantes sem receita | Fornecedores acima de R$ 10.000 sem receita registrada | Médio | 14 |
| SN-016B | Fornecedores elevados | Fornecedores acima de 80% da receita trimestral | Médio | 14 |
| SN-016C | Fornecedores muito elevados | Fornecedores acima de 150% da receita trimestral | Alto | 22 |
| SN-017 | Créditos fiscais relevantes | Créditos fiscais acima da maior referência entre R$ 5.000 e 2% da receita | Médio | 16 |
| SN-018A | Receita comercial sem CMV | Receita com sinais comerciais, mas sem custo de mercadorias identificado | Alto | 24 |
| SN-018B | CMV baixo | CMV abaixo de 30% da receita com sinais comerciais | Médio | 14 |
| SN-018C | CMV muito elevado | CMV acima de 95% da receita | Alto | 24 |
| SN-019 | Sublimite de ICMS | Receita trimestral anualizada acima de R$ 3.600.000 | Médio | 16 |
| SN-020 | Receita mista sem segregação | Comércio e serviços sem contas de receita suficientemente segregadas | Médio | 18 |
| SN-021A | Margem de lucro acima da referência | Lucro contábil acima de 45% da receita | Baixo | 6 |
| SN-021B | Margem de lucro muito elevada | Lucro contábil acima de 64% da receita | Médio | 12 |
| SN-022A | Caixa físico acima do parâmetro | Caixa físico acima do maior limite entre valor absoluto e percentual da receita | Médio | 12 |
| SN-022B | Caixa físico muito elevado | Caixa físico acima de 3x o parâmetro esperado | Alto | 18 |
| SN-023 | Clientes zerados com receita relevante | Receita >= R$ 200.000 sem saldo ou movimentação em clientes | Baixo | 6 |
| SN-024 | Validação de ICMS-ST | Créditos fiscais relevantes em contexto comercial com estoque/fornecedores/CMV | Baixo | 6 |
| SN-025 | Serviços prestados por terceiros | Conta 325/serviços de terceiros >= 20% das despesas e acima de R$ 10.000 | Médio | 12 |
| SN-COMP-01 | Omissão de receita e despesas elevadas | SN-008 + SN-007 ambos acionados | Alto | 15 |
| SN-COMP-02 | Prejuízo significativo e caixa negativo | SN-009B + SN-006A ambos acionados | Alto | 15 |
| SN-COMP-03 | Recebíveis elevados e adiantamentos | SN-010B/C + SN-011A ambos acionados | Médio | 10 |
| SN-COMP-04 | Estoque incompatível e CMV inconsistente | SN-015 + SN-018 ambos acionados | Alto | 15 |
| SN-COMP-05 | Receita mista e carga baixa | SN-020 + SN-002 ambos acionados | Alto | 15 |

Notas de versao 1.6.0:

- `SN-001` e `SN-019` priorizam RBT12 consolidado quando o backend possui os quatro trimestres salvos; sem esse historico, mantem `receita x 4` apenas como alerta.
- `SN-024` permanece documental: o balancete nao contem NCM, CFOP, CST ou item fiscal, entao a validacao de ICMS-ST depende de notas fiscais, PGDAS-D e apuracoes fiscais.
- O JSON resumido diferencia a natureza do achado no texto de impacto: possivel inconsistencia material, alerta tecnico, validacao documental ou ponto de atencao.

Notas de versao 1.7.0:

- `SN-025` valida a conta 325/servicos prestados por terceiros quando ela representa percentual relevante das despesas do trimestre; o achado pede validacao de contratos, notas fiscais, comprovantes bancarios, retencoes e suporte documental.
- A evidencia da `SN-025` inclui quantidade de contas identificadas, contas rastreadas e criterio de rastreio para facilitar a revisao documental.
- O reconhecimento de contas pode ser ajustado em `config/plano_contas_map.json`, usado quando o grupo vem invalido ou como `outros`.

Notas de versao 1.8.0:

- `SN-005` passou a acionar revisao documental sempre que houver saldo em contas de socios, administradores, pessoas ligadas ou codigos monitorados `616`, `627` e `770`, solicitando contrato de mutuo e comprovacao de IOF quando aplicavel.
- O consolidado anual inclui `AN-DOC-MUTUO-001` quando o ultimo trimestre apresenta saldo final em contas de socios/mutuos.

Notas de versao 1.9.0:

- `SN-005` e `AN-DOC-MUTUO-001` passaram a usar materialidade configuravel: saldos abaixo dos parametros ficam como ponto de atencao baixo; saldos acima de R$ 10.000 ou 5% da receita ficam como risco medio.
- A API de upload mantem o JSON trimestral formal `v3.0.0` e adiciona um bloco auxiliar `dashboard` somente para a interface web, com metricas, contexto do regime e totais operacionais.
- O SQLite local foi versionado como schema `1.1.0` com migracao automatica via `PRAGMA user_version`.

## Observações de cálculo trimestral

- A regra `SN-001` usa a receita do trimestre anualizada (`receita x 4`) como alerta de ritmo; a conclusão legal deve validar a RBT12.
- A regra `SN-003` calcula um Fator R trimestral estimado; o Fator R oficial exige folha e receita acumuladas dos últimos 12 meses.
- A regra `SN-004A` usa o grupo `resultado` quando ele existir no CSV.
- Se o grupo `resultado` não existir, o protótipo usa a estimativa `receita - deduções - custos/despesas`.
- A regra `SN-004A` deixa de acionar quando houver lucros, reservas ou resultado acumulado identificados no patrimônio/resultado em montante suficiente para suportar a distribuição.
- A regra `SN-005` rastreia saldos nas contas `616` e `627` no ativo, `770` no passivo e outras contas cuja descrição indique sócio, administrador, pessoa ligada ou mútuo.
- Para `SN-005`, a evidência pede validação de contrato de mútuo ou instrumento equivalente, extratos, razão contábil, memória de cálculo e comprovante de recolhimento de IOF quando a operação caracterizar crédito/mútuo.
- Para `SN-005`, a materialidade padrao é: risco médio quando o saldo for maior ou igual a R$ 10.000 ou 5% da receita trimestral; abaixo disso, o achado permanece como risco baixo para revisão documental.
- A carga tributária efetiva usa `tributos_sobre_receita` e `despesas_tributarias`; para CSVs antigos, cai para o grupo legado `tributos`.
- A regra `SN-012` usa `tributos_a_recolher`; para CSVs antigos, cai para o grupo legado `tributos`.
- A regra `SN-011` considera `adiantamentos` e `adiantamentos_clientes`, usando a maior referência entre R$ 10.000 e 10% da receita trimestral.
- A regra `SN-010` compara o saldo final patrimonial com a receita trimestral; o achado é um alerta para aging list, prazo médio e baixa posterior, não uma conclusão isolada de irregularidade.
- As regras `SN-015` a `SN-019` são aplicadas nos conjuntos `simples_comercio` e `simples_comercio_servicos`.
- A regra `SN-020` é aplicada apenas no conjunto `simples_comercio_servicos` e procura ausência de segregação contábil entre receitas de comércio e receitas de serviços.
- A regra `SN-017` é alerta documental: créditos fiscais podem existir em situações específicas, mas exigem suporte e validação de natureza/recuperabilidade.
- A regra `SN-019` usa receita trimestral anualizada como alerta de sublimite; a conclusão legal depende da RBT12 e do sublimite estadual aplicável.
- A regra `SN-021` usa a referência de 32% apenas como parâmetro gerencial de plausibilidade, não como presunção tributária definitiva para empresas do Simples.
- A regra `SN-022` separa caixa físico de bancos; para serviços, o parâmetro é mais restritivo, pois caixa operacional relevante tende a exigir justificativa documental.
- A regra `SN-023` não presume erro quando clientes está zerado; ela pede validação de recebimento à vista, baixa no mesmo mês ou controle de recebíveis.
- A regra `SN-024` não recalcula ICMS-ST pelo balancete; ela aciona validação documental de NCM, CFOP, mercadorias sujeitas a substituição tributária, ressarcimentos e créditos fiscais.
- A regra `SN-025` identifica a conta 325 por codigo ou por descricoes como `servicos prestados por terceiros` e compara o valor com o total de despesas operacionais do trimestre.
- Para `SN-025`, a evidencia lista as contas encontradas com codigo, descricao, grupo, debito, credito e saldo.
- O contexto tributário usa `config/simples_anexos.json` para estimar Anexo I, III ou V. Para empresas mistas, o motor informa que a alíquota depende da segregação entre receitas de comércio e serviços.
- `_active_movement` é calculado apenas com `bancos` e `caixa`, sem `clientes`.
- `_operational_movement` inclui `bancos`, `caixa` e `clientes` para o cálculo do índice da `SN-008B`.
- Regras compostas (`SN-COMP-*`) são acionadas quando as regras base correspondentes estão presentes.
- O parser infere automaticamente o grupo via `_infer_grupo_from_conta` quando o grupo informado não está em `VALID_GRUPOS`.

## Consolidação anual

O consolidado anual lê os JSONs trimestrais já gerados e cria o schema `annual-1.0.0`.
As regras anuais não substituem as trimestrais; elas procuram recorrência, evolução
e materialidade no exercício.

| Código | Regra | Critério | Risco |
|---|---|---|---|
| AN-REC-* | Achado trimestral recorrente | Mesmo achado em 2 ou mais trimestres | Médio/Alto |
| AN-SN-001A | Receita anual em atenção | Receita anual >= 70% do limite do Simples Nacional | Médio |
| AN-SN-001B | Receita anual próxima ao limite | Receita anual >= 90% do limite do Simples Nacional | Alto |
| AN-LUC-001 | Lucros distribuídos acima do resultado anual | Distribuição anual > lucro anual apurado | Alto |
| AN-MAR-001 | Margem anual muito elevada | Lucro anual > 64% da receita anual | Médio |
| AN-DOC-325-001 | Serviços de terceiros relevantes no ano | Conta 325/serviços de terceiros >= 20% das despesas anuais | Médio |
| AN-DOC-MUTUO-001 | Saldo final em contas de sócios | Saldo final anual em contas de sócios/mútuos; baixo se imaterial, médio se >= R$ 10.000 ou >= 5% da receita anual | Baixo/Médio |
| AN-END-001 | Endividamento final elevado | Empréstimos finais > 60% da receita anual | Médio |
| AN-CLI-001 | Clientes zerados no fechamento anual | Receita anual relevante com clientes finais zerados | Baixo |
| AN-COM-EST-001 | Estoque final relevante | Estoques finais > 50% da receita anual | Médio |
| AN-COM-FOR-001 | Fornecedores finais relevantes | Fornecedores finais > 30% da receita anual | Médio |
| AN-COM-CMV-001 | Operação comercial sem CMV anual | Sinais comerciais com CMV anual zerado | Alto |
| AN-COM-ST-001 | Créditos fiscais finais | Créditos fiscais finais > 1% da receita anual | Baixo |
| AN-TEND-RIS-001 | Tendência de piora de risco | Risco ou pontuação piora do primeiro para o último trimestre | Médio |
| AN-TEND-REC-001 | Queda relevante de receita | Receita do último trimestre cai mais de 30% frente ao primeiro | Médio |
| AN-TRIB-001 | Passivo tributário crescente | Tributos a recolher crescem mais de 50% no ano | Médio |
| AN-TRIB-002 | Passivo tributário final relevante | Tributos finais > 10% da receita anual | Médio |
