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
    [/\bmovimentacao\b/gi, "movimentação"],
    [/\bmovimentacoes\b/gi, "movimentações"],
    [/\blancado\b/gi, "lançado"],
    [/\blancada\b/gi, "lançada"],
    [/\blancados\b/gi, "lançados"],
    [/\blancadas\b/gi, "lançadas"],
    [/\baliquota\b/gi, "alíquota"],
    [/\baliquotas\b/gi, "alíquotas"],
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
    [/\bhistorico\b/gi, "histórico"],
    [/\bparametro\b/gi, "parâmetro"],
    [/\bparametros\b/gi, "parâmetros"],
    [/\brelacao\b/gi, "relação"],
    [/\brelacoes\b/gi, "relações"],
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
  const normalized = normalizeOpinionCode(value);
  const opinions = {
    sem_ressalva: "Acompanhamento preventivo",
    com_ressalva: "Validação documental necessária",
    adversa: "Regularização prioritária",
    abstencao_opiniao: "Documentação insuficiente",
  };
  return opinions[normalized] || String(value || "[VERIFICAR: orientação]").replace(/_/g, " ");
}

function normalizeOpinionCode(value) {
  const text = String(value || "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .replace(/_/g, " ")
    .trim();
  if (["sem ressalva", "sem ressalvas", "sem modificacao"].includes(text)) return "sem_ressalva";
  if (["com ressalva", "com ressalvas", "ressalva"].includes(text)) return "com_ressalva";
  if (["adversa", "opiniao adversa"].includes(text)) return "adversa";
  if (["abstencao de opiniao", "abstencao opiniao"].includes(text)) return "abstencao_opiniao";
  return text.replace(/\s+/g, "_");
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
  if (value && typeof value === "object" && value.formatado !== undefined) {
    return numericValue(value.formatado);
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
  if (monetaryMetricKeys().has(key)) {
    return esc(formatCurrencyPtBr(numericValue(value)));
  }
  if (value && typeof value === "object" && value.formatado) {
    return esc(value.formatado);
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
