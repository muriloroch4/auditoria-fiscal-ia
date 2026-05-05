from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum


class RiskLevel(str, Enum):
    BAIXO = "baixo"
    MEDIO = "medio"
    ALTO = "alto"


@dataclass(frozen=True)
class LedgerAccount:
    codigo: str
    conta: str
    grupo: str
    saldo_anterior: Decimal
    debito: Decimal
    credito: Decimal
    saldo_atual: Decimal


@dataclass(frozen=True)
class TrialBalance:
    cliente: str
    periodo: str
    contas: list[LedgerAccount]

    def total_por_grupo(self, grupo: str) -> Decimal:
        return sum((c.saldo_atual for c in self.contas if c.grupo == grupo), Decimal("0"))

    def debito_por_grupo(self, grupo: str) -> Decimal:
        return sum((c.debito for c in self.contas if c.grupo == grupo), Decimal("0"))

    def credito_por_grupo(self, grupo: str) -> Decimal:
        return sum((c.credito for c in self.contas if c.grupo == grupo), Decimal("0"))

    def contas_por_grupo(self, grupo: str) -> list[LedgerAccount]:
        return [c for c in self.contas if c.grupo == grupo]


@dataclass(frozen=True)
class RuleFinding:
    codigo: str
    titulo: str
    nivel: RiskLevel
    pontuacao: int
    descricao: str
    evidencia: dict[str, str] = field(default_factory=dict)
    recomendacao: str = ""


@dataclass(frozen=True)
class AuditResult:
    cliente: str
    periodo: str
    nivel_geral: RiskLevel
    pontuacao_total: int
    achados: list[RuleFinding]
    resumo_metricas: dict[str, str]
    explicacao_pontuacao: list[str]
