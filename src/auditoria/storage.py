from __future__ import annotations

import datetime
import json
import os
import re
import sqlite3
import unicodedata
from contextlib import contextmanager
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterator

from .models import AuditResult


DB_SCHEMA_VERSION = "1.0.0"


class AuditStorage:
    """SQLite storage for quarterly audit results and annual consolidations."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db_path = str(db_path or os.environ.get("AUDIT_DB_PATH") or default_db_path())
        self._memory_conn: sqlite3.Connection | None = None
        if self.db_path == ":memory:":
            self._memory_conn = sqlite3.connect(self.db_path)
            self._memory_conn.row_factory = sqlite3.Row
            self._memory_conn.execute("PRAGMA foreign_keys = ON")
        else:
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self.init_schema()

    def init_schema(self) -> None:
        with self._connection() as conn:
            conn.executescript(
                """
                PRAGMA foreign_keys = ON;

                CREATE TABLE IF NOT EXISTS companies (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    nome TEXT NOT NULL,
                    cnpj TEXT NOT NULL UNIQUE,
                    cnpj_original TEXT,
                    regime_tributario TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS quarterly_audits (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
                    ano INTEGER NOT NULL,
                    trimestre INTEGER NOT NULL,
                    periodo TEXT NOT NULL,
                    atividade TEXT,
                    arquivo_nome TEXT,
                    arquivo_hash TEXT,
                    risco_geral TEXT,
                    pontuacao_total INTEGER NOT NULL DEFAULT 0,
                    total_regras_acionadas INTEGER NOT NULL DEFAULT 0,
                    summary_json TEXT NOT NULL,
                    annual_source_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(company_id, ano, trimestre)
                );

                CREATE TABLE IF NOT EXISTS annual_audits (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
                    ano INTEGER NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(company_id, ano)
                );
                """
            )

    def save_quarterly_audit(
        self,
        result: AuditResult,
        summary_payload: dict[str, Any],
        annual_source: dict[str, Any],
        *,
        filename: str = "",
        file_hash: str = "",
        atividade: str = "",
    ) -> int:
        ano, trimestre = infer_year_quarter(result.periodo)
        now = _now()

        with self._connection() as conn:
            company_id = self._upsert_company(
                conn,
                nome=result.cliente,
                cnpj=result.cnpj,
                regime_tributario=result.regime_tributario,
                now=now,
            )
            conn.execute(
                """
                INSERT INTO quarterly_audits (
                    company_id, ano, trimestre, periodo, atividade, arquivo_nome, arquivo_hash,
                    risco_geral, pontuacao_total, total_regras_acionadas, summary_json,
                    annual_source_json, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(company_id, ano, trimestre) DO UPDATE SET
                    periodo = excluded.periodo,
                    atividade = excluded.atividade,
                    arquivo_nome = excluded.arquivo_nome,
                    arquivo_hash = excluded.arquivo_hash,
                    risco_geral = excluded.risco_geral,
                    pontuacao_total = excluded.pontuacao_total,
                    total_regras_acionadas = excluded.total_regras_acionadas,
                    summary_json = excluded.summary_json,
                    annual_source_json = excluded.annual_source_json,
                    updated_at = excluded.updated_at
                """,
                (
                    company_id,
                    ano,
                    trimestre,
                    result.periodo,
                    atividade or result.conjunto_regras,
                    filename,
                    file_hash,
                    result.nivel_geral.value,
                    int(result.pontuacao_total),
                    len(result.achados),
                    _json_dumps(summary_payload),
                    _json_dumps(annual_source),
                    now,
                    now,
                ),
            )
            row = conn.execute(
                """
                SELECT id
                FROM quarterly_audits
                WHERE company_id = ? AND ano = ? AND trimestre = ?
                """,
                (company_id, ano, trimestre),
            ).fetchone()
            return int(row["id"])

    def list_quarterly_audits(self, *, cnpj: str = "", ano: int | None = None) -> list[dict[str, Any]]:
        conditions: list[str] = []
        params: list[Any] = []
        if cnpj:
            conditions.append("c.cnpj = ?")
            params.append(normalize_cnpj_key(cnpj))
        if ano is not None:
            conditions.append("q.ano = ?")
            params.append(int(ano))

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        with self._connection() as conn:
            rows = conn.execute(
                f"""
                SELECT
                    q.id, c.nome, c.cnpj_original, c.regime_tributario,
                    q.ano, q.trimestre, q.periodo, q.atividade, q.arquivo_nome,
                    q.arquivo_hash, q.risco_geral, q.pontuacao_total,
                    q.total_regras_acionadas, q.created_at, q.updated_at
                FROM quarterly_audits q
                JOIN companies c ON c.id = q.company_id
                {where}
                ORDER BY c.nome, q.ano, q.trimestre, q.updated_at
                """,
                params,
            ).fetchall()

        return [_quarter_row_to_dict(row) for row in rows]

    def annual_sources(self, *, cnpj: str, ano: int) -> list[dict[str, Any]]:
        with self._connection() as conn:
            rows = conn.execute(
                """
                SELECT q.annual_source_json
                FROM quarterly_audits q
                JOIN companies c ON c.id = q.company_id
                WHERE c.cnpj = ? AND q.ano = ?
                ORDER BY q.trimestre
                """,
                (normalize_cnpj_key(cnpj), int(ano)),
            ).fetchall()
        return [json.loads(row["annual_source_json"]) for row in rows]

    def save_annual_audit(self, *, cnpj: str, ano: int, payload: dict[str, Any]) -> int:
        identificacao = payload.get("identificacao", {})
        now = _now()
        with self._connection() as conn:
            company_id = self._upsert_company(
                conn,
                nome=str(identificacao.get("cliente") or "Cliente sem nome"),
                cnpj=cnpj or str(identificacao.get("cnpj") or ""),
                regime_tributario=str(identificacao.get("regime_tributario") or ""),
                now=now,
            )
            conn.execute(
                """
                INSERT INTO annual_audits (company_id, ano, payload_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(company_id, ano) DO UPDATE SET
                    payload_json = excluded.payload_json,
                    updated_at = excluded.updated_at
                """,
                (company_id, int(ano), _json_dumps(payload), now, now),
            )
            row = conn.execute(
                "SELECT id FROM annual_audits WHERE company_id = ? AND ano = ?",
                (company_id, int(ano)),
            ).fetchone()
            return int(row["id"])

    def latest_annual_audit(self, *, cnpj: str, ano: int) -> dict[str, Any] | None:
        with self._connection() as conn:
            row = conn.execute(
                """
                SELECT a.payload_json
                FROM annual_audits a
                JOIN companies c ON c.id = a.company_id
                WHERE c.cnpj = ? AND a.ano = ?
                ORDER BY a.updated_at DESC
                LIMIT 1
                """,
                (normalize_cnpj_key(cnpj), int(ano)),
            ).fetchone()
        return json.loads(row["payload_json"]) if row else None

    def _upsert_company(
        self,
        conn: sqlite3.Connection,
        *,
        nome: str,
        cnpj: str,
        regime_tributario: str,
        now: str,
    ) -> int:
        cnpj_key = normalize_cnpj_key(cnpj, fallback_name=nome)
        conn.execute(
            """
            INSERT INTO companies (nome, cnpj, cnpj_original, regime_tributario, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(cnpj) DO UPDATE SET
                nome = excluded.nome,
                cnpj_original = excluded.cnpj_original,
                regime_tributario = excluded.regime_tributario,
                updated_at = excluded.updated_at
            """,
            (nome or "Cliente sem nome", cnpj_key, cnpj or "", regime_tributario or "", now, now),
        )
        row = conn.execute("SELECT id FROM companies WHERE cnpj = ?", (cnpj_key,)).fetchone()
        return int(row["id"])

    def _connect(self) -> sqlite3.Connection:
        if self._memory_conn is not None:
            return self._memory_conn
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        conn = self._connect()
        try:
            with conn:
                yield conn
        finally:
            if self._memory_conn is None:
                conn.close()


def default_db_path() -> Path:
    return Path(__file__).resolve().parents[2] / "data" / "auditoria.sqlite"


def normalize_cnpj_key(cnpj: str, fallback_name: str = "") -> str:
    digits = re.sub(r"\D+", "", cnpj or "")
    if digits:
        return digits
    fallback = re.sub(r"[^a-z0-9]+", "-", (fallback_name or "sem-cnpj").lower()).strip("-")
    return f"SEM-CNPJ:{fallback or 'cliente'}"


_MONTH_ALIASES = {
    "jan": 1,
    "janeiro": 1,
    "fev": 2,
    "fevereiro": 2,
    "mar": 3,
    "marco": 3,
    "abr": 4,
    "abril": 4,
    "mai": 5,
    "maio": 5,
    "jun": 6,
    "junho": 6,
    "jul": 7,
    "julho": 7,
    "ago": 8,
    "agosto": 8,
    "set": 9,
    "setembro": 9,
    "out": 10,
    "outubro": 10,
    "nov": 11,
    "novembro": 11,
    "dez": 12,
    "dezembro": 12,
}

_ORDINAL_QUARTERS = {
    "primeiro": 1,
    "segundo": 2,
    "terceiro": 3,
    "quarto": 4,
}


def infer_year_quarter(periodo: str) -> tuple[int, int]:
    text = str(periodo or "")
    normalized = _normalize_period_text(text)

    year_match = re.search(r"(?:19|20)\d{2}", text)
    year = int(year_match.group(0)) if year_match else datetime.datetime.now().year

    quarter_match = re.search(r"\b(?:T|Q)\s*([1-4])\b", normalized)
    if not quarter_match:
        quarter_match = re.search(r"\b([1-4])\s*(?:T|TRI|TRIM|TRIMESTRE)\b", normalized)
    if not quarter_match:
        quarter_match = re.search(r"\b(?:TRI|TRIM|TRIMESTRE)\s*([1-4])\b", normalized)
    if quarter_match:
        return year, int(quarter_match.group(1))

    normalized_lower = normalized.lower()
    for ordinal, quarter in _ORDINAL_QUARTERS.items():
        if re.search(rf"\b{ordinal}\s+trimestre\b", normalized_lower):
            return year, quarter

    dates = re.findall(r"(\d{2})/(\d{2})/((?:19|20)\d{2})", text)
    if dates:
        month = int(dates[-1][1])
        return int(dates[-1][2]), ((month - 1) // 3) + 1

    months = [
        month
        for token in re.findall(r"\b[a-z]{3,9}\b", normalized_lower)
        for month in [_MONTH_ALIASES.get(token)]
        if month is not None
    ]
    if months:
        return year, ((months[-1] - 1) // 3) + 1

    return year, 0


def _normalize_period_text(value: str) -> str:
    text = unicodedata.normalize("NFKD", value or "")
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = text.upper().replace("º", "O").replace("°", "O")
    text = re.sub(r"([1-4])O\s+TRIM", r"\1 TRIM", text)
    text = re.sub(r"([TQ])([1-4])", r"\1 \2", text)
    text = re.sub(r"([1-4])([TQ])", r"\1 \2", text)
    text = re.sub(r"[^A-Z0-9/]+", " ", text)
    return " ".join(text.split())


def file_sha256(content: bytes) -> str:
    import hashlib

    return hashlib.sha256(content).hexdigest()


def _quarter_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    trimestre = int(row["trimestre"])
    return {
        "id": row["id"],
        "empresa": row["nome"],
        "cnpj": row["cnpj_original"],
        "regime_tributario": row["regime_tributario"],
        "ano": row["ano"],
        "trimestre": f"T{trimestre}" if trimestre in {1, 2, 3, 4} else "[VERIFICAR: trimestre]",
        "periodo": row["periodo"],
        "atividade": row["atividade"],
        "arquivo_nome": row["arquivo_nome"],
        "arquivo_hash": row["arquivo_hash"],
        "risco_geral": row["risco_geral"],
        "pontuacao_total": row["pontuacao_total"],
        "total_regras_acionadas": row["total_regras_acionadas"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _json_dumps(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=_json_default)


def _json_default(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def _now() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")
