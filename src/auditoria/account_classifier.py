from __future__ import annotations

import unicodedata

from .account_dominio_rules import infer_dominio_group
from .config_loader import load_account_map

VALID_GRUPOS = frozenset({
    "receita", "despesas", "tributos", "folha", "clientes", "fornecedores",
    "bancos", "caixa", "socios", "adiantamentos", "lucros", "resultado",
    "provisoes", "imobilizado", "despesas_representacao", "despesas_veiculos",
    "custos", "investimentos", "patrimonio_liquido", "patrimonio", "estoque",
    "estoques", "creditos_fiscais", "adiantamentos_clientes", "emprestimos",
    "tributos_a_recolher", "tributos_sobre_receita", "despesas_tributarias",
    "multas_fiscais", "outros",
})


def classify_group(codigo: str, conta: str, grupo_original: str) -> tuple[str, str, str, str]:
    mapped_by_code = _mapped_grupo_from_config(codigo, conta, allow_description=False)
    inferred = _infer_grupo_from_conta(codigo, conta)
    mapped_by_description = _mapped_grupo_from_config(codigo, conta, allow_description=True)
    mapped_group = mapped_by_code or inferred or mapped_by_description

    if grupo_original in VALID_GRUPOS and grupo_original != "outros":
        observacao = "Grupo informado no arquivo de entrada."
        if mapped_group and mapped_group != grupo_original:
            observacao = f"Grupo informado no arquivo; mapa/inferencia sugeriu '{mapped_group}'."
        return grupo_original, "arquivo", "alta", observacao

    if inferred and mapped_by_code and inferred != mapped_by_code:
        return (
            inferred,
            "inferido_codigo_descricao",
            "media",
            f"Descricao especifica sugeriu '{inferred}', enquanto o mapa por codigo/prefixo sugeriu '{mapped_by_code}'.",
        )
    if mapped_by_code:
        return mapped_by_code, "mapa_codigo_prefixo", "alta", "Classificado pelo mapa configuravel por codigo exato, segmento ou prefixo."
    if inferred:
        return inferred, "inferido_codigo_descricao", "media", "Classificado por fallback interno com base no codigo e/ou descricao da conta."
    if mapped_by_description:
        return mapped_by_description, "mapa_descricao", "media", "Classificado pelo mapa configuravel por descricao da conta."

    motivo = "Grupo original invalido." if grupo_original not in VALID_GRUPOS else "Grupo original informado como outros."
    return "outros", "nao_classificado", "baixa", f"{motivo} Revisar mapeamento do plano de contas."


def dominio_group(classification: str, description: str) -> str:
    c = (classification or "").strip()
    mapped_group = _mapped_grupo_from_config(c, description, allow_description=False)
    return infer_dominio_group(c, description, mapped_group=mapped_group)


def classify_dominio_group(classification: str, description: str) -> tuple[str, str, str, str]:
    mapped_group = _mapped_grupo_from_config(classification, description, allow_description=False)
    inferred = _infer_grupo_from_conta(classification, description)
    if inferred and mapped_group and inferred != mapped_group:
        return (
            inferred,
            "inferido_codigo_descricao",
            "media",
            f"Descricao especifica sugeriu '{inferred}', enquanto o mapa por codigo/prefixo sugeriu '{mapped_group}'.",
        )
    if mapped_group:
        return mapped_group, "mapa_codigo_prefixo", "alta", "Classificado pelo mapa configuravel antes dos fallbacks do layout Dominio."

    group = dominio_group(classification, description)
    if group == "outros":
        return group, "nao_classificado", "baixa", "Layout Dominio nao encontrou grupo especifico; revisar mapeamento do plano de contas."
    return group, "layout_dominio", "media", "Classificado por prefixos e descricoes conhecidos do layout Dominio."


def _infer_grupo_from_conta(codigo: str, conta: str) -> str | None:
    text = normalize_key(conta)

    if "provisao" in text or "provisoes" in text or "ferias" in text or "13" in text:
        return "provisoes"
    if "imovel" in text or "imoveis" in text or "imobilizado" in text:
        return "imobilizado"
    if "veiculo" in text:
        return "imobilizado"
    if any(k in text for k in ("socio", "socios", "administrador", "administradores", "pessoa ligada", "mutuo")):
        return "socios"
    if any(k in text for k in ("juros sobre emprestimo", "juros de emprestimo", "juros a transcorrer", "juros a incorrer", "encargos financeiros", "despesas financeiras", "despesa financeira", "encargos a apropriar", "iof sobre emprestimo", "variacao monetaria")):
        return "despesas"
    if any(k in text for k in ("emprestimo", "emprestimos", "financiamento", "financiamentos", "capital de giro")):
        return "emprestimos"
    if "fornecedor" in text:
        return "fornecedores"
    if "representacao" in text or "viagem" in text or "hospedagem" in text or "alimentacao" in text:
        return "despesas_representacao"
    if "combustivel" in text or "manutencao veicular" in text or "estacionamento" in text:
        return "despesas_veiculos"
    if "custo" in text:
        return "custos"
    if "investimento" in text or "aplicacao" in text:
        return "investimentos"
    if "capital social" in text or "reserva" in text or "prejuizo" in text or "lucro acumulado" in text:
        return "patrimonio_liquido"
    if any(k in text for k in ("imposto", "tributo", "simples", "irrf", "iss", "icms", "pis", "cofins", "inss", "fgts")):
        if codigo.startswith("2."):
            return "tributos_a_recolher"
        if codigo.startswith("3."):
            return "tributos_sobre_receita"
        if codigo.startswith("4."):
            return "despesas_tributarias"
        return "tributos"
    if "despesa" in text:
        return "despesas"

    return None


def _mapped_grupo_from_config(codigo: str, conta: str, *, allow_description: bool = True) -> str | None:
    try:
        mappings = load_account_map().get("mapeamentos", [])
    except Exception:
        return None

    code = str(codigo or "").strip()
    text = normalize_key(conta)
    code_parts = "".join(char if char.isdigit() else " " for char in code).split()

    for mapping in mappings:
        if not isinstance(mapping, dict):
            continue

        group = str(mapping.get("grupo") or "").strip().lower()
        if group not in VALID_GRUPOS:
            continue

        exact_codes = {str(value).strip() for value in mapping.get("codigos_exatos", [])}
        if code and code in exact_codes:
            return group

        prefixes = [str(value).strip() for value in mapping.get("prefixos", []) if str(value).strip()]
        if code and any(code.startswith(prefix) for prefix in prefixes):
            return group

        segments = {str(value).strip() for value in mapping.get("segmentos_codigo", []) if str(value).strip()}
        if segments and any(segment in code_parts for segment in segments):
            return group

        if allow_description:
            descriptions = [
                normalize_key(str(value))
                for value in mapping.get("descricoes_contem", [])
                if str(value).strip()
            ]
            if text and any(pattern and pattern in text for pattern in descriptions):
                return group

    return None

def normalize_key(value: str | None) -> str:
    text = unicodedata.normalize("NFKD", value or "")
    text = "".join(char for char in text if not unicodedata.combining(char))
    return " ".join(text.strip().lower().split())
