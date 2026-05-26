# Regras Fiscais do Prototipo

Motor para empresas de servicos enquadradas no Simples Nacional.

| Codigo | Regra | Criterio | Risco | Peso |
|---|---|---|---|---|
| SN-001A | Receita trimestral proxima ao limite do Simples | Receita acima de 70% do limite proporcional trimestral | Medio | 18 |
| SN-001B | Receita trimestral proxima ao limite do Simples | Receita acima de 90% do limite proporcional trimestral | Alto | 35 |
| SN-002A | Carga tributaria sobre receita | Impostos / receita abaixo de 5,5% | Medio | 15 |
| SN-002B | Carga tributaria sobre receita | Impostos / receita abaixo de 3% | Alto | 20 |
| SN-003 | Folha e pro-labore baixos | Folha + pro-labore abaixo de 8% da receita | Medio | 14 |
| SN-004A | Distribuicao de lucros | Distribuicao maior que lucro apurado | Alto | 32 |
| SN-004B | Distribuicao de lucros | Distribuicao maior que 30% da receita | Medio | 16 |
| SN-005 | Movimentacoes com socios | Contas de socios acima de 20% da receita | Medio | 18 |
| SN-006A | Caixa e bancos | Saldo menor que zero | Alto | 28 |
| SN-006B | Caixa e bancos | Saldo acima de 60% da receita | Medio | 12 |
| SN-007 | Despesas operacionais elevadas | Despesas acima de 70% da receita | Medio | 16 |
| SN-008A | Receita vs movimentacao | Receita igual a zero com movimentacao bancaria acima de R$ 10.000 | Alto | 20 |
| SN-008B | Receita vs movimentacao | Receita abaixo de 5% da movimentacao operacional | Alto | 20 |
| SN-009A | Prejuizo contabil | Prejuizo contabil sem receita declarada | Alto | 25 |
| SN-009B | Prejuizo contabil | Prejuizo contabil acima de 10% da receita | Alto | 25 |
| SN-009C | Prejuizo contabil | Prejuizo contabil leve | Medio | 12 |
| SN-010A | Clientes e recebiveis sem movimentacao | Saldo de clientes sem debitocredito no periodo | Medio | 12 |
| SN-010B | Clientes e recebiveis elevados | Saldo acima de 100% da receita | Medio | 12 |
| SN-010C | Clientes e recebiveis muito elevados | Saldo acima de 200% da receita | Alto | 20 |
| SN-011A | Adiantamentos relevantes | Adiantamentos acima de 10% da receita ou R$ 10.000 | Medio | 12 |
| SN-012 | Passivo tributario crescente | Tributos a recolher cresceram >50% em relacao ao periodo anterior | Medio | 14 |
| SN-013A | Despesas de representacao elevadas | Despesas de representacao >15% das despesas totais | Medio | 10 |
| SN-013B | Despesas de veiculos elevadas | Despesas de veiculos >10% das despesas totais | Medio | 10 |
| SN-014 | Ausencia de provisoes com folha significativa | Folha >10% da receita sem provisoes trabalhistas | Medio | 12 |
| SN-COMP-01 | Omissao de receita + despesas elevadas | SN-008 + SN-007 ambos acionados | Alto | 15 |
| SN-COMP-02 | Prejuizo significativo + caixa negativo | SN-009B + SN-006A ambos acionados | Alto | 15 |
| SN-COMP-03 | Recebiveis elevados + adiantamentos | SN-010B/C + SN-011A ambos acionados | Medio | 10 |

## Observacoes de calculo

- A regra `SN-004A` usa o grupo `resultado` quando ele existir no CSV.
- Se o grupo `resultado` nao existir, o prototipo usa a estimativa `receita - despesas`.
- `_active_movement` e calculado apenas com `bancos` e `caixa` (sem `clientes`).
- `_operational_movement` inclui `bancos`, `caixa` e `clientes` para o calculo do ratio SN-008B.
- Regras compostas (SN-COMP-*) sao acionadas quando as regras base correspondentes estao presentes.
- O parser infere grupo automaticamente via `_infer_grupo_from_conta` quando o grupo informado nao esta em `VALID_GRUPOS`.
