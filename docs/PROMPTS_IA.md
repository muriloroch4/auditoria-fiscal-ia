# Prompts para Chats Externos por JSON

Este documento indica a fonte única dos prompts usados para gerar relatórios consultivos a partir dos JSONs do projeto.

## Fonte Única

Os prompts oficiais ficam em:

- [`prompts/relatorio_trimestral.md`](../prompts/relatorio_trimestral.md): relatório consultivo trimestral, compatível com o schema `v3.3.0`.
- [`prompts/relatorio_anual.md`](../prompts/relatorio_anual.md): relatório consultivo anual comparativo, compatível com o schema `annual-1.2.0`.

Use esses arquivos como fonte de verdade. Não mantenha cópias manuais do prompt neste documento nem em outros arquivos, para evitar divergências entre o chat externo e o prompt realmente usado pelo sistema.

## Chat 1 — Relatório Consultivo Trimestral via JSON

1. Abra [`prompts/relatorio_trimestral.md`](../prompts/relatorio_trimestral.md).
2. Cole todo o conteúdo como instrução fixa do chat/assistente externo.
3. Depois, envie somente o JSON trimestral gerado pelo sistema.

O mesmo arquivo também é carregado internamente por `src/auditoria/report_ai.py` quando a geração via IA está habilitada.

## Chat 2 — Relatório Consultivo Anual Comparativo via JSON

1. Abra [`prompts/relatorio_anual.md`](../prompts/relatorio_anual.md).
2. Cole todo o conteúdo como instrução fixa do chat/assistente externo.
3. Depois, envie somente o JSON anual consolidado gerado pelo sistema.

## Política de Manutenção

- Alterações de conteúdo devem ser feitas diretamente em `prompts/relatorio_trimestral.md` ou `prompts/relatorio_anual.md`.
- Este arquivo deve apenas apontar para as fontes oficiais.
- Os testes automatizados verificam que o prompt trimestral usado internamente é exatamente o mesmo arquivo documentado.
- O prompt trimestral adota um único padrão de extensão: relatório equivalente a 5 a 7 páginas em PDF para um trimestre comum.
