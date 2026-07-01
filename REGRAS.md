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
| SN-005 | Movimentações com sócios | Contas de sócios acima de 20% da receita | Médio | 18 |
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
| SN-COMP-01 | Omissão de receita e despesas elevadas | SN-008 + SN-007 ambos acionados | Alto | 15 |
| SN-COMP-02 | Prejuízo significativo e caixa negativo | SN-009B + SN-006A ambos acionados | Alto | 15 |
| SN-COMP-03 | Recebíveis elevados e adiantamentos | SN-010B/C + SN-011A ambos acionados | Médio | 10 |
| SN-COMP-04 | Estoque incompatível e CMV inconsistente | SN-015 + SN-018 ambos acionados | Alto | 15 |
| SN-COMP-05 | Receita mista e carga baixa | SN-020 + SN-002 ambos acionados | Alto | 15 |

## Observações de cálculo trimestral

- A regra `SN-001` usa a receita do trimestre anualizada (`receita x 4`) como alerta de ritmo; a conclusão legal deve validar a RBT12.
- A regra `SN-003` calcula um Fator R trimestral estimado; o Fator R oficial exige folha e receita acumuladas dos últimos 12 meses.
- A regra `SN-004A` usa o grupo `resultado` quando ele existir no CSV.
- Se o grupo `resultado` não existir, o protótipo usa a estimativa `receita - deduções - custos/despesas`.
- A regra `SN-004A` deixa de acionar quando houver lucros, reservas ou resultado acumulado identificados no patrimônio/resultado em montante suficiente para suportar a distribuição.
- A carga tributária efetiva usa `tributos_sobre_receita` e `despesas_tributarias`; para CSVs antigos, cai para o grupo legado `tributos`.
- A regra `SN-012` usa `tributos_a_recolher`; para CSVs antigos, cai para o grupo legado `tributos`.
- A regra `SN-011` considera `adiantamentos` e `adiantamentos_clientes`, usando a maior referência entre R$ 10.000 e 10% da receita trimestral.
- A regra `SN-010` compara o saldo final patrimonial com a receita trimestral; o achado é um alerta para aging list, prazo médio e baixa posterior, não uma conclusão isolada de irregularidade.
- As regras `SN-015` a `SN-019` são aplicadas nos conjuntos `simples_comercio` e `simples_comercio_servicos`.
- A regra `SN-020` é aplicada apenas no conjunto `simples_comercio_servicos` e procura ausência de segregação contábil entre receitas de comércio e receitas de serviços.
- A regra `SN-017` é alerta documental: créditos fiscais podem existir em situações específicas, mas exigem suporte e validação de natureza/recuperabilidade.
- A regra `SN-019` usa receita trimestral anualizada como alerta de sublimite; a conclusão legal depende da RBT12 e do sublimite estadual aplicável.
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
| AN-END-001 | Endividamento final elevado | Empréstimos finais > 60% da receita anual | Médio |
| AN-TRIB-001 | Passivo tributário crescente | Tributos a recolher crescem mais de 50% no ano | Médio |
| AN-TRIB-002 | Passivo tributário final relevante | Tributos finais > 10% da receita anual | Médio |
