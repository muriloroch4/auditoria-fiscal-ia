from __future__ import annotations

from decimal import Decimal

from ..config_loader import get_rule_config
from ..models import LedgerAccount, RiskLevel, RuleFinding, TrialBalance
from ..utils import format_brl, format_percent
from .metricas import ProfitBasis, format_account_trace
from .rulesets import RULESET_COMERCIO, RULESET_COMERCIO_SERVICOS, RULESET_SERVICOS

_money = format_brl
_percent = format_percent


def check_expense_ratio(
    revenue: Decimal,
    expenses: Decimal,
    balance: TrialBalance,
    ruleset: str = RULESET_SERVICOS,
) -> list[RuleFinding]:
    if revenue <= 0:
        return []

    findings: list[RuleFinding] = []

    cfg = get_rule_config("SN-007")
    lim = Decimal(str(cfg.get("limite_medio", 0.70)))
    ratio = expenses / revenue
    activity_label = _activity_label(ruleset)
    if ratio > lim:
        findings.append(
            RuleFinding(
                codigo="SN-007",
                titulo="Despesas operacionais elevadas",
                nivel=RiskLevel.MEDIO,
                pontuacao=cfg.get("pontuacao_medio", 16),
                descricao=f"As despesas operacionais representam percentual elevado da receita de {activity_label}.",
                evidencia={"receita": _money(revenue), "despesas": _money(expenses), "percentual": _percent(ratio)},
                recomendacao="Revisar despesas dedutíveis, gastos de sócios, documentos fiscais e coerência com a atividade.",
                normas_aplicaveis=("LC 123/2006", "RIR/2018"),
            )
        )

    cfg13 = get_rule_config("SN-013")
    rep_expenses = _abs(balance.debito_por_grupo("despesas_representacao"))
    if rep_expenses > 0:
        rep_ratio = rep_expenses / expenses
        lim_rep = Decimal(str(cfg13.get("limite_representacao", 0.15)))
        if rep_ratio > lim_rep:
            findings.append(
                RuleFinding(
                    codigo="SN-013A",
                    titulo="Despesas de representação elevadas",
                    nivel=RiskLevel.MEDIO,
                    pontuacao=cfg13.get("pontuacao_representacao", 10),
                    descricao=f"As despesas de representação representam {_percent(rep_ratio)} do total de despesas, percentual que pode indicar gastos particulares lançados na empresa.",
                    evidencia={
                        "despesas_representacao": _money(rep_expenses),
                        "total_despesas": _money(expenses),
                        "percentual": _percent(rep_ratio),
                    },
                    recomendacao="Revisar a natureza dos gastos de representação, exigindo comprovantes fiscais e documentação de suporte.",
                    normas_aplicaveis=("RIR/2018", "art. 47° LC 123/2006"),
                )
            )

    veh_expenses = _abs(balance.debito_por_grupo("despesas_veiculos"))
    if veh_expenses > 0:
        veh_ratio = veh_expenses / expenses
        lim_veh = Decimal(str(cfg13.get("limite_veiculos", 0.10)))
        if veh_ratio > lim_veh:
            findings.append(
                RuleFinding(
                    codigo="SN-013B",
                    titulo="Despesas de veículos elevadas",
                    nivel=RiskLevel.MEDIO,
                    pontuacao=cfg13.get("pontuacao_veiculos", 10),
                    descricao=f"As despesas com veículos representam {_percent(veh_ratio)} do total de despesas, percentual que merece validação quanto à atividade da empresa.",
                    evidencia={
                        "despesas_veiculos": _money(veh_expenses),
                        "total_despesas": _money(expenses),
                        "percentual": _percent(veh_ratio),
                    },
                    recomendacao="Confrontar despesas de veículos com a quantidade de veículos, contratos de leasing/combustível e efetiva necessidade operacional.",
                    normas_aplicaveis=("RIR/2018", "art. 47° LC 123/2006"),
                )
            )

    return findings

def check_third_party_services_expense(
    third_party_services: Decimal,
    expenses: Decimal,
    accounts: list[LedgerAccount],
) -> list[RuleFinding]:
    if third_party_services <= 0 or expenses <= 0:
        return []

    cfg = get_rule_config("SN-025")
    absolute_limit = Decimal(str(cfg.get("limite_absoluto", 10000)))
    ratio_limit = Decimal(str(cfg.get("limite_ratio_despesas", 0.20)))
    ratio = third_party_services / expenses

    if third_party_services < absolute_limit or ratio < ratio_limit:
        return []

    return [
        RuleFinding(
            codigo="SN-025",
            titulo="Servicos prestados por terceiros relevantes nas despesas",
            nivel=RiskLevel.MEDIO,
            pontuacao=cfg.get("pontuacao_medio", 12),
            descricao="A conta 325/servicos prestados por terceiros representa percentual relevante das despesas do trimestre, indicando necessidade de validacao documental dos lancamentos.",
            evidencia={
                "conta_referencia": "325 - Servicos prestados por terceiros",
                "servicos_terceiros": _money(third_party_services),
                "total_despesas": _money(expenses),
                "percentual_sobre_despesas": _percent(ratio),
                "limite_percentual_despesas": _percent(ratio_limit),
                "limite_absoluto": _money(absolute_limit),
                "quantidade_contas_identificadas": str(len(accounts)),
                "contas_identificadas": format_account_trace(accounts),
                "criterio_rastreio": "codigo 325, prefixo configurado ou descricao de servicos prestados por terceiros",
                "tipo_achado": "validacao_documental",
            },
            recomendacao="Verificar e validar os lancamentos da conta 325, confrontando pagamentos, contratos, notas fiscais, comprovantes bancarios, retencoes aplicaveis e suporte documental antes de manter a despesa.",
            normas_aplicaveis=("ITG 2000", "NBC TG 1000"),
        )
    ]

def check_accounting_loss(revenue: Decimal, profit_basis: ProfitBasis) -> list[RuleFinding]:
    cfg = get_rule_config("SN-009")

    if profit_basis.value >= 0:
        return []

    if revenue <= 0:
        return [
            RuleFinding(
                codigo="SN-009A",
                titulo="Prejuízo contábil sem receita declarada",
                nivel=RiskLevel.ALTO,
                pontuacao=cfg.get("pontuacao_alto", 25),
                descricao="A empresa apresenta prejuízo contábil e nenhuma receita declarada, indicando risco de continuidade operacional.",
                evidencia={
                    "lucro_apurado": _money(profit_basis.value),
                    "origem_lucro": profit_basis.source,
                },
                recomendacao="Avaliar viabilidade operacional, verificar passivos acumulados e documentar o enquadramento fiscal aplicável.",
                normas_aplicaveis=("NBC TG 1000", "ITG 2000"),
            )
        ]

    loss_ratio = abs(profit_basis.value) / revenue
    lim = Decimal(str(cfg.get("limite_medio_ratio", 0.10)))
    if loss_ratio > lim:
        return [
            RuleFinding(
                codigo="SN-009B",
                titulo=f"Prejuízo contábil significativo ({_percent(abs(profit_basis.value) / revenue)} da receita)",
                nivel=RiskLevel.ALTO,
                pontuacao=cfg.get("pontuacao_alto", 25),
                descricao=f"O prejuízo apurado representa {_percent(loss_ratio)} da receita, indicando desequilíbrio entre custos e receitas.",
                evidencia={
                    "lucro_apurado": _money(profit_basis.value),
                    "receita": _money(revenue),
                    "percentual_prejuizo": _percent(loss_ratio),
                },
                recomendacao="Revisar estrutura de custos, margem de contribuição, viabilidade do modelo de negócio e efeitos tributários aplicáveis.",
                normas_aplicaveis=("NBC TG 1000", "ITG 2000"),
            )
        ]

    return [
        RuleFinding(
            codigo="SN-009C",
            titulo="Prejuízo contábil leve",
            nivel=RiskLevel.MEDIO,
            pontuacao=cfg.get("pontuacao_medio", 12),
            descricao="A empresa apurou prejuízo contábil no período, mesmo que em proporção reduzida.",
            evidencia={
                "lucro_apurado": _money(profit_basis.value),
                "receita": _money(revenue),
            },
            recomendacao="Acompanhar evolução do resultado nos próximos trimestres e identificar causas do déficit.",
            normas_aplicaveis=("NBC TG 1000", "ITG 2000"),
        )
    ]

def check_high_profit_margin(revenue: Decimal, profit_basis: ProfitBasis) -> list[RuleFinding]:
    if revenue <= 0 or profit_basis.value <= 0:
        return []

    cfg = get_rule_config("SN-021")
    margin = profit_basis.value / revenue
    reference = Decimal(str(cfg.get("referencia_presuncao_servicos", 0.32)))

    high_limit = Decimal(str(cfg.get("limite_medio_ratio", 0.64)))
    if margin > high_limit:
        return [
            RuleFinding(
                codigo="SN-021B",
                titulo="Margem de lucro contábil muito elevada",
                nivel=RiskLevel.MEDIO,
                pontuacao=cfg.get("pontuacao_medio", 12),
                descricao="O lucro contábil representa percentual muito elevado da receita, sugerindo possível ausência de despesas, custos ou lançamentos de competência.",
                evidencia={
                    "receita": _money(revenue),
                    "lucro_apurado": _money(profit_basis.value),
                    "origem_lucro": profit_basis.source,
                    "margem_lucro": _percent(margin),
                    "referencia_presuncao": _percent(reference),
                },
                recomendacao="Revisar se todas as despesas, custos, folha, pró-labore, fornecedores, serviços tomados e encargos foram reconhecidos pelo regime de competência.",
                normas_aplicaveis=("NBC TG 1000", "ITG 2000"),
            )
        ]

    attention_limit = Decimal(str(cfg.get("limite_baixo_ratio", 0.45)))
    if margin > attention_limit:
        return [
            RuleFinding(
                codigo="SN-021A",
                titulo="Margem de lucro contábil acima da referência esperada",
                nivel=RiskLevel.BAIXO,
                pontuacao=cfg.get("pontuacao_baixo", 6),
                descricao="O lucro contábil está acima da referência gerencial usada como alerta, exigindo validação das despesas e custos do período.",
                evidencia={
                    "receita": _money(revenue),
                    "lucro_apurado": _money(profit_basis.value),
                    "origem_lucro": profit_basis.source,
                    "margem_lucro": _percent(margin),
                    "referencia_presuncao": _percent(reference),
                },
                recomendacao="Conferir despesas, custos e apropriações de competência para confirmar se a margem elevada representa a realidade operacional.",
                normas_aplicaveis=("NBC TG 1000", "ITG 2000"),
            )
        ]

    return []

def check_missing_provisions(revenue: Decimal, payroll: Decimal, balance: TrialBalance) -> list[RuleFinding]:
    if revenue <= 0 or payroll <= 0:
        return []

    cfg = get_rule_config("SN-014")
    payroll_ratio = payroll / revenue
    lim_folha = Decimal(str(cfg.get("limite_folha_receita", 0.10)))

    if payroll_ratio < lim_folha:
        return []

    provisions = _abs(balance.total_por_grupo("provisoes"))
    if provisions > 0:
        return []

    return [
        RuleFinding(
            codigo="SN-014",
            titulo="Ausência de provisões trabalhistas com folha significativa",
            nivel=RiskLevel.MEDIO,
            pontuacao=cfg.get("pontuacao_medio", 12),
            descricao=f"A folha de pagamento representa {_percent(payroll_ratio)} da receita, mas não foram identificadas provisões para férias, 13º salário ou encargos no balancete.",
            evidencia={
                "receita": _money(revenue),
                "folha_pro_labore": _money(payroll),
                "percentual_folha": _percent(payroll_ratio),
                "provisoes": _money(provisions),
            },
            recomendacao="Constituir provisões trabalhistas (férias, 13º, FGTS, INSS) conforme regime de competência e ITG 2000.",
            normas_aplicaveis=("ITG 2000", "CLT", "art. 47° LC 123/2006"),
        )
    ]

def _activity_label(ruleset: str) -> str:
    if ruleset == RULESET_COMERCIO:
        return "comercio"
    if ruleset == RULESET_COMERCIO_SERVICOS:
        return "comercio e servicos"
    return "servicos"


def _abs(value: Decimal) -> Decimal:
    return abs(value)

