# common/responses/responses.py
from fastapi.responses import JSONResponse, Response
from typing import Any, Optional

error_code_dict = {
    400: "Invalid request parameters",
    401: "Authentication failed",
    403: "Permission denied",
    404: "Resource not found",
    500: "Internal server error",
    422: "Validation error",
    503: "Service unavailable",
    999: "Unknown error",
}

def success_response(data: Any, message: str = "Success", status_code: int = 200) -> dict:
    return JSONResponse(
        status_code=status_code,
        content={
            "err_code": 0,
            "code": status_code,
            "message": message,
            "data": data
        }
    )


def error_response(code: int = 500, message: Optional[str] = None, data: Optional[Any] = None) -> dict:
    if message is None:
        message = error_code_dict.get(code, "未知错误")  # 默认消息为"未知错误"
    return JSONResponse(
        status_code=200,
        content={
            "err_code": 1,
            "code": code,
            "message": message,
            "data": data
        }
    )

def base_response(code: int,message: Optional[Any] = None, data: Optional[Any] = None) -> dict:
    return JSONResponse(
        status_code=200,
        content={
            "err_code": 0,
            "code": code,
            "message": message,
            "data": data
        }
    )