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
            "fmt": "%(levelname)s | %(asctime)s | %(name)s | %(message)s",
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
    Returns:
        dict: A dictionary mapping admin usernames to their UserIDs (UUIDs).
    """
    logger.info("--- 开始创建开发者管理员账户 ---")
    cursor = conn.cursor()
    
    admin_users_data = [
        {"username": "siyuantao", "email": "siyuantao@bjtu.edu.cn", "major": "软件工程", "phone": "13800000001","avatar_url": "/uploads/user_siyuantao.jpg"}, # Updated AvatarUrl
        {"username": "cyq", "email": "23301003@bjtu.edu.cn", "major": "计算机科学与技术", "phone": "13800000002","avatar_url": "/uploads/user_cyq.jpg"}, # Added AvatarUrl
        {"username": "cy", "email": "23301002@bjtu.edu.cn", "major": "计算机科学与技术", "phone": "13800000003","avatar_url": "/uploads/user_cy.jpg"}, # Added AvatarUrl
        {"username": "ssc", "email": "23301011@bjtu.edu.cn", "major": "软件工程", "phone": "13800000004","avatar_url": "/uploads/user_ssc.jpg"}, # Added AvatarUrl
        {"username": "zsq", "email": "23301027@bjtu.edu.cn", "major": "人工智能", "phone": "13800000005","avatar_url": "/uploads/user_zsq.jpg"}, # Added AvatarUrl
    ]
    
    created_admin_ids = {} # To store created IDs
    
    for user_data in admin_users_data:
        try:
            check_query = "SELECT UserID FROM [User] WHERE UserName = ?" # Change to select UserID if exists
            check_params = (user_data['username'],)
            cursor.execute(check_query, check_params)
            existing_user_id = cursor.fetchone()
            
            if existing_user_id:
                user_id_from_db = uuid.UUID(existing_user_id[0])
                logger.info(f"  用户 {user_data['username']} ({user_data.get('email', '无邮箱')}) 已存在，跳过创建. UserID: {user_id_from_db}")
                created_admin_ids[user_data['username']] = user_id_from_db
            else:
                logger.info(f"  创建用户: {user_data['username']} ({user_data.get('email', '无邮箱')})")

                is_staff_value = 1
                is_super_admin_value = 0
                if user_data.get('email') == 'siyuantao@bjtu.edu.cn':
                    is_super_admin_value = 1

                hashed_password = hash_password("password123")
                new_user_id = uuid.uuid4() # Generate UUID here

                cursor.execute("""
                    INSERT INTO [User] (UserID, UserName, Password, Email, Status, Credit, IsStaff, IsVerified, Major, PhoneNumber, AvatarUrl, JoinTime, IsSuperAdmin)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, GETDATE(), ?)
                """, (
                    new_user_id, # Use the generated UUID
                    user_data['username'],
                    hashed_password,
                    user_data.get('email'),
                    'Active',
                    100,
                    is_staff_value,
                    1,
                    user_data.get('major'),
                    user_data['phone'],
                    user_data.get('avatar_url'), # 添加 AvatarUrl
                    is_super_admin_value
                ))
                conn.commit()
                logger.info(f"  用户 {user_data['username']} 创建成功. UserID: {new_user_id}")
                created_admin_ids[user_data['username']] = new_user_id

        except pyodbc.IntegrityError as e:
            sqlstate = e.args[0]
            error_message = e.args[1] if len(e.args) > 1 else str(e)
            logger.error(f"  创建用户 {user_data['username']} 失败 (Integrity Error): {sqlstate} - {error_message}")
            conn.rollback()
        except Exception as e:
            logger.error(f"  创建用户 {user_data['username']} 失败: {e}", exc_info=True)
            if conn:
                 try:
                      conn.rollback()
                 except Exception as rb_e:
                      logger.error(f"Error during rollback: {rb_e}")

    logger.info("--- 开发者管理员账户创建完成 ---")
    return created_admin_ids

# Add this utility function for password hashing, mirroring backend's auth_service
def hash_password(password: str) -> str:
    """Hashes a password using PBKDF2 with SHA256."""
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 100000)
    # Store salt and hashed password together, separated by a colon, in hex format
    return f"{salt.hex()}:{dk.hex()}"

# Add this function for inserting sample data
async def insert_sample_data(conn: pyodbc.Connection, logger: logging.Logger, admin_user_ids: dict):

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
            "/uploads/user_alice.jpg", # 更换为本地图片链接
            "热爱编程和二手交易的学生，喜欢分享好物。", "13800000006", datetime.now(), datetime.now()
        )
        logger.info("User Alice inserted.")
    except pyodbc.Error as e:
        logger.error(f"Failed to insert user Alice: {e}")
        raise # Change pass to raise

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
            "/uploads/user_bob.jpg", # 更换为本地图片链接
            "喜欢电子产品，经常出售闲置物品，乐于助人。", "13900000002", datetime.now(), datetime.now()
        )
        logger.info("User Bob inserted.")
    except pyodbc.Error as e:
        logger.error(f"Failed to insert user Bob: {e}")
        raise # Change pass to raise

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
            "/uploads/user_carol.jpg", # 更换为本地图片链接
            "一个新用户，还没有完成认证，目前账户已禁用。", "13700000003", datetime.now(), datetime.now()
        )
        logger.info("User Carol inserted.")
    except pyodbc.Error as e:
        logger.error(f"Failed to insert user Carol: {e}")
        raise # Change pass to raise

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
            "/uploads/user_david.jpg", # 更换为本地图片链接
            "一名对电子产品和开源硬件感兴趣的用户。", "13600000004", datetime.now(), datetime.now()
        )
        logger.info("User David inserted.")
    except pyodbc.Error as e:
        logger.error(f"Failed to insert user David: {e}")
        raise # Change pass to raise

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
            "/uploads/user_eve.jpg", # 更换为本地图片链接
            "喜欢阅读和探索自然的新用户，待认证。", "13500000005", datetime.now(), datetime.now() # 添加了手机号
        )
        logger.info("User Eve inserted.")
    except pyodbc.Error as e:
        logger.error(f"Failed to insert user Eve: {e}")
        raise # Change pass to raise

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
            "/uploads/user_tom.jpg",
            "平台管理员，负责维护社区秩序。", "13400000006", datetime.now(), datetime.now()
        )
        logger.info("User Tom (Admin) inserted.")
    except pyodbc.Error as e:
        logger.error(f"Failed to insert user Tom (Admin): {e}")
        raise # Change pass to raise

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
            "/uploads/user_lucy.jpg",
            "信用分较低，但正在努力改进。", "13300000007", datetime.now(), datetime.now()
        )
        logger.info("User Lucy inserted.")
    except pyodbc.Error as e:
        logger.error(f"Failed to insert user Lucy: {e}")
        raise # Change pass to raise

        # For now, let's assume `create_admin_users` has already defined and inserted `siyuaotao`.
    # We should get siyuaotao's ID from the User table.
    siyuaotao_id = admin_user_ids.get('siyuantao')
    cyq_id = admin_user_ids.get('cyq')
    cy_id = admin_user_ids.get('cy')
    ssc_id = admin_user_ids.get('ssc')
    zsq_id = admin_user_ids.get('zsq')
    # If admin IDs can't be retrieved, subsequent product insertions for them will fail.
    # This is a critical error for test data.
    if not all([siyuaotao_id, cyq_id, cy_id, ssc_id, zsq_id]):
        logger.error(f"Failed to retrieve all expected admin user IDs from create_admin_users: siyuaotao={siyuaotao_id}, cyq={cyq_id}, cy={cy_id}, ssc={ssc_id}, zsq={zsq_id}")
        raise ValueError("Critical: Not all admin user IDs were successfully created or retrieved.")

    logger.info(f"Retrieved admin IDs: siyuaotao={siyuaotao_id}, cyq={cyq_id}, cy={cy_id}, ssc={ssc_id}, zsq={zsq_id}")

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
            2, 6200.00, datetime.now(), "Active"
        )
        logger.info("Product 1 inserted.")
    except pyodbc.Error as e:
        logger.error(f"Failed to insert product 1: {e}")
        raise # Change pass to raise

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
            2, 2750.00, datetime.now(), "Active"
        )
        logger.info("Product 2 inserted.")
    except pyodbc.Error as e:
        logger.error(f"Failed to insert product 2: {e}")
        raise # Change pass to raise

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
        raise # Change pass to raise

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
            2, 850.00, datetime.now(), "Withdrawn" # 改为 Withdrawn, 数量为1
        )
        logger.info("Product 4 inserted.")
    except pyodbc.Error as e:
        logger.error(f"Failed to insert product 4: {e}")
        raise # Change pass to raise

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
            2, 700.00, datetime.now(), "Active"
        )
        logger.info("Product 5 (Keyboard) inserted.")
    except pyodbc.Error as e:
        logger.error(f"Failed to insert product 5: {e}")
        raise # Change pass to raise

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
            2, 120.00, datetime.now(), "PendingReview"
        )
        logger.info("Product 6 (Dress) inserted.")
    except pyodbc.Error as e:
        logger.error(f"Failed to insert product 6: {e}")
        raise # Change pass to raise

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
            2, 1500.00, datetime.now(), "Rejected"
        )
        logger.info("Product 7 (Graphics Card - Rejected) inserted.")
    except pyodbc.Error as e:
        logger.error(f"Failed to insert product 7: {e}")
        raise # Change pass to raise

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
        raise # Change pass to raise

    # Product 9: David's Desk Lamp (Active)
    product9_id = uuid.uuid4()
    logger.info(f"Inserting product 9 (Desk Lamp) for David with ID: {product9_id}")
    try:
        cursor.execute(
            """
            INSERT INTO [Product] (ProductID, OwnerID, CategoryName, ProductName, Description, Quantity, Price, PostTime, Status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            product9_id, david_id, "家居日用", "小米LED智能台灯Pro", "可调节亮度和色温，保护视力，几乎全新。",
            2, 180.00, datetime.now(), "Active"
        )
        logger.info("Product 9 (Desk Lamp) inserted.")
    except pyodbc.Error as e:
        logger.error(f"Failed to insert product 9: {e}")
        raise # Change pass to raise

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
            2, 280.00, datetime.now(), "Withdrawn"
        )
        logger.info("Product 10 (Skincare Set - Withdrawn) inserted.")
    except pyodbc.Error as e:
        logger.error(f"Failed to insert product 10: {e}")
        raise # Change pass to raise

        # --- New Products for Admin Users ---

    # Product 11: siyuaotao's Drawing Tablet (Active)
    product11_id = uuid.uuid4()
    if siyuaotao_id:
        logger.info(f"Inserting product 11 (Drawing Tablet) for siyuaotao with ID: {product11_id}")
        try:
            cursor.execute(
                """
                INSERT INTO [Product] (ProductID, OwnerID, CategoryName, ProductName, Description, Quantity, Price, PostTime, Status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                product11_id, siyuaotao_id, "电子产品", "Wacom Intuos 绘图板", "9成新，很少使用，适合设计专业学生。",
                2, 550.00, datetime.now(), "Active"
            )
            logger.info("Product 11 (Drawing Tablet) inserted.")
        except pyodbc.Error as e:
            logger.error(f"Failed to insert product 11: {e}")
            raise # Change pass to raise

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
                2, 380.00, datetime.now(), "Active"
            )
            logger.info("Product 12 (Sports Shoes) inserted.")
        except pyodbc.Error as e:
            logger.error(f"Failed to insert product 12: {e}")
            raise # Change pass to raise

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
                2, 1500.00, datetime.now(), "PendingReview"
            )
            logger.info("Product 13 (Vintage Camera) inserted.")
        except pyodbc.Error as e:
            logger.error(f"Failed to insert product 13: {e}")
            raise # Change pass to raise

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
                2, 450.00, datetime.now(), "Active"
            )
            logger.info("Product 14 (Guitar) inserted.")
        except pyodbc.Error as e:
            logger.error(f"Failed to insert product 14: {e}")
            raise # Change pass to raise

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
                2, 99.00, datetime.now(), "Active"
            )
            logger.info("Product 15 (AI Textbook) inserted.")
        except pyodbc.Error as e:
            logger.error(f"Failed to insert product 15: {e}")
            raise # Change pass to raise

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
            raise # Change pass to raise

    # Product 17: siyuaotao's Monitor (Active)
    product17_id = uuid.uuid4()
    if siyuaotao_id:
        logger.info(f"Inserting product 17 (Monitor) for siyuaotao with ID: {product17_id}")
        try:
            cursor.execute(
                """
                INSERT INTO [Product] (ProductID, OwnerID, CategoryName, ProductName, Description, Quantity, Price, PostTime, Status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                product17_id, siyuaotao_id, "电子产品", "戴尔27英寸2K显示器", "IPS面板，色彩准确，适合设计和日常使用。",
                2, 1500.00, datetime.now(), "Active"
            )
            logger.info("Product 17 (Monitor) inserted.")
        except pyodbc.Error as e:
            logger.error(f"Failed to insert product 17: {e}")
            raise # Change pass to raise

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
                2, 280.00, datetime.now(), "Active"
            )
            logger.info("Product 18 (Backpack) inserted.")
        except pyodbc.Error as e:
            logger.error(f"Failed to insert product 18: {e}")
            raise # Change pass to raise

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
                2, 150.00, datetime.now(), "Active"
            )
            logger.info("Product 19 (Painting Set) inserted.")
        except pyodbc.Error as e:
            logger.error(f"Failed to insert product 19: {e}")
            raise # Change pass to raise

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
                product20_id, ssc_id, "电子产品", "HyperX Cloud Stinger Core 耳机", "轻量舒适，音质清晰，适合游戏和日常使用。",
                2, 200.00, datetime.now(), "Active"
            )
            logger.info("Product 20 (Headset) inserted.")
        except pyodbc.Error as e:
            logger.error(f"Failed to insert product 20: {e}")
            raise # Change pass to raise

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
                product21_id, zsq_id, "书籍文具", "《算法导论》（第3版）", "计算机科学经典教材，英文原版，9成新。",
                2, 150.00, datetime.now(), "Active"
            )
            logger.info("Product 21 (Algorithm Book) inserted.")
        except pyodbc.Error as e:
            logger.error(f"Failed to insert product 21: {e}")
            raise # Change pass to raise

    # Product 22: siyuaotao's Projector (Active)
    product22_id = uuid.uuid4()
    if siyuaotao_id:
        logger.info(f"Inserting product 22 (Projector) for siyuaotao with ID: {product22_id}")
        try:
            cursor.execute(
                """
                INSERT INTO [Product] (ProductID, OwnerID, CategoryName, ProductName, Description, Quantity, Price, PostTime, Status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                product22_id, siyuaotao_id, "电子产品", "迷你家用投影仪", "小巧便携，支持1080P，适合宿舍观影。",
                2, 600.00, datetime.now(), "Active"
            )
            logger.info("Product 22 (Projector) inserted.")
        except pyodbc.Error as e:
            logger.error(f"Failed to insert product 22: {e}")
            raise # Change pass to raise

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
                product23_id, cyq_id, "运动户外", "可调节哑铃套装（10kg）", "家用健身器材，方便收纳，几乎全新。",
                2, 250.00, datetime.now(), "Active"
            )
            logger.info("Product 23 (Dumbbells) inserted.")
        except pyodbc.Error as e:
            logger.error(f"Failed to insert product 23: {e}")
            raise # Change pass to raise

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
                product24_id, cy_id, "文体用品", "便携式画架", "铝合金材质，带收纳袋，适合户外写生。",
                2, 180.00, datetime.now(), "PendingReview"
            )
            logger.info("Product 24 (Art Easel) inserted.")
        except pyodbc.Error as e:
            logger.error(f"Failed to insert product 24: {e}")
            raise # Change pass to raise

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
                product25_id, ssc_id, "电子产品", "大疆Mini 2无人机（已损坏）", "摔过一次，摄像头故障，可用于零件。", # 描述可能导致拒绝
                2, 800.00, datetime.now(), "Rejected"
            )
            logger.info("Product 25 (Drone) inserted.")
        except pyodbc.Error as e:
            logger.error(f"Failed to insert product 25: {e}")
            raise # Change pass to raise

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
                product26_id, zsq_id, "电子产品", "Arduino智能小车套件", "全新未组装，附赠教程，适合机器人入门学习。",
                2, 300.00, datetime.now(), "Active"
            )
            logger.info("Product 26 (Robotics Kit) inserted.")
        except pyodbc.Error as e:
            logger.error(f"Failed to insert product 26: {e}")
            raise # Change pass to raise

    conn.commit()
    logger.info("Sample products committed.")

    # --- 3. Insert Sample Product Images ---
    # Images for Product 1 (Laptop) - (已存在, 更新URL)
    logger.info(f"Inserting images for Product 1: {product1_id}")
    try:
        cursor.execute(
            """INSERT INTO [ProductImage] (ImageID, ProductID, ImageURL, SortOrder) VALUES (?, ?, ?, ?)""",
            uuid.uuid4(), product1_id, "/uploads/product1_1.jpg", 0
        )
        cursor.execute(
            """INSERT INTO [ProductImage] (ImageID, ProductID, ImageURL, SortOrder) VALUES (?, ?, ?, ?)""",
            uuid.uuid4(), product1_id, "/uploads/product1_2.jpg", 1
        )
        cursor.execute(
            """INSERT INTO [ProductImage] (ImageID, ProductID, ImageURL, SortOrder) VALUES (?, ?, ?, ?)""",
            uuid.uuid4(), product1_id, "/uploads/product1_3.jpg", 2
        )
        logger.info("Images for Product 1 inserted.")
    except pyodbc.Error as e:
        logger.error(f"Failed to insert images for Product 1: {e}")
        raise # Change pass to raise

    # Images for Product 2 (Camera) - (已存在, 更新URL)
    logger.info(f"Inserting images for Product 2: {product2_id}")
    try:
        cursor.execute(
            """INSERT INTO [ProductImage] (ImageID, ProductID, ImageURL, SortOrder) VALUES (?, ?, ?, ?)""",
            uuid.uuid4(), product2_id, "/uploads/product2_1.jpg", 0
        )
        cursor.execute(
            """INSERT INTO [ProductImage] (ImageID, ProductID, ImageURL, SortOrder) VALUES (?, ?, ?, ?)""",
            uuid.uuid4(), product2_id, "/uploads/product2_2.jpg", 1
        )
        logger.info("Images for Product 2 inserted.")
    except pyodbc.Error as e:
        logger.error(f"Failed to insert images for Product 2: {e}")
        raise # Change pass to raise

    # Images for Product 3 (Textbook)
    logger.info(f"Inserting images for Product 3: {product3_id}")
    try:
        cursor.execute(
            """INSERT INTO [ProductImage] (ImageID, ProductID, ImageURL, SortOrder) VALUES (?, ?, ?, ?)""",
            uuid.uuid4(), product3_id, "/uploads/product3_1.jpg", 0
        )
        logger.info("Images for Product 3 inserted.")
    except pyodbc.Error as e:
        logger.error(f"Failed to insert images for Product 3: {e}")
        raise # Change pass to raise

    # Images for Product 4 (bicycle)
    logger.info(f"Inserting images for Product 4: {product4_id}")
    try:
        cursor.execute(
            """INSERT INTO [ProductImage] (ImageID, ProductID, ImageURL, SortOrder) VALUES (?, ?, ?, ?)""",
            uuid.uuid4(), product4_id, "/uploads/product4_1.jpg", 0
        )
        logger.info("Images for Product 4 inserted.")
    except pyodbc.Error as e:
        logger.error(f"Failed to insert images for Product 4: {e}")
        raise # Change pass to raise

    # Images for Product 5 (Keyboard)
    logger.info(f"Inserting images for Product 5: {product5_id}")
    try:
        cursor.execute(
            """INSERT INTO [ProductImage] (ImageID, ProductID, ImageURL, SortOrder) VALUES (?, ?, ?, ?)""",
            uuid.uuid4(), product5_id, "/uploads/product5_1.jpg", 0
        )
        cursor.execute(
            """INSERT INTO [ProductImage] (ImageID, ProductID, ImageURL, SortOrder) VALUES (?, ?, ?, ?)""",
            uuid.uuid4(), product5_id, "/uploads/product5_2.jpg", 1
        )
        logger.info("Images for Product 5 inserted.")
    except pyodbc.Error as e:
        logger.error(f"Failed to insert images for Product 5: {e}")
        raise # Change pass to raise

    # Images for Product 6 (Dress)
    logger.info(f"Inserting images for Product 6: {product6_id}")
    try:
        cursor.execute(
            """INSERT INTO [ProductImage] (ImageID, ProductID, ImageURL, SortOrder) VALUES (?, ?, ?, ?)""",
            uuid.uuid4(), product6_id, "/uploads/product6_1.jpg", 0
        )
        logger.info("Images for Product 6 inserted.")
    except pyodbc.Error as e:
        logger.error(f"Failed to insert images for Product 6: {e}")
        raise # Change pass to raise

    # Images for Product 7 (显卡)
    logger.info(f"Inserting images for Product 7: {product7_id}")
    try:
        cursor.execute(
            """INSERT INTO [ProductImage] (ImageID, ProductID, ImageURL, SortOrder) VALUES (?, ?, ?, ?)""",
            uuid.uuid4(), product7_id, "/uploads/product7_1.jpg", 0
        )
        logger.info("Images for Product 7 inserted.")
    except pyodbc.Error as e:
        logger.error(f"Failed to insert images for Product 7: {e}")
        raise # Change pass to raise

    # Images for Product 8 (Desk)
    logger.info(f"Inserting images for Product 8: {product8_id}")
    try:
        cursor.execute(
            """INSERT INTO [ProductImage] (ImageID, ProductID, ImageURL, SortOrder) VALUES (?, ?, ?, ?)""",
            uuid.uuid4(), product8_id, "/uploads/product8_1.jpg", 0
        )
        logger.info("Images for Product 8 inserted.")
    except pyodbc.Error as e:
        logger.error(f"Failed to insert images for Product 8: {e}")
        raise # Change pass to raise
        
    # Images for Product 9 (Desk Lamp)
    logger.info(f"Inserting images for Product 9: {product9_id}")
    try:
        cursor.execute(
            """INSERT INTO [ProductImage] (ImageID, ProductID, ImageURL, SortOrder) VALUES (?, ?, ?, ?)""",
            uuid.uuid4(), product9_id, "/uploads/product9_1.jpg", 0
        )
        logger.info("Images for Product 9 inserted.")
    except pyodbc.Error as e:
        logger.error(f"Failed to insert images for Product 9: {e}")
        raise # Change pass to raise

    # Images for Product 10 (Desk)
    logger.info(f"Inserting images for Product 10: {product10_id}")
    try:
        cursor.execute(
            """INSERT INTO [ProductImage] (ImageID, ProductID, ImageURL, SortOrder) VALUES (?, ?, ?, ?)""",
            uuid.uuid4(), product10_id, "/uploads/product10_1.jpg", 0
        )
        logger.info("Images for Product 10 inserted.")
    except pyodbc.Error as e:
        logger.error(f"Failed to insert images for Product 10: {e}")
        raise # Change pass to raise

        # --- New Images for Admin Products ---
    if product11_id: # siyuaotao's Drawing Tablet
        logger.info(f"Inserting images for Product 11: {product11_id}")
        try:
            cursor.execute(
                """INSERT INTO [ProductImage] (ImageID, ProductID, ImageURL, SortOrder) VALUES (?, ?, ?, ?)""",
                uuid.uuid4(), product11_id, "/uploads/product11_1.jpg", 0
            )
            logger.info("Images for Product 11 inserted.")
        except pyodbc.Error as e:
            logger.error(f"Failed to insert images for Product 11: {e}")
            raise # Change pass to raise

    if product12_id: # Cyq's Sports Shoes
        logger.info(f"Inserting images for Product 12: {product12_id}")
        try:
            cursor.execute(
                """INSERT INTO [ProductImage] (ImageID, ProductID, ImageURL, SortOrder) VALUES (?, ?, ?, ?)""",
                uuid.uuid4(), product12_id, "/uploads/product12_1.jpg", 0
            )
            logger.info("Images for Product 12 inserted.")
        except pyodbc.Error as e:
            logger.error(f"Failed to insert images for Product 12: {e}")
            raise # Change pass to raise

    if product13_id: # Cy's Vintage Camera
        logger.info(f"Inserting images for Product 13: {product13_id}")
        try:
            cursor.execute(
                """INSERT INTO [ProductImage] (ImageID, ProductID, ImageURL, SortOrder) VALUES (?, ?, ?, ?)""",
                uuid.uuid4(), product13_id, "/uploads/product13_1.jpg", 0
            )
            logger.info("Images for Product 13 inserted.")
        except pyodbc.Error as e:
            logger.error(f"Failed to insert images for Product 13: {e}")
            raise # Change pass to raise

    if product14_id: # Ssc's Guitar
        logger.info(f"Inserting images for Product 14: {product14_id}")
        try:
            cursor.execute(
                """INSERT INTO [ProductImage] (ImageID, ProductID, ImageURL, SortOrder) VALUES (?, ?, ?, ?)""",
                uuid.uuid4(), product14_id, "/uploads/product14_1.jpg", 0
            )
            logger.info("Images for Product 14 inserted.")
        except pyodbc.Error as e:
            logger.error(f"Failed to insert images for Product 14: {e}")
            raise # Change pass to raise

    if product15_id: # Zsq's AI Textbook
        logger.info(f"Inserting images for Product 15: {product15_id}")
        try:
            cursor.execute(
                """INSERT INTO [ProductImage] (ImageID, ProductID, ImageURL, SortOrder) VALUES (?, ?, ?, ?)""",
                uuid.uuid4(), product15_id, "/uploads/product15_1.jpg", 0
            )
            logger.info("Images for Product 15 inserted.")
        except pyodbc.Error as e:
            logger.error(f"Failed to insert images for Product 15: {e}")
            raise # Change pass to raise
            
    if product16_id: # Tom's Smartwatch
        logger.info(f"Inserting images for Product 16: {product16_id}")
        try:
            cursor.execute(
                """INSERT INTO [ProductImage] (ImageID, ProductID, ImageURL, SortOrder) VALUES (?, ?, ?, ?)""",
                uuid.uuid4(), product16_id, "/uploads/product16_1.jpg", 0
            )
            logger.info("Images for Product 16 inserted.")
        except pyodbc.Error as e:
            logger.error(f"Failed to insert images for Product 16: {e}")
            raise # Change pass to raise

    if product17_id: # siyuaotao's Monitor
        logger.info(f"Inserting images for Product 17: {product17_id}")
        try:
            cursor.execute(
                """INSERT INTO [ProductImage] (ImageID, ProductID, ImageURL, SortOrder) VALUES (?, ?, ?, ?)""",
                uuid.uuid4(), product17_id, "/uploads/product17_1.jpg", 0
            )
            logger.info("Images for Product 17 inserted.")
        except pyodbc.Error as e:
            logger.error(f"Failed to insert images for Product 17: {e}")
            raise # Change pass to raise

    if product18_id: # Cyq's Backpack
        logger.info(f"Inserting images for Product 18: {product18_id}")
        try:
            cursor.execute(
                """INSERT INTO [ProductImage] (ImageID, ProductID, ImageURL, SortOrder) VALUES (?, ?, ?, ?)""",
                uuid.uuid4(), product18_id, "/uploads/product18_1.jpg", 0
            )
            logger.info("Images for Product 18 inserted.")
        except pyodbc.Error as e:
            logger.error(f"Failed to insert images for Product 18: {e}")
            raise # Change pass to raise

    if product19_id: # Cy's Painting Set
        logger.info(f"Inserting images for Product 19: {product19_id}")
        try:
            cursor.execute(
                """INSERT INTO [ProductImage] (ImageID, ProductID, ImageURL, SortOrder) VALUES (?, ?, ?, ?)""",
                uuid.uuid4(), product19_id, "/uploads/product19_1.jpg", 0
            )
            logger.info("Images for Product 19 inserted.")
        except pyodbc.Error as e:
            logger.error(f"Failed to insert images for Product 19: {e}")
            raise # Change pass to raise

    if product20_id: # Ssc's Headset
        logger.info(f"Inserting images for Product 20: {product20_id}")
        try:
            cursor.execute(
                """INSERT INTO [ProductImage] (ImageID, ProductID, ImageURL, SortOrder) VALUES (?, ?, ?, ?)""",
                uuid.uuid4(), product20_id, "/uploads/product20_1.jpg", 0
            )
            logger.info("Images for Product 20 inserted.")
        except pyodbc.Error as e:
            logger.error(f"Failed to insert images for Product 20: {e}")
            raise # Change pass to raise

    if product21_id: # Zsq's Algorithm Book
        logger.info(f"Inserting images for Product 21: {product21_id}")
        try:
            cursor.execute(
                """INSERT INTO [ProductImage] (ImageID, ProductID, ImageURL, SortOrder) VALUES (?, ?, ?, ?)""",
                uuid.uuid4(), product21_id, "/uploads/product21_1.jpg", 0
            )
            logger.info("Images for Product 21 inserted.")
        except pyodbc.Error as e:
            logger.error(f"Failed to insert images for Product 21: {e}")
            raise # Change pass to raise

    if product22_id: # siyuaotao's Projector
        logger.info(f"Inserting images for Product 22: {product22_id}")
        try:
            cursor.execute(
                """INSERT INTO [ProductImage] (ImageID, ProductID, ImageURL, SortOrder) VALUES (?, ?, ?, ?)""",
                uuid.uuid4(), product22_id, "/uploads/product22_1.jpg", 0
            )
            logger.info("Images for Product 22 inserted.")
        except pyodbc.Error as e:
            logger.error(f"Failed to insert images for Product 22: {e}")
            raise # Change pass to raise

    if product23_id: # Cyq's Dumbbells
        logger.info(f"Inserting images for Product 23: {product23_id}")
        try:
            cursor.execute(
                """INSERT INTO [ProductImage] (ImageID, ProductID, ImageURL, SortOrder) VALUES (?, ?, ?, ?)""",
                uuid.uuid4(), product23_id, "/uploads/product23_1.jpg", 0
            )
            logger.info("Images for Product 23 inserted.")
        except pyodbc.Error as e:
            logger.error(f"Failed to insert images for Product 23: {e}")
            raise # Change pass to raise

    if product24_id: # Cy's Art Easel
        logger.info(f"Inserting images for Product 24: {product24_id}")
        try:
            cursor.execute(
                """INSERT INTO [ProductImage] (ImageID, ProductID, ImageURL, SortOrder) VALUES (?, ?, ?, ?)""",
                uuid.uuid4(), product24_id, "/uploads/product24_1.jpg", 0 # Using a generic art supply image
            )
            logger.info("Images for Product 24 inserted.")
        except pyodbc.Error as e:
            logger.error(f"Failed to insert images for Product 24: {e}")
            raise # Change pass to raise

    if product25_id: # Ssc's Drone (Rejected)
        logger.info(f"Inserting images for Product 25: {product25_id}")
        try:
            cursor.execute(
                """INSERT INTO [ProductImage] (ImageID, ProductID, ImageURL, SortOrder) VALUES (?, ?, ?, ?)""",
                uuid.uuid4(), product25_id, "/uploads/product25_1.jpg", 0
            )
            logger.info("Images for Product 25 inserted.")
        except pyodbc.Error as e:
            logger.error(f"Failed to insert images for Product 25: {e}")
            raise # Change pass to raise

    if product26_id: # Zsq's Robotics Kit
        logger.info(f"Inserting images for Product 26: {product26_id}")
        try:
            cursor.execute(
                """INSERT INTO [ProductImage] (ImageID, ProductID, ImageURL, SortOrder) VALUES (?, ?, ?, ?)""",
                uuid.uuid4(), product26_id, "/uploads/product26_1.jpg", 0
            )
            logger.info("Images for Product 26 inserted.")
        except pyodbc.Error as e:
            logger.error(f"Failed to insert images for Product 26: {e}")
            raise # Change pass to raise

    conn.commit()
    logger.info("Sample product images committed.")

    # --- 4. Insert Sample Orders, Evaluations, ChatMessages ---
    # Order 1: Bob buys Alice's Laptop (Product 1)
    order1_id = uuid.uuid4()
    logger.info(f"Inserting Order 1 (Bob buys Alice's Laptop) with ID: {order1_id}")
    try:
        cursor.execute(
            """
            INSERT INTO [Order] (OrderID, SellerID, BuyerID, ProductID, Quantity, TradeTime, TradeLocation, CreateTime, UpdateTime, Status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            order1_id, alice_id, bob_id, product1_id, 1, datetime.now(), "大学图书馆", datetime.now(), datetime.now(), "Completed"
        )
        logger.info("Order 1 inserted.")
    except pyodbc.Error as e:
        logger.error(f"Failed to insert Order 1: {e}")
        raise # Change pass to raise

    # Evaluation for Order 1 (Bob evaluates Alice)
    evaluation1_id = uuid.uuid4()
    logger.info(f"Inserting Evaluation 1 (Bob evaluates Alice) with ID: {evaluation1_id}")
    try:
        cursor.execute(
            """
            INSERT INTO [Evaluation] (EvaluationID, OrderID, Rating, Content, CreateTime)
            VALUES (?, ?, ?, ?, ?)
            """,
            evaluation1_id, order1_id, 5, "卖家响应迅速，商品描述属实，交易非常顺利！", datetime.now()
        )
        logger.info("Evaluation 1 inserted.")
    except pyodbc.Error as e:
        logger.error(f"Failed to insert Evaluation 1: {e}")
        raise # Change pass to raise

    # Order 2: Alice buys Bob's Camera (Product 2)
    order2_id = uuid.uuid4()
    logger.info(f"Inserting Order 2 (Alice buys Bob's Camera) with ID: {order2_id}")
    try:
        cursor.execute(
            """
            INSERT INTO [Order] (OrderID, SellerID, BuyerID, ProductID, Quantity, TradeTime, TradeLocation, CreateTime, UpdateTime, Status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            order2_id, bob_id, alice_id, product2_id, 1, datetime.now(), "学生活动中心", datetime.now(), datetime.now(), "ConfirmedBySeller"
        )
        logger.info("Order 2 inserted.")
    except pyodbc.Error as e:
        logger.error(f"Failed to insert Order 2: {e}")
        raise # Change pass to raise

    # ChatMessage 1: Alice to Bob about Camera
    chat_alice_bob_product2_conversation_id = uuid.uuid4() # New UUID for this conversation
    chat1_id = uuid.uuid4()
    logger.info(f"Inserting ChatMessage 1 (Alice to Bob about Camera) with ID: {chat1_id}")
    try:
        cursor.execute(
            """
            INSERT INTO [ChatMessage] (MessageID, ConversationIdentifier, SenderID, ReceiverID, ProductID, Content, SendTime, IsRead)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            chat1_id, chat_alice_bob_product2_conversation_id, alice_id, bob_id, product2_id, "您好，请问相机最低多少钱可以出？", datetime.now(), 0
        )
        logger.info("ChatMessage 1 inserted.")
    except pyodbc.Error as e:
        logger.error(f"Failed to insert ChatMessage 1: {e}")
        raise # Change pass to raise

    # ChatMessage 2: Bob to Alice about Camera
    chat2_id = uuid.uuid4()
    logger.info(f"Inserting ChatMessage 2 (Bob to Alice about Camera) with ID: {chat2_id}")
    try:
        cursor.execute(
            """
            INSERT INTO [ChatMessage] (MessageID, ConversationIdentifier, SenderID, ReceiverID, ProductID, Content, SendTime, IsRead)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            chat2_id, chat_alice_bob_product2_conversation_id, bob_id, alice_id, product2_id, "你好，最低2700。如果真心想要可以再优惠一些。", datetime.now(), 1
        )
        logger.info("ChatMessage 2 inserted.")
    except pyodbc.Error as e:
        logger.error(f"Failed to insert ChatMessage 2: {e}")
        raise # Change pass to raise

    # Order 3: David buys Alice's Textbook (Product 3) - Pending Seller Confirmation
    order3_id = uuid.uuid4()
    logger.info(f"Inserting Order 3 (David buys Alice's Textbook) with ID: {order3_id}")
    try:
        cursor.execute(
            """
            INSERT INTO [Order] (OrderID, SellerID, BuyerID, ProductID, Quantity, TradeTime, TradeLocation, CreateTime, UpdateTime, Status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            order3_id, alice_id, david_id, product3_id, 1, datetime.now(), "教学楼A栋", datetime.now(), datetime.now(), "PendingSellerConfirmation"
        )
        logger.info("Order 3 inserted.")
    except pyodbc.Error as e:
        logger.error(f"Failed to insert Order 3: {e}")
        raise # Change pass to raise

    # Return Request 1: Lucy requests return for a hypothetical purchase (no matching order currently, just example)
    # To make this work, Lucy needs to have bought something first.
    # Let's assume Lucy bought Product 9 (David's Desk Lamp) and wants to return.
    # This requires an order first.
    order4_id = uuid.uuid4()
    logger.info(f"Inserting Order 4 (Lucy buys David's Desk Lamp) with ID: {order4_id}")
    try:
        cursor.execute(
            """
            INSERT INTO [Order] (OrderID, SellerID, BuyerID, ProductID, Quantity, TradeTime, TradeLocation, CreateTime, UpdateTime, Status, CompleteTime)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            order4_id, david_id, lucy_id, product9_id, 1, datetime.now(), "宿舍楼下", datetime.now(), datetime.now(), "Completed", datetime.now() # Added CompleteTime and its parameter
        )
        logger.info("Order 4 inserted.")
    except pyodbc.Error as e:
        logger.error(f"Failed to insert Order 4: {e}")
        raise # Change pass to raise

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
        raise # Change pass to raise

    # New Order: siyuaotao buys Cyq's Sports Shoes (Product 12)
    order_siyuaotao_cyq_shoes = uuid.uuid4()
    if siyuaotao_id and cyq_id and product12_id:
        logger.info(f"Inserting Order (siyuaotao buys Cyq's Sports Shoes) with ID: {order_siyuaotao_cyq_shoes}")
        try:
            cursor.execute(
                """
                INSERT INTO [Order] (OrderID, SellerID, BuyerID, ProductID, Quantity, TradeTime, TradeLocation, CreateTime, UpdateTime, Status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                order_siyuaotao_cyq_shoes, cyq_id, siyuaotao_id, product12_id, 1, datetime.now(), "学校南门", datetime.now(), datetime.now(), "Completed"
            )
            logger.info("Order (siyuaotao buys Cyq's Sports Shoes) inserted.")
        except pyodbc.Error as e:
            logger.error(f"Failed to insert Order (siyuaotao buys Cyq's Sports Shoes): {e}")
            raise # Change pass to raise

    # New Evaluation: siyuaotao evaluates Cyq for Sports Shoes
    eval_siyuaotao_cyq_shoes = uuid.uuid4()
    if siyuaotao_id and cyq_id and order_siyuaotao_cyq_shoes:
        logger.info(f"Inserting Evaluation (siyuaotao evaluates Cyq) with ID: {eval_siyuaotao_cyq_shoes}")
        try:
            cursor.execute(
                """
                INSERT INTO [Evaluation] (EvaluationID, OrderID, Rating, Content, CreateTime)
                VALUES (?, ?, ?, ?, ?)
                """,
                eval_siyuaotao_cyq_shoes, order_siyuaotao_cyq_shoes, 5, "鞋子很新，描述准确，卖家回复及时，好评！", datetime.now()
            )
            logger.info("Evaluation (siyuaotao evaluates Cyq) inserted.")
        except pyodbc.Error as e:
            logger.error(f"Failed to insert Evaluation (siyuaotao evaluates Cyq): {e}")
            raise # Change pass to raise

    # New Order: Cy buys Ssc's Guitar (Product 14) - Pending Confirmation
    order_cy_ssc_guitar = uuid.uuid4()
    if cy_id and ssc_id and product14_id:
        logger.info(f"Inserting Order (Cy buys Ssc's Guitar) with ID: {order_cy_ssc_guitar}")
        try:
            cursor.execute(
                """
                INSERT INTO [Order] (OrderID, SellerID, BuyerID, ProductID, Quantity, TradeTime, TradeLocation, CreateTime, UpdateTime, Status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                order_cy_ssc_guitar, ssc_id, cy_id, product14_id, 1, datetime.now(), "艺术楼排练室", datetime.now(), datetime.now(), "PendingSellerConfirmation"
            )
            logger.info("Order (Cy buys Ssc's Guitar) inserted.")
        except pyodbc.Error as e:
            logger.error(f"Failed to insert Order (Cy buys Ssc's Guitar): {e}")
            raise # Change pass to raise

    # New Chat: Cy to Ssc about Guitar
    chat_cy_ssc_product14_conversation_id = uuid.uuid4() # New UUID for this conversation
    chat_cy_ssc_guitar = uuid.uuid4()
    if cy_id and ssc_id and product14_id:
        logger.info(f"Inserting Chat (Cy to Ssc about Guitar) with ID: {chat_cy_ssc_guitar}")
        try:
            cursor.execute(
                """
                INSERT INTO [ChatMessage] (MessageID, ConversationIdentifier, SenderID, ReceiverID, ProductID, Content, SendTime, IsRead)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                chat_cy_ssc_guitar, chat_cy_ssc_product14_conversation_id, cy_id, ssc_id, product14_id, "您好，吉他是在校内交易吗？", datetime.now(), 0
            )
            logger.info("Chat (Cy to Ssc about Guitar) inserted.")
        except pyodbc.Error as e:
            logger.error(f"Failed to insert Chat (Cy to Ssc about Guitar): {e}")
            raise # Change pass to raise

    # New Order: Zsq buys siyuaotao's Monitor (Product 17)
    order_zsq_siyuaotao_monitor = uuid.uuid4()
    if zsq_id and siyuaotao_id and product17_id:
        logger.info(f"Inserting Order (Zsq buys siyuaotao's Monitor) with ID: {order_zsq_siyuaotao_monitor}")
        try:
            cursor.execute(
                """
                INSERT INTO [Order] (OrderID, SellerID, BuyerID, ProductID, Quantity, TradeTime, TradeLocation, CreateTime, UpdateTime, Status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                order_zsq_siyuaotao_monitor, siyuaotao_id, zsq_id, product17_id, 1, datetime.now(), "图书馆门口", datetime.now(), datetime.now(), "Completed"
            )
            logger.info("Order (Zsq buys siyuaotao's Monitor) inserted.")
        except pyodbc.Error as e:
            logger.error(f"Failed to insert Order (Zsq buys siyuaotao's Monitor): {e}")
            raise # Change pass to raise

    # New Evaluation: Zsq evaluates siyuaotao for Monitor
    eval_zsq_siyuaotao_monitor = uuid.uuid4()
    if zsq_id and siyuaotao_id and order_zsq_siyuaotao_monitor:
        logger.info(f"Inserting Evaluation (Zsq evaluates siyuaotao) with ID: {eval_zsq_siyuaotao_monitor}")
        try:
            cursor.execute(
                """
                INSERT INTO [Evaluation] (EvaluationID, OrderID, Rating, Content, CreateTime)
                VALUES (?, ?, ?, ?, ?)
                """,
                eval_zsq_siyuaotao_monitor, order_zsq_siyuaotao_monitor, 4, "显示器状态不错，可惜附赠的线材有点短。", datetime.now()
            )
            logger.info("Evaluation (Zsq evaluates siyuaotao) inserted.")
        except pyodbc.Error as e:
            logger.error(f"Failed to insert Evaluation (Zsq evaluates siyuaotao): {e}")
            raise # Change pass to raise

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
        admin_user_ids = create_admin_users(conn) # Capture the returned IDs
        logger.info(f"管理员账户创建完成。Admin IDs: {admin_user_ids}")

        # 调用函数插入示例数据
        logger.info("开始插入示例数据...")
        await insert_sample_data(conn, logger, admin_user_ids) # Pass to insert_sample_data
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