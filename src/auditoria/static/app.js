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
  const dashboard = data.dashboard || {};
  const dashboardMeta = dashboard.meta || {};
  const dashboardContext = dashboard.contexto_regime || {};
  const classificationData = data.classificacao_contas || dashboard.classificacao_contas || {};
  const counts = summary.achados_por_severidade || {};
  const recommendations = data.recomendacoes_tecnicas || [];
  const findings = (data.principais_achados || []).map((finding, index) => ({
    codigo: finding.codigo,
    titulo: finding.achado,
    nivel: severityToLevel(finding.severidade),
    pontuacao: finding.pontuacao || 0,
    descricao: finding.impacto_tecnico || "",
    evidencia: evidenceFromSummaryFinding(finding),
    evidencia_estruturada: finding.evidencia || {},
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
    metricas: dashboard.metricas || data.metricas || {},
    achados: findings,
    contexto_regime: {
      regime: dashboardContext.regime || ident.regime_tributario,
      anexo_estimado: dashboardContext.anexo_estimado || "",
      faixa_receita_estimada: dashboardContext.faixa_receita_estimada || "",
      aliquota_efetiva_esperada: dashboardContext.aliquota_efetiva_esperada || "",
      aliquota_nominal_estimada: dashboardContext.aliquota_nominal_estimada || "",
      parcela_deduzir_estimada: dashboardContext.parcela_deduzir_estimada || "",
      base_calculo_estimativa: dashboardContext.base_calculo_estimativa || "",
      receita_rbt12_utilizada: dashboardContext.receita_rbt12_utilizada || "",
      rbt12_disponivel: dashboardContext.rbt12_disponivel,
      origem_rbt12: dashboardContext.origem_rbt12 || "",
      fator_r_calculado: dashboardContext.fator_r_calculado || "",
      fator_r_threshold: dashboardContext.fator_r_threshold || "",
      sublimite_risco: Boolean(dashboardContext.sublimite_risco),
      observacoes: dashboardContext.observacoes || foundation.observacoes_tecnicas || [],
    },
    meta: {
      versao_schema: meta.versao_schema,
      versao_regras: meta.versao_regras,
      conjunto_regras: meta.conjunto_regras,
      data_analise: meta.data_analise,
      total_contas_analisadas: dashboardMeta.total_contas_analisadas ?? classificationData.total_contas ?? 0,
      total_regras_verificadas: dashboardMeta.total_regras_verificadas ?? summary.total_regras_verificadas ?? 0,
      total_regras_acionadas: dashboardMeta.total_regras_acionadas ?? summary.total_regras_acionadas ?? findings.length,
    },
    consultivo: data.consultivo || dashboard.consultivo || {},
    classificacao_contas: classificationData,
  };
}

function formalAuditPayload(data) {
  if (!data || typeof data !== "object" || Array.isArray(data)) return data;
  const { dashboard, ...payload } = data;
  return payload;
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

function displayText(value) {
  return esc(polishPortugueseText(value));
}

function polishPortugueseText(value) {
  let text = String(value ?? "");
  const replacements = [
    [/\brelatorio\b/gi, "relatório"],
    [/\banalise\b/gi, "análise"],
    [/\bacao\b/gi, "ação"],
    [/\bacoes\b/gi, "ações"],
    [/\batencao\b/gi, "atenção"],
    [/\bdecisao\b/gi, "decisão"],
    [/\bdecisoes\b/gi, "decisões"],
    [/\bsocios\b/gi, "sócios"],
    [/\bsocio\b/gi, "sócio"],
    [/\bvalidacao\b/gi, "validação"],
    [/\bmutuo\b/gi, "mútuo"],
    [/\brazao\b/gi, "razão"],
    [/\bcalculo\b/gi, "cálculo"],
    [/\bmemoria\b/gi, "memória"],
    [/\bproximo\b/gi, "próximo"],
    [/\bproximos\b/gi, "próximos"],
    [/\bperiodo\b/gi, "período"],
    [/\bretencoes\b/gi, "retenções"],
    [/\bservicos\b/gi, "serviços"],
    [/\bservico\b/gi, "serviço"],
    [/\bnao\b/gi, "não"],
    [/\bate\b/gi, "até"],
    [/\bja\b/gi, "já"],
    [/\bcompetencia\b/gi, "competência"],
    [/\bcompetencias\b/gi, "competências"],
    [/\bdistribuicao\b/gi, "distribuição"],
    [/\bdocumentacao\b/gi, "documentação"],
    [/\bapuracao\b/gi, "apuração"],
    [/\bcontabil\b/gi, "contábil"],
    [/\bcontabeis\b/gi, "contábeis"],
    [/\blancamento\b/gi, "lançamento"],
    [/\blancamentos\b/gi, "lançamentos"],
    [/\bbancario\b/gi, "bancário"],
    [/\bbancarios\b/gi, "bancários"],
    [/\bliquidacao\b/gi, "liquidação"],
    [/\bfisico\b/gi, "físico"],
    [/\bcompativel\b/gi, "compatível"],
    [/\boperacao\b/gi, "operação"],
    [/\boperacoes\b/gi, "operações"],
    [/\bnumerario\b/gi, "numerário"],
    [/\bespecie\b/gi, "espécie"],
    [/\bconciliacao\b/gi, "conciliação"],
    [/\bsaida\b/gi, "saída"],
    [/\bsaidas\b/gi, "saídas"],
    [/\baplicavel\b/gi, "aplicável"],
    [/\baplicaveis\b/gi, "aplicáveis"],
    [/\bultimos\b/gi, "últimos"],
    [/\bultimo\b/gi, "último"],
    [/\bcontraprestacao\b/gi, "contraprestação"],
    [/\bapropriacao\b/gi, "apropriação"],
    [/\bapropriacoes\b/gi, "apropriações"],
    [/\bcomprovacao\b/gi, "comprovação"],
    [/\brevisao\b/gi, "revisão"],
    [/\bevidencia\b/gi, "evidência"],
    [/\bevidencias\b/gi, "evidências"],
    [/\btributario\b/gi, "tributário"],
    [/\btributaria\b/gi, "tributária"],
    [/\btecnico\b/gi, "técnico"],
    [/\btecnica\b/gi, "técnica"],
    [/\bclassificacao\b/gi, "classificação"],
    [/\brecebiveis\b/gi, "recebíveis"],
    [/\bemissao\b/gi, "emissão"],
    [/\bpossivel\b/gi, "possível"],
    [/\bnecessario\b/gi, "necessário"],
    [/\bnecessarios\b/gi, "necessários"],
    [/\bpro-labore\b/gi, "pró-labore"],
    [/\bmedia\b/gi, "média"],
    [/\bmedio\b/gi, "médio"],
  ];

  replacements.forEach(([pattern, replacement]) => {
    text = text.replace(pattern, (match) => matchCase(match, replacement));
  });

  return text
    .replace(/\s+([,.;:])/g, "$1")
    .replace(/\s{2,}/g, " ")
    .trim();
}

function matchCase(match, replacement) {
  if (match === match.toUpperCase()) return replacement.toUpperCase();
  if (match.charAt(0) === match.charAt(0).toUpperCase()) {
    return replacement.charAt(0).toUpperCase() + replacement.slice(1);
  }
  return replacement;
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
    return esc(formatNumberPtBr(value));
  }
  return esc(value ?? "");
}

function formatNumberPtBr(value, options = {}) {
  const number = Number(value);
  const safeNumber = Number.isFinite(number) ? number : 0;
  return safeNumber.toLocaleString("pt-BR", {
    minimumFractionDigits: options.minimumFractionDigits ?? 0,
    maximumFractionDigits: options.maximumFractionDigits ?? 2,
  });
}

function formatCountDisplay(value) {
  const number = Number(value);
  if (Number.isFinite(number)) return formatNumberPtBr(number);
  return String(value ?? "0");
}

function formatCurrencyPtBr(value) {
  const number = Number(value);
  const safeNumber = Number.isFinite(number) ? number : 0;
  return safeNumber.toLocaleString("pt-BR", {
    style: "currency",
    currency: "BRL",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

function numericValue(value) {
  if (value && typeof value === "object" && value.valor !== undefined) {
    return numericValue(value.valor);
  }
  if (typeof value === "number") {
    return Number.isFinite(value) ? value : 0;
  }
  const text = String(value ?? "").trim();
  if (!text) return 0;
  const normalized = text
    .replace(/[^\d,.-]/g, "")
    .replace(/\.(?=\d{3}(?:\D|$))/g, "")
    .replace(",", ".");
  const number = Number(normalized);
  return Number.isFinite(number) ? number : 0;
}

function percentValue(value) {
  const number = numericValue(value);
  if (String(value ?? "").includes("%")) return number;
  if (Math.abs(number) <= 1) return number * 100;
  return number;
}

function clampPercent(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return 0;
  return Math.max(0, Math.min(100, number));
}

function formatMetricDisplay(key, value) {
  if (value && typeof value === "object" && value.formatado) {
    return esc(value.formatado);
  }
  if (monetaryMetricKeys().has(key)) {
    return esc(formatCurrencyPtBr(numericValue(value)));
  }
  return fmt(value);
}

function monetaryMetricKeys() {
  return new Set([
    "receita_servicos",
    "receita_operacional",
    "deducoes_receita",
    "tributos",
    "tributos_a_recolher",
    "tributos_registrados",
    "folha_pro_labore",
    "despesas",
    "despesas_operacionais",
    "servicos_terceiros",
    "saldo_contas_socios",
    "lucros_distribuidos",
    "lucro_apurado_base",
    "caixa_bancos",
    "caixa_e_bancos",
    "clientes_recebiveis",
    "adiantamentos",
    "adiantamentos_clientes",
    "fornecedores",
    "estoques",
    "cmv_custos",
    "creditos_fiscais",
    "emprestimos",
    "patrimonio_liquido",
  ]);
}

function formatDateTimePtBr(value = new Date()) {
  const date = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleString("pt-BR", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function hasDisplayValue(value) {
  return value !== undefined && value !== null && value !== "";
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
      <p>Informe os dados da empresa e envie um arquivo CSV, XLSX ou XLS para iniciar a análise trimestral.</p>
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
        <h3>${esc(opinionLabel(risk.modalidade_opiniao_sugerida))}</h3>
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
          <small>Pontuação ${esc(formatNumberPtBr(risk.pontuacao_total ?? 0))}</small>
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

function renderPrintMetaItem(label, value) {
  return `
    <div class="pdf-meta-item">
      <span>${esc(label)}</span>
      <strong>${esc(value)}</strong>
    </div>
  `;
}

function renderPrintSummaryText(level, risk, triggeredRules, checkedRules, counts) {
  const orientation = consultativeOpinionText(risk.modalidade_opiniao_sugerida);
  const score = formatNumberPtBr(risk.pontuacao_total ?? 0);
  return `Foram verificadas ${esc(checkedRules)} regras, das quais ${esc(triggeredRules)} foram acionadas. O risco geral foi classificado como ${levelLabel(level).toLowerCase()}, com pontuação total de ${esc(score)} ${pluralize(Number(risk.pontuacao_total ?? 0), "ponto", "pontos")}. A orientação consultiva é: ${esc(orientation)}. A distribuição dos achados foi de ${findingCountText(counts)}. Este relatório deve ser usado como roteiro de revisão, validação documental e orientação ao cliente.`;
}

function renderPrintSummaryCard(label, value) {
  return `
    <div class="pdf-summary-card">
      <span>${esc(label)}</span>
      <strong>${esc(formatCountDisplay(value))}</strong>
    </div>
  `;
}

function renderPrintVisualSummary(risk, counts, context) {
  const score = Number(risk.pontuacao_total ?? 0);
  const rbt12Value = numericValue(context.receita_rbt12_utilizada);
  const rbt12Percent = rbt12Value ? (rbt12Value / 4800000) * 100 : 0;
  const totalFindings = Math.max(1, counts.alto + counts.medio + counts.baixo);
  const severityRows = [
    ["alto", "Alta", counts.alto],
    ["medio", "Média", counts.medio],
    ["baixo", "Baixa", counts.baixo],
  ].map(([level, label, value]) => {
    const width = (Number(value || 0) / totalFindings) * 100;
    return `
      <div class="pdf-severity-row ${level}">
        <span>${esc(label)}</span>
        <i><b style="width: ${clampPercent(width)}%"></b></i>
        <strong>${esc(value)}</strong>
      </div>
    `;
  }).join("");

  return `
    <div class="pdf-visual-grid">
      <div class="pdf-visual-card">
        <span>Pontuação</span>
        <strong>${esc(formatNumberPtBr(score))}</strong>
        <div class="pdf-progress"><i style="width: ${clampPercent(score)}%"></i></div>
      </div>
      <div class="pdf-visual-card">
        <span>RBT12 / limite</span>
        <strong>${esc(rbt12Value ? formatCurrencyPtBr(rbt12Value) : "Não informado")}</strong>
        <div class="pdf-progress"><i style="width: ${clampPercent(rbt12Percent)}%"></i></div>
      </div>
      <div class="pdf-visual-card pdf-severity-card">
        <span>Severidade</span>
        ${severityRows}
      </div>
    </div>
  `;
}

function pluralize(value, singular, plural) {
  return Math.abs(Number(value || 0)) === 1 ? singular : plural;
}

function findingCountText(counts) {
  const parts = [
    `${counts.alto} ${pluralize(counts.alto, "achado alto", "achados altos")}`,
    `${counts.medio} ${pluralize(counts.medio, "achado médio", "achados médios")}`,
    `${counts.baixo} ${pluralize(counts.baixo, "achado baixo", "achados baixos")}`,
  ];
  return parts.join(", ");
}

function consultativeOpinionText(value) {
  if (value === "sem_ressalva") {
    return "manter a documentação suporte e acompanhar os controles nos próximos trimestres";
  }
  if (value === "com_ressalva") {
    return "corrigir ou documentar os pontos destacados antes do fechamento definitivo";
  }
  if (value === "adversa") {
    return "priorizar a regularização dos achados relevantes antes de usar os dados para decisões externas ou fechamento anual";
  }
  if (value === "abstencao_opiniao") {
    return "obter documentação complementar antes de concluir a análise";
  }
  return "validar os achados com documentação de suporte e registrar as providências adotadas";
}

function renderClientGuidanceSection(level, findings, counts, consultivo = {}) {
  const priority = level === "alto"
    ? "prioridade imediata"
    : level === "medio"
      ? "prioridade de acompanhamento no curto prazo"
      : "prioridade de manutenção e conferência preventiva";
  const mainText = consultivo.leitura_cliente || `O resultado indica ${priority}. A análise não substitui a conferência documental, mas mostra os pontos que merecem atenção para reduzir riscos fiscais, contábeis, trabalhistas e societários.`;
  const orientativeSummary = consultivo.resumo_orientativo
    ? `<p class="pdf-consultive-note">${displayText(consultivo.resumo_orientativo)}</p>`
    : "";
  const topFindings = findings.slice(0, 3)
    .map((finding) => `<li>${displayText(clientSafeText(finding.titulo || finding.codigo))}</li>`)
    .join("");
  const noFindings = "<li>Nenhum achado foi acionado, mas recomenda-se manter a documentação organizada para conferência futura.</li>";

  return `
    <section class="pdf-section pdf-client-section">
      <h2>Leitura para o cliente</h2>
      <p>${displayText(mainText)}</p>
      <div class="pdf-client-grid">
        <div>
          <h3>Principais mensagens</h3>
          <ul class="pdf-list">${topFindings || noFindings}</ul>
        </div>
        <div>
          <h3>Como conduzir</h3>
          <ul class="pdf-list">
            <li>Separar os documentos que comprovam cada lançamento apontado.</li>
            <li>Validar saldos com razão contábil, extratos, notas fiscais, contratos e relatórios auxiliares.</li>
            <li>Regularizar lançamentos, baixas ou reclassificações antes do fechamento definitivo.</li>
            <li>Manter registro da providência tomada para acompanhamento nos próximos trimestres.</li>
          </ul>
        </div>
      </div>
      ${orientativeSummary}
      <p class="pdf-consultive-note">Leitura de risco: ${counts.alto > 0 ? "há pontos que devem ser tratados antes de decisões como distribuição de lucros, obtenção de crédito ou fechamento anual." : "os pontos identificados devem ser acompanhados para evitar acúmulo de pendências no fechamento anual."}</p>
    </section>
  `;
}

function renderConsultativeActionPlan(findings, consultivo = {}) {
  const structuredPlan = Array.isArray(consultivo.plano_acao) ? consultivo.plano_acao : [];
  if (structuredPlan.length) {
    const cards = structuredPlan.map(renderStructuredConsultativeActionCard).join("");
    return `
      <section class="pdf-section pdf-action-section">
        <h2>Plano de ação consultivo</h2>
        <p>Roteiro prático estruturado a partir do JSON consultivo para orientar o cliente e apoiar a equipe contábil.</p>
        <div class="pdf-action-list">${cards}</div>
      </section>
    `;
  }

  if (!findings.length) {
    return `
      <section class="pdf-section pdf-action-section">
        <h2>Plano de ação consultivo</h2>
        <div class="pdf-action-empty">
          <strong>Nenhuma ação corretiva prioritária foi indicada pelo motor.</strong>
          <span>Manter conciliações, documentação fiscal e controles auxiliares atualizados para os próximos trimestres.</span>
        </div>
      </section>
    `;
  }

  const visibleFindings = findings.slice(0, 8);
  const cards = visibleFindings.map(renderConsultativeActionCard).join("");
  const hiddenCount = findings.length - visibleFindings.length;
  const footer = hiddenCount > 0
    ? `<p class="pdf-consultive-note">Além dos itens acima, existem ${hiddenCount} ${pluralize(hiddenCount, "achado adicional", "achados adicionais")} ${pluralize(hiddenCount, "detalhado", "detalhados")} na análise técnica.</p>`
    : "";

  return `
    <section class="pdf-section pdf-action-section">
      <h2>Plano de ação consultivo</h2>
      <p>Roteiro prático para orientar o cliente e apoiar a equipe contábil na correção ou validação dos pontos identificados.</p>
      <div class="pdf-action-list">${cards}</div>
      ${footer}
    </section>
  `;
}

function renderStructuredConsultativeActionCard(item) {
  const level = severityToLevel(item.prioridade);
  const documents = Array.isArray(item.documentos_necessarios)
    ? item.documentos_necessarios.map((doc) => `<li>${displayText(doc)}</li>`).join("")
    : "";
  return `
    <article class="pdf-action-card ${level}">
      <header>
        <span class="finding-code">${esc(item.codigo)}</span>
        <span class="chip ${level}">${priorityLabel(level)}</span>
      </header>
      <h3>${displayText(clientSafeText(item.ponto_atencao || "Ponto de atenção"))}</h3>
      <div class="pdf-action-grid">
        <div>
          <span>O que significa</span>
          <p>${displayText(item.o_que_significa || "[VERIFICAR: significado]")}</p>
        </div>
        <div>
          <span>Como solucionar</span>
          <p>${displayText(item.como_solucionar || "[VERIFICAR: solução]")}</p>
        </div>
        <div>
          <span>Documentos necessários</span>
          <ul>${documents || "<li>[VERIFICAR: documentos necessários]</li>"}</ul>
        </div>
        <div>
          <span>Responsável e prazo</span>
          <p>${displayText(item.responsavel_sugerido || "[VERIFICAR: responsável]")}</p>
          <p>${displayText(item.prazo_sugerido || "[VERIFICAR: prazo]")}</p>
        </div>
      </div>
    </article>
  `;
}

function renderConsultativeActionCard(finding) {
  const level = normalizeLevel(finding.nivel);
  const documents = requiredDocumentsForFinding(finding)
    .map((item) => `<li>${displayText(item)}</li>`)
    .join("");
  return `
    <article class="pdf-action-card ${level}">
      <header>
        <span class="finding-code">${esc(finding.codigo)}</span>
        <span class="chip ${level}">${priorityLabel(level)}</span>
      </header>
      <h3>${displayText(clientSafeText(finding.titulo || "Ponto de atenção"))}</h3>
      <div class="pdf-action-grid">
        <div>
          <span>O que significa</span>
          <p>${displayText(consultativeMeaning(finding))}</p>
        </div>
        <div>
          <span>Como solucionar</span>
          <p>${displayText(consultativeSolution(finding))}</p>
        </div>
        <div>
          <span>Documentos necessários</span>
          <ul>${documents}</ul>
        </div>
        <div>
          <span>Responsável sugerido</span>
          <p>${displayText(suggestedOwner(finding))}</p>
        </div>
      </div>
    </article>
  `;
}

function priorityLabel(level) {
  if (level === "alto") return "Prioridade alta";
  if (level === "medio") return "Prioridade média";
  if (level === "baixo") return "Prioridade baixa";
  return "Acompanhar";
}

function clientSafeText(value) {
  return String(value || "")
    .replace(/poss[ií]vel sinal de sonega[cç][aã]o fiscal/gi, "risco de receita não reconhecida ou tratamento fiscal pendente")
    .replace(/sonega[cç][aã]o fiscal/gi, "risco fiscal")
    .replace(/omiss[aã]o de receita/gi, "receita possivelmente não reconhecida")
    .replace(/fraude/gi, "irregularidade")
    .replace(/adversa/gi, "risco elevado");
}

function consultativeMeaning(finding) {
  const code = String(finding.codigo || "");
  const text = clientSafeText(finding.descricao || "");
  if (code.startsWith("SN-004")) return "A distribuição de lucros precisa ter lastro contábil suficiente. Sem suporte, pode gerar questionamentos fiscais e societários.";
  if (code.startsWith("SN-005")) return "Saldos com sócios indicam movimentações que precisam de contrato, conciliação e validação tributária, especialmente quando houver mútuo.";
  if (code.startsWith("SN-006") || code.startsWith("SN-022")) return "O saldo de caixa ou bancos precisa ser compatível com a operação e com os comprovantes financeiros disponíveis.";
  if (code.startsWith("SN-008")) return "A movimentação financeira pode não estar totalmente alinhada ao faturamento reconhecido no período.";
  if (code.startsWith("SN-010") || code.startsWith("SN-023")) return "Os recebíveis precisam refletir vendas ou serviços efetivamente pendentes de recebimento, com baixas e controles auxiliares consistentes.";
  if (code.startsWith("SN-015") || code.startsWith("SN-018")) return "Estoque, CMV e margem precisam estar coerentes com a atividade, compras, vendas e controles internos.";
  if (code.startsWith("SN-025")) return "Serviços de terceiros relevantes em despesas exigem comprovação documental para confirmar natureza, competência e vínculo com a atividade.";
  if (code.startsWith("SN-026")) return "Adiantamentos de clientes no passivo podem ser legítimos, mas precisam comprovar se ainda estão pendentes ou se já deveriam ter sido baixados e reconhecidos.";
  return clientSafeText(text || "O achado indica um ponto que deve ser validado antes do fechamento contábil definitivo.");
}

function consultativeSolution(finding) {
  const code = String(finding.codigo || "");
  const fallback = clientSafeText(finding.recomendacao || "Validar documentos, conciliar saldos e registrar a providência adotada.");
  if (code.startsWith("SN-004")) return "Reconciliar resultado, lucros acumulados, reservas e atas/decisões de distribuição antes de manter a distribuição como isenta.";
  if (code.startsWith("SN-005")) return "Levantar extratos e razão das contas de sócios, formalizar contrato de mútuo quando aplicável e verificar IOF, juros, prazo e liquidação.";
  if (code.startsWith("SN-006") || code.startsWith("SN-022")) return "Conciliar extratos bancários, caixa físico e lançamentos de sócios; reclassificar valores que não representem disponibilidade real.";
  if (code.startsWith("SN-008")) return "Comparar faturamento, extratos, notas fiscais e recebimentos para identificar lançamentos ausentes, duplicados ou em competência incorreta.";
  if (code.startsWith("SN-010") || code.startsWith("SN-023")) return "Validar relatório de clientes, aging list, recebimentos posteriores e baixas realizadas no período seguinte.";
  if (code.startsWith("SN-015") || code.startsWith("SN-018")) return "Confrontar estoque, compras, vendas, inventário e CMV; ajustar baixas ou reclassificações quando necessário.";
  if (code.startsWith("SN-025")) return "Conferir a conta 325 com notas fiscais, contratos, comprovantes bancários e retenções; reclassificar lançamentos sem suporte adequado.";
  if (code.startsWith("SN-026")) return "Validar contrato, pedido, nota fiscal, extrato e baixa posterior; regularizar valores já liquidados que ainda permanecem como adiantamento.";
  return fallback;
}

function requiredDocumentsForFinding(finding) {
  const code = String(finding.codigo || "");
  if (code.startsWith("SN-004")) return ["Balancete e razão contábil", "Demonstração do resultado", "Lucros acumulados/reservas", "Comprovantes de distribuição"];
  if (code.startsWith("SN-005")) return ["Razão das contas de sócios", "Extratos bancários", "Contrato de mútuo ou instrumento equivalente", "Comprovante de IOF, quando aplicável"];
  if (code.startsWith("SN-006") || code.startsWith("SN-022")) return ["Conciliação bancária", "Extratos bancários", "Livro/controle de caixa", "Comprovantes de pagamentos e recebimentos"];
  if (code.startsWith("SN-008")) return ["Notas fiscais emitidas", "Extratos bancários", "Relatório de faturamento", "PGDAS-D/DAS do período"];
  if (code.startsWith("SN-010") || code.startsWith("SN-023")) return ["Relatório de contas a receber", "Aging list", "Notas fiscais", "Comprovantes de baixa e recebimento"];
  if (code.startsWith("SN-015") || code.startsWith("SN-018")) return ["Inventário", "Notas de compra e venda", "Relatório de estoque", "Memória de cálculo do CMV"];
  if (code.startsWith("SN-025")) return ["Razão da conta 325", "Notas fiscais de serviços tomados", "Contratos", "Comprovantes bancários e retenções"];
  if (code.startsWith("SN-026")) return ["Contratos ou pedidos", "Notas fiscais", "Extratos e recibos", "Razão contábil e baixas posteriores"];
  return ["Balancete", "Razão contábil", "Documentos fiscais", "Extratos e relatórios auxiliares"];
}

function suggestedOwner(finding) {
  const code = String(finding.codigo || "");
  if (code.startsWith("SN-003") || code.startsWith("SN-014")) return "Departamento pessoal + contabilidade";
  if (code.startsWith("SN-005") || code.startsWith("SN-004")) return "Sócios/administradores + contabilidade";
  if (code.startsWith("SN-015") || code.startsWith("SN-016") || code.startsWith("SN-018") || code.startsWith("SN-024")) return "Cliente/financeiro/estoque + contabilidade";
  if (code.startsWith("SN-001") || code.startsWith("SN-002") || code.startsWith("SN-019") || code.startsWith("SN-020")) return "Fiscal + contabilidade";
  return "Cliente + contabilidade";
}

function renderPrintMetricSection(metrics, context) {
  const rows = [
    ["receita_operacional", "Receita operacional"],
    ["lucro_apurado_base", "Resultado apurado"],
    ["tributos_registrados", "Tributos registrados"],
    ["despesas_operacionais", "Despesas operacionais"],
    ["servicos_terceiros", "Serviços de terceiros"],
    ["caixa_e_bancos", "Caixa e bancos"],
    ["clientes_recebiveis", "Clientes e recebíveis"],
    ["adiantamentos_clientes", "Adiantamentos de clientes"],
    ["estoques", "Estoques"],
    ["fornecedores", "Fornecedores"],
    ["cmv_custos", "CMV/custos"],
    ["patrimonio_liquido", "Patrimônio líquido"],
  ].map(([key, label]) => renderPrintMetricItem(key, label, metricValue(metrics, key))).filter(Boolean).join("");

  const indicators = metrics.indicadores_derivados || {};
  const indicatorRows = [
    ["carga_tributaria_efetiva_percentual", "Carga tributária efetiva"],
    ["percentual_despesas_sobre_receita", "Despesas sobre receita"],
    ["percentual_servicos_terceiros_sobre_despesas", "Serviços de terceiros sobre despesas"],
    ["percentual_cmv_sobre_receita", "CMV/custos sobre receita"],
    ["endividamento_bancario_sobre_receita", "Endividamento bancário sobre receita"],
  ].map(([key, label]) => hasDisplayValue(indicators[key]) ? renderPrintMetricItem(key, label, indicators[key]) : "").join("");

  const anexo = context.anexo_estimado
    ? renderPrintMetricItem("anexo_estimado", "Anexo estimado", context.anexo_estimado)
    : "";
  const factorR = context.fator_r_calculado
    ? renderPrintMetricItem("fator_r_calculado", "Fator R calculado", `${context.fator_r_calculado} | limite ${context.fator_r_threshold || "28%"}`)
    : "";

  if (!rows && !indicatorRows && !anexo && !factorR) return "";

  return `
    <section class="pdf-section">
      <h2>Métricas e indicadores</h2>
      <div class="pdf-metric-grid">${rows}${indicatorRows}${anexo}${factorR}</div>
    </section>
  `;
}

function renderPrintMetricItem(key, label, value) {
  if (!hasDisplayValue(value)) return "";
  return `
    <div class="pdf-metric-item">
      <span>${esc(label)}</span>
      <strong>${formatMetricDisplay(key, value)}</strong>
    </div>
  `;
}

function renderPrintContextSection(context) {
  const observations = Array.isArray(context.observacoes)
    ? context.observacoes.filter(Boolean)
    : [];
  if (!observations.length && !context.sublimite_risco) return "";

  const items = observations.map((item) => `<li>${displayText(item)}</li>`).join("");
  const sublimit = context.sublimite_risco
    ? "<li>Receita estimada em faixa de atenção para sublimite, exigindo validação documental e tributária.</li>"
    : "";

  return `
    <section class="pdf-section">
      <h2>Contexto tributário</h2>
      <ul class="pdf-list">${items}${sublimit}</ul>
    </section>
  `;
}

function renderPrintFindingsSection(findings) {
  if (!findings.length) {
    return `
      <section class="pdf-section pdf-technical-section">
        <h2>Análise técnica para a contabilidade</h2>
        <p>Nenhum achado foi acionado pelo motor de regras para o período analisado.</p>
      </section>
    `;
  }

  const cards = findings.map(renderPrintFindingCard).join("");
  return `
    <section class="pdf-section pdf-technical-section">
      <h2>Análise técnica para a contabilidade</h2>
      <div class="pdf-finding-list">${cards}</div>
    </section>
  `;
}

function renderPrintFindingCard(finding) {
  const level = normalizeLevel(finding.nivel);
  const evidence = evidenceSummary(finding.evidencia);
  const norms = Array.isArray(finding.normas_aplicaveis) && finding.normas_aplicaveis.length
    ? finding.normas_aplicaveis.join("; ")
    : "[VERIFICAR: fundamento normativo]";

  return `
    <article class="pdf-finding-card ${level}">
      <header>
        <span class="finding-code">${esc(finding.codigo)}</span>
        <span class="chip ${level}">${levelLabel(level)}</span>
        <span class="pdf-score">Pontuação ${esc(formatNumberPtBr(finding.pontuacao ?? 0))}</span>
      </header>
      <h3>${displayText(clientSafeText(finding.titulo || "Achado sem título"))}</h3>
      <dl>
        <dt>Evidência</dt>
        <dd>${displayText(truncateText(clientSafeText(evidence), 220))}</dd>
        <dt>Impacto técnico</dt>
        <dd>${displayText(truncateText(clientSafeText(finding.descricao || "[VERIFICAR: impacto técnico]"), 240))}</dd>
        <dt>Procedimento sugerido</dt>
        <dd>${displayText(truncateText(clientSafeText(finding.recomendacao || "[VERIFICAR: recomendação técnica]"), 260))}</dd>
        <dt>Fundamento</dt>
        <dd>${displayText(truncateText(norms, 260))}</dd>
      </dl>
    </article>
  `;
}

function evidenceSummary(evidence) {
  if (!evidence || !Object.keys(evidence).length) return "[VERIFICAR: evidência]";
  return Object.entries(evidence)
    .slice(0, 4)
    .map(([key, value]) => `${humanizeKey(key)}: ${evidenceValue(value)}`)
    .join(" | ");
}

function humanizeKey(key) {
  return String(key || "")
    .replace(/_/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/^./, (char) => char.toUpperCase());
}

function renderPrintAccountSection(classification) {
  if (!classification || !classification.total_contas) return "";
  const reviewAccounts = Array.isArray(classification.contas_revisao)
    ? classification.contas_revisao.slice(0, 6)
    : [];
  const rows = reviewAccounts.map((account) => `
    <li>
      <strong>${esc(account.codigo)} - ${esc(account.conta)}</strong>
      <span>${esc(account.grupo_atribuido || "grupo não informado")} | confiança ${esc(account.confianca || "não informada")}</span>
    </li>
  `).join("");

  return `
    <section class="pdf-section pdf-account-section">
      <h2>Classificação das contas</h2>
      <p>Foram analisadas ${esc(formatNumberPtBr(classification.total_contas || 0))} conta(s). Total indicado para revisão: ${esc(formatNumberPtBr(classification.total_contas_revisao || 0))}.</p>
      ${rows ? `<ul class="pdf-account-list">${rows}</ul>` : "<p>Nenhuma conta foi marcada para revisão de classificação.</p>"}
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
  const blob = new Blob([JSON.stringify(formalAuditPayload(lastData), null, 2)], { type: "application/json" });
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
  const title = `Relatório consultivo de pré-auditoria fiscal - ${ident.cliente || "cliente"} - ${ident.periodo || "periodo"}`;
  const content = buildPrintDocumentHtml(viewData);
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
      </section>
      ${renderAnnualTrendSection(data)}
      ${renderAnnualFindingsSection(findings)}
      <section class="section">
        <div class="section-header">
          <h3 class="section-title">JSON completo</h3>
          <button class="toggle-button" type="button" data-toggle-target="annual-raw-json">Mostrar ou ocultar</button>
        </div>
        <pre id="annual-raw-json" class="raw-json is-hidden">${esc(JSON.stringify(data, null, 2))}</pre>
      </section>
    </div>
  `;
  bindDynamicControls();
}

function renderAnnualTrendSection(data) {
  const quarters = Array.isArray(data.comparativo_trimestral) ? data.comparativo_trimestral : [];
  if (!quarters.length) return "";

  const width = 560;
  const height = 180;
  const padding = 28;
  const scores = quarters.map((quarter) => Number(quarter.pontuacao ?? quarter.score ?? 0));
  const maxScore = Math.max(10, ...scores);
  const points = quarters.map((quarter, index) => {
    const x = quarters.length === 1
      ? width / 2
      : padding + (index / (quarters.length - 1)) * (width - padding * 2);
    const score = Number(quarter.pontuacao ?? quarter.score ?? 0);
    const y = height - padding - (score / maxScore) * (height - padding * 2);
    return { x, y, score, quarter };
  });
  const polyline = points.map((point) => `${point.x},${point.y}`).join(" ");
  const markers = points.map((point) => `
    <g>
      <circle cx="${point.x}" cy="${point.y}" r="5" class="trend-point ${normalizeLevel(point.quarter.risco)}"></circle>
      <text x="${point.x}" y="${height - 7}" text-anchor="middle">${esc(point.quarter.trimestre || quarterLabel(point.quarter.periodo) || "")}</text>
    </g>
  `).join("");
  const cards = quarters.map((quarter) => {
    const codes = Array.isArray(quarter.achados_codigos) ? quarter.achados_codigos : [];
    return `
      <article class="annual-trend-card ${normalizeLevel(quarter.risco)}">
        <span>${esc(quarter.trimestre || quarterLabel(quarter.periodo))}</span>
        <strong>${esc(formatNumberPtBr(quarter.pontuacao ?? 0))} pts</strong>
        <small>Risco ${levelLabel(quarter.risco).toLowerCase()} | ${esc(codes.length)} achado(s)</small>
      </article>
    `;
  }).join("");

  return `
    <section class="section annual-trend-section">
      <div class="section-header">
        <h3 class="section-title">Tendência trimestral</h3>
        <span class="section-note">Pontuação de risco ao longo do exercício</span>
      </div>
      <div class="trend-layout">
        <svg class="trend-chart" viewBox="0 0 ${width} ${height}" role="img" aria-label="Tendência de pontuação por trimestre">
          <line x1="${padding}" y1="${height - padding}" x2="${width - padding}" y2="${height - padding}" class="trend-axis"></line>
          <line x1="${padding}" y1="${padding}" x2="${padding}" y2="${height - padding}" class="trend-axis"></line>
          <polyline points="${polyline}" class="trend-line"></polyline>
          ${markers}
        </svg>
        <div class="annual-trend-grid">${cards}</div>
      </div>
    </section>
  `;
}

function renderAnnualFindingsSection(findings) {
  if (!findings.length) {
    return `
      <section class="section">
        <div class="section-header">
          <h3 class="section-title">Achados anuais</h3>
        </div>
        <div class="finding-empty">Nenhum achado anual adicional foi identificado.</div>
      </section>
    `;
  }

  const rows = findings.map((finding, index) => renderFindingRow({
    codigo: finding.codigo,
    titulo: finding.titulo,
    nivel: finding.nivel,
    pontuacao: finding.pontuacao,
    descricao: finding.descricao,
    evidencia: finding.evidencia,
    recomendacao: finding.recomendacao,
    normas_aplicaveis: finding.normas_aplicaveis,
  }, index, "annual-finding-detail")).join("");

  return `
    <section class="section findings-section">
      <div class="section-header">
        <h3 class="section-title">Achados anuais (${esc(findings.length)})</h3>
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
          <tbody>${rows}</tbody>
        </table>
      </div>
    </section>
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
