// Print/PDF document rendering helpers for the dashboard.

function buildPrintDocumentHtml(data) {
  const ident = data.identificacao || {};
  const risk = data.risco || {};
  const metrics = data.metricas || {};
  const context = data.contexto_regime || {};
  const meta = data.meta || {};
  const consultivo = data.consultivo || {};
  const findings = sortedFindings(data.achados || []);
  const classification = risk.classificacao || {};
  const level = normalizeLevel(risk.nivel_geral);
  const counts = countFindings(findings);
  const triggeredRules = meta.total_regras_acionadas ?? findings.length;
  const checkedRules = meta.total_regras_verificadas ?? "?";
  const issuedAt = formatDateTimePtBr();

  return `
    <article class="pdf-document">
      <header class="pdf-cover ${level}">
        <div>
          <span class="pdf-kicker">Pré-auditoria fiscal consultiva</span>
          <h1>Relatório consultivo trimestral</h1>
          <p>Documento gerado a partir do motor de regras e do JSON de auditoria fiscal para orientar a contabilidade, apresentar os principais pontos de atenção ao cliente e priorizar ações de regularização.</p>
        </div>
        <div class="pdf-risk-card">
          <span>Risco geral</span>
          <strong>${levelLabel(level)}</strong>
          <small>Pontuação ${esc(formatNumberPtBr(risk.pontuacao_total ?? 0))}/100</small>
        </div>
      </header>

      <section class="pdf-meta-grid" aria-label="Identificação">
        ${renderPrintMetaItem("Empresa", ident.cliente || "[VERIFICAR: empresa]")}
        ${renderPrintMetaItem("CNPJ", ident.cnpj || "[VERIFICAR: CNPJ]")}
        ${renderPrintMetaItem("Regime tributário", ident.regime_tributario || "Simples Nacional")}
        ${renderPrintMetaItem("Período analisado", ident.periodo || "[VERIFICAR: período]")}
        ${renderPrintMetaItem("Emissão", issuedAt)}
        ${renderPrintMetaItem("Conjunto de regras", `${meta.conjunto_regras || "não informado"} ${meta.versao_regras || ""}`.trim())}
      </section>

      <section class="pdf-section">
        <h2>Resumo executivo</h2>
        <p>${renderPrintSummaryText(level, risk, triggeredRules, checkedRules, counts)}</p>
        <div class="pdf-summary-grid">
          ${renderPrintSummaryCard("Regras verificadas", checkedRules)}
          ${renderPrintSummaryCard("Regras acionadas", triggeredRules)}
          ${renderPrintSummaryCard("Achados de risco alto", counts.alto)}
          ${renderPrintSummaryCard("Achados de risco médio", counts.medio)}
          ${renderPrintSummaryCard("Achados de risco baixo", counts.baixo)}
          ${renderPrintSummaryCard("Achados compostos", classification.achados_compostos || 0)}
        </div>
        ${renderPrintVisualSummary(risk, counts, context)}
      </section>

      ${renderClientGuidanceSection(level, findings, counts, consultivo)}
      ${renderConsultativeActionPlan(findings, consultivo)}
      ${renderPrintMetricSection(metrics, context)}
      ${renderPrintContextSection(context)}
      ${renderPrintFindingsSection(findings)}
      ${renderPrintAccountSection(data.classificacao_contas)}

      <section class="pdf-section pdf-note-section">
        <h2>Observação metodológica</h2>
        <p>A análise é automatizada e foi elaborada com base exclusivamente nos dados estruturados recebidos no JSON de auditoria. A conclusão final deve ser validada com balancete, razão contábil, documentos fiscais, extratos, contratos e demais evidências aplicáveis ao período.</p>
      </section>
      <footer class="pdf-footer">
        Relatório consultivo gerado pelo motor de regras. Uso recomendado: revisão interna, orientação ao cliente e acompanhamento de providências.
      </footer>
    </article>
  `;
}

function printDashboardPdf() {
  if (!lastData) return;

  const viewData = normalizeAuditPayload(lastData);
  const ident = viewData.identificacao || {};
  const title = `Relatório consultivo de pré-auditoria fiscal - ${ident.cliente || "cliente"} - ${ident.periodo || "periodo"}`;
  const content = buildPrintDocumentHtml(viewData);
  const styleUrl = `${window.location.origin}/static/styles.css`;
  const dashboardStyleUrl = `${window.location.origin}/static/dashboard.css`;
  const printStyleUrl = `${window.location.origin}/static/print.css`;
  const printWindow = window.open("", "_blank");

  if (!printWindow) {
    window.print();
    return;
  }

  printWindow.document.open();
  printWindow.document.write(`<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <title>${esc(title)}</title>
  <link rel="stylesheet" href="${esc(styleUrl)}">
  <link rel="stylesheet" href="${esc(dashboardStyleUrl)}">
  <link rel="stylesheet" href="${esc(printStyleUrl)}">
</head>
<body>
  <main class="print-page">${content}</main>
</body>
</html>`);
  printWindow.document.close();
  let printed = false;
  const triggerPrint = () => {
    if (printed) return;
    printed = true;
    printWindow.focus();
    printWindow.print();
  };
  printWindow.addEventListener("load", () => setTimeout(triggerPrint, 200), { once: true });
  setTimeout(triggerPrint, 900);
}
