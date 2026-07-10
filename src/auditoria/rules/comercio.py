from __future__ import annotations

from decimal import Decimal

from ..config_loader import get_rule_config
from ..models import RiskLevel, RuleFinding
from ..utils import format_brl, format_percent


def analyze_commerce_rules(
    revenue: Decimal,
    inventory: Decimal,
    suppliers: Decimal,
    tax_credits: Decimal,
    cogs: Decimal,
    rbt12_revenue: Decimal | None = None,
) -> list[RuleFinding]:
    findings: list[RuleFinding] = []
    findings.extend(check_inventory_position(revenue, inventory, cogs))
    findings.extend(check_supplier_position(revenue, suppliers, inventory))
    findings.extend(check_tax_credits_simples(revenue, tax_credits))
    findings.extend(check_cogs_for_commerce(revenue, inventory, suppliers, cogs))
    findings.extend(check_commerce_sublimit(revenue, rbt12_revenue))
    findings.extend(check_icms_st_attention(revenue, inventory, suppliers, cogs, tax_credits))
    return findings


def check_inventory_position(revenue: Decimal, inventory: Decimal, cogs: Decimal) -> list[RuleFinding]:
    if inventory <= 0:
        return []

    cfg = get_rule_config("SN-015")
    absolute_limit = Decimal(str(cfg.get("limite_absoluto_sem_receita", 10000)))

    if revenue <= 0 and inventory > absolute_limit:
        return [
            RuleFinding(
                codigo="SN-015A",
                titulo="Estoque relevante sem receita registrada",
                nivel=RiskLevel.ALTO,
                pontuacao=cfg.get("pontuacao_alto", 24),
                descricao="A empresa apresenta saldo relevante de estoques sem receita registrada no trimestre.",
                evidencia={
                    "receita": format_brl(revenue),
                    "estoques": format_brl(inventory),
                    "limite_absoluto": format_brl(absolute_limit),
                },
                recomendacao="Validar inventario, notas fiscais de entrada e saida, baixas por venda, perdas e eventual receita nao reconhecida.",
                normas_aplicaveis=("LC 123/2006", "CPC 16 R1", "ITG 2000"),
            )
        ]

    if revenue <= 0:
        return []

    ratio = inventory / revenue
    lim_alto = Decimal(str(cfg.get("limite_alto_ratio", 2.0)))
    if ratio > lim_alto:
        return [
            RuleFinding(
                codigo="SN-015C",
                titulo="Estoque muito elevado em relacao a receita trimestral",
                nivel=RiskLevel.ALTO,
                pontuacao=cfg.get("pontuacao_alto", 24),
                descricao="O saldo de estoques supera parametro elevado em relacao a receita trimestral, indicando risco de inventario sem giro, baixa pendente ou classificacao inadequada.",
                evidencia={
                    "receita": format_brl(revenue),
                    "estoques": format_brl(inventory),
                    "cmv_custos": format_brl(cogs),
                    "percentual_sobre_receita": format_percent(ratio),
                },
                recomendacao="Conciliar estoque contabil com inventario fisico, compras, notas fiscais de venda, perdas, devolucoes e criterios de avaliacao.",
                normas_aplicaveis=("LC 123/2006", "CPC 16 R1", "ITG 2000"),
            )
        ]

    lim_medio = Decimal(str(cfg.get("limite_medio_ratio", 1.0)))
    if ratio > lim_medio:
        return [
            RuleFinding(
                codigo="SN-015B",
                titulo="Estoque elevado em relacao a receita trimestral",
                nivel=RiskLevel.MEDIO,
                pontuacao=cfg.get("pontuacao_medio", 14),
                descricao="O saldo de estoques esta relevante em relacao a receita do trimestre e deve ser confrontado com o giro operacional.",
                evidencia={
                    "receita": format_brl(revenue),
                    "estoques": format_brl(inventory),
                    "cmv_custos": format_brl(cogs),
                    "percentual_sobre_receita": format_percent(ratio),
                },
                recomendacao="Revisar inventario, compras do periodo, baixas por venda e composicao de itens sem giro.",
                normas_aplicaveis=("CPC 16 R1", "ITG 2000"),
            )
        ]

    return []


def check_supplier_position(revenue: Decimal, suppliers: Decimal, inventory: Decimal) -> list[RuleFinding]:
    if suppliers <= 0:
        return []

    cfg = get_rule_config("SN-016")
    absolute_limit = Decimal(str(cfg.get("limite_absoluto_sem_receita", 10000)))

    if revenue <= 0 and suppliers > absolute_limit:
        return [
            RuleFinding(
                codigo="SN-016A",
                titulo="Fornecedores relevantes sem receita registrada",
                nivel=RiskLevel.MEDIO,
                pontuacao=cfg.get("pontuacao_medio", 14),
                descricao="Ha saldo relevante de fornecedores sem receita registrada no trimestre, exigindo conciliacao entre compras, estoques e operacao.",
                evidencia={
                    "receita": format_brl(revenue),
                    "fornecedores": format_brl(suppliers),
                    "estoques": format_brl(inventory),
                },
                recomendacao="Conciliar contas a pagar, notas fiscais de compra, estoque e eventual faturamento posterior.",
                normas_aplicaveis=("LC 123/2006", "ITG 2000"),
            )
        ]

    if revenue <= 0:
        return []

    ratio = suppliers / revenue
    lim_alto = Decimal(str(cfg.get("limite_alto_ratio", 1.5)))
    if ratio > lim_alto:
        return [
            RuleFinding(
                codigo="SN-016C",
                titulo="Fornecedores muito elevados em relacao a receita",
                nivel=RiskLevel.ALTO,
                pontuacao=cfg.get("pontuacao_alto", 22),
                descricao="O saldo de fornecedores e muito elevado em relacao a receita trimestral, podendo indicar passivo comercial sem baixa, compras sem giro ou erro de classificacao.",
                evidencia={
                    "receita": format_brl(revenue),
                    "fornecedores": format_brl(suppliers),
                    "estoques": format_brl(inventory),
                    "percentual_sobre_receita": format_percent(ratio),
                },
                recomendacao="Conferir aging de fornecedores, documentos fiscais de compra, pagamentos posteriores e vinculo com estoque/CMV.",
                normas_aplicaveis=("NBC TG 1000", "ITG 2000"),
            )
        ]

    lim_medio = Decimal(str(cfg.get("limite_medio_ratio", 0.8)))
    if ratio > lim_medio:
        return [
            RuleFinding(
                codigo="SN-016B",
                titulo="Fornecedores elevados em relacao a receita",
                nivel=RiskLevel.MEDIO,
                pontuacao=cfg.get("pontuacao_medio", 14),
                descricao="O saldo de fornecedores esta relevante em relacao a receita trimestral e deve ser conciliado com compras e pagamentos.",
                evidencia={
                    "receita": format_brl(revenue),
                    "fornecedores": format_brl(suppliers),
                    "estoques": format_brl(inventory),
                    "percentual_sobre_receita": format_percent(ratio),
                },
                recomendacao="Revisar composicao de fornecedores, notas fiscais, duplicatas pagas e mercadorias recebidas.",
                normas_aplicaveis=("NBC TG 1000", "ITG 2000"),
            )
        ]

    return []


def check_tax_credits_simples(revenue: Decimal, tax_credits: Decimal) -> list[RuleFinding]:
    if tax_credits <= 0:
        return []

    cfg = get_rule_config("SN-017")
    absolute_limit = Decimal(str(cfg.get("limite_absoluto", 5000)))
    ratio_limit = Decimal(str(cfg.get("limite_ratio", 0.02)))
    ratio_reference = revenue * ratio_limit if revenue > 0 else Decimal("0")
    reference = max(absolute_limit, ratio_reference)

    if tax_credits <= reference:
        return []

    ratio = tax_credits / revenue if revenue > 0 else Decimal("0")
    return [
        RuleFinding(
            codigo="SN-017",
            titulo="Creditos fiscais relevantes em empresa do Simples Nacional",
            nivel=RiskLevel.MEDIO,
            pontuacao=cfg.get("pontuacao_medio", 16),
            descricao="Foram identificados creditos fiscais relevantes em empresa optante pelo Simples Nacional, exigindo validacao da natureza e recuperabilidade.",
            evidencia={
                "receita": format_brl(revenue),
                "creditos_fiscais": format_brl(tax_credits),
                "referencia_aplicada": format_brl(reference),
                "percentual_sobre_receita": format_percent(ratio) if revenue > 0 else "0,0%",
            },
            recomendacao="Validar se os creditos decorrem de retencoes, ICMS-ST, ressarcimentos ou saldos recuperaveis documentados, evitando manter ativo fiscal sem suporte.",
            normas_aplicaveis=("LC 123/2006", "NBC TG 1000", "ITG 2000"),
        )
    ]


def check_cogs_for_commerce(
    revenue: Decimal,
    inventory: Decimal,
    suppliers: Decimal,
    cogs: Decimal,
) -> list[RuleFinding]:
    if revenue <= 0:
        return []

    cfg = get_rule_config("SN-018")
    commerce_signal = inventory > 0 or suppliers > 0
    min_revenue = Decimal(str(cfg.get("receita_minima", 10000)))

    if commerce_signal and cogs <= 0 and revenue > min_revenue:
        return [
            RuleFinding(
                codigo="SN-018A",
                titulo="Receita de comercio sem CMV ou custo de mercadorias identificado",
                nivel=RiskLevel.ALTO,
                pontuacao=cfg.get("pontuacao_alto", 24),
                descricao="Ha receita e indicadores comerciais, mas nao foi identificado custo de mercadorias vendidas ou baixa equivalente no balancete.",
                evidencia={
                    "receita": format_brl(revenue),
                    "estoques": format_brl(inventory),
                    "fornecedores": format_brl(suppliers),
                    "cmv_custos": format_brl(cogs),
                },
                recomendacao="Verificar se as baixas de estoque/CMV foram contabilizadas por competencia e se as contas de custo foram classificadas corretamente.",
                normas_aplicaveis=("CPC 16 R1", "NBC TG 1000", "ITG 2000"),
            )
        ]

    if cogs <= 0:
        return []

    ratio = cogs / revenue
    lim_alto = Decimal(str(cfg.get("limite_alto_ratio", 0.95)))
    if ratio > lim_alto:
        return [
            RuleFinding(
                codigo="SN-018C",
                titulo="CMV muito elevado em relacao a receita",
                nivel=RiskLevel.ALTO,
                pontuacao=cfg.get("pontuacao_alto", 24),
                descricao="O custo de mercadorias representa percentual muito elevado da receita, indicando margem bruta insuficiente ou possivel classificacao indevida.",
                evidencia={
                    "receita": format_brl(revenue),
                    "cmv_custos": format_brl(cogs),
                    "percentual_cmv_receita": format_percent(ratio),
                },
                recomendacao="Revisar precificacao, devolucoes, descontos, compras, criterio de custeio e classificacao entre custo e despesa.",
                normas_aplicaveis=("CPC 16 R1", "NBC TG 1000"),
            )
        ]

    lim_baixo = Decimal(str(cfg.get("limite_baixo_ratio", 0.30)))
    if commerce_signal and ratio < lim_baixo:
        return [
            RuleFinding(
                codigo="SN-018B",
                titulo="CMV baixo para operacao comercial com estoque ou fornecedores",
                nivel=RiskLevel.MEDIO,
                pontuacao=cfg.get("pontuacao_medio", 14),
                descricao="O custo de mercadorias esta baixo em relacao a receita diante de sinais de operacao comercial, exigindo validacao das baixas de estoque.",
                evidencia={
                    "receita": format_brl(revenue),
                    "cmv_custos": format_brl(cogs),
                    "estoques": format_brl(inventory),
                    "fornecedores": format_brl(suppliers),
                    "percentual_cmv_receita": format_percent(ratio),
                },
                recomendacao="Conferir baixas de estoque, notas fiscais de saida, custo medio e eventual classificacao de custos em outras contas.",
                normas_aplicaveis=("CPC 16 R1", "ITG 2000"),
            )
        ]

    return []


def check_commerce_sublimit(revenue: Decimal, rbt12_revenue: Decimal | None = None) -> list[RuleFinding]:
    if revenue <= 0:
        return []

    cfg = get_rule_config("SN-019")
    has_rbt12 = rbt12_revenue is not None and rbt12_revenue > 0
    annualized_revenue = (rbt12_revenue or Decimal("0")) if has_rbt12 else revenue * Decimal("4")
    base_calculo_limite = "RBT12 consolidado pelo historico" if has_rbt12 else "receita trimestral anualizada (receita x 4)"
    sublimite = Decimal(str(cfg.get("sublimite_anual", 3600000)))
    if annualized_revenue <= sublimite:
        return []

    return [
        RuleFinding(
            codigo="SN-019",
            titulo="Receita anualizada acima do sublimite de ICMS",
            nivel=RiskLevel.MEDIO,
            pontuacao=cfg.get("pontuacao_medio", 16),
            descricao="A receita trimestral anualizada supera o sublimite usado como alerta para ICMS fora do DAS em empresas comerciais.",
            evidencia={
                "receita_trimestre": format_brl(revenue),
                "receita_anualizada_estimativa": format_brl(annualized_revenue),
                "sublimite_anual": format_brl(sublimite),
                "base_calculo_limite": base_calculo_limite,
            },
            recomendacao="Validar a RBT12, sublimite estadual aplicavel, segregacao de receitas e eventual recolhimento de ICMS fora do DAS.",
            normas_aplicaveis=("LC 123/2006", "art. 20 LC 123/2006"),
        )
    ]


def check_icms_st_attention(
    revenue: Decimal,
    inventory: Decimal,
    suppliers: Decimal,
    cogs: Decimal,
    tax_credits: Decimal,
) -> list[RuleFinding]:
    cfg = get_rule_config("SN-024")
    min_revenue = Decimal(str(cfg.get("receita_minima", 10000)))
    if revenue <= min_revenue:
        return []

    credit_ratio_limit = Decimal(str(cfg.get("limite_creditos_ratio", 0.01)))
    credit_ratio = tax_credits / revenue if revenue > 0 else Decimal("0")
    commercial_signal = inventory > 0 or suppliers > 0 or cogs > 0
    has_relevant_tax_credits = tax_credits > 0 and credit_ratio >= credit_ratio_limit

    if not commercial_signal or not has_relevant_tax_credits:
        return []

    return [
        RuleFinding(
            codigo="SN-024",
            titulo="Validacao de ICMS-ST e creditos fiscais em operacao comercial",
            nivel=RiskLevel.BAIXO,
            pontuacao=cfg.get("pontuacao_baixo", 6),
            descricao="Foram identificados creditos fiscais em contexto comercial, exigindo validacao documental de ICMS-ST, retencoes, ressarcimentos ou saldos recuperaveis.",
            evidencia={
                "receita": format_brl(revenue),
                "creditos_fiscais": format_brl(tax_credits),
                "percentual_sobre_receita": format_percent(credit_ratio),
                "estoques": format_brl(inventory),
                "fornecedores": format_brl(suppliers),
                "cmv_custos": format_brl(cogs),
                "tipo_achado": "validacao_documental",
                "limitacao_dados": "Balancete nao contem NCM, CFOP, CST ou item fiscal; exige confronto com notas fiscais e PGDAS-D.",
            },
            recomendacao="Validar NCM, CFOP, mercadorias sujeitas a substituicao tributaria, documentos de compra/venda, ressarcimentos e suporte dos creditos fiscais antes de concluir sobre margem e DAS.",
            normas_aplicaveis=("LC 123/2006", "art. 20 LC 123/2006", "ITG 2000"),
        )
    ]
