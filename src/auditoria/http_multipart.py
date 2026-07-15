from __future__ import annotations

from dataclasses import dataclass
from email import policy
from email.parser import BytesParser
from typing import Any, BinaryIO


@dataclass(frozen=True)
class UploadedFile:
    filename: str
    content: bytes


def read_multipart_form(headers: Any, stream: BinaryIO) -> dict[str, str | UploadedFile]:
    content_type = str(headers.get("Content-Type", "") or "")
    if not content_type.startswith("multipart/form-data"):
        raise ValueError("A API espera multipart/form-data.")

    content_length = int(str(headers.get("Content-Length", "0") or "0"))
    body = stream.read(content_length)
    raw_message = (
        f"Content-Type: {content_type}\r\n"
        "MIME-Version: 1.0\r\n"
        "\r\n"
    ).encode("utf-8") + body

    message = BytesParser(policy=policy.default).parsebytes(raw_message)
    form: dict[str, str | UploadedFile] = {}

    for part in message.iter_parts():
        raw_name = part.get_param("name", header="content-disposition")
        if not isinstance(raw_name, str) or not raw_name:
            continue
        name = raw_name

        raw_payload = part.get_payload(decode=True)
        payload = raw_payload if isinstance(raw_payload, bytes) else b""
        filename = part.get_filename()
        if filename:
            form[name] = UploadedFile(filename=filename, content=payload)
            continue

        charset = part.get_content_charset() or "utf-8-sig"
        form[name] = payload.decode(charset, errors="replace")

    return form
