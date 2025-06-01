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
    cursor = None # Initialize cursor to None
    try:
        # Get cursor from the connection
        # Since conn is now a direct pyodbc.Connection, conn.cursor() is synchronous.
        # We run it in an executor to avoid blocking the event loop.
        cursor = await loop.run_in_executor(None, conn.cursor)
        
        logger.debug(f"Executing SQL: {sql[:200]}... with params: {params}")
        if params:
            await loop.run_in_executor(None, cursor.execute, sql, params)
        else:
            await loop.run_in_executor(None, cursor.execute, sql)

        if fetchone:
            row = await loop.run_in_executor(None, cursor.fetchone)
            if row:
                # Convert row to dictionary (column names as keys)
                columns = [column[0] for column in cursor.description]
                return dict(zip(columns, row))
            return None # No row found
        elif fetchall:
            rows = await loop.run_in_executor(None, cursor.fetchall)
            columns = [column[0] for column in cursor.description]
            return [dict(zip(columns, r)) for r in rows]
        else:
            # For INSERT, UPDATE, DELETE, or SELECT where only rowcount is needed
            # cursor.rowcount is available after execute
            return cursor.rowcount
            
    except pyodbc.Error as e:
        logger.error(f"DAL execute_query error: {e} (SQL: {sql[:200]}..., Params: {params})", exc_info=True)
        # Re-raise the original pyodbc.Error to be handled by the transaction manager or higher-level error handlers
        raise
    except Exception as e:
        logger.error(f"DAL execute_query unexpected error: {e} (SQL: {sql[:200]}..., Params: {params})", exc_info=True)
        raise # Re-raise other unexpected errors
    finally:
        if cursor:
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
    cursor = None # Initialize cursor to None
    try:
        cursor = await loop.run_in_executor(None, conn.cursor)
        logger.debug(f"Executing Non-Query SQL: {sql[:200]}... with params: {params}")
        if params:
            await loop.run_in_executor(None, cursor.execute, sql, params)
        else:
            await loop.run_in_executor(None, cursor.execute, sql)
        
        # For non-query statements, rowcount gives the number of affected rows
        row_count = cursor.rowcount
        # No commit here, transaction is handled by the transaction context manager in get_db_connection
        return row_count

    except pyodbc.Error as e:
        logger.error(f"DAL execute_non_query error: {e} (SQL: {sql[:200]}..., Params: {params})", exc_info=True)
        raise # Re-raise to be handled by transaction manager or higher level
    except Exception as e:
        logger.error(f"DAL execute_non_query unexpected error: {e} (SQL: {sql[:200]}..., Params: {params})", exc_info=True)
        raise
    finally:
        if cursor:
            await loop.run_in_executor(None, cursor.close)

# Removed the transaction context manager from base.py as it's now in connection.py
# @asynccontextmanager
# async def transaction(conn: pyodbc.Connection):
#     ...