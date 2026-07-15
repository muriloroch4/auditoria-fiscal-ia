from __future__ import annotations

from decimal import Decimal

from ..config_loader import get_rule_config, load_config
from ..models import RiskLevel, RuleFinding, TrialBalance
from ..utils import format_brl, format_percent
from .metricas import LEGACY_TAX_GROUP, TAX_LIABILITY_GROUPS
from .rulesets import RULESET_COMERCIO, RULESET_COMERCIO_SERVICOS, RULESET_SERVICOS

_money = format_brl
_percent = format_percent


def check_low_or_missing_revenue(revenue: Decimal, active_movement: Decimal, operational_movement: Decimal) -> list[RuleFinding]:
    cfg = load_config()
    lim_mov = Decimal(str(cfg.get("limites_gerais", {}).get("limite_movimentacao_ativa", 10000)))
    if active_movement < lim_mov:
        return []

    cfg008 = get_rule_config("SN-008")
    pts = cfg008.get("pontuacao_alto", 20)

    if revenue <= 0:
        return [
            RuleFinding(
                codigo="SN-008A",
                titulo="Receita inexistente com movimentação ativa",
                nivel=RiskLevel.ALTO,
                pontuacao=pts,
                descricao="A empresa apresenta movimentação contábil relevante, mas não possui receita registrada no período.",
                evidencia={"receita": _money(revenue), "movimentacao_ativa": _money(active_movement)},
                recomendacao="Verificar emissão de notas fiscais, reconhecimento de receita, classificação de entradas e possível tributação não apurada.",
                normas_aplicaveis=("LC 123/2006", "art. 3° LC 123/2006"),
            )
        ]

    if operational_movement <= 0:
        return []

    ratio_lim = Decimal(str(cfg.get("limites_gerais", {}).get("receita_baixa_ratio", 0.05)))
    if revenue / operational_movement < ratio_lim:
        return [
            RuleFinding(
                codigo="SN-008B",
                titulo="Receita muito baixa com movimentação ativa",
                nivel=RiskLevel.ALTO,
                pontuacao=pts,
                descricao="A receita registrada é muito baixa em relação à movimentação contábil ativa do período.",
                evidencia={
                    "receita": _money(revenue),
                    "movimentacao_ativa": _money(operational_movement),
                    "percentual": _percent(revenue / operational_movement),
                },
                recomendacao="Investigar operação sem emissão fiscal, receitas classificadas incorretamente ou movimentações que deveriam compor faturamento.",
                normas_aplicaveis=("LC 123/2006", "art. 3° LC 123/2006"),
            )
        ]

    return []

def check_revenue_limit(revenue: Decimal, rbt12_revenue: Decimal | None = None) -> list[RuleFinding]:
    cfg = get_rule_config("SN-001")
    anual = Decimal(str(load_config().get("limites_gerais", {}).get("simples_anual", 4800000)))
    has_rbt12 = rbt12_revenue is not None and rbt12_revenue > 0
    annualized_revenue = (rbt12_revenue or Decimal("0")) if has_rbt12 else revenue * Decimal("4")
    ratio = annualized_revenue / anual if anual > 0 else Decimal("0")
    base_calculo_limite = "RBT12 consolidado pelo historico" if has_rbt12 else "receita trimestral anualizada (receita x 4)"

    lim_alto = Decimal(str(cfg.get("limite_alto", 0.90)))
    if ratio >= lim_alto:
        return [
            RuleFinding(
                codigo="SN-001B",
                titulo="Receita trimestral anualizada acima de 90% do limite do Simples",
                nivel=RiskLevel.ALTO,
                pontuacao=cfg.get("pontuacao_alto", 35),
                descricao="A receita do trimestre, quando anualizada para fins de alerta, fica próxima do limite anual do Simples Nacional.",
                evidencia={
                    "receita_trimestre": _money(revenue),
                    "receita_anualizada_estimativa": _money(annualized_revenue),
                    "limite_anual_simples": _money(anual),
                    "percentual_limite_anual": _percent(ratio),
                    "base_calculo_limite": base_calculo_limite,
                },
                recomendacao="Validar a receita bruta acumulada dos últimos 12 meses (RBT12), projetar os próximos trimestres e avaliar risco de sublimite, desenquadramento ou excesso de receita.",
                normas_aplicaveis=("LC 123/2006", "art. 3° LC 123/2006", "LC 155/2016"),
            )
        ]

    lim_medio = Decimal(str(cfg.get("limite_medio", 0.70)))
    if ratio >= lim_medio:
        return [
            RuleFinding(
                codigo="SN-001A",
                titulo="Receita trimestral anualizada acima de 70% do limite do Simples",
                nivel=RiskLevel.MEDIO,
                pontuacao=cfg.get("pontuacao_medio", 18),
                descricao="A receita do trimestre, quando anualizada para fins de alerta, representa mais de 70% do limite anual do Simples Nacional.",
                evidencia={
                    "receita_trimestre": _money(revenue),
                    "receita_anualizada_estimativa": _money(annualized_revenue),
                    "limite_anual_simples": _money(anual),
                    "percentual_limite_anual": _percent(ratio),
                    "base_calculo_limite": base_calculo_limite,
                },
                recomendacao="Acompanhar receita acumulada dos últimos 12 meses (RBT12) e simular cenários de crescimento para os próximos trimestres.",
                normas_aplicaveis=("LC 123/2006", "art. 3° LC 123/2006", "LC 155/2016"),
            )
        ]

    return []

def check_tax_ratio(revenue: Decimal, tax_expense: Decimal, ruleset: str = RULESET_SERVICOS) -> list[RuleFinding]:
    if revenue <= 0:
        return []

    cfg = get_rule_config("SN-002")
    ratio = tax_expense / revenue
    tax_norm = _tax_annex_norm(ruleset)

    lim_alto = Decimal(str(cfg.get("limite_alto", 0.03)))
    if ratio < lim_alto:
        return [
            RuleFinding(
                codigo="SN-002B",
                titulo="Carga tributária abaixo de 3% da receita",
                nivel=RiskLevel.ALTO,
                pontuacao=cfg.get("pontuacao_alto", 20),
                descricao="Os impostos registrados representam menos de 3% da receita do período, indicando possível subapuração ou divergência fiscal a validar.",
                evidencia={"receita": _money(revenue), "tributos_registrados": _money(tax_expense), "percentual": _percent(ratio)},
                recomendacao="Conferir apuração do DAS, anexo aplicado, retenções, competência e possíveis lançamentos ausentes.",
                normas_aplicaveis=("LC 123/2006", tax_norm),
            )
        ]

    lim_medio = Decimal(str(cfg.get("limite_medio", 0.055)))
    if ratio < lim_medio:
        return [
            RuleFinding(
                codigo="SN-002A",
                titulo="Carga tributária abaixo de 5,5% da receita",
                nivel=RiskLevel.MEDIO,
                pontuacao=cfg.get("pontuacao_medio", 15),
                descricao="A relação entre tributos registrados e receita está em uma faixa que merece revisão.",
                evidencia={"receita": _money(revenue), "tributos_registrados": _money(tax_expense), "percentual": _percent(ratio)},
                recomendacao="Validar se todas as guias do trimestre foram reconhecidas e se houve retenções compensáveis.",
                normas_aplicaveis=("LC 123/2006", tax_norm),
            )
        ]

    return []

def check_tax_liability_growth(balance: TrialBalance, revenue: Decimal) -> list[RuleFinding]:
    if revenue <= 0:
        return []

    cfg = get_rule_config("SN-012")
    pts = cfg.get("pontuacao_medio", 14)

    tax_accounts = []
    for group in TAX_LIABILITY_GROUPS:
        tax_accounts.extend(balance.contas_por_grupo(group))
    if not tax_accounts:
        tax_accounts = balance.contas_por_grupo(LEGACY_TAX_GROUP)
    if not tax_accounts:
        return []

    previous_tax = _abs(sum((account.saldo_anterior for account in tax_accounts), Decimal("0")))
    current_tax = _abs(sum((account.saldo_atual for account in tax_accounts), Decimal("0")))

    if previous_tax >= current_tax or previous_tax <= 0:
        return []

    growth_ratio = (current_tax - previous_tax) / previous_tax
    lim = Decimal(str(cfg.get("limite_medio", 0.50)))
    if growth_ratio > lim:
        return [
            RuleFinding(
                codigo="SN-012",
                titulo="Passivo tributário com crescimento relevante",
                nivel=RiskLevel.MEDIO,
                pontuacao=pts,
                descricao=f"O saldo de tributos a recolher cresceu {_percent(growth_ratio)} em relação ao período anterior, indicando possível acúmulo de débitos fiscais.",
                evidencia={
                    "saldo_anterior_tributos": _money(previous_tax),
                    "saldo_atual_tributos": _money(current_tax),
                    "crescimento": _percent(growth_ratio),
                },
                recomendacao="Conferir apuração do DAS dos períodos, regularidade fiscal e possíveis parcelamentos em aberto.",
                normas_aplicaveis=("LC 123/2006", "art. 47° LC 123/2006"),
            )
        ]

    return []

def _tax_annex_norm(ruleset: str) -> str:
    if ruleset == RULESET_COMERCIO:
        return "Anexo I da LC 123/2006"
    if ruleset == RULESET_COMERCIO_SERVICOS:
        return "Anexos I e III/V da LC 123/2006"
    return "Anexo III da LC 123/2006"


def _abs(value: Decimal) -> Decimal:
    return abs(value)

