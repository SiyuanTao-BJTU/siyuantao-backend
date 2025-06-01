# app/dal/connection.py
from app.exceptions import DALError, InternalServerError

import pyodbc
from app.config import settings # Re-import settings to get connection string components
import logging
import asyncio # Keep asyncio for `to_thread` if we wrap `pyodbc.connect`
from app.dal.transaction import transaction # Keep the transaction context manager
# from app.core.db import get_pooled_connection # Comment out or remove
from fastapi import Request, HTTPException # Add HTTPException
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)

# This is the dependency that will be used by FastAPI routes
async def get_db_connection(request: Request):
    conn = None
    try:
        conn_str = (
            f"DRIVER={{{settings.ODBC_DRIVER}}};"
            f"SERVER={settings.DATABASE_SERVER};"
            f"DATABASE={settings.DATABASE_NAME};"
            f"UID={settings.DATABASE_UID};"
            f"PWD={settings.DATABASE_PWD};"
            "Trusted_Connection=no;"
            "Encrypt=yes;"
            "TrustServerCertificate=yes;"
            "Connection Timeout=30;"
        )
        # Establish the raw connection
        raw_conn = await asyncio.to_thread(pyodbc.connect, conn_str, autocommit=False)
        logger.debug("Raw database connection established.")

        # Use the transaction context manager
        async with transaction(raw_conn) as transactional_conn:
            conn = transactional_conn # The connection to be used for operations
            yield conn # Yield the connection for the route handler

    except HTTPException as http_exc:
        logger.warning(f"HTTPException propagated during DB connection/transaction: {http_exc.status_code} - {http_exc.detail}")
        # No explicit rollback here, transaction context manager handles it if exception occurs within its block
        raise http_exc
    except pyodbc.Error as db_exc:
        logger.error(f"Database connection or operation error: {db_exc}", exc_info=True)
        # No explicit rollback here, transaction context manager handles it
        raise DALError(f"Database operation failed: {db_exc}") from db_exc # Wrap for consistent error type
    except Exception as e:
        logger.error(f"An unexpected error occurred during database setup/yield: {str(e)}", exc_info=True)
        if isinstance(e, HTTPException):
            raise e
        # No explicit rollback here, transaction context manager handles it
        raise InternalServerError(f"An unexpected error occurred: {str(e)}") from e
    finally:
        # The 'conn' here refers to the 'transactional_conn' if successfully yielded.
        # If an error occurred before 'yield', 'conn' might be None or 'raw_conn'
        # The transaction context manager closes 'raw_conn' if it was yielded from it.
        # If 'raw_conn' was established but the transaction context manager failed to enter or an error occurred before yield,
        # 'raw_conn' might still need closing.
        # However, the `transaction` context manager's `finally` block should handle the rollback/close of `raw_conn` if an error occurs *within* the `async with transaction(...)` block.
        # If error occurs *before* `async with transaction(...)` enters, then raw_conn needs to be closed here.

        # The current structure of the transaction manager means it will handle raw_conn's closure
        # if the `yield conn` within `transaction` is reached.
        # If `pyodbc.connect` fails, `raw_conn` is never assigned.
        # If `transaction()` call itself fails before yielding, its finally block should clean up `raw_conn`.
        logger.debug("get_db_connection finalization.")
        # No explicit close here, assuming the transaction context manager handles the underlying raw_conn closure correctly.
        # If 'raw_conn' was created but 'transaction' context manager failed before its own finally block,
        # then 'raw_conn' could be leaked. Let's ensure `transaction` always closes the connection it was given.


@asynccontextmanager
async def transaction(conn_to_manage: pyodbc.Connection): # Renamed parameter for clarity
    """
    An async context manager to manage database transactions on a given connection.
    It ensures the connection is in manual commit mode, commits on successful exit,
    and rolls back on exception. It also ensures the connection is closed in its finally block.
    """
    try:
        if conn_to_manage.autocommit:
            conn_to_manage.autocommit = False
        logger.debug(f"Transaction started on connection ID: {id(conn_to_manage)}")
        yield conn_to_manage
        logger.debug(f"Transaction successful, committing changes for connection ID: {id(conn_to_manage)}.")
        await asyncio.to_thread(conn_to_manage.commit)
    except HTTPException as http_exc:
        logger.warning(f"Transaction: HTTPException ({http_exc.status_code}) for conn ID {id(conn_to_manage)}, rolling back and propagating.")
        if conn_to_manage and not conn_to_manage.closed:
            await asyncio.to_thread(conn_to_manage.rollback)
        raise http_exc
    except pyodbc.Error as db_exc:
        logger.error(f"Transaction: pyodbc.Error for conn ID {id(conn_to_manage)}, rolling back: {db_exc}", exc_info=True)
        if conn_to_manage and not conn_to_manage.closed:
            await asyncio.to_thread(conn_to_manage.rollback)
        raise DALError(f"Database transaction failed: {db_exc}") from db_exc
    except Exception as e:
        logger.error(f"Transaction: Unexpected error for conn ID {id(conn_to_manage)}, rolling back: {str(e)}", exc_info=True)
        if conn_to_manage and not conn_to_manage.closed:
            await asyncio.to_thread(conn_to_manage.rollback)
        if isinstance(e, HTTPException):
            raise e
        raise DALError(f"An unexpected error occurred within transaction: {str(e)}") from e
    finally:
        # Ensure the managed connection is always closed by the transaction context manager
        if conn_to_manage and not conn_to_manage.closed:
            logger.debug(f"Transaction context manager closing connection ID: {id(conn_to_manage)}.")
            await asyncio.to_thread(conn_to_manage.close)
        else:
            logger.debug(f"Transaction context manager: Connection ID {id(conn_to_manage)} was already closed or None.")

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