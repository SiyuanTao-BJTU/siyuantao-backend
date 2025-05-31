# app/exceptions.py
from fastapi import HTTPException, status, Request
from fastapi.responses import JSONResponse

class DALError(Exception):
    """Base exception for Data Access Layer errors."""
    def __init__(self, message="Database operation failed", detail=None):
        self.message = message
        self.detail = detail
        super().__init__(self.message)

class NotFoundError(DALError):
    """Raised when a specific resource is not found in the database."""
    def __init__(self, message="Resource not found"):
        super().__init__(message)

class IntegrityError(DALError):
    """Raised when a database integrity constraint is violated (e.g., duplicate unique key)."""
    def __init__(self, message="Integrity constraint violation"):
        super().__init__(message)

# ... 您可以根据业务需求添加更多特定异常，例如 AuthorizationError, ValidationError (for business logic)

class DatabaseError(DALError):
    """Raised for general database errors (e.g., connection issues, query execution failures)."""
    def __init__(self, message="Database error"):
        super().__init__(message)

class EmailSendingError(Exception):
    """Raised when there is an error sending email."""
    def __init__(self, message="Email sending failed", detail=None):
        self.message = message
        self.detail = detail
        super().__init__(self.message)

class AuthenticationError(Exception):
    """Raised when authentication fails."""
    def __init__(self, message="Authentication failed"):
        self.message = message
        super().__init__(self.message)

class ForbiddenError(Exception):
    """Raised when a user is forbidden from accessing a resource or performing an action."""
    def __init__(self, message="Operation forbidden"):
        self.message = message
        super().__init__(self.message)

class PermissionError(Exception):
    """Raised when a user does not have permission to perform an action on a resource."""
    def __init__(self, message="Permission denied"):
        self.message = message
        super().__init__(self.message)

# FastAPI 异常处理器 - 确保将 DAL 异常转换为标准 HTTP 响应
async def not_found_exception_handler(request: Request, exc: NotFoundError):
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={"message": exc.message}
    )

async def integrity_exception_handler(request: Request, exc: IntegrityError):
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT, # Conflict
        content={"message": exc.message}
    )

async def dal_exception_handler(request: Request, exc: DALError):
    # 捕获所有未被更具体处理器捕获的 DAL 错误
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"message": f"An unexpected database error occurred: {exc.message}"}
    )

async def forbidden_exception_handler(request: Request, exc: PermissionError):
    return JSONResponse(
        status_code=status.HTTP_403_FORBIDDEN,
        content={"message": exc.message}
    )

# 映射 SQLSTATE 错误码到自定义异常 (在 dal/base.py 中使用)
SQLSTATE_ERROR_MAP = {
    '23000': IntegrityError, # Integrity Constraint Violation (通用)
    '23001': IntegrityError, # Restrict Violation
    '23502': IntegrityError, # Not Null Violation
    '23503': IntegrityError, # Foreign Key Violation
    '23505': IntegrityError, # Unique Violation
    # 可以在这里添加更具体的 SQL Server 错误码
    # 例如，对于重复键错误，SQL Server 可能是 2627 或 2601
    '2627': IntegrityError, # Unique constraint violation (SQL Server)
    '2601': IntegrityError, # Cannot insert duplicate key (SQL Server)
} 