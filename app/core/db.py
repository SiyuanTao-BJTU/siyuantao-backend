import pyodbc
from DBUtils.PooledDB import PooledDB
from app.config import settings
from app.exceptions import DALError
import logging

logger = logging.getLogger(__name__)

db_pool = None

def initialize_db_pool():
    """
    Initializes the database connection pool.
    """
    global db_pool
    if db_pool is None:
        try:
            # Construct connection string from settings
            conn_str = (
                f"DRIVER={{{settings.ODBC_DRIVER}}};"
                f"SERVER={settings.DATABASE_SERVER};"
                f"DATABASE={settings.DATABASE_NAME};"
                f"UID={settings.DATABASE_UID};"
                f"PWD={settings.DATABASE_PWD}"
            )

            # Combine with any additional pyodbc params
            connect_args = {"cnxn_str": conn_str, **settings.PYODBC_PARAMS}

            db_pool = PooledDB(
                pyodbc.connect,
                mincached=settings.DATABASE_POOL_MIN,
                maxcached=settings.DATABASE_POOL_MAX_IDLE,
                maxconnections=settings.DATABASE_POOL_MAX_TOTAL,
                blocking=settings.DATABASE_POOL_BLOCKING,
                **connect_args # Pass connection string and other params to pyodbc.connect
            )
            logger.info("Database connection pool initialized successfully")
        except Exception as e:
            logger.error(f"Database connection pool initialization failed: {e}")
            raise DALError(f"数据库连接池初始化失败: {e}") from e

def close_db_pool():
    """
    Closes the database connection pool.
    """
    global db_pool
    if db_pool:
        db_pool.close()
        logger.info("Database connection pool closed")
        db_pool = None

def get_pooled_connection() -> pyodbc.Connection:
    """
    Retrieves a database connection from the connection pool.
    """
    if db_pool is None:
        logger.warning("Database connection pool not initialized, attempting to initialize.")
        initialize_db_pool() # Attempt initialization (for development/emergency scenarios)
        if db_pool is None:
            logger.error("Database connection pool initialization failed, cannot get connection.")
            raise DALError("Database connection pool not initialized.")
            
    try:
        conn = db_pool.connection()
        # Ensure the connection is in manual commit mode for transaction manager
        conn.autocommit = False
        return conn
    except Exception as e:
        logger.error(f"Failed to get connection from pool: {e}")
        raise DALError(f"Failed to get database connection from pool: {e}") from e 