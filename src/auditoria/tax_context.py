from __future__ import annotations

from decimal import Decimal
from typing import Any

from .config_loader import load_simples_anexos
from .utils import format_brl, format_percent


def build_contexto_regime_simples(
    regime: str,
    revenue: Decimal,
    payroll: Decimal,
    taxes: Decimal,
    conjunto_regras: str,
    rbt12_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    annual_proxy = revenue * Decimal("4")
    rbt12_revenue = context_decimal(rbt12_context, "receita")
    rbt12_payroll = context_decimal(rbt12_context, "folha")
    has_rbt12_revenue = rbt12_revenue is not None and rbt12_revenue > 0
    if has_rbt12_revenue:
        base_revenue = rbt12_revenue or Decimal("0")
        base_description = str((rbt12_context or {}).get("base_calculo") or "RBT12 consolidado a partir do historico salvo")
    else:
        base_revenue = annual_proxy
        base_description = "receita trimestral anualizada (receita x 4)"

    faixa = simples_faixa(base_revenue)
    fator_r: str | None = None
    fator_r_valor: Decimal | None = None
    fator_r_base = "nao calculado"
    fator_r_threshold = "28%"
    if revenue > 0 and conjunto_regras in {"simples_servicos", "simples_comercio_servicos"}:
        if has_rbt12_revenue and rbt12_payroll is not None:
            fator_r_valor = rbt12_payroll / base_revenue
            fator_r_base = "RBT12 consolidado"
        else:
            fator_r_valor = payroll / revenue
            fator_r_base = "trimestre analisado"
        fator_r = format_percent(fator_r_valor)

    anexo_key, anexo_label = simples_anexo_estimado(conjunto_regras, fator_r_valor)
    aliquota_info = simples_aliquota_esperada(base_revenue, anexo_key) if anexo_key else None
    aliquota_esperada = aliquota_context_label(aliquota_info, anexo_label)

    observacoes: list[str] = []
    if conjunto_regras == "simples_comercio":
        observacoes.append(
            "Atividade analisada como comercio: contexto tributario estimado pelo Anexo I; validar segregacao de receitas, estoque, fornecedores, CMV, ICMS e possivel ICMS-ST."
        )
    elif conjunto_regras == "simples_comercio_servicos":
        observacoes.append(
            "Atividade analisada como comercio e servicos: nao ha aliquota unica sem segregacao; validar receitas por natureza, Anexo I para comercio e Anexo III/V para servicos, Fator R, ISS, ICMS e ICMS-ST."
        )

    if fator_r:
        if fator_r_valor is not None and fator_r_valor < Decimal("0.28"):
            observacoes.append(
                f"Fator R trimestral estimado de {fator_r} está abaixo da referência de 28%. "
                "Para servicos sujeitos ao Fator R, o contexto estimado aponta para Anexo V; validar o calculo oficial com folha e receita acumuladas dos ultimos 12 meses antes de concluir sobre o anexo aplicavel."
            )
        else:
            observacoes.append(
                f"Fator R trimestral estimado de {fator_r} está acima de 28%. "
                "Para servicos sujeitos ao Fator R, o contexto estimado aponta para Anexo III; validar o calculo oficial com folha e receita acumuladas dos ultimos 12 meses antes de concluir sobre o anexo aplicavel."
            )

    sublimite_risco = base_revenue > Decimal("3600000")
    if sublimite_risco:
        observacoes.append(
            "Receita trimestral anualizada supera R$ 3.600.000 — verificar receita acumulada dos últimos 12 meses, sublimite estadual "
            "para ICMS/ISS fora do DAS (art. 20 da LC 123/2006)."
        )

    if has_rbt12_revenue:
        observacoes.append(
            "O contexto tributario usou RBT12 consolidado pelo historico disponivel; conferir PGDAS-D e segregacao oficial antes de emitir conclusao definitiva."
        )
    else:
        observacoes.append(
            "Sem RBT12 completo informado ao motor, a faixa e a aliquota usam receita trimestral anualizada apenas como alerta."
        )

    return {
        "regime": regime,
        "atividade": conjunto_regras,
        "faixa_receita_estimada": faixa,
        "aliquota_efetiva_esperada": aliquota_esperada,
        "anexo_estimado": anexo_label,
        "aliquota_nominal_estimada": aliquota_info["aliquota_nominal"] if aliquota_info else "[VERIFICAR: receita segregada por anexo]",
        "parcela_deduzir_estimada": aliquota_info["parcela_deduzir"] if aliquota_info else "[VERIFICAR: receita segregada por anexo]",
        "base_calculo_estimativa": base_description,
        "receita_rbt12_utilizada": format_brl(rbt12_revenue) if has_rbt12_revenue else None,
        "folha_rbt12_utilizada": format_brl(rbt12_payroll) if rbt12_payroll is not None else None,
        "rbt12_disponivel": has_rbt12_revenue,
        "origem_rbt12": str((rbt12_context or {}).get("origem") or ""),
        "fonte_tabela_anexos": "Lei Complementar n. 123/2006, anexos I, III e V",
        "fator_r_calculado": fator_r,
        "fator_r_base": fator_r_base,
        "fator_r_threshold": fator_r_threshold,
        "sublimite_risco": sublimite_risco,
        "observacoes": observacoes,
    }


def normalize_rbt12_context(context: dict[str, Any] | None) -> dict[str, Any] | None:
    if not context:
        return None

    normalized = dict(context)
    for key in ("receita", "folha"):
        value = context_decimal(normalized, key)
        if value is not None:
            normalized[key] = value
    return normalized


def context_decimal(context: dict[str, Any] | None, key: str) -> Decimal | None:
    if not context:
        return None

    value = context.get(key)
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None


def simples_faixa(annual_revenue: Decimal) -> str:
    faixas = [
        (Decimal("180000"), "1ª faixa (até R$ 180.000,00/ano)"),
        (Decimal("360000"), "2ª faixa (R$ 180.000,01 a R$ 360.000,00/ano)"),
        (Decimal("720000"), "3ª faixa (R$ 360.000,01 a R$ 720.000,00/ano)"),
        (Decimal("1800000"), "4ª faixa (R$ 720.000,01 a R$ 1.800.000,00/ano)"),
        (Decimal("3600000"), "5ª faixa (R$ 1.800.000,01 a R$ 3.600.000,00/ano)"),
        (Decimal("4800000"), "6ª faixa (R$ 3.600.000,01 a R$ 4.800.000,00/ano)"),
    ]
    for limite, descricao in faixas:
        if annual_revenue <= limite:
            return descricao
    return "Acima do limite do Simples Nacional"


def simples_anexo_estimado(conjunto_regras: str, fator_r_valor: Decimal | None) -> tuple[str | None, str]:
    if conjunto_regras == "simples_comercio":
        return "anexo_i", "Anexo I (comercio)"
    if conjunto_regras == "simples_comercio_servicos":
        return None, "Anexos I e III/V (exige segregacao de receitas)"
    if fator_r_valor is not None and fator_r_valor < Decimal("0.28"):
        return "anexo_v", "Anexo V estimado (Fator R trimestral abaixo de 28%)"
    return "anexo_iii", "Anexo III estimado"


def simples_aliquota_esperada(annual_revenue: Decimal, anexo_key: str) -> dict[str, str] | None:
    anexos = load_simples_anexos().get("anexos", {})
    anexo = anexos.get(anexo_key)
    if not anexo:
        return None

    if annual_revenue <= 0:
        return {
            "anexo": str(anexo.get("nome") or anexo_key),
            "aliquota_nominal": "0,00%",
            "parcela_deduzir": "R$ 0,00",
            "aliquota_efetiva": "0,00%",
        }

    for faixa in anexo.get("faixas", []):
        limite = Decimal(str(faixa.get("limite_superior", 0)))
        if annual_revenue <= limite:
            nominal = Decimal(str(faixa.get("aliquota", 0)))
            deduction = Decimal(str(faixa.get("parcela_deduzir", 0)))
            effective = max((annual_revenue * nominal - deduction) / annual_revenue, Decimal("0"))
            return {
                "anexo": str(anexo.get("nome") or anexo_key),
                "aliquota_nominal": format_percent(nominal),
                "parcela_deduzir": format_brl(deduction),
                "aliquota_efetiva": format_percent(effective),
            }

    return {
        "anexo": str(anexo.get("nome") or anexo_key),
        "aliquota_nominal": "Acima do limite",
        "parcela_deduzir": "Acima do limite",
        "aliquota_efetiva": "Acima do limite",
    }


def aliquota_context_label(aliquota_info: dict[str, str] | None, anexo_label: str) -> str:
    if not aliquota_info:
        return "[VERIFICAR: segregar receita de comercio e servicos para estimar aliquota por anexo]"
    return (
        f"{anexo_label}: nominal {aliquota_info['aliquota_nominal']}; "
        f"efetiva estimada {aliquota_info['aliquota_efetiva']}; "
        f"parcela a deduzir {aliquota_info['parcela_deduzir']}"
    )
