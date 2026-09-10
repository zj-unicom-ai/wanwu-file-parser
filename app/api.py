"""API routes + response envelope."""
from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.config import settings
from app.services.file_convert import Doc2mdNotAvailable, OfficeConversionNotSupported
from app.services.parser import (
    ParseRequest,
    is_allowed_filename,
    is_path_traversal,
    parse_document,
)
from app.utils.logging_utils import get_trace_id, set_trace_id

router = APIRouter(prefix="/rag", tags=["rag"])


class ParseResponse(BaseModel):
    """Envelope for all API responses."""

    code: str = Field(..., description="HTTP-style code string, e.g. '200'")
    status: str = Field(..., description="success | failed")
    message: str = ""
    content: str = ""
    json_content: str = ""
    trace_id: str = ""
    version: str = ""
    prefix_image_url: str = ""


def _make_response(
    *,
    code: str,
    status: str,
    message: str = "",
    content: str = "",
    json_content: str = "",
    prefix_image_url: str = "",
    status_code: int = 200,
) -> JSONResponse:
    body = ParseResponse(
        code=code,
        status=status,
        message=message,
        content=content,
        json_content=json_content,
        trace_id=get_trace_id(),
        version=settings.version,
        prefix_image_url=prefix_image_url or settings.prefix_image_url,
    )
    return JSONResponse(status_code=status_code, content=body.model_dump())


@router.get("/health")
def health_check() -> dict:
    return {"code": "200", "status": "healthy", "service": "wanwu-file-parser"}


@router.post("/model_parser_file")
async def model_parser_file(
    file: UploadFile = File(...),
    file_name: Optional[str] = Form(None),
    extract_image: str = Form("False"),
    extract_image_content: int = Form(0),
    return_json: str = Form("False"),
) -> JSONResponse:
    if not file.filename or not is_allowed_filename(file.filename):
        return _make_response(
            code="400", status="failed", message="上传的文件类型错误", status_code=400
        )

    name = file_name or file.filename
    if not is_allowed_filename(name):
        return _make_response(
            code="400", status="failed", message="上传的文件扩展名错误", status_code=400
        )
    if is_path_traversal(name):
        return _make_response(
            code="400", status="failed", message="文件名包含非法字符: ..或/或\\", status_code=400
        )

    try:
        file_bytes = await file.read()
    except Exception as exc:  # noqa: BLE001
        return _make_response(
            code="400", status="failed", message=f"读取文件失败: {exc}", status_code=400
        )

    req = ParseRequest(
        file_bytes=file_bytes,
        file_name=name,
        extract_image=extract_image.strip().lower() in ("true", "1"),
        extract_image_content=int(extract_image_content),
        return_json=return_json.strip().lower() == "true",
    )

    try:
        md, json_content, prefix = parse_document(req)
    except (OfficeConversionNotSupported, Doc2mdNotAvailable) as exc:
        # Expected client error: this backend can't ingest the Office format.
        # Surface a 400 with a clear hint (no need to log a stack trace).
        return _make_response(
            code="400", status="failed", message=str(exc), status_code=400
        )
    except Exception as exc:  # noqa: BLE001 — top-level guard returns 500
        import traceback

        from app.utils.logging_utils import setup_logger

        logger = setup_logger(__name__, "./logs/app.log")
        logger.error(
            "parse failed. trace_id=%s, exception=%s, stack=%s",
            get_trace_id(),
            exc,
            traceback.format_exc(),
        )
        return _make_response(
            code="500", status="failed", message=str(exc), status_code=500
        )

    return _make_response(
        code="200",
        status="success",
        message="文档处理完成",
        content=md,
        json_content=json_content,
        prefix_image_url=prefix,
    )


async def trace_id_middleware(request: Request, call_next):
    """Assign a per-request trace id and expose it in the response header."""
    set_trace_id(str(uuid.uuid4()))
    response = await call_next(request)
    response.headers["X-Trace-Id"] = get_trace_id()
    return response


__all__ = ["router", "trace_id_middleware", "ParseResponse", "HTTPException"]
