# app/main.py
from fastapi import FastAPI, Depends, HTTPException, status, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.encoders import jsonable_encoder
from app.exceptions import (
    NotFoundError, IntegrityError, DALError,
    not_found_exception_handler, integrity_exception_handler, dal_exception_handler
)

# Import standard logging and dictConfig
import logging
from logging.config import dictConfig

# Import StaticFiles
from fastapi.staticfiles import StaticFiles

# Import uvicorn.logging for potential formatters
try:
    import uvicorn.logging
except ImportError:
    uvicorn = None # Handle case where uvicorn might not be installed in this env

# 导入所有模块路由
from app.routers import users, auth # 暂时只导入已存在的路由
from app.routers import users, auth, order # 暂时只导入已存在的路由
from app.routers import evaluation # 新增：导入评价路由
from app.routers import product_routes  # 添加商品路由
# from app.routers import  orders # 这些文件后面会创建
from app.routers import upload_routes # 导入图片上传路由
# from app.routers import products, orders # 这些文件后面会创建

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
        "access": { # Formatter for Uvicorn's access logs
            "()": "uvicorn.logging.AccessFormatter" if uvicorn and hasattr(uvicorn.logging, "AccessFormatter") else "logging.Formatter",
            "fmt": '%(levelprefix)s %(asctime)s | %(name)s | %(client_addr)s - "%(request_line)s" %(status_code)s',
            "datefmt": "%Y-%m-%d %H:%M:%S",
            "use_colors": True if uvicorn and hasattr(uvicorn.logging, "AccessFormatter") else False,
        },
    },
    "handlers": {
        "default": { # Handler for general logs (e.g., to stderr)
            "formatter": "default",
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stderr", # Directs to standard error stream
        },
        # Add a file handler if you need logs written to a file in production
        # "file": {
        #     "formatter": "default",
        #     "class": "logging.FileHandler",
        #     "filename": "app.log",
        #     "encoding": "utf-8",
        # },
        "access": { # Handler for access logs (e.g., to stdout)
            "formatter": "access",
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stdout", # Directs to standard output stream
        },
    },
    "loggers": {
        "": { # Root logger: catches logs from any unconfigured logger
            "handlers": ["default"], # Send root logs to the default handler
            "level": "INFO", # Default level
            "propagate": False,
        },
        "app": { # Logger specifically for your application code (e.g., app.main, app.routers)
             "handlers": ["default"], # Send app logs to the default handler
             "level": "DEBUG", # Set application logger to DEBUG for verbose output
             "propagate": False,
        },
        "uvicorn.error": { # Uvicorn's internal error logger
            "level": "INFO",
            "handlers": ["default"],
            "propagate": False,
        },
        "uvicorn.access": { # Uvicorn's HTTP access logger
            "level": "INFO",
            "handlers": ["access"],
            "propagate": False,
        },
    },
}

# Apply the configuration as early as possible
dictConfig(LOGGING_CONFIG)

# Get the logger for this module (app.main)
logger = logging.getLogger(__name__)


app = FastAPI(
    title="[思源淘] 交大校园二手交易平台 API",
    description="基于 FastAPI 和原生 SQL 构建的后端 API",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

logger.info("FastAPI application instance created.") # Changed from print to logger

logger.info(f"FastAPI app instance created with id: {id(app)}")

# Custom Middleware to log requests
@app.middleware("http")
async def log_requests(request: Request, call_next):
    logger.debug(f"Middleware: Request received for path: {request.url.path}")
    response = await call_next(request)
    logger.debug(f"Middleware: Response status code: {response.status_code} for path: {request.url.path}")
    return response

# 注册 CORS 中间件 (生产环境中请限制 allow_origins)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # 生产环境请限制为您的前端域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册全局异常处理器
app.add_exception_handler(NotFoundError, not_found_exception_handler)
app.add_exception_handler(IntegrityError, integrity_exception_handler)
app.add_exception_handler(DALError, dal_exception_handler)
# 对于未捕获的 HTTPException (例如 Pydantic 验证失败)
@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc: HTTPException):
    logger.error(f"HTTPException caught by global handler: Status {exc.status_code}, Detail: {exc.detail}, Headers: {exc.headers}")
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
        headers=exc.headers
    )

# Custom exception handler for Pydantic RequestValidationError
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    # Log the detailed validation errors
    logger.error(f"RequestValidationError caught for URL: {request.url}. Detail: {exc.errors()}")
    # Return a standard 422 response with validation details
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=jsonable_encoder({"detail": exc.errors()}),
    )


# 注册路由模块
app.include_router(users.router, prefix="/api/v1")
app.include_router(product_routes.router, prefix="/api/v1/products", tags=["Products"])  # 注册商品路由
# app.include_router(products.router, prefix="/api/v1/products", tags=["Products"]) # 暂时注释掉未创建的路由
# app.include_router(orders.router, prefix="/api/v1/orders", tags=["Orders"]) # 暂时注释掉未创建的路由
app.include_router(auth.router, prefix="/api/v1")
# ... 注册其他模块路由

@app.get("/")
async def root():
    return {"message": "Welcome to the Campus Exchange API!"}

# 您可以添加一些启动和关闭事件 (例如，初始化数据库连接池)
@app.on_event("startup")
async def startup_event():
    logger.info("Application startup...") # Changed from print to logger
    # 可以在这里做一些数据库连接池初始化等操作

@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Application shutdown...") # Changed from print to logger
    # 可以在这里关闭数据库连接池等