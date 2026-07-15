from __future__ import annotations

import unicodedata

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
    text = normalize_key(description)
    mapped_group = _mapped_grupo_from_config(c, description, allow_description=False)
    if mapped_group:
        return mapped_group

    if "lucros distribuidos" in text or "distribuicao antecipada de lucros" in text:
        return "lucros"

    if c.startswith("1.1.1"):
        if any(k in text for k in ("cliente", "duplicata", "receber")):
            return "clientes"
        if any(k in text for k in ("banco", "conta corrente", "aplicacao", "poupanca", "cdb", "lci", "lca", "rdbi", "fundo", "tesouro")):
            return "bancos"
        return "caixa"
    if c.startswith("1.1.2"):
        if any(k in text for k in ("caixa", "banco", "conta corrente", "aplicacao", "poupanca")):
            return "bancos"
        return "clientes"
    if c.startswith("1.1.3"):
        if c.startswith("1.1.3.01"):
            return "bancos"
        if c.startswith(("1.1.3.02", "1.1.3.03")):
            return "clientes"
        if any(k in text for k in ("adiantamento", "adiantamentos")):
            return "adiantamentos"
        if any(k in text for k in ("recuperar", "compensar", "credito", "inss", "pis", "cofins", "irrf", "csll", "icms", "iss")):
            return "creditos_fiscais"
        return "outros"
    if c.startswith("1.1.40"):
        return "estoques"
    if c.startswith("1.1.4"):
        if "lucro" in text:
            return "lucros"
        return "investimentos"
    if c.startswith("1.1.5"):
        return "estoques"
    if c.startswith(("1.1.6", "1.1.7", "1.1.8", "1.1.9")):
        return "outros"

    if c.startswith("1.1.10.1"):
        if any(k in text for k in ("banco", "conta corrente", "aplicacao", "poupanca", "cdb", "lci", "lca", "rdbi", "fundo", "tesouro")):
            return "bancos"
        return "caixa"
    if c.startswith("1.1.10.2"):
        if any(k in text for k in ("caixa", "fundo fixo", "pequena caixa")):
            return "caixa"
        return "bancos"
    if c.startswith("1.1.10"):
        return "bancos"
    if c.startswith("1.1.20"):
        return "clientes"
    if c.startswith("1.1.30.5"):
        return "adiantamentos"
    if c.startswith("1.1.30.8"):
        return "creditos_fiscais"
    if c.startswith("1.1.30.9"):
        return "outros"
    if c.startswith("1.1.30"):
        parts = c.split(".")
        sub = parts[3] if len(parts) > 3 else ""
        if sub.startswith("5"):
            return "adiantamentos"
        if sub.startswith("8"):
            return "creditos_fiscais"
        return "outros"
    if c.startswith("1.1"):
        return "outros"

    if c.startswith("1.2.10"):
        return "outros"
    if c.startswith("1.2.20"):
        return "patrimonio"
    if c.startswith(("1.2.30", "1.2.40")):
        return "imobilizado"
    if c.startswith("1.2.1"):
        if "cliente" in text or "duplicata" in text or "receber" in text:
            return "clientes"
        return "outros"
    if c.startswith("1.2.2"):
        if "banco" in text or "aplicacao" in text:
            return "bancos"
        if any(k in text for k in ("tributo", "recuperar", "compensar", "credito", "inss", "pis", "cofins", "irrf", "csll", "icms", "iss")):
            return "creditos_fiscais"
        return "outros"
    if c.startswith("1.2.3"):
        return "investimentos"
    if c.startswith(("1.2.4", "1.2.5")):
        return "imobilizado"
    if c.startswith("1.2.6"):
        return "outros"
    if c.startswith(("1.3.3", "1.3")):
        return "outros"
    if c.startswith(("1.2.30", "1.2.40", "1.2")):
        return "imobilizado"

    if c.startswith("2.1.10"):
        return "fornecedores"
    if c.startswith("2.1.20"):
        return "folha"
    if c.startswith("2.1.70"):
        return "provisoes"
    if c.startswith("2.1.1"):
        return "emprestimos"
    if c.startswith("2.1.2"):
        return "emprestimos"
    if c.startswith("2.1.3"):
        return "fornecedores"
    if c.startswith("2.1.4"):
        return "tributos_a_recolher"
    if c.startswith("2.1.5"):
        if c.startswith(("2.1.5.04", "2.1.5.05", "2.1.5.06")):
            return "tributos_a_recolher"
        if c.startswith("2.1.5.03"):
            return "provisoes"
        if any(k in text for k in ("inss", "fgts", "previdencia", "contribuicao social", "imposto", "tributo", "simples", "irrf", "iss", "pis", "cofins")):
            return "tributos_a_recolher"
        if any(k in text for k in ("salario", "ordenado", "pro-labore", "rescis", "ferias", "13")):
            return "folha"
        return "folha"
    if c.startswith("2.1.6"):
        if any(k in text for k in ("socio", "administrador", "pessoa ligada", "mutuo")):
            return "socios"
        if c.startswith("2.1.6.01") or any(k in text for k in ("adiantamento de cliente", "adiantamentos de clientes", "cliente")):
            return "adiantamentos_clientes"
        return "outros"
    if c.startswith("2.1.7"):
        return "lucros"
    if c.startswith(("2.1.30", "2.1.40")):
        return "tributos_a_recolher"
    if c.startswith("2.1.50.1"):
        return "folha"
    if c.startswith("2.1.50.2"):
        return "tributos_a_recolher"
    if c.startswith("2.1.50"):
        if any(k in text for k in ("inss", "fgts", "previdencia", "contribuicao social")):
            return "tributos_a_recolher"
        if any(k in text for k in ("salario", "ordenado", "pro-labore", "rescis", "ferias", "13")):
            return "folha"
        return "folha"
    if c.startswith("2.1.60.1"):
        return "adiantamentos_clientes"
    if c.startswith("2.1.60.6"):
        return "socios"
    if c.startswith("2.1.60"):
        if any(k in text for k in ("socio", "administrador", "pessoa ligada", "mutuo")):
            return "socios"
        return "outros"
    if c.startswith("2.1.70"):
        return "provisoes"
    if c.startswith("2.1"):
        if "fornecedor" in text:
            return "fornecedores"
        if any(k in text for k in ("inss", "fgts", "simples", "irrf", "iss", "icms", "pis", "cofins", "tributo", "imposto")):
            return "tributos_a_recolher"
        if any(k in text for k in ("salario", "pro-labore", "ferias", "rescis")):
            return "folha"
        return "outros"

    if c.startswith("2.2.1.08"):
        return "fornecedores"
    if c.startswith(("2.2.1.09", "2.2.1.15", "2.2.1.16")):
        return "tributos_a_recolher"
    if c.startswith("2.2.1.10"):
        return "adiantamentos_clientes"
    if c.startswith(("2.2.11.3", "2.2")):
        return "emprestimos"

    if c.startswith(("2.3.10", "2.3.20", "2.3.30", "2.3.40")):
        return "patrimonio"
    if c.startswith("2.3.50"):
        return "resultado"
    if c.startswith("2.3"):
        return "patrimonio"

    if c.startswith("3.1.2"):
        if any(k in text for k in ("simples", "imposto", "tributo", "iss", "icms", "pis", "cofins")):
            return "tributos_sobre_receita"
        return "receita"
    if c.startswith(("3.1.1", "3.1.10", "3.1")):
        if c.startswith("3.1.20"):
            return "tributos_sobre_receita"
        return "receita"
    if c.startswith("3.2"):
        return "receita"

    if c.startswith("4.1"):
        return "custos"
    if c.startswith("4.2.1.01"):
        return "folha"
    if c.startswith("4.2.1.05"):
        return "despesas_representacao"
    if c.startswith(("4.2.1.11", "4.2.1.12", "4.2.2.03")):
        return "despesas_tributarias"
    if c.startswith("4.2.2.01"):
        return "folha"
    if c.startswith("4.2.2.05"):
        return "despesas"
    if c.startswith("4.2.3"):
        return "despesas"
    if c.startswith(("4.2.20.100", "4.2.20.200")):
        return "folha"
    if c.startswith("4.2.20.300.007"):
        return "multas_fiscais"
    if c.startswith("4.2.20.300"):
        return "despesas_tributarias"
    if c.startswith(("4.2.20.400", "4.2.20.500")):
        if any(k in text for k in ("representacao", "viagem", "hospedagem", "brinde", "alimentacao")):
            return "despesas_representacao"
        if any(k in text for k in ("combustivel", "ipva", "pedagio", "veiculo", "manutencao")):
            return "despesas_veiculos"
        return "despesas"
    if c.startswith(("4.2", "4.3", "4")):
        if any(k in text for k in ("pro-labore", "salario", "ordenado", "ferias", "fgts", "13")):
            return "folha"
        if "provisao" in text or "provisoes" in text:
            return "provisoes"
        if any(k in text for k in ("representacao", "viagem", "hospedagem")):
            return "despesas_representacao"
        if any(k in text for k in ("veiculo", "combustivel", "manutencao")):
            return "despesas_veiculos"
        if any(k in text for k in ("imposto", "taxa", "tributo", "inss", "fgts")):
            return "despesas_tributarias"
        return "despesas"

    if "socio" in text or "socios" in text or "administradores" in text:
        return "socios"
    if "adiantamento" in text or "adiantamentos" in text:
        return "adiantamentos"
    if "caixa" in text:
        return "caixa"
    if text.startswith("banco ") or "conta corrente" in text:
        return "bancos"
    if "duplicatas a receber" in text or "cliente" in text:
        return "clientes"
    if "estoque" in text:
        return "estoques"
    if "imobilizado" in text or "imovel" in text or "veiculo" in text:
        return "imobilizado"
    if "fornecedor" in text:
        return "fornecedores"
    if "receita" in text:
        return "receita"
    if any(k in text for k in ("imposto", "tributo", "simples", "irrf", "iss", "icms", "pis", "cofins", "inss", "fgts")):
        return "tributos"
    if any(k in text for k in ("pro-labore", "salario", "ordenado", "ferias", "rescis")):
        return "folha"
    if "provisao" in text or "provisoes" in text:
        return "provisoes"
    if any(k in text for k in ("representacao", "viagem", "hospedagem")):
        return "despesas_representacao"
    if any(k in text for k in ("veiculo", "combustivel", "manutencao")):
        return "despesas_veiculos"
    if "despesa" in text:
        return "despesas"

    return "outros"


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
