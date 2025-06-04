import pyodbc
import os
from dotenv import load_dotenv

# 加载 .env 文件中的环境变量
load_dotenv()

# 从环境变量中获取数据库连接信息
DATABASE_SERVER = os.getenv('DATABASE_SERVER')
DATABASE_NAME = os.getenv('DATABASE_NAME')
DATABASE_UID = os.getenv('DATABASE_UID')
DATABASE_PWD = os.getenv('DATABASE_PWD')

# 检查是否所有必要的环境变量都已设置
if not all([DATABASE_SERVER, DATABASE_NAME, DATABASE_UID, DATABASE_PWD]):
    print("错误：数据库连接信息未在 .env 文件中完全配置。")
    print(f"DATABASE_SERVER: {DATABASE_SERVER}")
    print(f"DATABASE_NAME: {DATABASE_NAME}")
    print(f"DATABASE_UID: {DATABASE_UID}")
    # 为安全起见，不直接打印密码
    print(f"DATABASE_PWD: {'已设置' if DATABASE_PWD else '未设置'}")
    exit()

print(f"尝试连接到服务器: {DATABASE_SERVER}")
print(f"数据库: {DATABASE_NAME}")
print(f"用户名: {DATABASE_UID}")

# Corrected connection string format
conn_str = (
    f"DRIVER={{ODBC Driver 17 for SQL Server}};"
    f"SERVER={DATABASE_SERVER};"
    f"DATABASE={DATABASE_NAME};"
    f"UID={DATABASE_UID};"
    f"PWD={DATABASE_PWD};"
    f"TrustServerCertificate=yes;"
)

cnxn = None  # 初始化 cnxn
try:
    # 建立连接
    cnxn = pyodbc.connect(conn_str, timeout=5) # 设置5秒超时
    cursor = cnxn.cursor()

    # 执行一个简单的查询
    cursor.execute("SELECT @@VERSION;")
    row = cursor.fetchone()

    if row:
        print("\n连接成功!")
        print(f"SQL Server 版本信息: {row[0]}")
    else:
        print("\n连接成功，但未获取到版本信息。")

except pyodbc.Error as ex:
    sqlstate = ex.args[0]
    print(f"\n数据库连接失败。错误状态: {sqlstate}")
    print(f"错误信息: {ex}")

except Exception as e:
    print(f"\n发生了一个预料之外的错误: {e}")

finally:
    if cnxn:
        cnxn.close()
        print("\n数据库连接已关闭。")