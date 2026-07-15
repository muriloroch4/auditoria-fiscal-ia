// Dashboard section renderers for the quarterly analysis view.

function buildDashboardHtml(data, options = {}) {
  const risk = data.risco || {};
  const metrics = data.metricas || {};
  const context = data.contexto_regime || {};
  const meta = data.meta || {};
  const findings = sortedFindings(data.achados || []);
  const classification = risk.classificacao || {};
  const level = normalizeLevel(risk.nivel_geral);
  const filter = options.findingFilter || "all";
  const printMode = Boolean(options.printMode);
  const rawData = options.rawData || data;
  return `
    <div class="dashboard-stack">
      ${renderRiskPanel(risk, findings, meta, level)}
      ${renderExecutiveSummary(data, metrics, findings, meta, context, classification)}
      ${renderVisualSummary(risk, findings, metrics, context)}
      ${renderAnalysisGrid(context, findings, meta, filter, printMode)}
      ${renderMetricGroups(metrics)}
      ${renderIndicators(metrics.indicadores_derivados)}
      ${renderAccountClassification(data.classificacao_contas)}
      ${renderScoreExplanation(risk.explicacao_pontuacao || [], printMode)}
      ${printMode ? "" : renderRawJson(formalAuditPayload(rawData))}
    </div>
  `;
}
