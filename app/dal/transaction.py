import pyodbc
import asyncio
from contextlib import asynccontextmanager
from app.exceptions import DALError
import logging
from fastapi import HTTPException

logger = logging.getLogger(__name__)

@asynccontextmanager
async def transaction(conn: pyodbc.Connection):
    """
    一个异步上下文管理器，用于管理数据库事务。
    在进入上下文时，确保连接处于手动提交模式。
    在成功退出上下文时提交事务。
    在发生异常时回滚事务。
    """
    try:
        # Ensure the connection is in manual commit mode if it's from a pool and autocommit is enabled by default
        # For PooledDB connections, conn.autocommit should be False by default, but it's good to be explicit.
        if conn.autocommit:
            conn.autocommit = False

        yield conn
        logger.debug("Transaction: Committing changes.")
        # Use asyncio.to_thread for blocking commit operation
        await asyncio.to_thread(conn.commit)
    except HTTPException:
        logger.debug("Transaction: HTTPException raised, propagating.")
        raise
    except pyodbc.Error as db_exc: # Catch specific database errors
        logger.error(f"Transaction: Rolling back due to database error: {db_exc}", exc_info=True)
        if conn:
            await asyncio.to_thread(conn.rollback)
        raise DALError(f"Database transaction failed: {db_exc}") from db_exc # Wrap and re-raise as DALError
    except Exception as e: # Catch other non-HTTP, non-DB application exceptions
        logger.warning(f"Transaction: Rolling back due to application error: {e}", exc_info=True)
        if conn:
            await asyncio.to_thread(conn.rollback) # Still rollback
        raise e # Re-raise the original application-level exception
 