# Regras Fiscais do Prototipo

Motor inicial para empresas de servicos enquadradas no Simples Nacional.

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
| SN-008A | Receita vs movimentacao | Receita igual a zero com movimentacao acima de R$ 10.000 | Alto | 20 |
| SN-008B | Receita vs movimentacao | Receita abaixo de 5% da movimentacao | Alto | 20 |
| SN-009A | Prejuizo contabil | Prejuizo contabil sem receita declarada | Alto | 25 |
| SN-009B | Prejuizo contabil | Prejuizo contabil acima de 10% da receita | Alto | 25 |
| SN-009C | Prejuizo contabil | Prejuizo contabil leve | Medio | 12 |

## Observacoes de calculo

- A regra `SN-004A` usa o grupo `resultado` quando ele existir no CSV.
- Se o grupo `resultado` nao existir, o prototipo usa a estimativa `receita - despesas`.
- O resultado da auditoria agora inclui uma explicacao da pontuacao, com a soma dos pesos e os principais achados que formaram o score.
