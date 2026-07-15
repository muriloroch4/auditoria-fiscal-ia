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
      pontuacao_bruta: summary.pontuacao_bruta || 0,
      pontuacao_maxima_aplicavel: summary.pontuacao_maxima_aplicavel || 100,
      escala_pontuacao: summary.escala_pontuacao || "0 a 100",
      modalidade_opiniao_sugerida: conclusion.conclusao_sugerida || "",
      orientacao_consultiva: conclusion.orientacao_consultiva || "",
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
    `<span class="chip info">Pontuação: ${esc(risk.pontuacao_total ?? 0)}/100</span>`,
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
