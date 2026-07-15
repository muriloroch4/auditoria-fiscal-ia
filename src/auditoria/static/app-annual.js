// Annual comparison panel and annual JSON generation helpers.

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
          <div class="annual-meta">${esc(item.periodo)} · risco ${esc(item.risk || "n/d")} · ${esc(item.score)}/100</div>
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
          <div class="annual-meta">${esc(item.periodo)} · risco ${esc(item.risco_geral || "n/d")} · ${esc(item.pontuacao_total || 0)}/100</div>
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
    `<span class="chip info">Pontuação: ${esc(risk.pontuacao_total ?? 0)}/100</span>`,
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
  const maxScore = 100;
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
        <strong>${esc(formatNumberPtBr(quarter.pontuacao ?? 0))}/100</strong>
        <small>Risco ${levelLabel(quarter.risco).toLowerCase()} | ${esc(codes.length)} achado(s)</small>
      </article>
    `;
  }).join("");

  return `
    <section class="section annual-trend-section">
      <div class="section-header">
        <h3 class="section-title">Tendência trimestral</h3>
        <span class="section-note">Pontuação de risco em escala de 0 a 100 ao longo do exercício</span>
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
