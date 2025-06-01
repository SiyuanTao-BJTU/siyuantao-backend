# app/dal/base.py
import pyodbc
from app.exceptions import DALError, NotFoundError, IntegrityError, ForbiddenError
from app.dal.exceptions import map_db_exception # Import the new mapping function
from uuid import UUID
import logging
import asyncio # Import asyncio
import functools # Import functools
from typing import List, Dict, Any, Optional
from app.dal.transaction import transaction # Import transaction from its new home

logger = logging.getLogger(__name__)

# --- 通用查询执行器 ---
async def execute_query(
    conn: pyodbc.Connection,
    sql: str,
    params: tuple = None,
    fetchone: bool = False,
    fetchall: bool = False
) -> Optional[Dict[str, Any] | List[Dict[str, Any]] | int]:
    """
    通用 SQL 查询执行器。
    在线程池中异步执行同步数据库操作，将数据库结果转换为 Python 字典，并处理异常。
    :param conn: 数据库连接对象 (通过 FastAPI Depends 注入)
    :param sql: SQL 语句或存储过程调用字符串
    :param params: SQL 参数元组
    :param fetchone: 是否只获取一行结果 (返回 dict 或 None)
    :param fetchall: 是否获取所有结果 (返回 dict 列表)
    :return: 字典列表、单个字典、受影响的行数或 None
    """
    loop = asyncio.get_event_loop()

    # 在线程池中获取游标，因为 conn.cursor() 是阻塞的同步操作
    cursor = await loop.run_in_executor(None, conn.cursor)

    try:
        logger.debug(f"Executing SQL: {sql} with params: {params}")

        # 转换 UUID 对象为字符串，因为 pyodbc 可能不支持直接绑定 UUID 对象
        processed_params = []
        if params:
            for p in params:
                if isinstance(p, UUID):
                    processed_params.append(str(p))
                else:
                    processed_params.append(p)
            processed_params = tuple(processed_params)
        else:
            processed_params = None

        # 在线程池中执行 SQL 语句 (cursor.execute 是同步操作)
        if processed_params is not None:
            await loop.run_in_executor(None, functools.partial(cursor.execute, sql, processed_params))
        else:
            await loop.run_in_executor(None, functools.partial(cursor.execute, sql))

        if fetchone:
            # 在线程池中获取单行结果 (cursor.fetchone 是同步操作)
            row = await loop.run_in_executor(None, cursor.fetchone)
            if row:
                # 将 pyodbc Row 对象转换为字典
                columns = await loop.run_in_executor(None, lambda: [column[0] for column in cursor.description])
                result_dict = dict(zip(columns, row))
                return result_dict if result_dict else None # 返回字典或 None

            return None # No rows found

        elif fetchall:
            # 在线程池中获取所有结果 (cursor.fetchall 是同步操作)
            rows = await loop.run_in_executor(None, cursor.fetchall)
            if rows:
                columns = await loop.run_in_executor(None, lambda: [column[0] for column in cursor.description])
                results_list = []
                for row in rows:
                     result_dict = dict(zip(columns, row))
                     results_list.append(result_dict)
                return results_list

            return [] # Return empty list if no rows found

        else:
            # 对于 INSERT, UPDATE, DELETE 等非 SELECT 语句，返回受影响的行数
            # 在线程池中获取 rowcount (cursor.rowcount 是同步操作)
            rowcount = await loop.run_in_executor(None, lambda: cursor.rowcount)
            return rowcount # 返回受影响的行数


    except pyodbc.Error as e:
        # Use the new mapping function for pyodbc.Error
        raise map_db_exception(e) from e

    except Exception as e:
        # Catch other unexpected exceptions and wrap them in DALError
        logger.error(f"Unexpected error executing SQL: {sql} - {e}")
        raise DALError(f"An unexpected database error occurred: {e}") from e

    finally:
        # In-executor cursor close
        if 'cursor' in locals() and cursor:
            await loop.run_in_executor(None, cursor.close)
        # 注意：连接不在此处关闭，由依赖注入管理其生命周期

        
# TODO: Transaction context manager might also need similar async/sync handling

# 事务上下文管理器 (用于涉及多个 DAL 操作的原子性)
from contextlib import asynccontextmanager
def transaction(conn: pyodbc.Connection):
    @asynccontextmanager
    async def _transaction_context():
        try:
            yield conn
            await asyncio.get_event_loop().run_in_executor(None, conn.commit)
        except Exception as e:
            await asyncio.get_event_loop().run_in_executor(None, conn.rollback)
            raise
    return _transaction_context()


async def execute_non_query(conn: pyodbc.Connection, sql: str, params: tuple = ()) -> int:
    """
    Executes a SQL non-query (INSERT, UPDATE, DELETE) with the given parameters asynchronously.
    Returns the number of rows affected.
    """
    loop = asyncio.get_event_loop()
    cursor = None
    try:
        cursor = await loop.run_in_executor(None, conn.cursor)
        logger.debug(f"Executing non-query SQL: {sql} with params: {params}")

        processed_params = []
        if params:
            for p in params:
                if isinstance(p, UUID):
                    processed_params.append(str(p))
                else:
                    processed_params.append(p)
            processed_params = tuple(processed_params)
        else:
            processed_params = None

        if processed_params is not None:
            await loop.run_in_executor(None, functools.partial(cursor.execute, sql, processed_params))
        else:
            await loop.run_in_executor(None, functools.partial(cursor.execute, sql))

    except pyodbc.Error as e:
        await loop.run_in_executor(None, conn.rollback)
        logger.error(f"Database error executing non-query SQL: {sql} - {e}")
        # Use the new mapping function for pyodbc.Error
        raise map_db_exception(e) from e
    except Exception as e:
        await loop.run_in_executor(None, conn.rollback)
        logger.error(f"An unexpected error occurred during non-query execution: {e}")
        raise DALError(f"An unexpected error occurred during non-query execution: {e}") from e
    finally:
        if cursor:
            await loop.run_in_executor(None, cursor.close)