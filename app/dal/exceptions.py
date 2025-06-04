from app.exceptions import NotFoundError, IntegrityError, DALError, ForbiddenError

# SQLSTATE 映射到自定义异常
# 常见的 SQLSTATE 值：
# '23000': Integrity Constraint Violation (通用完整性约束错误)
# '23505': Unique Violation (唯一约束错误，属于 23000 的子类)
# '42S02': Base Table or View Not Found (表或视图不存在)
# '02000': No Data (无数据)

# 针对 SQL Server 的错误码 (通过 pyodbc.Error.args[1])
# 例如：2601 (唯一约束重复), 2627 (主键约束重复), 547 (外键约束)
SQLSERVER_ERROR_CODE_MAP = {
    2601: IntegrityError, # Cannot insert duplicate key row in object... (Duplicate Key)
    2627: IntegrityError, # Violation of PRIMARY KEY constraint... (Primary Key Violation)
    547: IntegrityError, # The INSERT statement conflicted with the FOREIGN KEY constraint... (Foreign Key Violation)
    # Add other SQL Server specific error codes as needed
}

# 综合映射：优先SQL Server错误码，其次SQLSTATE
ERROR_MAP = {
    # SQLSTATE mappings (通用)
    '23000': IntegrityError, # 通用完整性约束
    '23505': IntegrityError, # 唯一约束 (Often caught by SQLSERVER_ERROR_CODE_MAP first)
    '42S02': DALError,     # 表不存在
    '02000': NotFoundError,  # 无数据 (适用于预期返回单行但实际没有的情况，但通常 DAL 方法内部根据 SP返回码更精确判断)
}

def map_db_exception(e: Exception):
    """
    根据 pyodbc.Error 的 SQLSTATE 或错误码映射到自定义应用异常。
    如果是非 pyodbc.Error，则直接包装为 DALError。
    """
    # Check if the exception is a pyodbc.Error
    import pyodbc # Import inside function to avoid circular dependency if exceptions are imported in base.py

    if isinstance(e, pyodbc.Error):
        # Prefer checking SQL Server error codes first
        if len(e.args) > 1 and isinstance(e.args[1], int):
            sqlserver_error_code = e.args[1]
            if sqlserver_error_code in SQLSERVER_ERROR_CODE_MAP:
                return SQLSERVER_ERROR_CODE_MAP[sqlserver_error_code](f"数据库完整性错误: {e}")

        # Then check SQLSTATE
        sqlstate = e.args[0] if e.args else None
        if sqlstate and sqlstate in ERROR_MAP:
             return ERROR_MAP[sqlstate](f"数据库错误: {e}")

    # If no specific mapping found for pyodbc.Error, or if it's not a pyodbc.Error,
    # wrap it in a generic DALError.
    if not isinstance(e, (NotFoundError, IntegrityError, DALError, ForbiddenError)):
        return DALError(f"未知数据库错误: {e}")
    else:
        return e # Re-raise already mapped custom exceptions 