// Executive and visual summary renderers for the dashboard.

function renderRiskPanel(risk, findings, meta, level) {
  const rules = `${esc(meta.total_regras_acionadas ?? findings.length)} de ${esc(meta.total_regras_verificadas ?? "?")} regras`;
  const score = Number(risk.pontuacao_total ?? 0);
  const scoreWidth = Math.max(4, Math.min(100, score));
  const rawScore = risk.pontuacao_bruta ?? 0;
  const maxScore = risk.pontuacao_maxima_aplicavel ?? 100;
  const version = `${esc(meta.conjunto_regras || "Conjunto não informado")} ${esc(meta.versao_regras || "")}`.trim();
  return `
    <section class="risk-panel ${level}">
      <div class="risk-copy">
        <span class="risk-kicker">Risco ${levelLabel(level)}</span>
        <h3>${esc(risk.orientacao_consultiva || opinionLabel(risk.modalidade_opiniao_sugerida))}</h3>
        <div class="risk-score-track" aria-hidden="true"><span style="width: ${scoreWidth}%"></span></div>
        <p>Classificação em escala de 0 a 100, calculada a partir das regras fiscais acionadas no período analisado.</p>
        <div class="risk-meta">
          <span>${rules}</span>
          <span>Base bruta: ${esc(rawScore)} de ${esc(maxScore)} pts</span>
          <span>${version}</span>
        </div>
      </div>
      <div class="risk-stats">
        <div class="stat-box"><strong>${esc(risk.pontuacao_total ?? 0)}/100</strong><span>Pontuação</span></div>
        <div class="stat-box"><strong>${esc(findings.length)}</strong><span>Achados</span></div>
        <div class="stat-box"><strong>${esc(meta.total_contas_analisadas ?? 0)}</strong><span>Contas</span></div>
      </div>
    </section>
  `;
}

function renderExecutiveSummary(data, metrics, findings, meta, context, classification) {
  const ident = data.identificacao || {};
  const counts = countFindings(findings);
  const accountClassification = data.classificacao_contas || {};
  const reviewAccounts = Number(accountClassification.total_contas_revisao || 0);
  const triggeredRules = meta.total_regras_acionadas ?? findings.length;
  const checkedRules = meta.total_regras_verificadas ?? "?";
  const revenue = metricValue(metrics, "receita_operacional") || metricValue(metrics, "receita_servicos");
  const result = metricValue(metrics, "lucro_apurado_base");
  const taxes = metricValue(metrics, "tributos_registrados") || metricValue(metrics, "tributos_a_recolher");
  const highlights = executiveHighlights(findings);
  const cards = [
    renderExecutiveCard(
      "Empresa",
      ident.cliente || "[VERIFICAR: empresa]",
      `${ident.regime_tributario || "Regime não informado"} | ${ident.periodo || "Período não informado"}`,
    ),
    renderExecutiveCard(
      "Regras",
      `${triggeredRules} acionadas`,
      `${checkedRules} verificadas no motor`,
      Number(triggeredRules) ? "warning" : "success",
    ),
    renderExecutiveCard(
      "Achados",
      findings.length,
      `Alta ${counts.alto} | Média ${counts.medio} | Baixa ${counts.baixo}`,
      counts.alto ? "danger" : counts.medio ? "warning" : "success",
    ),
    renderExecutiveCard(
      "Próxima revisão",
      nextDashboardAction(counts, reviewAccounts),
      reviewAccounts ? `${reviewAccounts} conta(s) para revisar` : "Sem conta marcada para revisão",
      counts.alto || reviewAccounts ? "warning" : "neutral",
    ),
  ].join("");
  const metricStrip = [
    renderExecutiveMetric("receita_operacional", "Receita", revenue),
    renderExecutiveMetric("lucro_apurado_base", "Resultado", result),
    renderExecutiveMetric("tributos_registrados", "Tributos", taxes),
    renderExecutiveMetric("anexo_estimado", "Anexo estimado", context.anexo_estimado),
  ].filter(Boolean).join("");

  return `
    <section class="section executive-section">
      <div class="section-header">
        <h3 class="section-title">Leitura executiva</h3>
        <span class="section-note">${esc(classification.achados_compostos || 0)} achado(s) composto(s)</span>
      </div>
      <div class="executive-grid">${cards}</div>
      ${metricStrip ? `<div class="executive-metric-strip">${metricStrip}</div>` : ""}
      <div class="priority-board">
        <div>
          <h4>Principais pontos</h4>
          <p>Itens priorizados por severidade para orientar a revisão documental.</p>
        </div>
        <div class="priority-list">${highlights}</div>
      </div>
    </section>
  `;
}

function renderExecutiveCard(label, value, detail, tone = "neutral") {
  return `
    <div class="executive-card ${tone}">
      <span>${esc(label)}</span>
      <strong>${esc(value)}</strong>
      <small>${esc(detail)}</small>
    </div>
  `;
}

function renderExecutiveMetric(key, label, value) {
  if (!value) return "";
  return `
    <div class="executive-metric">
      <span>${esc(label)}</span>
      <strong>${formatMetricDisplay(key, value)}</strong>
    </div>
  `;
}

function renderVisualSummary(risk, findings, metrics, context) {
  const counts = countFindings(findings);
  const indicators = metrics.indicadores_derivados || {};
  const score = Number(risk.pontuacao_total ?? 0);
  const scoreTone = score >= 60 ? "alto" : score >= 30 ? "medio" : "baixo";
  const rbt12Value = numericValue(context.receita_rbt12_utilizada);
  const rbt12Percent = rbt12Value ? (rbt12Value / 4800000) * 100 : 0;
  const rbt12Tone = rbt12Percent >= 90 ? "alto" : rbt12Percent >= 75 ? "medio" : "baixo";
  const rbt12Label = rbt12Value ? formatCurrencyPtBr(rbt12Value) : "Não informado";
  const rbt12Detail = context.rbt12_disponivel === false
    ? "Usar como alerta: RBT12 completo não foi informado"
    : context.origem_rbt12 || context.base_calculo_estimativa || "Base tributária informada pelo motor";
  const factor = context.fator_r_calculado ? percentValue(context.fator_r_calculado) : null;
  const factorCard = factor === null ? "" : renderVisualProgressCard(
    "Fator R",
    context.fator_r_calculado,
    clampPercent(factor),
    `Referência ${context.fator_r_threshold || "28%"}`,
    factor < 28 ? "medio" : "baixo",
  );

  return `
    <section class="section visual-section">
      <div class="section-header">
        <h3 class="section-title">Visualização executiva</h3>
        <span class="section-note">Leitura rápida dos principais indicadores</span>
      </div>
      <div class="visual-grid">
        ${renderVisualProgressCard("Pontuação de risco", `${formatNumberPtBr(score)}/100`, clampPercent(score), "Escala operacional de 0 a 100 pontos", scoreTone)}
        ${renderSeverityBars(counts)}
        ${renderVisualProgressCard("RBT12 / limite do Simples", rbt12Label, clampPercent(rbt12Percent), rbt12Detail, rbt12Tone)}
        ${factorCard || renderIndicatorMiniBars(indicators)}
        ${factorCard ? renderIndicatorMiniBars(indicators) : ""}
      </div>
    </section>
  `;
}

function renderVisualProgressCard(title, value, width, detail, tone = "info") {
  return `
    <article class="visual-card ${tone}">
      <div class="visual-card-header">
        <span>${esc(title)}</span>
        <strong>${esc(value)}</strong>
      </div>
      <div class="visual-track" aria-hidden="true">
        <span style="width: ${clampPercent(width)}%"></span>
      </div>
      <p>${esc(detail)}</p>
    </article>
  `;
}

function renderSeverityBars(counts) {
  const total = Math.max(1, counts.alto + counts.medio + counts.baixo);
  const rows = [
    ["alto", "Alto", counts.alto],
    ["medio", "Médio", counts.medio],
    ["baixo", "Baixo", counts.baixo],
  ].map(([level, label, value]) => {
    const width = (Number(value || 0) / total) * 100;
    return `
      <div class="visual-bar-row ${level}">
        <span>${esc(label)}</span>
        <div class="visual-bar-track"><i style="width: ${clampPercent(width)}%"></i></div>
        <strong>${esc(value)}</strong>
      </div>
    `;
  }).join("");

  return `
    <article class="visual-card">
      <div class="visual-card-header">
        <span>Severidade dos achados</span>
        <strong>${esc(counts.all)}</strong>
      </div>
      <div class="visual-bars">${rows}</div>
      <p>Distribuição dos achados acionados no período.</p>
    </article>
  `;
}

function renderIndicatorMiniBars(indicators) {
  const items = [
    ["percentual_despesas_sobre_receita", "Despesas/receita"],
    ["percentual_servicos_terceiros_sobre_despesas", "Terceiros/despesas"],
    ["percentual_cmv_sobre_receita", "CMV/receita"],
  ].filter(([key]) => hasDisplayValue(indicators[key]));

  if (!items.length) {
    return renderVisualProgressCard("Indicadores percentuais", "Sem dados", 0, "Indicadores derivados não informados no JSON.", "info");
  }

  const rows = items.map(([key, label]) => {
    const value = indicators[key];
    const percent = percentValue(value);
    return `
      <div class="visual-bar-row info">
        <span>${esc(label)}</span>
        <div class="visual-bar-track"><i style="width: ${clampPercent(percent)}%"></i></div>
        <strong>${esc(value)}</strong>
      </div>
    `;
  }).join("");

  return `
    <article class="visual-card">
      <div class="visual-card-header">
        <span>Indicadores percentuais</span>
        <strong>${esc(items.length)}</strong>
      </div>
      <div class="visual-bars">${rows}</div>
      <p>Percentuais que ajudam a explicar margem, custos e despesas.</p>
    </article>
  `;
}

function executiveHighlights(findings) {
  if (!findings.length) {
    return `
      <div class="priority-item success">
        <span class="priority-code">OK</span>
        <div>
          <strong>Nenhum achado acionado</strong>
          <p>Manter evidências e documentação de suporte do período analisado.</p>
        </div>
      </div>
    `;
  }

  return findings.slice(0, 3).map((finding) => {
    const level = normalizeLevel(finding.nivel);
    const detail = truncateText(finding.descricao || finding.recomendacao || "Detalhe técnico disponível na tabela de achados.", 150);
    return `
      <div class="priority-item ${level}">
        <span class="priority-code">${esc(finding.codigo)}</span>
        <div>
          <strong>${displayText(finding.titulo || "Achado sem título")}</strong>
          <p>${displayText(detail)}</p>
        </div>
      </div>
    `;
  }).join("");
}

function nextDashboardAction(counts, reviewAccounts) {
  if (counts.alto) return "Revisar alto risco";
  if (counts.medio) return "Validar evidências";
  if (reviewAccounts) return "Conferir contas";
  return "Manter suporte";
}

function truncateText(value, maxLength) {
  const text = String(value || "").trim();
  if (text.length <= maxLength) return text;
  return `${text.slice(0, Math.max(0, maxLength - 3)).trim()}...`;
}
