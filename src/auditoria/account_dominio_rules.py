from __future__ import annotations

import unicodedata


def infer_dominio_group(classification: str, description: str, mapped_group: str | None = None) -> str:
    c = (classification or "").strip()
    text = _normalize_key(description)
    if mapped_group:
        return mapped_group

    if "lucros distribuidos" in text or "distribuicao antecipada de lucros" in text:
        return "lucros"

    if _has_prefix(c, "1.1.1"):
        if any(k in text for k in ("cliente", "duplicata", "receber")):
            return "clientes"
        if any(k in text for k in ("banco", "conta corrente", "aplicacao", "poupanca", "cdb", "lci", "lca", "rdbi", "fundo", "tesouro")):
            return "bancos"
        return "caixa"
    if _has_prefix(c, "1.1.2"):
        if any(k in text for k in ("caixa", "banco", "conta corrente", "aplicacao", "poupanca")):
            return "bancos"
        return "clientes"
    if _has_prefix(c, "1.1.3"):
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
    if _has_prefix(c, "1.1.4"):
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
    if _has_prefix(c, "1.2.1"):
        if "cliente" in text or "duplicata" in text or "receber" in text:
            return "clientes"
        return "outros"
    if _has_prefix(c, "1.2.2"):
        if "banco" in text or "aplicacao" in text:
            return "bancos"
        if any(k in text for k in ("tributo", "recuperar", "compensar", "credito", "inss", "pis", "cofins", "irrf", "csll", "icms", "iss")):
            return "creditos_fiscais"
        return "outros"
    if _has_prefix(c, "1.2.3"):
        return "investimentos"
    if c.startswith(("1.2.4", "1.2.5")):
        return "imobilizado"
    if _has_prefix(c, "1.2.6"):
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
    if _has_prefix(c, "2.1.1"):
        return "emprestimos"
    if _has_prefix(c, "2.1.2"):
        return "emprestimos"
    if _has_prefix(c, "2.1.3"):
        return "fornecedores"
    if _has_prefix(c, "2.1.4"):
        return "tributos_a_recolher"
    if _has_prefix(c, "2.1.5"):
        if c.startswith(("2.1.5.04", "2.1.5.05", "2.1.5.06")):
            return "tributos_a_recolher"
        if c.startswith("2.1.5.03"):
            return "provisoes"
        if any(k in text for k in ("inss", "fgts", "previdencia", "contribuicao social", "imposto", "tributo", "simples", "irrf", "iss", "pis", "cofins")):
            return "tributos_a_recolher"
        if any(k in text for k in ("salario", "ordenado", "pro-labore", "rescis", "ferias", "13")):
            return "folha"
        return "folha"
    if _has_prefix(c, "2.1.6"):
        if any(k in text for k in ("socio", "administrador", "pessoa ligada", "mutuo")):
            return "socios"
        if c.startswith("2.1.6.01") or any(k in text for k in ("adiantamento de cliente", "adiantamentos de clientes", "cliente")):
            return "adiantamentos_clientes"
        return "outros"
    if _has_prefix(c, "2.1.7"):
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

    if _has_prefix(c, "3.1.2"):
        if any(k in text for k in ("simples", "imposto", "tributo", "iss", "icms", "pis", "cofins")):
            return "tributos_sobre_receita"
        return "receita"
    if _has_any_prefix(c, "3.1.1", "3.1.10", "3.1"):
        if _has_prefix(c, "3.1.20"):
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


def _normalize_key(value: str | None) -> str:
    text = unicodedata.normalize("NFKD", value or "")
    text = "".join(char for char in text if not unicodedata.combining(char))
    return " ".join(text.strip().lower().split())


def _has_prefix(code: str, prefix: str) -> bool:
    return code == prefix or code.startswith(prefix + ".")


def _has_any_prefix(code: str, *prefixes: str) -> bool:
    return any(_has_prefix(code, prefix) for prefix in prefixes)
