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

    # Convert UUID objects in params to their string representation
    # and ensure they are properly cast/converted in the SQL if needed.
    # This assumes that SQL Server's UNIQUEIDENTIFIER will accept string literals.
    # For the `?` placeholder, pyodbc should handle the string conversion correctly.
    processed_params = []
    if params:
        for p in params:
            if isinstance(p, UUID):
                processed_params.append(str(p))  # Convert UUID to string
            else:
                processed_params.append(p)
    
    # log_params = ", ".join([f"{p} (Type: {type(p)})" for p in processed_params])
    # logger.debug(f"Executing SQL: {sql}... with params: ({log_params})")
    logger.debug(f"Executing SQL: {sql}... with params: {processed_params}")

    try:
        await loop.run_in_executor(None, cursor.execute, sql, tuple(processed_params))
        
        if fetchone:
            row = await loop.run_in_executor(None, cursor.fetchone)
            return dict(zip([column[0] for column in cursor.description], row)) if row else None
        elif fetchall:
            rows = await loop.run_in_executor(None, cursor.fetchall)
            columns = [column[0] for column in cursor.description]
            return [dict(zip(columns, row)) for row in rows]
        else: # For non-query operations, return rowcount (handled by execute_non_query mostly)
            return await loop.run_in_executor(None, lambda: cursor.rowcount)
    except pyodbc.ProgrammingError as e:
        logger.error(f"DAL execute_query error: {e} (SQL: {sql}..., Params: {processed_params})")
        raise map_db_exception(e) from e
    except Exception as e:
        logger.error(f"An unexpected error occurred during DAL execute_query: {e}", exc_info=True)
        raise DatabaseError(f"An unexpected database error occurred: {e}") from e
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

    processed_params = []
    if params:
        for p in params:
            if isinstance(p, UUID):
                processed_params.append(str(p)) # Convert UUID to string
            else:
                processed_params.append(p)
    
    logger.debug(f"Executing SQL (non-query): {sql}... with params: {processed_params}")

    try:
        await loop.run_in_executor(None, cursor.execute, sql, tuple(processed_params))
        rowcount = await loop.run_in_executor(None, lambda: cursor.rowcount)
        return rowcount
    except pyodbc.ProgrammingError as e:
        logger.error(f"DAL execute_non_query error: {e} (SQL: {sql}..., Params: {processed_params})")
        raise map_db_exception(e) from e
    except Exception as e:
        logger.error(f"An unexpected error occurred during DAL execute_non_query: {e}", exc_info=True)
        raise DatabaseError(f"An unexpected database error occurred: {e}") from e
    finally:
        await loop.run_in_executor(None, cursor.close)

# Removed the transaction context manager from base.py as it's now in connection.py
# @asynccontextmanager
# async def transaction(conn: pyodbc.Connection):
#     ...