from __future__ import annotations

from typing import Any

from .consultivo import documents_for_code
from .models import RiskLevel, RuleFinding


BALANCETE_SOURCE = "balancete_contabil"


def structured_finding_evidence(finding: RuleFinding) -> dict[str, Any]:
    return structured_evidence(
        finding.codigo,
        finding.evidencia,
        severity=finding.nivel.value,
        source=BALANCETE_SOURCE,
    )


def structured_evidence(
    code: str,
    extracted_fields: dict[str, Any] | None = None,
    *,
    severity: str | None = None,
    source: str = BALANCETE_SOURCE,
) -> dict[str, Any]:
    normalized_code = str(code or "")
    return {
        "fonte_dado": source,
        "confianca": _confidence(normalized_code, severity),
        "necessita_documento": True,
        "documentos_recomendados": list(documents_for_code(normalized_code)),
        "campos_extraidos": {str(key): value for key, value in (extracted_fields or {}).items()},
    }


def _confidence(code: str, severity: str | None) -> str:
    if code.startswith(("SN-COMP", "AN-REC")):
        return "media"
    if code.startswith(("SN-003", "SN-017", "SN-019", "SN-020", "SN-024")):
        return "baixa"
    if severity == RiskLevel.ALTO.value:
        return "media"
    return "media"
