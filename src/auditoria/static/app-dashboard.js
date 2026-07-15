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

function renderRiskPanel(risk, findings, meta, level) {
  const rules = `${esc(meta.total_regras_acionadas ?? findings.length)} de ${esc(meta.total_regras_verificadas ?? "?")} regras`;
  const score = Number(risk.pontuacao_total ?? 0);
  const scoreWidth = Math.max(4, Math.min(100, score));
  const version = `${esc(meta.conjunto_regras || "Conjunto não informado")} ${esc(meta.versao_regras || "")}`.trim();
  return `
    <section class="risk-panel ${level}">
      <div class="risk-copy">
        <span class="risk-kicker">Risco ${levelLabel(level)}</span>
        <h3>${esc(risk.orientacao_consultiva || opinionLabel(risk.modalidade_opiniao_sugerida))}</h3>
        <div class="risk-score-track" aria-hidden="true"><span style="width: ${scoreWidth}%"></span></div>
        <p>Classificação calculada a partir das regras fiscais acionadas no período analisado.</p>
        <div class="risk-meta">
          <span>${rules}</span>
          <span>${version}</span>
        </div>
      </div>
      <div class="risk-stats">
        <div class="stat-box"><strong>${esc(risk.pontuacao_total ?? 0)}</strong><span>Pontuação</span></div>
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
        ${renderVisualProgressCard("Pontuação de risco", formatNumberPtBr(score), clampPercent(score), "Escala operacional de 0 a 100 pontos", scoreTone)}
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

function renderClassification(classification) {
  const composite = classification.achados_compostos ?? 0;
  return `
    <section class="section">
      <div class="section-header">
        <h3 class="section-title">Resumo dos achados</h3>
      </div>
      <div class="indicator-list">
        <span class="chip alto">Risco alto: ${esc(classification.achados_alto ?? 0)}</span>
        <span class="chip medio">Risco médio: ${esc(classification.achados_medio ?? 0)}</span>
        <span class="chip baixo">Risco baixo: ${esc(classification.achados_baixo ?? 0)}</span>
        ${composite ? `<span class="chip alto">Achados compostos: ${esc(composite)}</span>` : ""}
      </div>
    </section>
  `;
}

function renderAccountClassification(classification) {
  if (!classification || !classification.total_contas) return "";

  const reviewAccounts = Array.isArray(classification.contas_revisao)
    ? classification.contas_revisao.slice(0, 8)
    : [];
  const reviewTotal = Number(classification.total_contas_revisao || 0);
  const originChips = renderCountChips(classification.classificacoes_por_origem, "Origem");
  const confidenceChips = renderCountChips(classification.classificacoes_por_confianca, "Confiança");
  const reviewRows = reviewAccounts.map(renderAccountReviewRow).join("");
  const reviewTable = reviewRows
    ? `
      <div class="table-wrap">
        <table class="findings-table account-classification-table">
          <thead>
            <tr>
              <th>Código</th>
              <th>Conta</th>
              <th>Grupo</th>
              <th>Origem</th>
              <th>Confiança</th>
              <th>Observação</th>
            </tr>
          </thead>
          <tbody>${reviewRows}</tbody>
        </table>
      </div>
    `
    : `
      <div class="account-review-empty ${reviewTotal ? "warning" : "success"}">
        <strong>${reviewTotal ? "Contas pendentes sem detalhe listado" : "Nenhuma conta marcada para revisão"}</strong>
        <span>${reviewTotal ? "Validar a origem da classificação no JSON técnico." : "A classificação automática não encontrou contas com baixa confiança."}</span>
      </div>
    `;

  return `
    <section class="section account-classification-section">
      <div class="section-header">
        <h3 class="section-title">Classificação das contas</h3>
        <span class="section-note">Apoio para revisar o plano de contas</span>
      </div>
      <div class="indicator-list">
        <span class="indicator-badge"><strong>Contas analisadas:</strong>&nbsp;${esc(classification.total_contas ?? 0)}</span>
        <span class="indicator-badge ${reviewTotal ? "bad" : "ok"}"><strong>Para revisão:</strong>&nbsp;${esc(classification.total_contas_revisao ?? 0)}</span>
        ${originChips}
        ${confidenceChips}
      </div>
      ${reviewTable}
    </section>
  `;
}

function renderCountChips(counts, label) {
  if (!counts || typeof counts !== "object") return "";
  return Object.entries(counts)
    .filter(([, count]) => Number(count) > 0)
    .map(([key, count]) => `<span class="indicator-badge"><strong>${esc(label)} ${esc(key)}:</strong>&nbsp;${esc(count)}</span>`)
    .join("");
}

function renderAccountReviewRow(account) {
  return `
    <tr>
      <td class="finding-code">${esc(account.codigo)}</td>
      <td><span class="finding-title">${esc(account.conta)}</span></td>
      <td>${esc(account.grupo_atribuido)}</td>
      <td>${esc(account.origem_classificacao)}</td>
      <td><span class="chip ${confidenceClass(account.confianca)}">${esc(account.confianca || "nao_informada")}</span></td>
      <td>${esc(account.observacao || "")}</td>
    </tr>
  `;
}

function confidenceClass(value) {
  const normalized = String(value || "").toLowerCase();
  if (normalized === "alta") return "baixo";
  if (normalized === "media") return "medio";
  if (normalized === "baixa") return "alto";
  return "info";
}

function renderMetricGroups(metrics) {
  const groups = [
    {
      title: "Receita e resultado",
      items: [
        ["receita_operacional", "Receita operacional"],
        ["receita_servicos", "Receita de serviços"],
        ["deducoes_receita", "Deduções da receita"],
        ["despesas_operacionais", "Despesas operacionais"],
        ["servicos_terceiros", "Serviços de terceiros"],
        ["lucro_apurado_base", "Lucro apurado"],
      ],
    },
    {
      title: "Tributos e folha",
      items: [
        ["tributos_registrados", "Tributos registrados"],
        ["tributos_a_recolher", "Tributos a recolher"],
        ["folha_pro_labore", "Folha e pró-labore"],
        ["creditos_fiscais", "Créditos fiscais"],
      ],
    },
    {
      title: "Posição patrimonial",
      items: [
        ["caixa_e_bancos", "Caixa e bancos"],
        ["clientes_recebiveis", "Clientes e recebíveis"],
        ["fornecedores", "Fornecedores"],
        ["emprestimos", "Empréstimos"],
        ["adiantamentos", "Adiantamentos"],
        ["adiantamentos_clientes", "Adiantamentos de clientes"],
        ["estoques", "Estoques"],
        ["cmv_custos", "CMV/custos"],
        ["patrimonio_liquido", "Patrimônio líquido"],
        ["lucros_distribuidos", "Lucros distribuídos"],
      ],
    },
  ];

  const renderedGroups = groups
    .map((group) => renderMetricGroup(group.title, group.items, metrics))
    .filter(Boolean)
    .join("");

  if (!renderedGroups) return "";

  return `
    <section class="section">
      <div class="section-header">
        <h3 class="section-title">Métricas</h3>
      </div>
      ${renderedGroups}
    </section>
  `;
}

function renderMetricGroup(title, items, metrics) {
  const cards = items
    .map(([key, label]) => renderMetricCard(key, label, metricValue(metrics, key), metrics))
    .filter(Boolean)
    .join("");

  if (!cards) return "";

  return `
    <div class="metric-group">
      <h4 class="metric-group-title">${esc(title)}</h4>
      <div class="metric-grid">${cards}</div>
    </div>
  `;
}

function renderMetricCard(key, label, value, metrics) {
  if (!value) return "";
  const detail = key === "lucro_apurado_base" && metrics.origem_lucro_apurado
    ? `<div class="detail">${esc(metrics.origem_lucro_apurado)}</div>`
    : "";

  return `
    <div class="metric-card">
      <div class="label">${esc(label)}</div>
      <div class="value">${formatMetricDisplay(key, value)}</div>
      ${detail}
    </div>
  `;
}

function renderIndicators(indicators) {
  if (!indicators) return "";

  const indicatorLabels = [
    ["carga_tributaria_efetiva_percentual", "Carga tributária"],
    ["percentual_deducoes_sobre_receita", "Deduções sobre receita"],
    ["percentual_folha_sobre_receita", "Folha sobre receita"],
    ["percentual_despesas_sobre_receita", "Despesas sobre receita"],
    ["percentual_servicos_terceiros_sobre_despesas", "Serviços terceiros/despesas"],
    ["endividamento_bancario_sobre_receita", "Empréstimos sobre receita"],
  ];

  const badges = indicatorLabels
    .map(([key, label]) => indicators[key] ? `<span class="indicator-badge"><strong>${esc(label)}:</strong>&nbsp;${esc(indicators[key])}</span>` : "")
    .join("");

  const resultBadge = indicators.resultado_positivo === undefined
    ? ""
    : `<span class="indicator-badge ${indicators.resultado_positivo ? "ok" : "bad"}"><strong>Resultado:</strong>&nbsp;${indicators.resultado_positivo ? "Positivo" : "Negativo"}</span>`;

  if (!badges && !resultBadge) return "";

  return `
    <section class="section">
      <div class="section-header">
        <h3 class="section-title">Indicadores derivados</h3>
      </div>
      <div class="indicator-list">${badges}${resultBadge}</div>
    </section>
  `;
}

function renderContext(context) {
  if (!context.regime) return "";

  const items = [
    ["regime", "Regime"],
    ["anexo_estimado", "Anexo estimado"],
    ["faixa_receita_estimada", "Faixa de receita"],
    ["aliquota_efetiva_esperada", "Alíquota estimada"],
    ["aliquota_nominal_estimada", "Alíquota nominal"],
    ["parcela_deduzir_estimada", "Parcela a deduzir"],
  ].map(([key, label]) => {
    if (!context[key]) return "";
    return `<div class="context-item"><div class="label">${esc(label)}</div><div class="value">${esc(context[key])}</div></div>`;
  }).join("");

  const factor = context.fator_r_calculado
    ? `<div class="context-item"><div class="label">Fator R</div><div class="value">${esc(context.fator_r_calculado)} (${esc(context.fator_r_threshold || "28%")})</div></div>`
    : "";

  const sublimit = context.sublimite_risco
    ? `<div class="context-item warning"><div class="label">Sublimite</div><div class="value">Acima da faixa de atenção</div></div>`
    : "";

  const observations = Array.isArray(context.observacoes)
    ? context.observacoes.map((item) => `<div class="context-observation">${esc(item)}</div>`).join("")
    : "";

  return `
    <section class="section context-section">
      <div class="section-header">
        <h3 class="section-title">Contexto do regime</h3>
      </div>
      <div class="context-grid">${items}${factor}${sublimit}</div>
      ${observations}
    </section>
  `;
}

function renderAnalysisGrid(context, findings, meta, filter, printMode = false) {
  const contextHtml = renderContext(context);
  const findingsHtml = renderFindingsSection(findings, meta, filter, printMode);
  if (!contextHtml) return findingsHtml;
  return `<div class="analysis-grid">${contextHtml}${findingsHtml}</div>`;
}

function renderFindingsSection(findings, meta, filter, printMode = false) {
  const counts = countFindings(findings);
  const visibleFindings = filteredFindings(findings, filter);
  const filterButtons = [
    ["all", "Todos", counts.all],
    ["alto", "Alto", counts.alto],
    ["medio", "Médio", counts.medio],
    ["baixo", "Baixo", counts.baixo],
    ["compostos", "Compostos", counts.compostos],
  ].map(([key, label, count]) => (
    `<button class="filter-button ${filter === key ? "is-active" : ""}" type="button" data-finding-filter="${key}">${label} (${count})</button>`
  )).join("");

  const rows = visibleFindings.map((finding, index) => renderFindingRow(finding, index, "finding-detail", printMode)).join("");
  const body = rows || `<tr><td colspan="5"><div class="finding-empty">Nenhum achado nesta seleção.</div></td></tr>`;

  return `
    <section class="section findings-section">
      <div class="section-header">
        <h3 class="section-title">Achados (${esc(findings.length)})</h3>
        <div class="finding-toolbar">${filterButtons}</div>
      </div>
      <div class="indicator-list">
        <span class="indicator-badge">${esc(meta.total_regras_acionadas ?? findings.length)} regras acionadas</span>
        <span class="indicator-badge">${esc(meta.total_regras_verificadas ?? "?")} regras verificadas</span>
        <span class="indicator-badge">${esc(meta.conjunto_regras || "Conjunto não informado")} ${esc(meta.versao_regras || "")}</span>
      </div>
      <div class="table-wrap">
        <table class="findings-table">
          <thead>
            <tr>
              <th>Código</th>
              <th>Achado</th>
              <th>Nível</th>
              <th>Pontuação</th>
              <th>Detalhes</th>
            </tr>
          </thead>
          <tbody>${body}</tbody>
        </table>
      </div>
    </section>
  `;
}

function renderFindingRow(finding, index, prefix = "finding-detail", expanded = false) {
  const composite = isCompositeFinding(finding);
  const detailId = findingDetailId(finding, index, prefix);
  const detailClass = expanded ? "finding-detail-row" : "finding-detail-row is-hidden";

  return `
    <tr class="${composite ? "finding-composite" : ""}">
      <td class="finding-code">${esc(finding.codigo)}</td>
      <td>
        <span class="finding-title">${displayText(finding.titulo)}</span>
        <span class="finding-impact-summary">${displayText(finding.descricao || "Impacto técnico não informado.")}</span>
      </td>
      <td><span class="chip ${normalizeLevel(finding.nivel)}">${levelLabel(finding.nivel)}</span></td>
      <td><strong>${esc(finding.pontuacao ?? 0)}</strong></td>
      <td><button class="toggle-button finding-detail-button" type="button" data-toggle-target="${detailId}">Abrir</button></td>
    </tr>
    <tr id="${detailId}" class="${detailClass}">
      <td colspan="5">${renderFindingDetail(finding)}</td>
    </tr>
  `;
}

function findingDetailId(finding, index, prefix) {
  const code = String(finding.codigo || "achado")
    .toLowerCase()
    .replace(/[^\w-]+/g, "-");
  return `${prefix}-${index}-${code}`;
}

function renderFindingDetail(finding) {
  const norms = Array.isArray(finding.normas_aplicaveis) && finding.normas_aplicaveis.length
    ? finding.normas_aplicaveis.map((item) => `<li>${displayText(item)}</li>`).join("")
    : `<li>[VERIFICAR: fundamento normativo]</li>`;
  const evidence = renderEvidenceList(finding.evidencia);

  return `
    <div class="finding-detail-panel">
      <div>
        <span class="detail-label">Evidência identificada</span>
        ${evidence}
      </div>
      ${renderStructuredEvidence(finding.evidencia_estruturada)}
      <div>
        <span class="detail-label">Impacto técnico</span>
        <p>${displayText(finding.descricao || "[VERIFICAR: impacto técnico]")}</p>
      </div>
      <div>
        <span class="detail-label">Normas e fundamentos</span>
        <ul>${norms}</ul>
      </div>
      <div>
        <span class="detail-label">Recomendação técnica</span>
        <p>${displayText(finding.recomendacao || "[VERIFICAR: recomendação]")}</p>
      </div>
    </div>
  `;
}

function renderStructuredEvidence(evidence) {
  if (!evidence || typeof evidence !== "object" || !Object.keys(evidence).length) return "";

  const docs = Array.isArray(evidence.documentos_recomendados)
    ? evidence.documentos_recomendados.map((item) => `<li>${displayText(item)}</li>`).join("")
    : "";
  const fields = evidence.campos_extraidos && typeof evidence.campos_extraidos === "object"
    ? Object.entries(evidence.campos_extraidos)
      .map(([key, value]) => `<li><strong>${displayText(humanizeKey(key))}:</strong> ${displayText(evidenceValue(value))}</li>`)
      .join("")
    : "";

  return `
    <div>
      <span class="detail-label">Evidência estruturada</span>
      <ul>
        <li><strong>Fonte:</strong> ${displayText(evidence.fonte_dado || "[VERIFICAR: fonte]")}</li>
        <li><strong>Confiança:</strong> ${displayText(evidence.confianca || "[VERIFICAR: confiança]")}</li>
        <li><strong>Necessita documento:</strong> ${evidence.necessita_documento ? "Sim" : "Não"}</li>
      </ul>
      ${docs ? `<span class="detail-label">Documentos recomendados</span><ul>${docs}</ul>` : ""}
      ${fields ? `<span class="detail-label">Campos extraídos</span><ul>${fields}</ul>` : ""}
    </div>
  `;
}

function renderEvidence(evidence) {
  if (!evidence || !Object.keys(evidence).length) return "";
  const text = Object.entries(evidence)
    .map(([key, value]) => `${key}: ${evidenceValue(value)}`)
    .join(" | ");
  return `<span class="finding-evidence">${displayText(text)}</span>`;
}

function renderEvidenceList(evidence) {
  if (!evidence || !Object.keys(evidence).length) {
    return `<p>[VERIFICAR: evidência]</p>`;
  }
  const items = Object.entries(evidence)
    .map(([key, value]) => `<li><strong>${displayText(humanizeKey(key))}:</strong> ${displayText(evidenceValue(value))}</li>`)
    .join("");
  return `<ul>${items}</ul>`;
}

function renderScoreExplanation(lines, expanded = false) {
  if (!lines.length) return "";
  const detailClass = expanded ? "detail-panel" : "detail-panel is-hidden";
  return `
    <section class="section">
      <div class="section-header">
        <h3 class="section-title">Explicação da pontuação</h3>
        <button class="toggle-button" type="button" data-toggle-target="score-detail">Mostrar ou ocultar</button>
      </div>
      <div id="score-detail" class="${detailClass}">
        ${lines.map((line) => `<p>${displayText(line)}</p>`).join("")}
      </div>
    </section>
  `;
}

function renderRawJson(data) {
  return `
    <section class="section">
      <div class="section-header">
        <h3 class="section-title">JSON completo</h3>
        <button class="toggle-button" type="button" data-toggle-target="raw-json">Mostrar ou ocultar</button>
      </div>
      <pre id="raw-json" class="raw-json is-hidden">${esc(JSON.stringify(data, null, 2))}</pre>
    </section>
  `;
}
