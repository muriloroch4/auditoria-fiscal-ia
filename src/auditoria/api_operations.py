from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .annual import build_annual_comparison
from .api_helpers import saved_rbt12_context
from .api_payloads import audit_result_to_annual_source, audit_result_to_dashboard_payload
from .audit import run_quarterly_audit
from .http_multipart import UploadedFile
from .parser import read_trial_balance_upload
from .serializers import audit_result_to_dict
from .storage import AuditStorage, file_sha256


@dataclass(frozen=True)
class QuarterlyUploadResult:
    payload: dict[str, Any]
    storage_id: int
    risk_level: str
    score: int
    findings_count: int


def process_quarterly_upload(
    uploaded_file: UploadedFile,
    *,
    cliente: str,
    periodo: str,
    cnpj: str,
    atividade: str,
    regime_tributario: str,
    storage: AuditStorage,
) -> QuarterlyUploadResult:
    balance = read_trial_balance_upload(
        uploaded_file.filename,
        uploaded_file.content,
        cliente=cliente,
        periodo=periodo,
        cnpj=cnpj,
    )
    result = run_quarterly_audit(
        balance,
        regime_tributario=regime_tributario,
        atividade=atividade,
    )
    payload = audit_result_to_dict(result)
    annual_source = audit_result_to_annual_source(result)
    storage_id = storage.save_quarterly_audit(
        result,
        payload,
        annual_source,
        filename=uploaded_file.filename,
        file_hash=file_sha256(uploaded_file.content),
        atividade=atividade,
    )

    rbt12_context = saved_rbt12_context(storage, result.cnpj, result.periodo)
    if rbt12_context.get("dados_suficientes"):
        result = run_quarterly_audit(
            balance,
            regime_tributario=regime_tributario,
            atividade=atividade,
            contexto_rbt12=rbt12_context,
        )
        payload = audit_result_to_dict(result)
        annual_source = audit_result_to_annual_source(result)
        storage_id = storage.save_quarterly_audit(
            result,
            payload,
            annual_source,
            filename=uploaded_file.filename,
            file_hash=file_sha256(uploaded_file.content),
            atividade=atividade,
        )

    return QuarterlyUploadResult(
        payload=audit_result_to_dashboard_payload(result, payload),
        storage_id=storage_id,
        risk_level=result.nivel_geral.value,
        score=result.pontuacao_total,
        findings_count=len(result.achados),
    )


def build_uploaded_annual_payload(
    form: dict[str, str | UploadedFile],
    quarters: list[Any],
    *,
    default_atividade: str,
    regime_tributario: str,
) -> dict[str, Any]:
    annual_sources = []
    for index, quarter in enumerate(quarters, start=1):
        if not isinstance(quarter, dict):
            raise ValueError(f"Trimestre {index}: item inválido no manifest.")
        field = str(quarter.get("field") or f"balancete_{index - 1}")
        uploaded_file = form.get(field)
        if not isinstance(uploaded_file, UploadedFile) or not uploaded_file.content:
            raise ValueError(f"Trimestre {index}: arquivo não encontrado no campo '{field}'.")

        cliente = str(quarter.get("cliente") or "Cliente sem nome")
        periodo = str(quarter.get("periodo") or f"2025-T{index}")
        cnpj = str(quarter.get("cnpj") or "")
        atividade = str(quarter.get("atividade") or default_atividade)

        balance = read_trial_balance_upload(
            uploaded_file.filename,
            uploaded_file.content,
            cliente=cliente,
            periodo=periodo,
            cnpj=cnpj,
        )
        result = run_quarterly_audit(
            balance,
            regime_tributario=regime_tributario,
            atividade=atividade,
        )
        annual_sources.append(audit_result_to_annual_source(result))

    return build_annual_comparison(annual_sources)
