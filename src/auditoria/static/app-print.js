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
  const orientation = risk.orientacao_consultiva || consultativeOpinionText(risk.modalidade_opiniao_sugerida);
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
  const normalized = normalizeOpinionCode(value);
  if (normalized === "sem_ressalva") {
    return "manter a documentação suporte e acompanhar os controles nos próximos trimestres";
  }
  if (normalized === "com_ressalva") {
    return "corrigir ou documentar os pontos destacados antes do fechamento definitivo";
  }
  if (normalized === "adversa") {
    return "priorizar a regularização dos achados relevantes antes de usar os dados para decisões externas ou fechamento anual";
  }
  if (normalized === "abstencao_opiniao") {
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
    <section class="pdf-section pdf-metric-section">
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
        <dd>${displayText(clientSafeText(evidence))}</dd>
        <dt>Impacto técnico</dt>
        <dd>${displayText(clientSafeText(finding.descricao || "[VERIFICAR: impacto técnico]"))}</dd>
        <dt>Procedimento sugerido</dt>
        <dd>${displayText(clientSafeText(finding.recomendacao || "[VERIFICAR: recomendação técnica]"))}</dd>
        <dt>Fundamento</dt>
        <dd>${displayText(norms)}</dd>
      </dl>
    </article>
  `;
}

function evidenceSummary(evidence) {
  if (!evidence || !Object.keys(evidence).length) return "[VERIFICAR: evidência]";
  return Object.entries(evidence)
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
