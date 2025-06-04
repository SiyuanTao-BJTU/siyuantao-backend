# app/main.py
from fastapi import FastAPI, Depends, HTTPException, status, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.encoders import jsonable_encoder
from app.exceptions import (
    NotFoundError, IntegrityError, DALError,
    not_found_exception_handler, integrity_exception_handler, dal_exception_handler,
    forbidden_exception_handler
)

# Import standard logging and dictConfig
import logging
import os
from logging.config import dictConfig

# Import StaticFiles
from fastapi.staticfiles import StaticFiles

# Import uvicorn.logging for potential formatters
try:
    import uvicorn.logging
except ImportError:
    uvicorn = None # Handle case where uvicorn might not be installed in this env

# Import all module routes
from app.routers import users, product_routes, order, evaluation, auth, upload_routes, chat_routes

import sys
import os

# 这将在应用程序启动时打印 Python 解释器路径和模块搜索路径
# 您可以在 uvicorn 启动日志中找到这些信息
print(f"DEBUG: Python executable: {sys.executable}")
print(f"DEBUG: sys.path: {sys.path}")
print(f"DEBUG: Current working directory: {os.getcwd()}")

# Define a comprehensive logging configuration dictionary
LOGGING_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False, # Crucial: Prevents Uvicorn from silencing other loggers
    "formatters": {
        "default": { # Formatter for general application logs
            "()": "uvicorn.logging.DefaultFormatter" if uvicorn and hasattr(uvicorn.logging, "DefaultFormatter") else "logging.Formatter",
            "fmt": "%(levelprefix)s %(asctime)s | %(name)s | %(message)s",
            "datefmt": "%Y-%m-%d %H:%M:%S",
            "use_colors": True if uvicorn and hasattr(uvicorn.logging, "DefaultFormatter") else False,
        },
        "access": { # Formatter for access logs (HTTP requests)
            "()": "uvicorn.logging.AccessFormatter" if uvicorn and hasattr(uvicorn.logging, "AccessFormatter") else "logging.Formatter",
            "fmt": '%(levelprefix)s %(asctime)s | %(client_addr)s | "%(request_line)s" %(status_code)s',
            "datefmt": "%Y-%m-%d %H:%M:%S",
            "use_colors": True if uvicorn and hasattr(uvicorn.logging, "AccessFormatter") else False,
        },
    },
    "handlers": {
        "default": {
            "formatter": "default",
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stderr", # Direct output to stderr
        },
        "access": {
            "formatter": "access",
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stdout", # Direct output to stdout
        },
    },
    "loggers": {
        "uvicorn": { # Uvicorn's root logger
            "handlers": ["default"],
            "level": "INFO",
            "propagate": False, # Do not propagate to root logger
        },
        "uvicorn.error": { # Uvicorn's error messages
            "level": "INFO", # Keep INFO level for important server messages
            "handlers": ["default"],
            "propagate": False,
        },
        "uvicorn.access": { # Uvicorn's HTTP access logs
            "handlers": ["access"],
            "level": "INFO", # Keep INFO level for access logs
            "propagate": False,
        },
        "app": { # Custom application logger
            "handlers": ["default"],
            "level": "DEBUG", # Adjust to desired level (e.g., INFO, WARNING, ERROR)
            "propagate": False,
        },
        "pyodbc": { # Add pyodbc logger
            "handlers": ["default"],
            "level": "WARNING", # Suppress verbose pyodbc debug info
            "propagate": False,
        },
        "DBUtils": { # Add DBUtils logger
            "handlers": ["default"],
            "level": "WARNING", # Suppress verbose DBUtils debug info
            "propagate": False,
        }
    },
    "root": { # Fallback root logger
        "handlers": ["default"],
        "level": "INFO",
    },
}

dictConfig(LOGGING_CONFIG) # Apply the logging configuration

# Get the logger for the application
logger = logging.getLogger("app")

app = FastAPI(
    title="[思源淘] 交大校园二手交易平台 API",
    description="基于 FastAPI 和原生 SQL 构建的后端 API",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

logger.info("FastAPI application instance created.") # Changed from print to logger

logger.info(f"FastAPI app instance created with id: {id(app)}")

# Get allowed origins from environment variable, default to localhost for development
# Example: FRONTEND_DOMAIN="http://localhost:3301,https://yourdeployeddomain.com"
frontend_urls_str = os.getenv("FRONTEND_DOMAIN", "http://localhost:3301")
allowed_origins_list = [url.strip() for url in frontend_urls_str.split(',')]
logger.info(f"CORS allowed origins: {allowed_origins_list}")

# Custom Middleware to log requests
@app.middleware("http")
async def log_requests(request: Request, call_next):
    # Log incoming request
    logger.debug(f"Incoming Request: {request.method} {request.url}")
    try:
        response = await call_next(request)
        logger.debug(f"Outgoing Response: {request.method} {request.url} Status: {response.status_code}")
        return response
    except Exception as e:
        logger.error(f"Request processing failed for {request.method} {request.url}: {e}", exc_info=True)
        raise # Re-raise the exception to be caught by exception handlers

# 注册 CORS 中间件 (生产环境中请限制 allow_origins)
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins_list, # 使用从环境变量加载的列表
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册全局异常处理器
app.add_exception_handler(NotFoundError, not_found_exception_handler)
app.add_exception_handler(IntegrityError, integrity_exception_handler)
app.add_exception_handler(DALError, dal_exception_handler)
app.add_exception_handler(PermissionError, forbidden_exception_handler)
# 对于未捕获的 HTTPException (例如 Pydantic 验证失败)
@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc: HTTPException):
    # 添加更明确的日志，确认此处理器被调用
    logger.error(f"HTTPException caught: {exc.status_code} - {exc.detail}")
    return JSONResponse(
        status_code=exc.status_code,
        content={"message": exc.detail},
    )

# Custom exception handler for Pydantic RequestValidationError
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    # Log the detailed validation errors
    logger.error(f"Validation error: {exc.errors()} for request {request.url}")
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"message": "Validation Error", "details": exc.errors()},
    )

@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    # 捕获所有未被其他特定处理器捕获的通用异常
    logger.error(f"An unhandled exception occurred during request to {request.url}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"message": "Internal Server Error"},
    )

# 注册路由模块
app.include_router(users.router, prefix="/api/v1")
app.include_router(product_routes.router, prefix="/api/v1/products", tags=["Products"])
app.include_router(order.router, prefix="/api/v1/orders", tags=["Orders"])
app.include_router(evaluation.router, prefix="/api/v1/evaluations", tags=["Evaluations"])
app.include_router(auth.router, prefix="/api/v1")
app.include_router(upload_routes.router, prefix="/api/v1")
app.include_router(chat_routes.router, prefix="/api/v1/chat", tags=["Chat"])
# Mount the uploads directory to serve static files
app.mount("/uploads", StaticFiles(directory=os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'uploads'))), name="uploads")
# ... 注册其他模块路由

@app.get("/")
async def root():
    return {"message": "Welcome to the Campus Exchange API!"}

# 您可以添加一些启动和关闭事件 (例如，初始化数据库连接池)
@app.on_event("startup")
async def startup_event():
    logger.info("Application startup event triggered.")
    # Initialize database connection pool
    # try:
    #     initialize_db_pool()
    #     logger.info("Database connection pool initialized successfully during startup.")
    # except DALError as e:
    #     logger.critical(f"Failed to initialize database pool during startup: {e}")
    #     sys.exit(1) # Exit if essential service fails to start

@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Application shutdown event triggered.")
    # Close database connection pool
    # close_db_pool()
    # logger.info("Database connection pool closed successfully during shutdown.")