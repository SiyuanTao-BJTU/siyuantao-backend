# app/dal/base.py
import pyodbc
from app.exceptions import DALError, NotFoundError, IntegrityError, ForbiddenError
from app.dal.exceptions import map_db_exception # Import the new mapping function
from uuid import UUID
import logging
import asyncio # Import asyncio
import functools # Import functools
from typing import List, Dict, Any, Optional, Union
from app.dal.transaction import transaction # Import transaction from its new home

logger = logging.getLogger(__name__)

# --- 通用查询执行器 ---
async def execute_query(
    conn: pyodbc.Connection,
    sql: str,
    params: tuple = None,
    fetchone: bool = False,
    fetchall: bool = False
) -> Optional[Union[Dict[str, Any], List[Dict[str, Any]], int]]:
    """
    Executes a SQL query using the provided database connection.

    Args:
        conn: The pyodbc database connection.
        sql: The SQL query string (can include placeholders for parameters).
        params: A tuple of parameters to substitute into the SQL query.
        fetchone: If True, fetches only the first row.
        fetchall: If True, fetches all rows. (Ignored if fetchone is True)

    Returns:
        A dictionary representing a single row if fetchone is True.
        A list of dictionaries representing multiple rows if fetchall is True.
        The row count if neither fetchone nor fetchall is True (for non-SELECT or when only rowcount is needed).
        None if fetchone is True and no row is found.
    """
    loop = asyncio.get_event_loop()
    cursor = await loop.run_in_executor(None, conn.cursor)

    try:
        await loop.run_in_executor(None, cursor.execute, sql, params if params is not None else ())

        # 遍历所有结果集，直到找到包含数据的结果集或没有更多结果集
        # 存储过程可能返回多个结果集（例如，先UPDATE后SELECT），我们需要获取正确的那个
        result_set_found = False
        while True:
            if cursor.description:
                # 找到包含描述（列信息）的结果集，这意味着有数据或至少是空表结果
                result_set_found = True
                break
            else:
                # 如果没有描述，尝试移动到下一个结果集
                more_results = await loop.run_in_executor(None, cursor.nextset)
                if not more_results:
                    # 没有更多结果集，退出循环
                    break
        
        if not result_set_found:
            # 如果遍历完所有结果集都没有找到有效结果集，则返回 None
            return None

        if fetchone:
            columns = [column[0] for column in cursor.description]
            row = await loop.run_in_executor(None, cursor.fetchone)
            return dict(zip(columns, row)) if row else None
        elif fetchall:
            columns = [column[0] for column in cursor.description]
            rows = await loop.run_in_executor(None, cursor.fetchall)
            return [dict(zip(columns, row)) for row in rows] if rows else []
        else:
            return await loop.run_in_executor(None, lambda: cursor.rowcount) # Return rowcount for non-query operations
    except pyodbc.Error as e:
        logger.error(f"DAL execute_query error: {e} (SQL: {sql}, Params: {params})")
        raise map_db_exception(e) from e
    finally:
        await loop.run_in_executor(None, cursor.close)

async def execute_non_query(conn: pyodbc.Connection, sql: str, params: tuple = ()) -> int:
    """
    Executes a non-query SQL statement (INSERT, UPDATE, DELETE) and returns the row count.

    Args:
        conn: The pyodbc database connection.
        sql: The SQL statement.
        params: A tuple of parameters.

    Returns:
        The number of rows affected.
    """
    loop = asyncio.get_event_loop()
    cursor = await loop.run_in_executor(None, conn.cursor)

    try:
        await loop.run_in_executor(None, cursor.execute, sql, params if params is not None else ())
        return await loop.run_in_executor(None, lambda: cursor.rowcount)
    except pyodbc.Error as e:
        logger.error(f"DAL execute_non_query error: {e} (SQL: {sql}, Params: {params})")
        raise map_db_exception(e) from e
    finally:
        await loop.run_in_executor(None, cursor.close)

# Removed the transaction context manager from base.py as it's now in connection.py
# @asynccontextmanager
# async def transaction(conn: pyodbc.Connection):
#     ...