import uuid # 用于类型提示
from typing import Optional, List, Dict, Any # Ensure Optional is imported

class ReturnRequestDAL:
    def __init__(self, db_pool):
        """
        初始化 ReturnRequestDAL，注入数据库连接池。
        :param db_pool: 数据库连接池实例。
        """
        self.db_pool = db_pool

    # 复用 _execute_procedure 方法，假设它与 ChatMessageDAL 中的版本兼容
    # 或将其定义为通用的DAL基类或工具函数。
    # 为简单起见，这里直接复制过来；在实际项目中，应考虑代码复用。
    def _execute_procedure(self, procedure_name: str, params: tuple, 
                           fetch_mode: str = "one", expect_results: bool = True):
        """
        辅助函数，用于执行存储过程并获取结果。
        """
        conn = None
        cursor = None
        try:
            conn = self.db_pool.getconn()
            cursor = conn.cursor()
            placeholders = ", ".join(["?"] * len(params))
            sql = f"EXEC {procedure_name} {placeholders}"
            # print(f"Executing SQL: {sql} with params: {params}") # Debugging line
            cursor.execute(sql, params)

            if not expect_results or fetch_mode == "none":
                return None
            
            if not cursor.description:
                return None if fetch_mode == "one" else []

            columns = [column[0] for column in cursor.description]
            if fetch_mode == "one":
                row = cursor.fetchone()
                return dict(zip(columns, row)) if row else None
            elif fetch_mode == "all":
                rows = cursor.fetchall()
                return [dict(zip(columns, row)) for row in rows]
            return None
        except Exception as e:
            print(f"数据库错误 (执行 {procedure_name}): {e}")
            raise
        finally:
            if cursor:
                cursor.close()
            if conn:
                self.db_pool.putconn(conn)

    def create_return_request(self, order_id: str, buyer_id: str, 
                              request_reason_detail: str, return_reason_code: str
                             ) -> Dict[str, Any] | None:
        """
        调用 sp_CreateReturnRequest 存储过程创建退货请求。
        """
        return self._execute_procedure(
            "sp_CreateReturnRequest",
            (order_id, buyer_id, request_reason_detail, return_reason_code),
            fetch_mode="one"
        )

    def handle_return_request(self, return_request_id: str, seller_id: str, 
                              is_agree: bool, audit_idea: Optional[str]
                             ) -> Dict[str, Any] | None:
        """
        调用 sp_HandleReturnRequest 存储过程处理退货请求。
        """
        return self._execute_procedure(
            "sp_HandleReturnRequest",
            (return_request_id, seller_id, is_agree, audit_idea),
            fetch_mode="one"
        )

    def buyer_request_intervention(self, return_request_id: str, buyer_id: str, 
                                   intervention_reason: str
                                  ) -> Dict[str, Any] | None:
        """
        调用 sp_BuyerRequestIntervention 存储过程，买家申请介入。
        """
        return self._execute_procedure(
            "sp_BuyerRequestIntervention",
            (return_request_id, buyer_id, intervention_reason),
            fetch_mode="one"
        )

    def admin_resolve_return_request(self, return_request_id: str, admin_id: str, 
                                     resolution_action: str, admin_notes: Optional[str]
                                    ) -> Dict[str, Any] | None:
        """
        调用 sp_AdminResolveReturnRequest 存储过程，管理员处理退货请求。
        """
        return self._execute_procedure(
            "sp_AdminResolveReturnRequest",
            (return_request_id, admin_id, resolution_action, admin_notes),
            fetch_mode="one"
        )

    def get_return_request_by_id(self, return_request_id: str) -> Dict[str, Any] | None:
        """
        调用 sp_GetReturnRequestById 存储过程获取退货请求详情。
        :param return_request_id: 退货请求ID。
        :return: 包含退货请求详情的字典或 None。
        """
        return self._execute_procedure(
            "sp_GetReturnRequestById",
            (return_request_id,),
            fetch_mode="one"
        )

    def get_return_requests_by_user_id(self, user_id: str) -> list[dict] | None:
        """
        调用 sp_GetReturnRequestsByUserId 存储过程获取用户的退货请求列表。
        :param user_id: 用户ID。
        :return: 包含退货请求字典的列表或 None。
        """
        return self._execute_procedure(
            "sp_GetReturnRequestsByUserId",
            (user_id,),
            fetch_mode="all"
        ) 