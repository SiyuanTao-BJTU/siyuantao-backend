#!/usr/bin/env python
"""
数据库初始化脚本。

执行此脚本将创建表、存储过程和触发器，完成数据库设置。
Usage: python init_database.py [--db-name DB_NAME] [--drop-existing] [--continue-on-error]
"""

import os
import sys
import pyodbc
import logging
import argparse
from datetime import datetime
import time # Add import for time module
import uuid # Ensure uuid is directly imported
import hashlib
import binascii

# 导入 dotenv 来加载 .env 文件
from dotenv import load_dotenv

# 导入 dictConfig
from logging.config import dictConfig
# Import Uvicorn logging formatters for consistency if needed
try:
    import uvicorn.logging
except ImportError:
    uvicorn = None # Handle case where uvicorn might not be installed in this env

# 加载 .env 文件中的环境变量
# 如果 .env 文件不在当前工作目录，需要指定路径
load_dotenv()

# Add the parent directory (backend/) to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Setup logging
log_dir = "logs"
# Use an absolute path for log_dir to avoid issues with changing CWD
log_dir_abs = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..' , log_dir)
if not os.path.exists(log_dir_abs):
    os.makedirs(log_dir_abs)

log_file_path = os.path.join(log_dir_abs, f"sql_deploy_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")

# Define a comprehensive logging configuration dictionary using dictConfig
# This configuration is for the db_init.py script itself.
# For FastAPI/Uvicorn, a similar configuration would be needed in the main application entry point.
LOGGING_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False, # Crucial: Prevents potential silencing by other configs (though less likely for a script)
    "formatters": {
        "default": { # Formatter for general application logs
            # Use Uvicorn's formatter if available, otherwise use a basic one
            "()": "uvicorn.logging.DefaultFormatter" if uvicorn and hasattr(uvicorn.logging, "DefaultFormatter") else "logging.Formatter",
            "fmt": "%(levelprefix)s %(asctime)s | %(name)s | %(message)s",
            "datefmt": "%Y-%m-%d %H:%M:%S",
          },
        # Add access formatter if needed, though less relevant for a script
        # "access": {
        #     "()": "uvicorn.logging.AccessFormatter",
        #     "fmt": '%(levelprefix)s %(asctime)s | %(name)s | %(client_addr)s - "%(request_line)s" %(status_code)s',
        #     "datefmt": "%Y-%m-%d %H:%M:%S",
        # },
    },
    "handlers": {
        "default": { # Handler for general logs (e.g., to stderr)
            "formatter": "default",
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stderr", # Directs to standard error stream
        },
        "file": { # Handler to write logs to a file
            "formatter": "default",
            "class": "logging.FileHandler",
            "filename": log_file_path,
            "encoding": "utf-8",
        },
        # Add access handler if needed
        # "access": {
        #     "formatter": "access",
        #     "class": "logging.StreamHandler",
        #     "stream": "ext://sys.stdout",
        # },
    },
    "loggers": {
        "": { # Root logger: catches logs from any unconfigured logger (like the ones from pyodbc)
            "handlers": ["default", "file"], # Send root logs to both console and file
            "level": "INFO", # Default level for unconfigured loggers
            "propagate": False, # Root logger does not propagate further
        },
        "db_init": { # Logger specifically for this script
             "handlers": ["default", "file"],
             "level": "DEBUG", # Set this script's logger to DEBUG for verbose output
             "propagate": False,
        },
        # You might define loggers for backend modules here if this was the main logging config file
        # e.g., "app": {"handlers": ["default", "file"], "level": "DEBUG", "propagate": False},
        # "app.services": {"handlers": ["default", "file"], "level": "DEBUG", "propagate": False},
        # "app.dal": {"handlers": ["default", "file"], "level": "DEBUG", "propagate": False},
        # Add Uvicorn loggers if this was the main app config
        # "uvicorn.error": {"level": "INFO", "handlers": ["default"], "propagate": False},
        # "uvicorn.access": {"level": "INFO", "handlers": ["access"], "propagate": False},
    },
}

# Apply the configuration
dictConfig(LOGGING_CONFIG)

# Get the logger for this script
logger = logging.getLogger("db_init")

def get_db_connection(db_name_override=None):
    """获取数据库连接, 如果指定的数据库不存在则尝试创建它。"""
    # 从环境变量读取配置，这将与 FastAPI 的 Pydantic BaseSettings 兼容
    server = os.getenv('DATABASE_SERVER')
    user = os.getenv('DATABASE_UID')
    password = os.getenv('DATABASE_PWD')
    default_db_name = os.getenv('DATABASE_NAME')
    driver = os.getenv('ODBC_DRIVER', '{ODBC Driver 17 for SQL Server}') # 从环境变量获取驱动名，或使用默认值

    if not all([server, user, password, default_db_name]):
        logger.error("请在环境变量中配置 DATABASE_SERVER, DATABASE_UID, DATABASE_PWD, DATABASE_NAME")
        raise ValueError("数据库连接配置不完整")
        
    target_db_name = db_name_override if db_name_override else default_db_name

    # 检查是否为高权限登录，如果是，跳过数据库用户和角色设置
    # 注意：这只是一个简单的判断，如果使用其他高权限登录，也需要在此处添加
    is_sysadmin_like_login = (user.lower() == 'sa') # 示例：判断是否为 sa 登录
    if is_sysadmin_like_login:
        logger.info(f"Using high-privilege login '{user}'. Skipping database user/role setup.")
    
    # Step 1: Connect to 'master' database to check existence and create if necessary
    master_conn_str = f"DRIVER={driver};SERVER={server};DATABASE=master;UID={user};PWD={password}"
    master_conn = None
    try:
        logger.info(f"Connecting to 'master' database on SERVER: {server} to check/create '{target_db_name}'.")
        # For CREATE DATABASE, it's often better to have autocommit=True for this specific connection
        master_conn = pyodbc.connect(master_conn_str, autocommit=True)
        cursor = master_conn.cursor()
        
        # Add: Drop the database if it already exists
        logger.info(f"Attempting to drop existing database '{target_db_name}' if it exists.")
        cursor.execute(f"DROP DATABASE IF EXISTS [{target_db_name}];")
        logger.info(f"DROP DATABASE IF EXISTS [{target_db_name}] executed.")
        time.sleep(1) # Give the system a moment
        
        # Check if the target database exists
        cursor.execute("SELECT name FROM sys.databases WHERE name = ?", (target_db_name,))
        if cursor.fetchone() is None:
            logger.info(f"Database '{target_db_name}' does not exist. Attempting to create it.")
            # Use [] around database name for safety, though pyodbc parameters usually handle this.
            # However, CREATE DATABASE doesn't allow parameterization for the DB name itself.
            # 使用 f-string 构建 SQL，并确保数据库名被正确引用
            create_db_sql = f"CREATE DATABASE [{target_db_name}]"
            logger.info(f"Executing: {create_db_sql}")
            cursor.execute(create_db_sql)
            logger.info(f"Database '{target_db_name}' created successfully.")
            
            # After creating the database, set up user mapping and permissions if not a high-privilege login
            if not is_sysadmin_like_login:
                try:
                    # Switch to the newly created database context
                    cursor.execute(f"USE [{target_db_name}];")
                    logger.info(f"Switched context to database: {target_db_name}")

                    # Check if a database user for the login already exists
                    # Use type IN ('S', 'U') to cover SQL users and Windows users if applicable
                    cursor.execute("SELECT 1 FROM sys.database_principals WHERE name = ? AND type IN ('S', 'U');", (user,))
                    user_exists_in_db = cursor.fetchone() is not None

                    if not user_exists_in_db:
                        logger.info(f"Database user '{user}' does not exist in '{target_db_name}'. Creating user and mapping login.")
                        # Create user from login
                        create_user_sql = f"CREATE USER [{user}] FOR LOGIN [{user}];"
                        cursor.execute(create_user_sql)
                        logger.info(f"Database user '{user}' created.")

                        # Add the user to the db_owner role for full permissions during initialization
                        # Using ALTER ROLE is the modern way.
                        add_role_sql = f"ALTER ROLE db_owner ADD MEMBER [{user}];"
                        logger.info(f"Adding user '{user}' to db_owner role in '{target_db_name}'.")
                        cursor.execute(add_role_sql)
                        logger.info(f"User '{user}' added to db_owner role.")

                        master_conn.commit() # Commit these user/permission changes
                        logger.info(f"User '{user}' permissions set up successfully in '{target_db_name}'.")

                except pyodbc.Error as e:
                    logger.error(f"Error setting up user permissions in database '{target_db_name}': {e}")
                    # This is critical, cannot proceed if user cannot connect/operate
                    raise # Re-raise the error to be caught by the outer try block
            else:
                 # Commit the database creation even if user setup is skipped
                 master_conn.commit()
                 logger.info(f"Database '{target_db_name}' creation committed (user setup skipped). ")

        else:
            logger.info(f"Database '{target_db_name}' already exists.")
            # If database already exists, we still need to ensure user mapping and permissions are correct
            # unless it's a high-privilege login.
            if not is_sysadmin_like_login:
                try:
                    # Switch to the existing database context
                    cursor.execute(f"USE [{target_db_name}];")
                    logger.info(f"Switched context to database: {target_db_name}")

                    # Check if a database user for the login already exists
                    cursor.execute("SELECT 1 FROM sys.database_principals WHERE name = ? AND type IN ('S', 'U');", (user,))
                    user_exists_in_db = cursor.fetchone() is not None

                    if not user_exists_in_db:
                        logger.warning(f"Database user '{user}' does not exist in existing database '{target_db_name}'. Creating user and mapping login.")
                        create_user_sql = f"CREATE USER [{user}] FOR LOGIN [{user}];"
                        cursor.execute(create_user_sql)
                        logger.info(f"Database user '{user}' created in existing database.")

                    # Add the user to the db_owner role (idempotent, safe to run if already member)
                    add_role_sql = f"ALTER ROLE db_owner ADD MEMBER [{user}];"
                    logger.info(f"Ensuring user '{user}' is in db_owner role in '{target_db_name}'.")
                    cursor.execute(add_role_sql)
                    logger.info(f"User '{user}' ensured to be in db_owner role.")

                    master_conn.commit() # Commit these user/permission changes
                    logger.info(f"User '{user}' permissions checked/set up successfully in existing '{target_db_name}'.")

                except pyodbc.Error as e:
                    logger.error(f"Error checking/setting up user permissions in existing database '{target_db_name}': {e}")
                    # This is critical, cannot proceed if user cannot connect/operate
                    raise # Re-raise the error
            else:
                # No user/role setup needed for high-privilege login when DB exists.
                logger.info(f"Database '{target_db_name}' exists. User setup skipped for high-privilege login '{user}'.")

        cursor.close()
    except pyodbc.Error as e:
        logger.error(f"Error while connecting to 'master', creating database, or setting initial permissions for '{target_db_name}': {e}")
        # If we can't ensure the database exists/is created and user permissions are set (if needed),
        # we should not proceed. The permission setup is now part of the critical path.
        raise
    finally:
        if master_conn:
            try:
                master_conn.close()
            except pyodbc.Error as e:
                 logger.error(f"Error closing master connection: {e}")

    # Step 2: Connect to the target database (now it should exist and user permissions should be set)
    target_conn_str = f"DRIVER={driver};SERVER={server};DATABASE={target_db_name};UID={user};PWD={password}"
    try:
        logger.info(f"Attempting connection to DATABASE: {target_db_name} on SERVER: {server} with user {user}")
        conn = pyodbc.connect(target_conn_str)
        logger.info("Successfully connected to target database.")
        return conn
    except pyodbc.Error as e: # Changed from generic Exception to pyodbc.Error for specificity
        logger.error(f"Database connection failed when connecting to {target_db_name} with user {user}: {e}")
        raise

def execute_sql_file(conn, file_path, continue_on_error=False):
    """
    执行SQL文件
    
    Args:
        conn: 数据库连接
        file_path: SQL文件路径
        continue_on_error: 出错时是否继续执行
    
    Returns:
        bool: 执行是否成功
    """
    logger.info(f"执行SQL文件: {file_path}")
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            sql_content = f.read()
        
        # 拆分SQL语句（按GO分隔）
        # Filter out empty strings that can result from split if GO is at the start/end or multiple GOs together
        statements = [s for s in sql_content.split('GO') if s.strip()]

        cursor = conn.cursor()
        success = True
        
        # Add an index to skip specific statements if needed
        # statement_index = 0 # Keep this outside the loop if used

        for i, statement in enumerate(statements):
            # The original skip logic was problematic, remove if not strictly needed
            # if file_path.endswith('03_trade_procedures.sql') and i == 3:
            #     logger.warning(f"  Skipping statement {i+1}/{len(statements)} in {os.path.basename(file_path)} due to persistent error 141.")
            #     continue

            statement = statement.strip() # Ensure trimming again, though list comprehension also trims for check
            if not statement:
                continue
            
            logger.info(f"  准备执行语句 {i+1}/{len(statements)}...")
            logger.debug(f"  SQL: {statement[:500]}...") # Log a snippet of the statement
            try:
                # Use cursor.execute() which is generally preferred
                cursor.execute(statement)
                
                # Check for messages from the server (warnings, info, non-fatal errors)
                # pyodbc.Error will be caught by the except block, but messages might have other info
                # Note: pyodbc.Cursor might not always expose .messages directly, behavior can vary by driver/version
                # A more robust check might involve querying server error state after execution if needed, but THROW/RAISERROR is better.
                # Let's rely on the pyodbc.Error exception for critical failures.
                
                # DDL statements often implicitly commit or manage their own transactions.
                # For safety and clarity, we can commit after each statement or rely on the connection's autocommit behavior.
                # Given the GO delimiter logic, committing after each block seems appropriate.
                conn.commit() # Commit after each statement block separated by GO
                logger.info(f"  语句 {i+1}/{len(statements)} 执行成功 (已提交)")

            except pyodbc.Error as e: # Catch specific pyodbc.Error
                logger.error(f"  语句 {i+1}/{len(statements)} 执行失败: {e}")
                # Also log messages if an exception occurred, as they might provide context
                # Accessing messages after an error might be tricky or driver-dependent.
                # Rely on the logged error message 'e'.
                if not continue_on_error:
                    success = False
                    break
            except Exception as e: # Catch any other unexpected exceptions
                logger.error(f"  语句 {i+1}/{len(statements)} 执行时发生意外错误: {e}", exc_info=True)
                if not continue_on_error:
                    success = False
                    break

            # Add a small delay after each statement block
            time.sleep(0.1)
        
        cursor.close()
        return success
    except Exception as e: # Catch file reading errors etc.
        logger.error(f"执行SQL文件失败: {e}", exc_info=True)
        return False

def create_admin_users(conn):
    """
    为开发者创建管理员账户。
    """
    logger.info("--- 开始创建开发者管理员账户 ---")
    cursor = conn.cursor()

    # Explicitly clear the User table before inserting initial admin users
    # This ensures a clean state and avoids conflicts with existing data, especially NULL email entries
    # The database dropping at the start of init_database.py ensures a clean state, so this explicit clear is redundant and causes issues.

    admin_users = [
        {"username": "pxk", "email": "23301132@bjtu.edu.cn", "major": "软件工程", "phone": "13800000001","avatar_url": "/uploads/10f7ab7a-95d2-4476-b2d2-9d31f2c7850e.jpg"},
        {"username": "cyq", "email": "23301003@bjtu.edu.cn", "major": "计算机科学与技术", "phone": "13800000002"},
        {"username": "cy", "email": "23301002@bjtu.edu.cn", "major": "计算机科学与技术", "phone": "13800000003"},
        {"username": "ssc", "email": "23301011@bjtu.edu.cn", "major": "软件工程", "phone": "13800000004"},
        {"username": "zsq", "email": "23301027@bjtu.edu.cn", "major": "人工智能", "phone": "13800000005"},
    ]
    # You might need to fetch or define get_password_hash here if not globally available
    # Assuming hash_password is defined in this script as it is below
    # from app.utils.auth import get_password_hash 

    for user_data in admin_users:
        try:
            # Refined Check: Check if user already exists by username or specific non-null email
            check_query = "SELECT COUNT(1) FROM [User] WHERE UserName = ?"
            check_params = (user_data['username'],)

            if user_data.get('email'): # Only add email check if email is provided and not None
                check_query += " OR Email = ?"
                check_params += (user_data['email'],)

            cursor.execute(check_query, check_params)
            if cursor.fetchone()[0] == 0:
                logger.info(f"  创建用户: {user_data['username']} ({user_data.get('email', '无邮箱')})") # Log email presence

                # Determine IsStaff and IsSuperAdmin status
                is_staff_value = 1  # Set all users in admin_users list as staff
                is_super_admin_value = 0 # Default to not super admin

                # Set pxk as Super Admin based on email
                if user_data.get('email') == '23301132@bjtu.edu.cn':
                    is_super_admin_value = 1

                hashed_password = hash_password("password123") # Use a default password

                # Insert the user
                cursor.execute("""
                    INSERT INTO [User] (UserName, Password, Email, Status, Credit, IsStaff, IsVerified, Major, PhoneNumber, AvatarUrl, JoinTime, IsSuperAdmin)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, GETDATE(), ?)
                """, (
                    user_data['username'],
                    hashed_password,
                    user_data.get('email'), # Pass email (can be None)
                    'Active',
                    100,
                    is_staff_value,
                    1, # Assume admin users are verified for simplicity in init
                    user_data.get('major'), # Pass major (can be None)
                    user_data['phone'],
                    user_data.get('avatar_url'), # 添加 AvatarUrl
                    is_super_admin_value
                ))
                conn.commit() # Commit after each user insertion
                logger.info(f"  用户 {user_data['username']} 创建成功.")
            else:
                logger.info(f"  用户 {user_data['username']} ({user_data.get('email', '无邮箱')}) 已存在，跳过创建.")

        except pyodbc.IntegrityError as e:
             # Catch specific IntegrityError to provide more context
             sqlstate = e.args[0]
             error_message = e.args[1] if len(e.args) > 1 else str(e)
             logger.error(f"  创建用户 {user_data['username']} 失败 (Integrity Error): {sqlstate} - {error_message}")
             # You might choose to continue or break here based on desired behavior for duplicates
             # For init script, logging and continuing might be acceptable for some duplicates
             conn.rollback() # Rollback the failed insert transaction if not auto-rolled back
        except Exception as e:
            logger.error(f"  创建用户 {user_data['username']} 失败: {e}")
            # Depending on how execute is configured, a rollback might be needed here too
            if conn: # Check if connection is valid
                 try:
                      conn.rollback()
                 except Exception as rb_e:
                      logger.error(f"Error during rollback: {rb_e}")


    logger.info("--- 开发者管理员账户创建完成 ---")

# Add this utility function for password hashing, mirroring backend's auth_service
def hash_password(password: str) -> str:
    """Hashes a password using PBKDF2 with SHA256."""
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 100000)
    # Store salt and hashed password together, separated by a colon, in hex format
    return f"{salt.hex()}:{dk.hex()}"

# Add this function for inserting sample data
async def insert_sample_data(conn: pyodbc.Connection, logger: logging.Logger):

    logger.info("Starting to insert sample data...")
    cursor = conn.cursor()

    # --- 1. Insert Sample Users ---
    # User 1: 普通用户 - Alice
    alice_id = uuid.uuid4()
    alice_password = hash_password("password123")
    logger.info(f"Inserting user Alice with ID: {alice_id}")
    try:
        cursor.execute(
            """
            INSERT INTO [User] (UserID, UserName, Password, Status, Credit, IsStaff, IsSuperAdmin, IsVerified, Major, Email, AvatarUrl, Bio, PhoneNumber, JoinTime, LastLoginTime)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            alice_id, "alice", alice_password, "Active", 95, 0, 0, 1, "计算机科学", "alice@example.com",
            "https://images.unsplash.com/photo-1520813792240-56fc4a3765a7?q=80&w=2070&auto=format&fit=crop&ixlib=rb-4.0.3&ixid=M3wxMjA3fDB8MHxwaG90by1wYWdlfHx8fGVufDB8fHx8fA%3D%3D", # 更换为真实图片链接
            "热爱编程和二手交易的学生，喜欢分享好物。", "13800000006", datetime.now(), datetime.now()
        )
        logger.info("User Alice inserted.")
    except pyodbc.Error as e:
        logger.error(f"Failed to insert user Alice: {e}")
        pass

    # User 2: 普通用户 - Bob
    bob_id = uuid.uuid4()
    bob_password = hash_password("password123")
    logger.info(f"Inserting user Bob with ID: {bob_id}")
    try:
        cursor.execute(
            """
            INSERT INTO [User] (UserID, UserName, Password, Status, Credit, IsStaff, IsSuperAdmin, IsVerified, Major, Email, AvatarUrl, Bio, PhoneNumber, JoinTime, LastLoginTime)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            bob_id, "bob", bob_password, "Active", 88, 0, 0, 0, "电子工程", "bob@example.com",
            "https://images.unsplash.com/photo-1500648767791-00dcc994a43e?q=80&w=1887&auto=format&fit=crop&ixlib=rb-4.0.3&ixid=M3wxMjA3fDB8MHxwaG90by1wYWdlfHx8fGVufDB8fHx8fA%3D%3D", # 更换为真实图片链接
            "喜欢电子产品，经常出售闲置物品，乐于助人。", "13900000002", datetime.now(), datetime.now()
        )
        logger.info("User Bob inserted.")
    except pyodbc.Error as e:
        logger.error(f"Failed to insert user Bob: {e}")
        pass

    # User 3: 普通用户 - Carol (未认证)
    carol_id = uuid.uuid4()
    carol_password = hash_password("password123")
    logger.info(f"Inserting user Carol with ID: {carol_id}")
    try:
        cursor.execute(
            """
            INSERT INTO [User] (UserID, UserName, Password, Status, Credit, IsStaff, IsSuperAdmin, IsVerified, Major, Email, AvatarUrl, Bio, PhoneNumber, JoinTime, LastLoginTime)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            carol_id, "carol", carol_password, "Disabled", 70, 0, 0, 0, "环境艺术", "carol@example.com",
            "https://images.unsplash.com/photo-1494790108377-be9c29b29330?q=80&w=1887&auto=format&fit=crop&ixlib=rb-4.0.3&ixid=M3wxMjA3fDB8MHxwaG90by1wYWdlfHx8fGVufDB8fHx8fA%3D%3D", # 更换为真实图片链接
            "一个新用户，还没有完成认证，目前账户已禁用。", "13700000003", datetime.now(), datetime.now()
        )
        logger.info("User Carol inserted.")
    except pyodbc.Error as e:
        logger.error(f"Failed to insert user Carol: {e}")
        pass

    # User 4: 普通用户 - David
    david_id = uuid.uuid4()
    david_password = hash_password("password123")
    logger.info(f"Inserting user David with ID: {david_id}")
    try:
        cursor.execute(
            """
            INSERT INTO [User] (UserID, UserName, Password, Status, Credit, IsStaff, IsSuperAdmin, IsVerified, Major, Email, AvatarUrl, Bio, PhoneNumber, JoinTime, LastLoginTime)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            david_id, "david", david_password, "Active", 92, 0, 0, 1, "自动化", "david@example.com",
            "https://images.unsplash.com/photo-1539571696357-5a69c17a67c6?q=80&w=1887&auto=format&fit=crop&ixlib=rb-4.0.3&ixid=M3wxMjA3fDB8MHxwaG90by1wYWdlfHx8fGVufDB8fHx8fA%3D%3D", # 更换为真实图片链接
            "一名对电子产品和开源硬件感兴趣的用户。", "13600000004", datetime.now(), datetime.now()
        )
        logger.info("User David inserted.")
    except pyodbc.Error as e:
        logger.error(f"Failed to insert user David: {e}")
        pass

    # User 5: 普通用户 - Eve
    eve_id = uuid.uuid4()
    eve_password = hash_password("password123")
    logger.info(f"Inserting user Eve with ID: {eve_id}")
    try:
        cursor.execute(
            """
            INSERT INTO [User] (UserID, UserName, Password, Status, Credit, IsStaff, IsSuperAdmin, IsVerified, Major, Email, AvatarUrl, Bio, PhoneNumber, JoinTime, LastLoginTime)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            eve_id, "eve", eve_password, "Active", 90, 0, 0, 0, "物理学", "eve@example.com",
            "https://images.unsplash.com/photo-1529626455594-4ff0802cfb7e?q=80&w=1887&auto=format&fit=crop&ixlib=rb-4.0.3&ixid=M3wxMjA3fDB8MHxwaG90by1wYWdlfHx8fGVufDB8fHx8fA%3D%3D", # 更换为真实图片链接
            "喜欢阅读和探索自然的新用户，待认证。", "13500000005", datetime.now(), datetime.now() # 添加了手机号
        )
        logger.info("User Eve inserted.")
    except pyodbc.Error as e:
        logger.error(f"Failed to insert user Eve: {e}")
        pass

    # User 6: Tom (管理员)
    tom_id = uuid.uuid4()
    tom_password = hash_password("password123")
    logger.info(f"Inserting user Tom (Admin) with ID: {tom_id}")
    try:
        cursor.execute(
            """
            INSERT INTO [User] (UserID, UserName, Password, Status, Credit, IsStaff, IsSuperAdmin, IsVerified, Major, Email, AvatarUrl, Bio, PhoneNumber, JoinTime, LastLoginTime)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            tom_id, "tom_admin", tom_password, "Active", 100, 1, 0, 1, "信息管理", "tom.admin@example.com",
            "https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?q=80&w=1887&auto=format&fit=crop&ixlib=rb-4.0.3&ixid=M3wxMjA3fDB8MHxwaG90by1wYWdlfHx8fGVufDB8fHx8fA%3D%3D",
            "平台管理员，负责维护社区秩序。", "13400000006", datetime.now(), datetime.now()
        )
        logger.info("User Tom (Admin) inserted.")
    except pyodbc.Error as e:
        logger.error(f"Failed to insert user Tom (Admin): {e}")
        pass

    # User 7: Lucy (信用较低的用户)
    lucy_id = uuid.uuid4()
    lucy_password = hash_password("password123")
    logger.info(f"Inserting user Lucy with ID: {lucy_id}")
    try:
        cursor.execute(
            """
            INSERT INTO [User] (UserID, UserName, Password, Status, Credit, IsStaff, IsSuperAdmin, IsVerified, Major, Email, AvatarUrl, Bio, PhoneNumber, JoinTime, LastLoginTime)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            lucy_id, "lucy_low_credit", lucy_password, "Active", 45, 0, 0, 1, "社会学", "lucy.low@example.com",
            "https://images.unsplash.com/photo-1517841905240-472988babdf9?q=80&w=1887&auto=format&fit=crop&ixlib=rb-4.0.3&ixid=M3wxMjA3fDB8MHxwaG90by1wYWdlfHx8fGVufDB8fHx8fA%3D%3D",
            "信用分较低，但正在努力改进。", "13300000007", datetime.now(), datetime.now()
        )
        logger.info("User Lucy inserted.")
    except pyodbc.Error as e:
        logger.error(f"Failed to insert user Lucy: {e}")
        pass

        # For now, let's assume `create_admin_users` has already defined and inserted `pxk`.
    # We should get pxk's ID from the User table.
    pxk_id = None
    cyq_id = None
    cy_id = None
    ssc_id = None
    zsq_id = None

    try:
        cursor.execute("SELECT UserID FROM [User] WHERE UserName = 'pxk'")
        pxk_id = cursor.fetchone()[0]
        cursor.execute("SELECT UserID FROM [User] WHERE UserName = 'cyq'")
        cyq_id = cursor.fetchone()[0]
        cursor.execute("SELECT UserID FROM [User] WHERE UserName = 'cy'")
        cy_id = cursor.fetchone()[0]
        cursor.execute("SELECT UserID FROM [User] WHERE UserName = 'ssc'")
        ssc_id = cursor.fetchone()[0]
        cursor.execute("SELECT UserID FROM [User] WHERE UserName = 'zsq'")
        zsq_id = cursor.fetchone()[0]
        logger.info(f"Retrieved admin IDs: pxk={pxk_id}, cyq={cyq_id}, cy={cy_id}, ssc={ssc_id}, zsq={zsq_id}")
    except Exception as e:
        logger.error(f"Failed to retrieve admin user IDs: {e}")
        # If admin IDs can't be retrieved, subsequent product insertions for them will fail.
        # This is a critical error for test data.
        raise # Re-raise to stop execution if admin IDs are not found.

    # Commit users
    conn.commit()
    logger.info("Sample users committed.")

    # --- 2. Insert Sample Products for Alice, Bob, David, Eve ---
    # Product 1: Alice's Laptop (已存在，更新图片链接)
    product1_id = uuid.uuid4()
    logger.info(f"Inserting product 1 (Laptop) with ID: {product1_id}")
    try:
        cursor.execute(
            """
            INSERT INTO [Product] (ProductID, OwnerID, CategoryName, ProductName, Description, Quantity, Price, PostTime, Status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            product1_id, alice_id, "电子产品", "二手MacBook Pro 2020", "8成新，13英寸，带原装充电器，适合学生党和轻办公。",
            1, 6200.00, datetime.now(), "Active"
        )
        logger.info("Product 1 inserted.")
    except pyodbc.Error as e:
        logger.error(f"Failed to insert product 1: {e}")
        pass

    # Product 2: Bob's Camera (已存在，更新图片链接)
    product2_id = uuid.uuid4()
    logger.info(f"Inserting product 2 (Camera) with ID: {product2_id}")
    try:
        cursor.execute(
            """
            INSERT INTO [Product] (ProductID, OwnerID, CategoryName, ProductName, Description, Quantity, Price, PostTime, Status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            product2_id, bob_id, "电子产品", "佳能EOS 80D单反相机", "入门级单反，含18-55mm套机镜头，快门数约5000，功能完好。",
            1, 2750.00, datetime.now(), "Active"
        )
        logger.info("Product 2 inserted.")
    except pyodbc.Error as e:
        logger.error(f"Failed to insert product 2: {e}")
        pass

    # Product 3: Alice's Textbook (Pending Review) (已存在)
    product3_id = uuid.uuid4()
    logger.info(f"Inserting product 3 (Textbook) with ID: {product3_id}")
    try:
        cursor.execute(
            """
            INSERT INTO [Product] (ProductID, OwnerID, CategoryName, ProductName, Description, Quantity, Price, PostTime, Status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            product3_id, alice_id, "书籍文具", "《线性代数及其应用》（第5版）", "经典教材，九成新，无笔记，适合工科学生。",
            2, 75.00, datetime.now(), "PendingReview" # 数量改为2
        )
        logger.info("Product 3 inserted.")
    except pyodbc.Error as e:
        logger.error(f"Failed to insert product 3: {e}")
        pass

    # Product 4: Bob's Bicycle (Sold) (已存在，改为Withdrawn)
    product4_id = uuid.uuid4()
    logger.info(f"Inserting product 4 (Bicycle) with ID: {product4_id}")
    try:
        cursor.execute(
            """
            INSERT INTO [Product] (ProductID, OwnerID, CategoryName, ProductName, Description, Quantity, Price, PostTime, Status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            product4_id, bob_id, "运动户外", "捷安特ATX777山地自行车", "骑行一年，保养良好，送车锁和打气筒。", # 类别改为运动户外
            1, 850.00, datetime.now(), "Withdrawn" # 改为 Withdrawn, 数量为1
        )
        logger.info("Product 4 inserted.")
    except pyodbc.Error as e:
        logger.error(f"Failed to insert product 4: {e}")
        pass

    # Product 5: David's Keyboard (Active)
    product5_id = uuid.uuid4()
    logger.info(f"Inserting product 5 (Keyboard) for David with ID: {product5_id}")
    try:
        cursor.execute(
            """
            INSERT INTO [Product] (ProductID, OwnerID, CategoryName, ProductName, Description, Quantity, Price, PostTime, Status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            product5_id, david_id, "电子产品", "Cherry MX8.0 机械键盘", "黑色，红轴，9成新，手感极佳，带原包装。",
            1, 700.00, datetime.now(), "Active"
        )
        logger.info("Product 5 (Keyboard) inserted.")
    except pyodbc.Error as e:
        logger.error(f"Failed to insert product 5: {e}")
        pass

    # Product 6: Eve's Dress (PendingReview)
    product6_id = uuid.uuid4()
    logger.info(f"Inserting product 6 (Dress) for Eve with ID: {product6_id}")
    try:
        cursor.execute(
            """
            INSERT INTO [Product] (ProductID, OwnerID, CategoryName, ProductName, Description, Quantity, Price, PostTime, Status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            product6_id, eve_id, "服装鞋包", "夏季碎花连衣裙", "全新，M码，仅试穿，风格不合适故转让。",
            1, 120.00, datetime.now(), "PendingReview"
        )
        logger.info("Product 6 (Dress) inserted.")
    except pyodbc.Error as e:
        logger.error(f"Failed to insert product 6: {e}")
        pass

    # Product 7: Alice's Graphics Card (Rejected)
    product7_id = uuid.uuid4()
    logger.info(f"Inserting product 7 (Graphics Card) for Alice (Rejected) with ID: {product7_id}")
    try:
        cursor.execute(
            """
            INSERT INTO [Product] (ProductID, OwnerID, CategoryName, ProductName, Description, Quantity, Price, PostTime, Status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            product7_id, alice_id, "电子产品", "NVIDIA RTX 3070 显卡", "挖矿锻炼卡，性能不稳定，便宜出。", # 描述可能导致拒绝
            1, 1500.00, datetime.now(), "Rejected"
        )
        logger.info("Product 7 (Graphics Card - Rejected) inserted.")
    except pyodbc.Error as e:
        logger.error(f"Failed to insert product 7: {e}")
        pass

    # Product 8: Bob's Headphones (Sold)
    product8_id = uuid.uuid4()
    logger.info(f"Inserting product 8 (Headphones) for Bob (Sold) with ID: {product8_id}")
    try:
        cursor.execute(
            """
            INSERT INTO [Product] (ProductID, OwnerID, CategoryName, ProductName, Description, Quantity, Price, PostTime, Status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            product8_id, bob_id, "影音娱乐", "索尼WH-1000XM4降噪耳机", "95新，音质出色，配件齐全。",
            0, 1200.00, datetime.now(), "Sold"
        )
        logger.info("Product 8 (Headphones - Sold) inserted.")
    except pyodbc.Error as e:
        logger.error(f"Failed to insert product 8: {e}")
        pass

    # Product 9: David's Desk Lamp (Active, Low Quantity)
    product9_id = uuid.uuid4()
    logger.info(f"Inserting product 9 (Desk Lamp) for David with ID: {product9_id}")
    try:
        cursor.execute(
            """
            INSERT INTO [Product] (ProductID, OwnerID, CategoryName, ProductName, Description, Quantity, Price, PostTime, Status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            product9_id, david_id, "家居日用", "小米LED智能台灯Pro", "可调节亮度和色温，保护视力，几乎全新。",
            1, 180.00, datetime.now(), "Active"
        )
        logger.info("Product 9 (Desk Lamp) inserted.")
    except pyodbc.Error as e:
        logger.error(f"Failed to insert product 9: {e}")
        pass

    # Product 10: Eve's Skincare Set (Withdrawn by user)
    product10_id = uuid.uuid4()
    logger.info(f"Inserting product 10 (Skincare Set) for Eve (Withdrawn) with ID: {product10_id}")
    try:
        cursor.execute(
            """
            INSERT INTO [Product] (ProductID, OwnerID, CategoryName, ProductName, Description, Quantity, Price, PostTime, Status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            product10_id, eve_id, "美妆个护", "某品牌水乳套装", "全新未拆封，朋友送的，自己用不上。",
            1, 280.00, datetime.now(), "Withdrawn"
        )
        logger.info("Product 10 (Skincare Set - Withdrawn) inserted.")
    except pyodbc.Error as e:
        logger.error(f"Failed to insert product 10: {e}")
        pass

        # --- New Products for Admin Users ---

    # Product 11: Pxk's Drawing Tablet (Active)
    product11_id = uuid.uuid4()
    if pxk_id:
        logger.info(f"Inserting product 11 (Drawing Tablet) for Pxk with ID: {product11_id}")
        try:
            cursor.execute(
                """
                INSERT INTO [Product] (ProductID, OwnerID, CategoryName, ProductName, Description, Quantity, Price, PostTime, Status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                product11_id, pxk_id, "电子产品", "Wacom Intuos 绘图板", "9成新，很少使用，适合设计专业学生。",
                1, 550.00, datetime.now(), "Active"
            )
            logger.info("Product 11 (Drawing Tablet) inserted.")
        except pyodbc.Error as e:
            logger.error(f"Failed to insert product 11: {e}")
            pass

    # Product 12: Cyq's Sports Shoes (Active)
    product12_id = uuid.uuid4()
    if cyq_id:
        logger.info(f"Inserting product 12 (Sports Shoes) for Cyq with ID: {product12_id}")
        try:
            cursor.execute(
                """
                INSERT INTO [Product] (ProductID, OwnerID, CategoryName, ProductName, Description, Quantity, Price, PostTime, Status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                product12_id, cyq_id, "服装鞋包", "Adidas UltraBoost 跑鞋", "8成新，尺码42，舒适透气，适合日常跑步。",
                1, 380.00, datetime.now(), "Active"
            )
            logger.info("Product 12 (Sports Shoes) inserted.")
        except pyodbc.Error as e:
            logger.error(f"Failed to insert product 12: {e}")
            pass

    # Product 13: Cy's Vintage Camera (PendingReview)
    product13_id = uuid.uuid4()
    if cy_id:
        logger.info(f"Inserting product 13 (Vintage Camera) for Cy with ID: {product13_id}")
        try:
            cursor.execute(
                """
                INSERT INTO [Product] (ProductID, OwnerID, CategoryName, ProductName, Description, Quantity, Price, PostTime, Status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                product13_id, cy_id, "电子产品", "Olympus OM-1 胶片相机", "老式胶片机，功能完好，适合摄影爱好者收藏。",
                1, 1500.00, datetime.now(), "PendingReview"
            )
            logger.info("Product 13 (Vintage Camera) inserted.")
        except pyodbc.Error as e:
            logger.error(f"Failed to insert product 13: {e}")
            pass

    # Product 14: Ssc's Guitar (Active)
    product14_id = uuid.uuid4()
    if ssc_id:
        logger.info(f"Inserting product 14 (Guitar) for Ssc with ID: {product14_id}")
        try:
            cursor.execute(
                """
                INSERT INTO [Product] (ProductID, OwnerID, CategoryName, ProductName, Description, Quantity, Price, PostTime, Status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                product14_id, ssc_id, "乐器", "民谣吉他初学套装", "全新未拆封，送拨片和变调夹，适合新手。",
                1, 450.00, datetime.now(), "Active"
            )
            logger.info("Product 14 (Guitar) inserted.")
        except pyodbc.Error as e:
            logger.error(f"Failed to insert product 14: {e}")
            pass

    # Product 15: Zsq's AI Textbook (Active)
    product15_id = uuid.uuid4()
    if zsq_id:
        logger.info(f"Inserting product 15 (AI Textbook) for Zsq with ID: {product15_id}")
        try:
            cursor.execute(
                """
                INSERT INTO [Product] (ProductID, OwnerID, CategoryName, ProductName, Description, Quantity, Price, PostTime, Status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                product15_id, zsq_id, "书籍文具", "《机器学习》（西瓜书）", "经典机器学习教材，九成新，少量笔记。",
                1, 99.00, datetime.now(), "Active"
            )
            logger.info("Product 15 (AI Textbook) inserted.")
        except pyodbc.Error as e:
            logger.error(f"Failed to insert product 15: {e}")
            pass

    # Product 16: Tom's Smartwatch (Sold)
    product16_id = uuid.uuid4()
    if tom_id:
        logger.info(f"Inserting product 16 (Smartwatch) for Tom with ID: {product16_id}")
        try:
            cursor.execute(
                """
                INSERT INTO [Product] (ProductID, OwnerID, CategoryName, ProductName, Description, Quantity, Price, PostTime, Status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                product16_id, tom_id, "电子产品", "华为Watch GT 2 Pro", "9成新，续航出色，功能齐全。",
                0, 800.00, datetime.now(), "Sold" # Sold out
            )
            logger.info("Product 16 (Smartwatch) inserted.")
        except pyodbc.Error as e:
            logger.error(f"Failed to insert product 16: {e}")
            pass

    # Product 17: Pxk's Monitor (Active)
    product17_id = uuid.uuid4()
    if pxk_id:
        logger.info(f"Inserting product 17 (Monitor) for Pxk with ID: {product17_id}")
        try:
            cursor.execute(
                """
                INSERT INTO [Product] (ProductID, OwnerID, CategoryName, ProductName, Description, Quantity, Price, PostTime, Status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                product17_id, pxk_id, "电子产品", "戴尔27英寸2K显示器", "IPS面板，色彩准确，适合设计和日常使用。",
                1, 1500.00, datetime.now(), "Active"
            )
            logger.info("Product 17 (Monitor) inserted.")
        except pyodbc.Error as e:
            logger.error(f"Failed to insert product 17: {e}")
            pass

    # Product 18: Cyq's Backpack (Active)
    product18_id = uuid.uuid4()
    if cyq_id:
        logger.info(f"Inserting product 18 (Backpack) for Cyq with ID: {product18_id}")
        try:
            cursor.execute(
                """
                INSERT INTO [Product] (ProductID, OwnerID, CategoryName, ProductName, Description, Quantity, Price, PostTime, Status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                product18_id, cyq_id, "服装鞋包", "Herschel经典双肩包", "耐磨防水，容量大，适合学生日常通勤。",
                1, 280.00, datetime.now(), "Active"
            )
            logger.info("Product 18 (Backpack) inserted.")
        except pyodbc.Error as e:
            logger.error(f"Failed to insert product 18: {e}")
            pass

    # Product 19: Cy's Painting Set (Active)
    product19_id = uuid.uuid4()
    if cy_id:
        logger.info(f"Inserting product 19 (Painting Set) for Cy with ID: {product19_id}")
        try:
            cursor.execute(
                """
                INSERT INTO [Product] (ProductID, OwnerID, CategoryName, ProductName, Description, Quantity, Price, PostTime, Status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                product19_id, cy_id, "文体用品", "马利牌水彩颜料套装", "全新，24色，适合水彩初学者。",
                1, 150.00, datetime.now(), "Active"
            )
            logger.info("Product 19 (Painting Set) inserted.")
        except pyodbc.Error as e:
            logger.error(f"Failed to insert product 19: {e}")
            pass

    # Product 20: Ssc's Headset (Active)
    product20_id = uuid.uuid4()
    if ssc_id:
        logger.info(f"Inserting product 20 (Headset) for Ssc with ID: {product20_id}")
        try:
            cursor.execute(
                """
                INSERT INTO [Product] (ProductID, OwnerID, CategoryName, ProductName, Description, Quantity, Price, PostTime, Status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                product20_id, ssc_id, "影音娱乐", "HyperX Cloud Stinger 游戏耳机", "音质清晰，佩戴舒适，适合游戏玩家。",
                1, 260.00, datetime.now(), "Active"
            )
            logger.info("Product 20 (Headset) inserted.")
        except pyodbc.Error as e:
            logger.error(f"Failed to insert product 20: {e}")
            pass

    # Product 21: Zsq's Algorithm Book (Active)
    product21_id = uuid.uuid4()
    if zsq_id:
        logger.info(f"Inserting product 21 (Algorithm Book) for Zsq with ID: {product21_id}")
        try:
            cursor.execute(
                """
                INSERT INTO [Product] (ProductID, OwnerID, CategoryName, ProductName, Description, Quantity, Price, PostTime, Status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                product21_id, zsq_id, "书籍文具", "《算法导论》（原书第3版）", "计算机经典教材，9成新，无笔记。",
                1, 120.00, datetime.now(), "Active"
            )
            logger.info("Product 21 (Algorithm Book) inserted.")
        except pyodbc.Error as e:
            logger.error(f"Failed to insert product 21: {e}")
            pass

    # Product 22: Pxk's Projector (Active)
    product22_id = uuid.uuid4()
    if pxk_id:
        logger.info(f"Inserting product 22 (Projector) for Pxk with ID: {product22_id}")
        try:
            cursor.execute(
                """
                INSERT INTO [Product] (ProductID, OwnerID, CategoryName, ProductName, Description, Quantity, Price, PostTime, Status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                product22_id, pxk_id, "电子产品", "极米H3S 投影仪", "自用投影仪，流明高，画质好，带幕布。",
                1, 3500.00, datetime.now(), "Active"
            )
            logger.info("Product 22 (Projector) inserted.")
        except pyodbc.Error as e:
            logger.error(f"Failed to insert product 22: {e}")
            pass

    # Product 23: Cyq's Dumbbells (Active)
    product23_id = uuid.uuid4()
    if cyq_id:
        logger.info(f"Inserting product 23 (Dumbbells) for Cyq with ID: {product23_id}")
        try:
            cursor.execute(
                """
                INSERT INTO [Product] (ProductID, OwnerID, CategoryName, ProductName, Description, Quantity, Price, PostTime, Status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                product23_id, cyq_id, "运动户外", "可调节哑铃套装", "20KG可调节哑铃一对，适合居家健身。",
                1, 200.00, datetime.now(), "Active"
            )
            logger.info("Product 23 (Dumbbells) inserted.")
        except pyodbc.Error as e:
            logger.error(f"Failed to insert product 23: {e}")
            pass

    # Product 24: Cy's Art Easel (PendingReview)
    product24_id = uuid.uuid4()
    if cy_id:
        logger.info(f"Inserting product 24 (Art Easel) for Cy with ID: {product24_id}")
        try:
            cursor.execute(
                """
                INSERT INTO [Product] (ProductID, OwnerID, CategoryName, ProductName, Description, Quantity, Price, PostTime, Status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                product24_id, cy_id, "文体用品", "实木画架写生架", "8成新，可折叠，轻便易携带。",
                1, 100.00, datetime.now(), "PendingReview"
            )
            logger.info("Product 24 (Art Easel) inserted.")
        except pyodbc.Error as e:
            logger.error(f"Failed to insert product 24: {e}")
            pass

    # Product 25: Ssc's Drone (Rejected)
    product25_id = uuid.uuid4()
    if ssc_id:
        logger.info(f"Inserting product 25 (Drone) for Ssc with ID: {product25_id}")
        try:
            cursor.execute(
                """
                INSERT INTO [Product] (ProductID, OwnerID, CategoryName, ProductName, Description, Quantity, Price, PostTime, Status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                product25_id, ssc_id, "电子产品", "大疆Mavic Mini 2 无人机", "坠机过，需要维修才能使用，便宜处理。",
                1, 500.00, datetime.now(), "Rejected"
            )
            logger.info("Product 25 (Drone) inserted.")
        except pyodbc.Error as e:
            logger.error(f"Failed to insert product 25: {e}")
            pass

    # Product 26: Zsq's Robotics Kit (Active)
    product26_id = uuid.uuid4()
    if zsq_id:
        logger.info(f"Inserting product 26 (Robotics Kit) for Zsq with ID: {product26_id}")
        try:
            cursor.execute(
                """
                INSERT INTO [Product] (ProductID, OwnerID, CategoryName, ProductName, Description, Quantity, Price, PostTime, Status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                product26_id, zsq_id, "电子产品", "Arduino智能小车套件", "全新未组装，适合入门级机器人爱好者。",
                1, 180.00, datetime.now(), "Active"
            )
            logger.info("Product 26 (Robotics Kit) inserted.")
        except pyodbc.Error as e:
            logger.error(f"Failed to insert product 26: {e}")
            pass

    # Commit products
    conn.commit()
    logger.info("Sample products committed.")

    # --- 3. Insert Sample Product Images ---
    # Images for Product 1 (Laptop) - (已存在, 更新URL)
    logger.info(f"Inserting images for Product 1: {product1_id}")
    try:
        cursor.execute(
            """INSERT INTO [ProductImage] (ImageID, ProductID, ImageURL, SortOrder) VALUES (?, ?, ?, ?)""",
            uuid.uuid4(), product1_id, "https://images.unsplash.com/photo-1517336714731-489689fd1ca8?q=80&w=1926&auto=format&fit=crop&ixlib=rb-4.0.3&ixid=M3wxMjA3fDB8MHxwaG90by1wYWdlfHx8fGVufDB8fHx8fA%3D%3D", 0
        )
        cursor.execute(
            """INSERT INTO [ProductImage] (ImageID, ProductID, ImageURL, SortOrder) VALUES (?, ?, ?, ?)""",
            uuid.uuid4(), product1_id, "https://images.unsplash.com/photo-1496181133206-80ce9b88a853?q=80&w=2071&auto=format&fit=crop&ixlib=rb-4.0.3&ixid=M3wxMjA3fDB8MHxwaG90by1wYWdlfHx8fGVufDB8fHx8fA%3D%3D", 1
        )
        cursor.execute(
            """INSERT INTO [ProductImage] (ImageID, ProductID, ImageURL, SortOrder) VALUES (?, ?, ?, ?)""",
            uuid.uuid4(), product1_id, "https://images.unsplash.com/photo-1588872657578-7efd1f1555ed?q=80&w=2070&auto=format&fit=crop&ixlib=rb-4.0.3&ixid=M3wxMjA3fDB8MHxwaG90by1wYWdlfHx8fGVufDB8fHx8fA%3D%3D", 2
        )
        logger.info("Images for Product 1 inserted.")
    except pyodbc.Error as e:
        logger.error(f"Failed to insert images for Product 1: {e}")
        pass

    # Images for Product 2 (Camera) - (已存在, 更新URL)
    logger.info(f"Inserting images for Product 2: {product2_id}")
    try:
        cursor.execute(
            """INSERT INTO [ProductImage] (ImageID, ProductID, ImageURL, SortOrder) VALUES (?, ?, ?, ?)""",
            uuid.uuid4(), product2_id, "https://images.unsplash.com/photo-1516035069371-29a1b244cc32?q=80&w=1964&auto=format&fit=crop&ixlib=rb-4.0.3&ixid=M3wxMjA3fDB8MHxwaG90by1wYWdlfHx8fGVufDB8fHx8fA%3D%3D", 0
        )
        cursor.execute(
            """INSERT INTO [ProductImage] (ImageID, ProductID, ImageURL, SortOrder) VALUES (?, ?, ?, ?)""",
            uuid.uuid4(), product2_id, "https://images.unsplash.com/photo-1505751172876-fa1923c5c528?q=80&w=2070&auto=format&fit=crop&ixlib=rb-4.0.3&ixid=M3wxMjA3fDB8MHxwaG90by1wYWdlfHx8fGVufDB8fHx8fA%3D%3D", 1
        )
        logger.info("Images for Product 2 inserted.")
    except pyodbc.Error as e:
        logger.error(f"Failed to insert images for Product 2: {e}")
        pass

    # Images for Product 3 (Textbook)
    logger.info(f"Inserting images for Product 3: {product3_id}")
    try:
        cursor.execute(
            """INSERT INTO [ProductImage] (ImageID, ProductID, ImageURL, SortOrder) VALUES (?, ?, ?, ?)""",
            uuid.uuid4(), product3_id, "https://images.unsplash.com/photo-1507842217343-583bb7270b66?q=80&w=2106&auto=format&fit=crop&ixlib=rb-4.0.3&ixid=M3wxMjA3fDB8MHxwaG90by1wYWdlfHx8fGVufDB8fHx8fA%3D%3D", 0
        )
        logger.info("Images for Product 3 inserted.")
    except pyodbc.Error as e:
        logger.error(f"Failed to insert images for Product 3: {e}")
        pass

    # Images for Product 5 (Keyboard)
    logger.info(f"Inserting images for Product 5: {product5_id}")
    try:
        cursor.execute(
            """INSERT INTO [ProductImage] (ImageID, ProductID, ImageURL, SortOrder) VALUES (?, ?, ?, ?)""",
            uuid.uuid4(), product5_id, "https://images.unsplash.com/photo-1601412436009-d964bd32edbc?q=80&w=1964&auto=format&fit=crop&ixlib=rb-4.0.3&ixid=M3wxMjA3fDB8MHxwaG90by1wYWdlfHx8fGVufDB8fHx8fA%3D%3D", 0
        )
        cursor.execute(
            """INSERT INTO [ProductImage] (ImageID, ProductID, ImageURL, SortOrder) VALUES (?, ?, ?, ?)""",
            uuid.uuid4(), product5_id, "https://images.unsplash.com/photo-1587829741301-dc798b83add3?q=80&w=2065&auto=format&fit=crop&ixlib=rb-4.0.3&ixid=M3wxMjA3fDB8MHxwaG90by1wYWdlfHx8fGVufDB8fHx8fA%3D%3D", 1
        )
        logger.info("Images for Product 5 inserted.")
    except pyodbc.Error as e:
        logger.error(f"Failed to insert images for Product 5: {e}")
        pass

    # Images for Product 6 (Dress)
    logger.info(f"Inserting images for Product 6: {product6_id}")
    try:
        cursor.execute(
            """INSERT INTO [ProductImage] (ImageID, ProductID, ImageURL, SortOrder) VALUES (?, ?, ?, ?)""",
            uuid.uuid4(), product6_id, "https://images.unsplash.com/photo-1595777457583-95e059d581b8?q=80&w=1887&auto=format&fit=crop&ixlib=rb-4.0.3&ixid=M3wxMjA3fDB8MHxwaG90by1wYWdlfHx8fGVufDB8fHx8fA%3D%3D", 0
        )
        logger.info("Images for Product 6 inserted.")
    except pyodbc.Error as e:
        logger.error(f"Failed to insert images for Product 6: {e}")
        pass
        
    # Images for Product 9 (Desk Lamp)
    logger.info(f"Inserting images for Product 9: {product9_id}")
    try:
        cursor.execute(
            """INSERT INTO [ProductImage] (ImageID, ProductID, ImageURL, SortOrder) VALUES (?, ?, ?, ?)""",
            uuid.uuid4(), product9_id, "https://images.unsplash.com/photo-1620127682229-333804207010?q=80&w=1887&auto=format&fit=crop&ixlib=rb-4.0.3&ixid=M3wxMjA3fDB8MHxwaG90by1wYWdlfHx8fGVufDB8fHx8fA%3D%3D", 0
        )
        logger.info("Images for Product 9 inserted.")
    except pyodbc.Error as e:
        logger.error(f"Failed to insert images for Product 9: {e}")
        pass

        # --- New Images for Admin Products ---
    if product11_id: # Pxk's Drawing Tablet
        logger.info(f"Inserting images for Product 11: {product11_id}")
        try:
            cursor.execute(
                """INSERT INTO [ProductImage] (ImageID, ProductID, ImageURL, SortOrder) VALUES (?, ?, ?, ?)""",
                uuid.uuid4(), product11_id, "https://images.unsplash.com/photo-1626868019082-f5c7b3b9b4d0?q=80&w=1887&auto=format&fit=crop&ixlib=rb-4.0.3&ixid=M3wxMjA3fDB8MHxwaG90by1wYWdlfHx8fGVufDB8fHx8fA%3D%3D", 0
            )
            logger.info("Images for Product 11 inserted.")
        except pyodbc.Error as e:
            logger.error(f"Failed to insert images for Product 11: {e}")
            pass

    if product12_id: # Cyq's Sports Shoes
        logger.info(f"Inserting images for Product 12: {product12_id}")
        try:
            cursor.execute(
                """INSERT INTO [ProductImage] (ImageID, ProductID, ImageURL, SortOrder) VALUES (?, ?, ?, ?)""",
                uuid.uuid4(), product12_id, "https://images.unsplash.com/photo-1549298351-d419b4b6b66a?q=80&w=1887&auto=format&fit=crop&ixlib=rb-4.0.3&ixid=M3wxMjA3fDB8MHxwaG90by1wYWdlfHx8fGVufDB8fHx8fA%3D%3D", 0
            )
            logger.info("Images for Product 12 inserted.")
        except pyodbc.Error as e:
            logger.error(f"Failed to insert images for Product 12: {e}")
            pass

    if product13_id: # Cy's Vintage Camera
        logger.info(f"Inserting images for Product 13: {product13_id}")
        try:
            cursor.execute(
                """INSERT INTO [ProductImage] (ImageID, ProductID, ImageURL, SortOrder) VALUES (?, ?, ?, ?)""",
                uuid.uuid4(), product13_id, "https://images.unsplash.com/photo-1510127267154-1502f689e4c3?q=80&w=1887&auto=format&fit=crop&ixlib=rb-4.0.3&ixid=M3wxMjA3fDB8MHxwaG90by1wYWdlfHx8fGVufDB8fHx8fA%3D%3D", 0
            )
            logger.info("Images for Product 13 inserted.")
        except pyodbc.Error as e:
            logger.error(f"Failed to insert images for Product 13: {e}")
            pass

    if product14_id: # Ssc's Guitar
        logger.info(f"Inserting images for Product 14: {product14_id}")
        try:
            cursor.execute(
                """INSERT INTO [ProductImage] (ImageID, ProductID, ImageURL, SortOrder) VALUES (?, ?, ?, ?)""",
                uuid.uuid4(), product14_id, "https://images.unsplash.com/photo-1547035541-f7614f107f97?q=80&w=1887&auto=format&fit=crop&ixlib=rb-4.0.3&ixid=M3wxMjA3fDB8MHxwaG90by1wYWdlfHx8fGVufDB8fHx8fA%3D%3D", 0
            )
            logger.info("Images for Product 14 inserted.")
        except pyodbc.Error as e:
            logger.error(f"Failed to insert images for Product 14: {e}")
            pass

    if product15_id: # Zsq's AI Textbook
        logger.info(f"Inserting images for Product 15: {product15_id}")
        try:
            cursor.execute(
                """INSERT INTO [ProductImage] (ImageID, ProductID, ImageURL, SortOrder) VALUES (?, ?, ?, ?)""",
                uuid.uuid4(), product15_id, "https://images.unsplash.com/photo-1533519846377-16075c328d6c?q=80&w=1887&auto=format&fit=crop&ixlib=rb-4.0.3&ixid=M3wxMjA3fDB8MHxwaG90by1wYWdlfHx8fGVufDB8fHx8fA%3D%3D", 0
            )
            logger.info("Images for Product 15 inserted.")
        except pyodbc.Error as e:
            logger.error(f"Failed to insert images for Product 15: {e}")
            pass
            
    if product16_id: # Tom's Smartwatch
        logger.info(f"Inserting images for Product 16: {product16_id}")
        try:
            cursor.execute(
                """INSERT INTO [ProductImage] (ImageID, ProductID, ImageURL, SortOrder) VALUES (?, ?, ?, ?)""",
                uuid.uuid4(), product16_id, "https://images.unsplash.com/photo-1579586382025-a74070a96931?q=80&w=1887&auto=format&fit=crop&ixlib=rb-4.0.3&ixid=M3wxMjA3fDB8MHxwaG90by1wYWdlfHx8fGVufDB8fHx8fA%3D%3D", 0
            )
            logger.info("Images for Product 16 inserted.")
        except pyodbc.Error as e:
            logger.error(f"Failed to insert images for Product 16: {e}")
            pass

    if product17_id: # Pxk's Monitor
        logger.info(f"Inserting images for Product 17: {product17_id}")
        try:
            cursor.execute(
                """INSERT INTO [ProductImage] (ImageID, ProductID, ImageURL, SortOrder) VALUES (?, ?, ?, ?)""",
                uuid.uuid4(), product17_id, "https://images.unsplash.com/photo-1582234057863-fd9e061b4d08?q=80&w=2070&auto=format&fit=crop&ixlib=rb-4.0.3&ixid=M3wxMjA3fDB8MHxwaG90by1wYWdlfHx8fGVufDB8fHx8fA%3D%3D", 0
            )
            logger.info("Images for Product 17 inserted.")
        except pyodbc.Error as e:
            logger.error(f"Failed to insert images for Product 17: {e}")
            pass

    if product18_id: # Cyq's Backpack
        logger.info(f"Inserting images for Product 18: {product18_id}")
        try:
            cursor.execute(
                """INSERT INTO [ProductImage] (ImageID, ProductID, ImageURL, SortOrder) VALUES (?, ?, ?, ?)""",
                uuid.uuid4(), product18_id, "https://images.unsplash.com/photo-1558778643-987820468498?q=80&w=1887&auto=format&fit=crop&ixlib=rb-4.0.3&ixid=M3wxMjA3fDB8MHxwaG90by1wYWdlfHx8fGVufDB8fHx8fA%3D%3D", 0
            )
            logger.info("Images for Product 18 inserted.")
        except pyodbc.Error as e:
            logger.error(f"Failed to insert images for Product 18: {e}")
            pass

    if product19_id: # Cy's Painting Set
        logger.info(f"Inserting images for Product 19: {product19_id}")
        try:
            cursor.execute(
                """INSERT INTO [ProductImage] (ImageID, ProductID, ImageURL, SortOrder) VALUES (?, ?, ?, ?)""",
                uuid.uuid4(), product19_id, "https://images.unsplash.com/photo-1628189679199-4d6d1d4021a8?q=80&w=1887&auto=format&fit=crop&ixlib=rb-4.0.3&ixid=M3wxMjA3fDB8MHxwaG90by1wYWdlfHx8fGVufDB8fHx8fA%3D%3D", 0
            )
            logger.info("Images for Product 19 inserted.")
        except pyodbc.Error as e:
            logger.error(f"Failed to insert images for Product 19: {e}")
            pass

    if product20_id: # Ssc's Headset
        logger.info(f"Inserting images for Product 20: {product20_id}")
        try:
            cursor.execute(
                """INSERT INTO [ProductImage] (ImageID, ProductID, ImageURL, SortOrder) VALUES (?, ?, ?, ?)""",
                uuid.uuid4(), product20_id, "https://images.unsplash.com/photo-1546435552-32b0a1f9d1b0?q=80&w=1887&auto=format&fit=crop&ixlib=rb-4.0.3&ixid=M3wxMjA3fDB8MHxwaG90by1wYWdlfHx8fGVufDB8fHx8fA%3D%3D", 0
            )
            logger.info("Images for Product 20 inserted.")
        except pyodbc.Error as e:
            logger.error(f"Failed to insert images for Product 20: {e}")
            pass

    if product21_id: # Zsq's Algorithm Book
        logger.info(f"Inserting images for Product 21: {product21_id}")
        try:
            cursor.execute(
                """INSERT INTO [ProductImage] (ImageID, ProductID, ImageURL, SortOrder) VALUES (?, ?, ?, ?)""",
                uuid.uuid4(), product21_id, "https://images.unsplash.com/photo-1544716278-ca5e3f4abd87?q=80&w=1974&auto=format&fit=crop&ixlib=rb-4.0.3&ixid=M3wxMjA3fDB8MHxwaG90by1wYWdlfHx8fGVufDB8fHx8fA%3D%3D", 0
            )
            logger.info("Images for Product 21 inserted.")
        except pyodbc.Error as e:
            logger.error(f"Failed to insert images for Product 21: {e}")
            pass

    if product22_id: # Pxk's Projector
        logger.info(f"Inserting images for Product 22: {product22_id}")
        try:
            cursor.execute(
                """INSERT INTO [ProductImage] (ImageID, ProductID, ImageURL, SortOrder) VALUES (?, ?, ?, ?)""",
                uuid.uuid4(), product22_id, "https://images.unsplash.com/photo-1629237277884-2a149a46f6f9?q=80&w=1887&auto=format&fit=crop&ixlib=rb-4.0.3&ixid=M3wxMjA3fDB8MHxwaG90by1wYWdlfHx8fGVufDB8fHx8fA%3D%3D", 0
            )
            logger.info("Images for Product 22 inserted.")
        except pyodbc.Error as e:
            logger.error(f"Failed to insert images for Product 22: {e}")
            pass

    if product23_id: # Cyq's Dumbbells
        logger.info(f"Inserting images for Product 23: {product23_id}")
        try:
            cursor.execute(
                """INSERT INTO [ProductImage] (ImageID, ProductID, ImageURL, SortOrder) VALUES (?, ?, ?, ?)""",
                uuid.uuid4(), product23_id, "https://images.unsplash.com/photo-1579213876020-f507b9a5c8e2?q=80&w=1887&auto=format&fit=crop&ixlib=rb-4.0.3&ixid=M3wxMjA3fDB8MHxwaG90by1wYWdlfHx8fGVufDB8fHx8fA%3D%3D", 0
            )
            logger.info("Images for Product 23 inserted.")
        except pyodbc.Error as e:
            logger.error(f"Failed to insert images for Product 23: {e}")
            pass

    if product24_id: # Cy's Art Easel
        logger.info(f"Inserting images for Product 24: {product24_id}")
        try:
            cursor.execute(
                """INSERT INTO [ProductImage] (ImageID, ProductID, ImageURL, SortOrder) VALUES (?, ?, ?, ?)""",
                uuid.uuid4(), product24_id, "https://images.unsplash.com/photo-1582234057863-fd9e061b4d08?q=80&w=2070&auto=format&fit=crop&ixlib=rb-4.0.3&ixid=M3wxMjA3fDB8MHxwaG90by1wYWdlfHx8fGVufDB8fHx8fA%3D%3D", 0 # Using a generic art supply image
            )
            logger.info("Images for Product 24 inserted.")
        except pyodbc.Error as e:
            logger.error(f"Failed to insert images for Product 24: {e}")
            pass

    if product25_id: # Ssc's Drone (Rejected)
        logger.info(f"Inserting images for Product 25: {product25_id}")
        try:
            cursor.execute(
                """INSERT INTO [ProductImage] (ImageID, ProductID, ImageURL, SortOrder) VALUES (?, ?, ?, ?)""",
                uuid.uuid4(), product25_id, "https://images.unsplash.com/photo-1521405903960-9372f53412a8?q=80&w=1887&auto=format&fit=crop&ixlib=rb-4.0.3&ixid=M3wxMjA3fDB8MHxwaG90by1wYWdlfHx8fGVufDB8fHx8fA%3D%3D", 0
            )
            logger.info("Images for Product 25 inserted.")
        except pyodbc.Error as e:
            logger.error(f"Failed to insert images for Product 25: {e}")
            pass

    if product26_id: # Zsq's Robotics Kit
        logger.info(f"Inserting images for Product 26: {product26_id}")
        try:
            cursor.execute(
                """INSERT INTO [ProductImage] (ImageID, ProductID, ImageURL, SortOrder) VALUES (?, ?, ?, ?)""",
                uuid.uuid4(), product26_id, "https://images.unsplash.com/photo-1620712959950-8b431c4f0b4d?q=80&w=1887&auto=format&fit=crop&ixlib=rb-4.0.3&ixid=M3wxMjA3fDB8MHxwaG90by1wYWdlfHx8fGVufDB8fHx8fA%3D%3D", 0
            )
            logger.info("Images for Product 26 inserted.")
        except pyodbc.Error as e:
            logger.error(f"Failed to insert images for Product 26: {e}")
            pass

    conn.commit()
    logger.info("Sample product images committed.")

    # --- 4. Insert Sample Orders, Evaluations, ChatMessages ---
    # Order 1: Bob buys Alice's Laptop (Product 1)
    order1_id = uuid.uuid4()
    logger.info(f"Inserting Order 1 (Bob buys Alice's Laptop) with ID: {order1_id}")
    try:
        cursor.execute(
            """
            INSERT INTO [Order] (OrderID, SellerID, BuyerID, ProductID, Quantity, CreateTime, Status)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            order1_id, alice_id, bob_id, product1_id, 1, datetime.now(), "Completed"
        )
        logger.info("Order 1 inserted.")
    except pyodbc.Error as e:
        logger.error(f"Failed to insert Order 1: {e}")
        pass

    # Evaluation for Order 1 (Bob evaluates Alice)
    evaluation1_id = uuid.uuid4()
    logger.info(f"Inserting Evaluation 1 (Bob evaluates Alice) with ID: {evaluation1_id}")
    try:
        cursor.execute(
            """
            INSERT INTO [Evaluation] (EvaluationID, OrderID, SellerID, BuyerID, Rating, Content, CreateTime)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            evaluation1_id, order1_id, alice_id, bob_id, 5, "卖家响应迅速，商品描述属实，交易非常顺利！", datetime.now()
        )
        logger.info("Evaluation 1 inserted.")
    except pyodbc.Error as e:
        logger.error(f"Failed to insert Evaluation 1: {e}")
        pass

    # Order 2: Alice buys Bob's Camera (Product 2)
    order2_id = uuid.uuid4()
    logger.info(f"Inserting Order 2 (Alice buys Bob's Camera) with ID: {order2_id}")
    try:
        cursor.execute(
            """
            INSERT INTO [Order] (OrderID, SellerID, BuyerID, ProductID, Quantity, CreateTime, Status)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            order2_id, bob_id, alice_id, product2_id, 1, datetime.now(), "ConfirmedBySeller" # Still pending completion
        )
        logger.info("Order 2 inserted.")
    except pyodbc.Error as e:
        logger.error(f"Failed to insert Order 2: {e}")
        pass

    # ChatMessage 1: Alice to Bob about Camera
    chat1_id = uuid.uuid4()
    logger.info(f"Inserting ChatMessage 1 (Alice to Bob about Camera) with ID: {chat1_id}")
    try:
        cursor.execute(
            """
            INSERT INTO [ChatMessage] (MessageID, SenderID, ReceiverID, ProductID, Content, SendTime, IsRead)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            chat1_id, alice_id, bob_id, product2_id, "您好，请问相机最低多少钱可以出？", datetime.now(), 0
        )
        logger.info("ChatMessage 1 inserted.")
    except pyodbc.Error as e:
        logger.error(f"Failed to insert ChatMessage 1: {e}")
        pass

    # ChatMessage 2: Bob to Alice about Camera
    chat2_id = uuid.uuid4()
    logger.info(f"Inserting ChatMessage 2 (Bob to Alice about Camera) with ID: {chat2_id}")
    try:
        cursor.execute(
            """
            INSERT INTO [ChatMessage] (MessageID, SenderID, ReceiverID, ProductID, Content, SendTime, IsRead)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            chat2_id, bob_id, alice_id, product2_id, "你好，最低2700。如果真心想要可以再优惠一些。", datetime.now(), 1
        )
        logger.info("ChatMessage 2 inserted.")
    except pyodbc.Error as e:
        logger.error(f"Failed to insert ChatMessage 2: {e}")
        pass

    # Order 3: David buys Alice's Textbook (Product 3) - Pending Seller Confirmation
    order3_id = uuid.uuid4()
    logger.info(f"Inserting Order 3 (David buys Alice's Textbook) with ID: {order3_id}")
    try:
        cursor.execute(
            """
            INSERT INTO [Order] (OrderID, SellerID, BuyerID, ProductID, Quantity, CreateTime, Status)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            order3_id, alice_id, david_id, product3_id, 1, datetime.now(), "PendingSellerConfirmation"
        )
        logger.info("Order 3 inserted.")
    except pyodbc.Error as e:
        logger.error(f"Failed to insert Order 3: {e}")
        pass

    # Return Request 1: Lucy requests return for a hypothetical purchase (no matching order currently, just example)
    # To make this work, Lucy needs to have bought something first.
    # Let's assume Lucy bought Product 9 (David's Desk Lamp) and wants to return.
    # This requires an order first.
    order4_id = uuid.uuid4()
    logger.info(f"Inserting Order 4 (Lucy buys David's Desk Lamp) with ID: {order4_id}")
    try:
        cursor.execute(
            """
            INSERT INTO [Order] (OrderID, SellerID, BuyerID, ProductID, Quantity, CreateTime, Status, CompleteTime)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            order4_id, david_id, lucy_id, product9_id, 1, datetime.now(), "Completed", datetime.now()
        )
        logger.info("Order 4 inserted.")
    except pyodbc.Error as e:
        logger.error(f"Failed to insert Order 4: {e}")
        pass
    
    return_request1_id = uuid.uuid4()
    logger.info(f"Inserting Return Request 1 (Lucy for Desk Lamp) with ID: {return_request1_id}")
    try:
        cursor.execute(
            """
            INSERT INTO [ReturnRequest] (ReturnRequestID, OrderID, ReturnReason, ApplyTime, SellerAgree)
            VALUES (?, ?, ?, ?, ?)
            """,
            return_request1_id, order4_id, "商品与描述不符，台灯有划痕。", datetime.now(), None # None means not processed yet
        )
        logger.info("Return Request 1 inserted.")
    except pyodbc.Error as e:
        logger.error(f"Failed to insert Return Request 1: {e}")
        pass

    # New Order: Pxk buys Cyq's Sports Shoes (Product 12)
    order_pxk_cyq_shoes = uuid.uuid4()
    if pxk_id and cyq_id and product12_id:
        logger.info(f"Inserting Order (Pxk buys Cyq's Sports Shoes) with ID: {order_pxk_cyq_shoes}")
        try:
            cursor.execute(
                """
                INSERT INTO [Order] (OrderID, SellerID, BuyerID, ProductID, Quantity, CreateTime, Status)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                order_pxk_cyq_shoes, cyq_id, pxk_id, product12_id, 1, datetime.now(), "Completed"
            )
            logger.info("Order (Pxk buys Cyq's Sports Shoes) inserted.")
        except pyodbc.Error as e:
            logger.error(f"Failed to insert Order (Pxk buys Cyq's Sports Shoes): {e}")
            pass

    # New Evaluation: Pxk evaluates Cyq for Sports Shoes
    eval_pxk_cyq_shoes = uuid.uuid4()
    if pxk_id and cyq_id and order_pxk_cyq_shoes:
        logger.info(f"Inserting Evaluation (Pxk evaluates Cyq) with ID: {eval_pxk_cyq_shoes}")
        try:
            cursor.execute(
                """
                INSERT INTO [Evaluation] (EvaluationID, OrderID, SellerID, BuyerID, Rating, Content, CreateTime)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                eval_pxk_cyq_shoes, order_pxk_cyq_shoes, cyq_id, pxk_id, 5, "鞋子很新，描述准确，卖家回复及时，好评！", datetime.now()
            )
            logger.info("Evaluation (Pxk evaluates Cyq) inserted.")
        except pyodbc.Error as e:
            logger.error(f"Failed to insert Evaluation (Pxk evaluates Cyq): {e}")
            pass

    # New Order: Cy buys Ssc's Guitar (Product 14) - Pending Confirmation
    order_cy_ssc_guitar = uuid.uuid4()
    if cy_id and ssc_id and product14_id:
        logger.info(f"Inserting Order (Cy buys Ssc's Guitar) with ID: {order_cy_ssc_guitar}")
        try:
            cursor.execute(
                """
                INSERT INTO [Order] (OrderID, SellerID, BuyerID, ProductID, Quantity, CreateTime, Status)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                order_cy_ssc_guitar, ssc_id, cy_id, product14_id, 1, datetime.now(), "PendingSellerConfirmation"
            )
            logger.info("Order (Cy buys Ssc's Guitar) inserted.")
        except pyodbc.Error as e:
            logger.error(f"Failed to insert Order (Cy buys Ssc's Guitar): {e}")
            pass

    # New Chat: Cy to Ssc about Guitar
    chat_cy_ssc_guitar = uuid.uuid4()
    if cy_id and ssc_id and product14_id:
        logger.info(f"Inserting Chat (Cy to Ssc about Guitar) with ID: {chat_cy_ssc_guitar}")
        try:
            cursor.execute(
                """
                INSERT INTO [ChatMessage] (MessageID, SenderID, ReceiverID, ProductID, Content, SendTime, IsRead)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                chat_cy_ssc_guitar, cy_id, ssc_id, product14_id, "您好，吉他是在校内交易吗？", datetime.now(), 0
            )
            logger.info("Chat (Cy to Ssc about Guitar) inserted.")
        except pyodbc.Error as e:
            logger.error(f"Failed to insert Chat (Cy to Ssc about Guitar): {e}")
            pass

    # New Order: Zsq buys Pxk's Monitor (Product 17)
    order_zsq_pxk_monitor = uuid.uuid4()
    if zsq_id and pxk_id and product17_id:
        logger.info(f"Inserting Order (Zsq buys Pxk's Monitor) with ID: {order_zsq_pxk_monitor}")
        try:
            cursor.execute(
                """
                INSERT INTO [Order] (OrderID, SellerID, BuyerID, ProductID, Quantity, CreateTime, Status)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                order_zsq_pxk_monitor, pxk_id, zsq_id, product17_id, 1, datetime.now(), "Completed"
            )
            logger.info("Order (Zsq buys Pxk's Monitor) inserted.")
        except pyodbc.Error as e:
            logger.error(f"Failed to insert Order (Zsq buys Pxk's Monitor): {e}")
            pass

    # New Evaluation: Zsq evaluates Pxk for Monitor
    eval_zsq_pxk_monitor = uuid.uuid4()
    if zsq_id and pxk_id and order_zsq_pxk_monitor:
        logger.info(f"Inserting Evaluation (Zsq evaluates Pxk) with ID: {eval_zsq_pxk_monitor}")
        try:
            cursor.execute(
                """
                INSERT INTO [Evaluation] (EvaluationID, OrderID, SellerID, BuyerID, Rating, Content, CreateTime)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                eval_zsq_pxk_monitor, order_zsq_pxk_monitor, pxk_id, zsq_id, 4, "显示器状态不错，可惜附赠的线材有点短。", datetime.now()
            )
            logger.info("Evaluation (Zsq evaluates Pxk) inserted.")
        except pyodbc.Error as e:
            logger.error(f"Failed to insert Evaluation (Zsq evaluates Pxk): {e}")
            pass

    conn.commit()
    logger.info("Sample orders, evaluations, chat messages committed.")
    logger.info("Finished inserting sample data.")

async def main():
    parser = argparse.ArgumentParser(description="初始化SQL Server数据库，创建表、存储过程和触发器。")
    parser.add_argument("--db-name", type=str, help="指定要操作的数据库名称，默认为环境变量DATABASE_NAME。")
    parser.add_argument("--drop-existing", action="store_true", help="如果数据库已存在，先删除它。")
    parser.add_argument("--continue-on-error", action="store_true", 
                        help="执行SQL文件时，即使遇到错误也继续执行下一个语句。")
    
    args = parser.parse_args()

    conn = None
    try:
        conn = get_db_connection(args.db_name)
        
        # 获取当前脚本的目录
        script_dir = os.path.dirname(__file__)

        # 定义需要执行的SQL文件顺序
        # 确保文件存在且路径正确
        # 定义 SQL 文件执行顺序
        # 1. 创建表
        # 2. 创建存储过程
        # 3. 创建触发器
        sql_files_to_execute = [
            os.path.join(script_dir, "tables", "01_create_tables.sql"),
            os.path.join(script_dir, "procedures", "01_user_procedures.sql"),
            os.path.join(script_dir, "procedures", "02_product_procedures.sql"),
            os.path.join(script_dir, "procedures", "03_trade_procedures.sql"),
            os.path.join(script_dir, "procedures", "04_image_procedures.sql"),
            os.path.join(script_dir, "procedures", "05_admin_procedures.sql"),
            os.path.join(script_dir, "procedures", "06_evaluation_procedures.sql"),
            os.path.join(script_dir, "procedures", "07_chat_procedures.sql"),
            os.path.join(script_dir, "triggers", "01_product_triggers.sql"),
            os.path.join(script_dir, "triggers", "02_order_triggers.sql"),
            os.path.join(script_dir, "triggers", "03_evaluation_triggers.sql"),
        ]
        
       # 检查所有SQL文件是否存在
        for f in sql_files_to_execute:
            if not os.path.exists(f):
                logger.error(f"SQL文件不存在: {f}")
                sys.exit(1)
        
        # 执行SQL文件
        for sql_file in sql_files_to_execute:
            if not execute_sql_file(conn, sql_file, args.continue_on_error):
                logger.error(f"执行 {sql_file} 失败，停止初始化。")
                sys.exit(1)
        
        # 调用函数创建管理员用户
        logger.info("开始创建管理员账户...")
        create_admin_users(conn)
        logger.info("管理员账户创建完成。")

        # 调用函数插入示例数据
        logger.info("开始插入示例数据...")
        await insert_sample_data(conn, logger) # Call the async function
        logger.info("示例数据插入完成。")

        logger.info("数据库初始化成功！")
        
    except ValueError as ve:
        logger.error(f"配置错误: {ve}")
        sys.exit(1)
    except pyodbc.Error as e:
        logger.error(f"数据库操作失败: {e}", exc_info=True)
        sys.exit(1)
    except Exception as e:
        logger.error(f"发生未知错误: {e}", exc_info=True)
        sys.exit(1)
    finally:
        if conn:
            try:
                conn.close()
                logger.info("数据库连接已关闭。")
            except pyodbc.Error as e:
                logger.error(f"关闭数据库连接失败: {e}")

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())