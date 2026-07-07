const form = document.querySelector("#audit-form");
const output = document.querySelector("#output");
const statusChips = document.querySelector("#status-chips");
const actionBar = document.querySelector("#action-bar");
const reportTitle = document.querySelector("#report-title");
const submitButton = document.querySelector("#submit-button");
const fileInput = document.querySelector("#balancete");
const fileMeta = document.querySelector("#file-meta");
const downloadButton = document.querySelector("#download-btn");
const pdfButton = document.querySelector("#pdf-btn");
const newUploadButton = document.querySelector("#new-upload-btn");
const annualList = document.querySelector("#annual-list");
const annualSavedList = document.querySelector("#annual-saved-list");
const annualGenerateButton = document.querySelector("#annual-generate-btn");
const annualLoadSavedButton = document.querySelector("#annual-load-saved-btn");
const annualGenerateSavedButton = document.querySelector("#annual-generate-saved-btn");
const annualClearButton = document.querySelector("#annual-clear-btn");
const annualStatus = document.querySelector("#annual-status");

let lastData = null;
let activeFindingFilter = "all";
let annualItems = [];
let savedAnnualItems = [];

function normalizeAuditPayload(data) {
  if (!data || !data.identificacao_empresa || !data.resumo_analise) {
    return data || {};
  }

  const ident = data.identificacao_empresa || {};
  const summary = data.resumo_analise || {};
  const conclusion = data.conclusao_tecnica || {};
  const foundation = data.fundamentacao_tecnica_resumida || {};
  const meta = data.metadados || {};
  const counts = summary.achados_por_severidade || {};
  const recommendations = data.recomendacoes_tecnicas || [];
  const findings = (data.principais_achados || []).map((finding, index) => ({
    codigo: finding.codigo,
    titulo: finding.achado,
    nivel: severityToLevel(finding.severidade),
    pontuacao: finding.pontuacao || 0,
    descricao: finding.impacto_tecnico || "",
    evidencia: evidenceFromSummaryFinding(finding),
    recomendacao: recommendationForFinding(recommendations, finding, index),
    normas_aplicaveis: finding.norma_fundamento || [],
  }));

  return {
    identificacao: {
      cliente: summary.empresa,
      cnpj: ident.cnpj,
      regime_tributario: ident.regime_tributario,
      periodo: ident.periodo_analisado,
    },
    risco: {
      nivel_geral: summary.risco_geral || conclusion.risco_geral,
      pontuacao_total: summary.pontuacao_total || 0,
      modalidade_opiniao_sugerida: conclusion.conclusao_sugerida || "",
      classificacao: {
        achados_alto: counts.alta || 0,
        achados_medio: counts.media || 0,
        achados_baixo: counts.baixa || 0,
        achados_compostos: findings.filter((finding) => isCompositeFinding(finding)).length,
      },
      explicacao_pontuacao: summary.principais_pontos || [],
    },
    metricas: {},
    achados: findings,
    contexto_regime: {
      regime: ident.regime_tributario,
      faixa_receita_estimada: "",
      aliquota_efetiva_esperada: "",
      fator_r_calculado: "",
      fator_r_threshold: "",
      sublimite_risco: false,
      observacoes: foundation.observacoes_tecnicas || [],
    },
    meta: {
      versao_schema: meta.versao_schema,
      versao_regras: meta.versao_regras,
      conjunto_regras: meta.conjunto_regras,
      data_analise: meta.data_analise,
      total_contas_analisadas: 0,
      total_regras_verificadas: summary.total_regras_verificadas || 0,
      total_regras_acionadas: summary.total_regras_acionadas || findings.length,
    },
  };
}

function severityToLevel(severity) {
  const value = String(severity || "").toLowerCase();
  if (value === "alta") return "alto";
  if (value === "media" || value === "média") return "medio";
  if (value === "baixa") return "baixo";
  return value;
}

function evidenceFromSummaryFinding(finding) {
  const evidence = {};
  if (finding.evidencia_identificada) evidence.evidencia = finding.evidencia_identificada;
  if (finding.impacto_tecnico) evidence.impacto = finding.impacto_tecnico;
  return evidence;
}

function recommendationForFinding(recommendations, finding, index) {
  const matched = recommendations.find((item) => item.descricao && String(item.descricao).includes(finding.codigo));
  return matched?.descricao || recommendations[index]?.descricao || "";
}

function esc(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function normalizeLevel(level) {
  const value = String(level || "").toLowerCase();
  return ["alto", "medio", "baixo"].includes(value) ? value : "info";
}

function levelLabel(level) {
  const labels = { alto: "Alto", medio: "Médio", baixo: "Baixo", info: "Informativo" };
  return labels[normalizeLevel(level)] || String(level || "").toUpperCase();
}

function opinionLabel(value) {
  const opinions = {
    sem_ressalva: "Sem ressalva",
    com_ressalva: "Com ressalva",
    adversa: "Adversa",
    abstencao_opiniao: "Abstenção de opinião",
  };
  return opinions[value] || String(value || "[VERIFICAR: opinião]").replace(/_/g, " ");
}

function fmt(value) {
  if (value && typeof value === "object" && value.formatado) {
    return esc(value.formatado);
  }
  if (typeof value === "number") {
    return esc(value.toLocaleString("pt-BR"));
  }
  return esc(value ?? "");
}

function metricValue(metrics, key) {
  return metrics?.[key];
}

function evidenceValue(value) {
  if (value && typeof value === "object") {
    if (value.formatado) return value.formatado;
    return JSON.stringify(value);
  }
  return value;
}

function countFindings(findings) {
  return {
    all: findings.length,
    alto: findings.filter((finding) => finding.nivel === "alto").length,
    medio: findings.filter((finding) => finding.nivel === "medio").length,
    baixo: findings.filter((finding) => finding.nivel === "baixo").length,
    compostos: findings.filter((finding) => isCompositeFinding(finding)).length,
  };
}

function isCompositeFinding(finding) {
  return String(finding?.codigo || "").startsWith("SN-COMP");
}

function sortedFindings(findings) {
  const order = { alto: 0, medio: 1, baixo: 2 };
  return [...findings].sort((left, right) => {
    const severity = (order[left.nivel] ?? 9) - (order[right.nivel] ?? 9);
    if (severity !== 0) return severity;
    return String(left.codigo || "").localeCompare(String(right.codigo || ""));
  });
}

function filteredFindings(findings, filter) {
  if (filter === "compostos") {
    return findings.filter((finding) => isCompositeFinding(finding));
  }
  if (["alto", "medio", "baixo"].includes(filter)) {
    return findings.filter((finding) => finding.nivel === filter);
  }
  return findings;
}

function dashboardFilename(ext) {
  const ident = normalizeAuditPayload(lastData)?.identificacao || {};
  const clean = (value, fallback) => String(value || fallback)
    .replace(/\s+/g, "_")
    .replace(/[^\w.-]/g, "_");
  return `auditoria_${clean(ident.cliente, "cliente")}_${clean(ident.periodo, "periodo")}.${ext}`;
}

function setActionsEnabled(enabled) {
  actionBar.classList.toggle("is-hidden", !enabled);
  downloadButton.disabled = !enabled;
  pdfButton.disabled = !enabled;
  newUploadButton.disabled = !enabled;
}

function renderStatus(data) {
  const risk = data?.risco || {};
  const findings = data?.achados || [];
  const level = normalizeLevel(risk.nivel_geral);

  statusChips.innerHTML = [
    `<span class="chip ${level}">Risco: ${levelLabel(level)}</span>`,
    `<span class="chip info">Pontuação: ${esc(risk.pontuacao_total ?? 0)}</span>`,
    `<span class="chip info">Achados: ${esc(findings.length)}</span>`,
  ].join("");
}

function renderEmpty() {
  reportTitle.textContent = "Pré-auditoria fiscal trimestral";
  statusChips.innerHTML = "";
  setActionsEnabled(false);
  output.innerHTML = `
    <div class="empty-state">
      <h3>Aguardando balancete</h3>
      <p>Nenhuma análise gerada nesta sessão.</p>
    </div>
  `;
}

function renderLoading() {
  reportTitle.textContent = "Processando balancete";
  statusChips.innerHTML = "";
  setActionsEnabled(false);
  output.innerHTML = `
    <div class="loading-state">
      <div class="spinner" aria-hidden="true"></div>
      <h3>Processando balancete</h3>
      <p>Leitura, classificação e avaliação de regras em andamento.</p>
    </div>
  `;
}

function renderError(message) {
  reportTitle.textContent = "Falha no processamento";
  statusChips.innerHTML = "";
  setActionsEnabled(false);
  output.innerHTML = `
    <div class="error-state">
      <h3>Não foi possível gerar a análise</h3>
      <p>${esc(message)}</p>
    </div>
  `;
}

function renderDashboard(data) {
  const viewData = normalizeAuditPayload(data);
  const ident = viewData.identificacao || {};
  reportTitle.textContent = `${ident.cliente || "Cliente"} - ${ident.periodo || "Período"}`;
  renderStatus(viewData);
  setActionsEnabled(true);
  output.innerHTML = buildDashboardHtml(viewData, { findingFilter: activeFindingFilter, rawData: data });
  bindDynamicControls();
}

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
      ${renderClassification(classification)}
      ${renderMetricGroups(metrics)}
      ${renderIndicators(metrics.indicadores_derivados)}
      ${renderAnalysisGrid(context, findings, meta, filter)}
      ${renderScoreExplanation(risk.explicacao_pontuacao || [], printMode)}
      ${printMode ? "" : renderRawJson(rawData)}
    </div>
  `;
}

function renderRiskPanel(risk, findings, meta, level) {
  return `
    <section class="risk-panel ${level}">
      <div>
        <span class="risk-kicker">Risco ${levelLabel(level)}</span>
        <h3>${esc(opinionLabel(risk.modalidade_opiniao_sugerida))}</h3>
        <p>Classificação calculada a partir das regras fiscais acionadas no período.</p>
      </div>
      <div class="risk-stats">
        <div class="stat-box"><strong>${esc(risk.pontuacao_total ?? 0)}</strong><span>Pontuação</span></div>
        <div class="stat-box"><strong>${esc(findings.length)}</strong><span>Achados</span></div>
        <div class="stat-box"><strong>${esc(meta.total_contas_analisadas ?? 0)}</strong><span>Contas</span></div>
      </div>
    </section>
  `;
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

function renderMetricGroups(metrics) {
  const groups = [
    {
      title: "Receita e resultado",
      items: [
        ["receita_operacional", "Receita operacional"],
        ["receita_servicos", "Receita de serviços"],
        ["deducoes_receita", "Deduções da receita"],
        ["despesas_operacionais", "Despesas operacionais"],
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
      <div class="value">${fmt(value)}</div>
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

function renderAnalysisGrid(context, findings, meta, filter) {
  const contextHtml = renderContext(context);
  const findingsHtml = renderFindingsSection(findings, meta, filter);
  if (!contextHtml) return findingsHtml;
  return `<div class="analysis-grid">${contextHtml}${findingsHtml}</div>`;
}

function renderFindingsSection(findings, meta, filter) {
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

  const rows = visibleFindings.map(renderFindingRow).join("");
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
              <th>Evidência</th>
              <th>Recomendação</th>
            </tr>
          </thead>
          <tbody>${body}</tbody>
        </table>
      </div>
    </section>
  `;
}

function renderFindingRow(finding) {
  const composite = isCompositeFinding(finding);
  const norms = Array.isArray(finding.normas_aplicaveis) && finding.normas_aplicaveis.length
    ? `<span class="finding-norms">${finding.normas_aplicaveis.map(esc).join("; ")}</span>`
    : "";

  return `
    <tr class="${composite ? "finding-composite" : ""}">
      <td class="finding-code">${esc(finding.codigo)}</td>
      <td><span class="finding-title">${esc(finding.titulo)}</span>${norms}</td>
      <td><span class="chip ${normalizeLevel(finding.nivel)}">${levelLabel(finding.nivel)}</span></td>
      <td>${esc(finding.descricao)}${renderEvidence(finding.evidencia)}</td>
      <td>${esc(finding.recomendacao || "[VERIFICAR: recomendação]")}</td>
    </tr>
  `;
}

function renderEvidence(evidence) {
  if (!evidence || !Object.keys(evidence).length) return "";
  const text = Object.entries(evidence)
    .map(([key, value]) => `${key}: ${evidenceValue(value)}`)
    .join(" | ");
  return `<span class="finding-evidence">${esc(text)}</span>`;
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
        ${lines.map((line) => `<p>${esc(line)}</p>`).join("")}
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

function bindDynamicControls() {
  output.querySelectorAll("[data-finding-filter]").forEach((button) => {
    button.addEventListener("click", () => {
      activeFindingFilter = button.dataset.findingFilter || "all";
      if (lastData) renderDashboard(lastData);
    });
  });

  output.querySelectorAll("[data-toggle-target]").forEach((button) => {
    button.addEventListener("click", () => {
      const target = document.getElementById(button.dataset.toggleTarget);
      if (target) target.classList.toggle("is-hidden");
    });
  });
}

function downloadJson() {
  if (!lastData) return;
  const blob = new Blob([JSON.stringify(lastData, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = dashboardFilename("json");
  link.click();
  URL.revokeObjectURL(url);
}

function printDashboardPdf() {
  if (!lastData) return;

  const viewData = normalizeAuditPayload(lastData);
  const ident = viewData.identificacao || {};
  const title = `Dashboard de auditoria fiscal - ${ident.cliente || "cliente"} - ${ident.periodo || "periodo"}`;
  const content = buildDashboardHtml(viewData, { findingFilter: "all", printMode: true });
  const styleUrl = `${window.location.origin}/static/styles.css`;
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
</head>
<body>
  <main class="print-page">
    <header class="print-header">
      <h1>${esc(title)}</h1>
      <p>Relatório emitido a partir do dashboard de auditoria fiscal.</p>
    </header>
    <section class="report">${content}</section>
  </main>
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

function quarterLabel(period) {
  const value = String(period || "").toUpperCase();
  const match = value.match(/(?:^|[-\s])T([1-4])$/) || value.match(/([1-4])(?:º|O)?\s*TRI/);
  return match ? `T${match[1]}` : value || "T?";
}

function quarterOrder(period) {
  const label = quarterLabel(period);
  const match = label.match(/T([1-4])/);
  return match ? Number(match[1]) : 9;
}

function annualYearFromPeriod(period) {
  const match = String(period || "").match(/(?:19|20)\d{2}/);
  return match ? match[0] : String(new Date().getFullYear());
}

function annualQueryFromForm() {
  return {
    cnpj: String(form?.elements?.cnpj?.value || "").trim(),
    ano: annualYearFromPeriod(form?.elements?.periodo?.value || ""),
  };
}

function saveAnnualQuarter(file, payload, formData) {
  if (!file || !payload) return;

  const summary = payload.resumo_analise || {};
  const ident = payload.identificacao_empresa || {};
  const item = {
    id: `${ident.periodo_analisado || formData.get("periodo") || file.name}`,
    file,
    filename: file.name,
    cliente: summary.empresa || formData.get("cliente") || "",
    cnpj: ident.cnpj || formData.get("cnpj") || "",
    periodo: ident.periodo_analisado || formData.get("periodo") || "",
    atividade: formData.get("atividade") || "servicos",
    risk: summary.risco_geral || "",
    score: summary.pontuacao_total ?? 0,
  };

  const existingIndex = annualItems.findIndex((current) => current.periodo === item.periodo);
  if (existingIndex >= 0) {
    annualItems[existingIndex] = item;
  } else {
    annualItems.push(item);
  }
  annualItems = annualItems.sort((left, right) => quarterOrder(left.periodo) - quarterOrder(right.periodo));
  renderAnnualPanel();
}

function renderAnnualPanel() {
  if (!annualList || !annualGenerateButton || !annualStatus) return;

  const slots = [1, 2, 3, 4].map((number) => {
    const item = annualItems.find((current) => quarterLabel(current.periodo) === `T${number}`);
    if (!item) {
      return `
        <div class="annual-item is-empty">
          <div class="annual-quarter">T${number}</div>
          <div>
            <div class="annual-name">Aguardando balancete</div>
            <div class="annual-meta">2025-T${number}</div>
          </div>
        </div>
      `;
    }
    return `
      <div class="annual-item">
        <div class="annual-quarter">${esc(quarterLabel(item.periodo))}</div>
        <div>
          <div class="annual-name">${esc(item.filename)}</div>
          <div class="annual-meta">${esc(item.periodo)} · risco ${esc(item.risk || "n/d")} · ${esc(item.score)} pts</div>
        </div>
      </div>
    `;
  }).join("");

  annualList.innerHTML = slots;
  annualGenerateButton.disabled = annualItems.length < 4;
  annualStatus.textContent = annualItems.length
    ? `${annualItems.length} de 4 trimestres armazenados nesta sessão.`
    : "Nenhum trimestre armazenado.";
  renderSavedAnnualPanel();
}

function renderSavedAnnualPanel() {
  if (!annualSavedList || !annualGenerateSavedButton) return;

  const query = annualQueryFromForm();
  const slots = [1, 2, 3, 4].map((number) => {
    const item = savedAnnualItems.find((current) => current.trimestre === `T${number}`);
    if (!item) {
      return `
        <div class="annual-item is-empty">
          <div class="annual-quarter">T${number}</div>
          <div>
            <div class="annual-name">Não salvo no backend</div>
            <div class="annual-meta">${esc(query.ano)}-T${number}</div>
          </div>
        </div>
      `;
    }
    return `
      <div class="annual-item">
        <div class="annual-quarter">${esc(item.trimestre)}</div>
        <div>
          <div class="annual-name">${esc(item.arquivo_nome || item.empresa || "Balancete salvo")}</div>
          <div class="annual-meta">${esc(item.periodo)} · risco ${esc(item.risco_geral || "n/d")} · ${esc(item.pontuacao_total || 0)} pts</div>
        </div>
      </div>
    `;
  }).join("");

  annualSavedList.innerHTML = `
    <div class="annual-saved-title">Trimestres salvos no backend</div>
    ${slots}
  `;
  annualGenerateSavedButton.disabled = savedAnnualItems.length < 4;
}

function annualFilename(data) {
  const ident = data?.identificacao || {};
  const clean = (value, fallback) => String(value || fallback)
    .replace(/\s+/g, "_")
    .replace(/[^\w.-]/g, "_");
  return `auditoria_anual_${clean(ident.cliente, "cliente")}_${clean(ident.exercicio, "exercicio")}.json`;
}

function downloadAnnualJson(data) {
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = annualFilename(data);
  link.click();
  URL.revokeObjectURL(url);
}

function renderAnnualResult(data) {
  const ident = data.identificacao || {};
  const risk = data.risco_anual || {};
  const totals = data.metricas_anual || {};
  const findings = data.achados_anuais || [];
  reportTitle.textContent = `${ident.cliente || "Cliente"} - análise anual ${ident.exercicio || ""}`;
  statusChips.innerHTML = [
    `<span class="chip ${normalizeLevel(risk.nivel_geral)}">Risco anual: ${levelLabel(risk.nivel_geral)}</span>`,
    `<span class="chip info">Pontuação: ${esc(risk.pontuacao_total ?? 0)}</span>`,
    `<span class="chip info">Achados anuais: ${esc(findings.length)}</span>`,
  ].join("");
  setActionsEnabled(false);
  output.innerHTML = `
    <div class="dashboard-stack">
      <section class="section">
        <div class="section-header">
          <h3 class="section-title">JSON anual gerado</h3>
        </div>
        <div class="indicator-list">
          <span class="indicator-badge"><strong>Receita anual:</strong>&nbsp;${esc(totals.receita_servicos_total?.formatado || "R$ 0,00")}</span>
          <span class="indicator-badge"><strong>Lucro anual:</strong>&nbsp;${esc(totals.lucro_apurado_total?.formatado || "R$ 0,00")}</span>
          <span class="indicator-badge"><strong>Trimestres:</strong>&nbsp;${esc(data.meta?.total_trimestres_informados || 0)}</span>
        </div>
        <p class="context-observation">O arquivo anual foi baixado automaticamente. O JSON completo também está abaixo para conferência.</p>
        <pre class="raw-json">${esc(JSON.stringify(data, null, 2))}</pre>
      </section>
    </div>
  `;
}

async function generateAnnualJson() {
  if (annualItems.length < 4 || !annualGenerateButton) return;

  annualGenerateButton.disabled = true;
  annualStatus.textContent = "Gerando JSON anual...";

  const body = new FormData();
  const manifest = {
    trimestres: annualItems.map((item, index) => ({
      field: `balancete_${index}`,
      cliente: item.cliente,
      cnpj: item.cnpj,
      periodo: item.periodo,
      atividade: item.atividade,
    })),
  };
  body.append("manifest", JSON.stringify(manifest));
  annualItems.forEach((item, index) => {
    body.append(`balancete_${index}`, item.file, item.filename);
  });

  try {
    const response = await fetch("/api/auditorias/anual-balancetes", {
      method: "POST",
      body,
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.erro || "Falha ao gerar JSON anual.");
    downloadAnnualJson(data);
    renderAnnualResult(data);
    annualStatus.textContent = "JSON anual gerado e baixado.";
  } catch (error) {
    annualStatus.textContent = error.message || "Erro inesperado ao gerar JSON anual.";
  } finally {
    annualGenerateButton.disabled = annualItems.length < 4;
  }
}

async function loadSavedQuarters(options = {}) {
  const { silent = false } = options;
  if (!annualStatus) return;

  const query = annualQueryFromForm();
  if (!query.cnpj) {
    savedAnnualItems = [];
    renderSavedAnnualPanel();
    annualStatus.textContent = "Informe o CNPJ para carregar os trimestres salvos.";
    return;
  }

  if (!silent) annualStatus.textContent = "Carregando trimestres salvos...";

  try {
    const params = new URLSearchParams({ cnpj: query.cnpj, ano: query.ano });
    const response = await fetch(`/api/auditorias?${params.toString()}`);
    const data = await response.json();
    if (!response.ok) throw new Error(data.erro || "Falha ao carregar trimestres salvos.");
    savedAnnualItems = Array.isArray(data.items) ? data.items : [];
    renderSavedAnnualPanel();
    annualStatus.textContent = savedAnnualItems.length
      ? `${savedAnnualItems.length} de 4 trimestres salvos no backend para ${query.ano}.`
      : `Nenhum trimestre salvo no backend para ${query.ano}.`;
  } catch (error) {
    annualStatus.textContent = error.message || "Erro inesperado ao carregar trimestres salvos.";
  }
}

async function generateSavedAnnualJson() {
  if (!annualGenerateSavedButton || savedAnnualItems.length < 4) return;

  const query = annualQueryFromForm();
  annualGenerateSavedButton.disabled = true;
  annualStatus.textContent = "Gerando JSON anual a partir do backend...";

  try {
    const params = new URLSearchParams({ cnpj: query.cnpj, ano: query.ano });
    const response = await fetch(`/api/auditorias/anual?${params.toString()}`, { method: "POST" });
    const data = await response.json();
    if (!response.ok) throw new Error(data.erro || "Falha ao gerar JSON anual salvo.");
    downloadAnnualJson(data);
    renderAnnualResult(data);
    annualStatus.textContent = "JSON anual salvo gerado e baixado.";
  } catch (error) {
    annualStatus.textContent = error.message || "Erro inesperado ao gerar JSON anual salvo.";
  } finally {
    annualGenerateSavedButton.disabled = savedAnnualItems.length < 4;
  }
}

fileInput.addEventListener("change", () => {
  const file = fileInput.files?.[0];
  fileMeta.textContent = file ? `${file.name} · ${(file.size / 1024).toFixed(1)} KB` : "CSV, XLSX ou XLS";
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  submitButton.disabled = true;
  lastData = null;
  activeFindingFilter = "all";
  renderLoading();
  const formData = new FormData(form);
  const uploadedFile = fileInput.files?.[0] || null;

  try {
    const response = await fetch("/api/auditorias", {
      method: "POST",
      body: formData,
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.erro || "Falha ao gerar auditoria.");
    lastData = data;
    saveAnnualQuarter(uploadedFile, data, formData);
    await loadSavedQuarters({ silent: true });
    renderDashboard(data);
  } catch (error) {
    renderError(error.message || "Erro inesperado.");
  } finally {
    submitButton.disabled = false;
  }
});

downloadButton.addEventListener("click", downloadJson);
pdfButton.addEventListener("click", printDashboardPdf);
annualGenerateButton?.addEventListener("click", generateAnnualJson);
annualLoadSavedButton?.addEventListener("click", () => loadSavedQuarters());
annualGenerateSavedButton?.addEventListener("click", generateSavedAnnualJson);
annualClearButton?.addEventListener("click", () => {
  annualItems = [];
  renderAnnualPanel();
  annualStatus.textContent = "Trimestres da sessão limpos. Os registros salvos no backend foram preservados.";
});
newUploadButton.addEventListener("click", () => {
  lastData = null;
  activeFindingFilter = "all";
  form.reset();
  fileMeta.textContent = "CSV, XLSX ou XLS";
  renderEmpty();
  document.querySelector("#cliente").focus();
});

setActionsEnabled(false);
renderAnnualPanel();
renderSavedAnnualPanel();
