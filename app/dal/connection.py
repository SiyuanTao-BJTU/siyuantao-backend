# app/dal/connection.py
from app.exceptions import DALError, InternalServerError

import pyodbc
from app.config import settings
import logging
import asyncio
from app.dal.transaction import transaction
from fastapi import Request, HTTPException
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)

# This is the dependency that will be used by FastAPI routes
async def get_db_connection(request: Request):
    conn = None
    try:
        conn_str = (
            f"DRIVER={settings.ODBC_DRIVER};"
            f"SERVER={settings.DATABASE_SERVER};"
            f"DATABASE={settings.DATABASE_NAME};"
            f"UID={settings.DATABASE_UID};"
            f"PWD={settings.DATABASE_PWD}"
        )

        connect_kwargs = settings.PYODBC_PARAMS

        raw_conn = await asyncio.to_thread(lambda: pyodbc.connect(conn_str, **connect_kwargs))
        logger.debug("Direct database connection obtained.")

        # 移除事务管理器，直接yield原始连接
        conn = raw_conn
        yield conn

    except HTTPException as http_exc:
        logger.warning(f"HTTPException propagated during DB connection/transaction: {http_exc.status_code} - {http_exc.detail}")
        raise http_exc
    except pyodbc.Error as db_exc:
        logger.error(f"Database connection or operation error: {db_exc}", exc_info=True)
        raise DALError(f"数据库操作失败: {db_exc}") from db_exc
    except Exception as e:
        logger.error(f"An unexpected error occurred during database setup/yield: {str(e)}", exc_info=True)
        if isinstance(e, HTTPException):
            raise e
        raise InternalServerError(f"An unexpected error occurred: {str(e)}") from e
    finally:
        logger.debug("get_db_connection finalization.")

# Dependency to get the UserDAL instance
# This should be defined where UserDAL is available, e.g., in app.dependencies
# For now, keep it here if it's a standalone DAL module, or move to where UserDAL is defined.
# from app.dal.user_dal import UserDAL 
# def get_user_dal(conn: pyodbc.Connection = Depends(get_db_connection)) -> UserDAL:
#     return UserDAL(conn)

import asyncio
from app.exceptions import DALError

# Database connection pool (simulated with direct connections for now)
# In a production environment, use a proper connection pool like pyodbc.pooling.ConnectionPool 