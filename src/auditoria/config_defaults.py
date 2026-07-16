from __future__ import annotations

from typing import Any


def build_rules_defaults() -> dict[str, Any]:
    return {
        "version": "1.12.0",
        "limites_gerais": {
            "simples_anual": 4800000,
            "limite_movimentacao_ativa": 10000,
            "receita_baixa_ratio": 0.05,
        },
        "conjuntos_regras": {
            "simples_servicos": [
                "SN-001", "SN-002", "SN-003", "SN-004", "SN-005", "SN-006", "SN-007",
                "SN-008", "SN-009", "SN-010", "SN-011", "SN-012", "SN-013", "SN-014",
                "SN-021", "SN-022", "SN-023", "SN-025", "SN-026", "SN-027", "SN-028",
                "SN-COMP-01", "SN-COMP-02", "SN-COMP-03",
            ],
            "simples_comercio": [
                "SN-001", "SN-002", "SN-004", "SN-005", "SN-006", "SN-007",
                "SN-008", "SN-009", "SN-010", "SN-011", "SN-012", "SN-013", "SN-014",
                "SN-015", "SN-016", "SN-017", "SN-018", "SN-019",
                "SN-021", "SN-022", "SN-023", "SN-024", "SN-025", "SN-026", "SN-027", "SN-028",
                "SN-COMP-01", "SN-COMP-02", "SN-COMP-03", "SN-COMP-04",
            ],
            "simples_comercio_servicos": [
                "SN-001", "SN-002", "SN-003", "SN-004", "SN-005", "SN-006", "SN-007",
                "SN-008", "SN-009", "SN-010", "SN-011", "SN-012", "SN-013", "SN-014",
                "SN-015", "SN-016", "SN-017", "SN-018", "SN-019", "SN-020",
                "SN-021", "SN-022", "SN-023", "SN-024", "SN-025", "SN-026", "SN-027", "SN-028",
                "SN-COMP-01", "SN-COMP-02", "SN-COMP-03", "SN-COMP-04", "SN-COMP-05",
            ],
        },
        "SN-001": {
            "limite_alto": 0.90,
            "pontuacao_alto": 35,
            "limite_medio": 0.70,
            "pontuacao_medio": 18,
        },
        "SN-002": {
            "limite_alto": 0.03,
            "pontuacao_alto": 20,
            "limite_medio": 0.055,
            "pontuacao_medio": 15,
        },
        "SN-003": {
            "limite_medio": 0.08,
            "pontuacao_medio": 14,
        },
        "SN-004": {
            "pontuacao_alto": 32,
            "limite_medio_ratio": 0.30,
            "pontuacao_medio": 16,
        },
        "SN-005": {
            "descricao": "Saldos em contas de socios, mutuos e IOF",
            "limite_medio_receita": 0.05,
            "limite_medio_absoluto": 10000,
            "limite_baixo_absoluto": 1000,
            "pontuacao_baixo": 6,
            "pontuacao_medio": 18,
        },
        "SN-006": {
            "pontuacao_alto": 28,
            "limite_medio_ratio": 0.60,
            "pontuacao_medio": 12,
        },
        "SN-007": {
            "limite_medio": 0.70,
            "pontuacao_medio": 16,
        },
        "SN-008": {
            "pontuacao_alto": 20,
        },
        "SN-009": {
            "pontuacao_alto": 25,
            "pontuacao_medio": 12,
            "limite_medio_ratio": 0.10,
        },
        "SN-010": {
            "limite_medio_ratio": 1.0,
            "pontuacao_medio": 12,
            "limite_alto_ratio": 2.0,
            "pontuacao_alto": 20,
        },
        "SN-011": {
            "limite_ratio": 0.10,
            "limite_absoluto": 10000,
            "pontuacao_medio": 12,
        },
        "SN-012": {
            "limite_medio": 0.50,
            "pontuacao_medio": 14,
        },
        "SN-013": {
            "limite_representacao": 0.15,
            "pontuacao_representacao": 10,
            "limite_veiculos": 0.10,
            "pontuacao_veiculos": 10,
        },
        "SN-014": {
            "limite_folha_receita": 0.10,
            "pontuacao_medio": 12,
        },
        "SN-015": {
            "limite_absoluto_sem_receita": 10000,
            "limite_medio_ratio": 1.0,
            "pontuacao_medio": 14,
            "limite_alto_ratio": 2.0,
            "pontuacao_alto": 24,
        },
        "SN-016": {
            "limite_absoluto_sem_receita": 10000,
            "limite_medio_ratio": 0.8,
            "pontuacao_medio": 14,
            "limite_alto_ratio": 1.5,
            "pontuacao_alto": 22,
        },
        "SN-017": {
            "limite_absoluto": 5000,
            "limite_ratio": 0.02,
            "pontuacao_medio": 16,
        },
        "SN-018": {
            "receita_minima": 10000,
            "limite_baixo_ratio": 0.30,
            "pontuacao_medio": 14,
            "limite_alto_ratio": 0.95,
            "pontuacao_alto": 24,
        },
        "SN-019": {
            "sublimite_anual": 3600000,
            "pontuacao_medio": 16,
        },
        "SN-020": {
            "tolerancia_receita_nao_segregada": 0.20,
            "pontuacao_medio": 18,
        },
        "SN-021": {
            "referencia_presuncao_servicos": 0.32,
            "limite_baixo_ratio": 0.45,
            "pontuacao_baixo": 6,
            "limite_medio_ratio": 0.64,
            "pontuacao_medio": 12,
        },
        "SN-022": {
            "limite_servicos_absoluto": 3000,
            "limite_servicos_ratio": 0.02,
            "limite_comercio_absoluto": 10000,
            "limite_comercio_ratio": 0.05,
            "multiplicador_alto": 3,
            "pontuacao_medio": 12,
            "pontuacao_alto": 18,
        },
        "SN-023": {
            "receita_minima": 200000,
            "pontuacao_baixo": 6,
        },
        "SN-024": {
            "receita_minima": 10000,
            "limite_creditos_ratio": 0.01,
            "pontuacao_baixo": 6,
        },
        "SN-025": {
            "limite_absoluto": 10000,
            "limite_ratio_despesas": 0.20,
            "pontuacao_medio": 12,
        },
        "SN-026": {
            "descricao": "Adiantamento de clientes no passivo com saldo",
            "limite_medio_absoluto": 10000,
            "limite_medio_receita": 0.05,
            "pontuacao_baixo": 6,
            "pontuacao_medio": 14,
        },
        "SN-027": {
            "descricao": "Contas patrimoniais com saldo em natureza inversa",
            "limite_medio_absoluto": 10000,
            "limite_medio_receita": 0.05,
            "limite_baixo_absoluto": 1000,
            "pontuacao_baixo": 6,
            "pontuacao_medio": 14,
        },
        "SN-028": {
            "descricao": "Emprestimos sem evidencia de juros ou encargos por competencia",
            "limite_medio_absoluto": 10000,
            "limite_medio_receita": 0.05,
            "limite_baixo_absoluto": 1000,
            "pontuacao_baixo": 6,
            "pontuacao_medio": 14,
        },
        "SN-COMP-01": {
            "pontuacao": 8,
        },
        "SN-COMP-02": {
            "pontuacao": 8,
        },
        "SN-COMP-03": {
            "pontuacao": 6,
        },
        "SN-COMP-04": {
            "pontuacao": 8,
        },
        "SN-COMP-05": {
            "pontuacao": 8,
        },
    }


def build_account_map_defaults() -> dict[str, Any]:
    return {
        "version": "1.3.0",
        "mapeamentos": [
            {
                "nome": "Servicos prestados por terceiros",
                "grupo": "despesas",
                "codigos_exatos": ["325"],
                "prefixos": ["4.2.325", "4.2.20.325"],
                "descricoes_contem": [
                    "servicos prestados por terceiros",
                    "servico prestado por terceiro",
                    "servicos de terceiros",
                    "servico de terceiro",
                    "terceirizacao",
                    "terceirizados",
                ],
            },
            {
                "nome": "Socios, administradores e mutuos",
                "grupo": "socios",
                "codigos_exatos": ["616", "627", "770"],
                "prefixos": ["1.1.616", "1.1.627", "2.1.770"],
                "descricoes_contem": [
                    "socio",
                    "socios",
                    "administrador",
                    "administradores",
                    "pessoa ligada",
                    "mutuo",
                    "conta corrente socio",
                    "emprestimo de socio",
                    "adiantamento a socio",
                ],
            },
            {
                "nome": "Caixa fisico",
                "grupo": "caixa",
                "prefixos": ["1.1.10.100", "1.1.1.01"],
                "descricoes_contem": ["caixa matriz", "fundo fixo", "pequena caixa"],
            },
            {
                "nome": "Bancos e aplicacoes",
                "grupo": "bancos",
                "prefixos": ["1.1.10.200", "1.1.1.02", "1.1.1.03"],
                "descricoes_contem": ["banco", "conta corrente", "aplicacao financeira"],
            },
            {
                "nome": "Adiantamentos de clientes",
                "grupo": "adiantamentos_clientes",
                "prefixos": ["2.1.6.01", "2.1.60.100"],
                "descricoes_contem": [
                    "adiantamento de clientes",
                    "adiantamentos de clientes",
                    "adiantamento recebido de cliente",
                    "adiantamentos recebidos de clientes",
                ],
            },
            {
                "nome": "Juros e encargos financeiros",
                "grupo": "despesas",
                "prefixos": ["4.3", "4.2.30"],
                "descricoes_contem": [
                    "juros sobre emprestimo",
                    "juros de emprestimo",
                    "juros a transcorrer",
                    "juros a incorrer",
                    "encargos financeiros",
                    "despesas financeiras",
                    "despesa financeira",
                    "encargos a apropriar",
                    "iof sobre emprestimos",
                    "variacao monetaria",
                ],
            },
            {
                "nome": "Emprestimos e financiamentos",
                "grupo": "emprestimos",
                "prefixos": ["2.1.1", "2.1.2", "2.2.11.3"],
                "descricoes_contem": [
                    "emprestimo",
                    "emprestimos",
                    "financiamento",
                    "financiamentos",
                    "capital de giro",
                    "parcelamento bancario",
                    "banco conta emprestimo",
                ],
            },
            {
                "nome": "Clientes e recebiveis",
                "grupo": "clientes",
                "prefixos": ["1.1.20", "1.1.2", "1.1.3.02"],
                "descricoes_contem": ["cliente", "duplicata a receber", "cartao de credito"],
            },
            {
                "nome": "Estoques",
                "grupo": "estoques",
                "prefixos": ["1.1.40", "1.1.5"],
                "descricoes_contem": ["estoque", "mercadorias para revenda"],
            },
            {
                "nome": "Fornecedores",
                "grupo": "fornecedores",
                "prefixos": ["2.1.10", "2.1.3"],
                "descricoes_contem": ["fornecedor", "fornecedores"],
            },
            {
                "nome": "Tributos a recolher",
                "grupo": "tributos_a_recolher",
                "prefixos": ["2.1.40", "2.1.50.200"],
                "descricoes_contem": ["simples nacional a recolher", "icms a recolher", "iss a recolher", "inss a recolher"],
            },
            {
                "nome": "Folha e pro-labore",
                "grupo": "folha",
                "prefixos": ["2.1.50.100", "4.2.20.100", "4.2.1.01"],
                "descricoes_contem": ["salarios", "ordenados", "pro-labore", "folha de pagamento"],
            },
            {
                "nome": "Receita operacional",
                "grupo": "receita",
                "prefixos": ["3.1.10", "3.1.1"],
                "descricoes_contem": ["receita de venda", "receita de servicos", "servicos prestados"],
            },
            {
                "nome": "Deducoes da receita",
                "grupo": "tributos_sobre_receita",
                "prefixos": ["3.1.20", "3.1.2"],
                "descricoes_contem": ["simples nacional", "deducao da receita", "tributos sobre receita"],
            },
            {
                "nome": "Custos e CMV",
                "grupo": "custos",
                "prefixos": ["4.1"],
                "descricoes_contem": ["cmv", "custo das mercadorias", "custos dos servicos"],
            },
        ],
    }


def build_anexos_defaults() -> dict[str, Any]:
    return {
        "version": "2026.1",
        "anexos": {
            "anexo_i": {
                "nome": "Anexo I",
                "descricao": "Comercio",
                "faixas": [
                    {"limite_superior": 180000, "aliquota": 0.04, "parcela_deduzir": 0},
                    {"limite_superior": 360000, "aliquota": 0.073, "parcela_deduzir": 5940},
                    {"limite_superior": 720000, "aliquota": 0.095, "parcela_deduzir": 13860},
                    {"limite_superior": 1800000, "aliquota": 0.107, "parcela_deduzir": 22500},
                    {"limite_superior": 3600000, "aliquota": 0.143, "parcela_deduzir": 87300},
                    {"limite_superior": 4800000, "aliquota": 0.19, "parcela_deduzir": 378000},
                ],
            },
            "anexo_iii": {
                "nome": "Anexo III",
                "descricao": "Servicos tributados pelo Anexo III ou deslocados pelo Fator R",
                "faixas": [
                    {"limite_superior": 180000, "aliquota": 0.06, "parcela_deduzir": 0},
                    {"limite_superior": 360000, "aliquota": 0.112, "parcela_deduzir": 9360},
                    {"limite_superior": 720000, "aliquota": 0.135, "parcela_deduzir": 17640},
                    {"limite_superior": 1800000, "aliquota": 0.16, "parcela_deduzir": 35640},
                    {"limite_superior": 3600000, "aliquota": 0.21, "parcela_deduzir": 125640},
                    {"limite_superior": 4800000, "aliquota": 0.33, "parcela_deduzir": 648000},
                ],
            },
            "anexo_v": {
                "nome": "Anexo V",
                "descricao": "Servicos sujeitos ao Fator R quando o fator estimado fica abaixo de 28%",
                "faixas": [
                    {"limite_superior": 180000, "aliquota": 0.155, "parcela_deduzir": 0},
                    {"limite_superior": 360000, "aliquota": 0.18, "parcela_deduzir": 4500},
                    {"limite_superior": 720000, "aliquota": 0.195, "parcela_deduzir": 9900},
                    {"limite_superior": 1800000, "aliquota": 0.205, "parcela_deduzir": 17100},
                    {"limite_superior": 3600000, "aliquota": 0.23, "parcela_deduzir": 62100},
                    {"limite_superior": 4800000, "aliquota": 0.305, "parcela_deduzir": 540000},
                ],
            },
        },
    }

