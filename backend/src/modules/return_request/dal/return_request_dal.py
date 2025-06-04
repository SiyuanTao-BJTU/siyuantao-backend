import uuid # 用于类型提示

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

    def create_return_request(self, order_id: str, buyer_id: str, return_reason: str) -> dict | None:
        """
        调用 sp_CreateReturnRequest 存储过程创建退货请求。
        :param order_id: 订单ID。
        :param buyer_id: 买家ID。
        :param return_reason: 退货原因。
        :return: 包含结果的字典或 None。
        """
        # 注意：sp_CreateReturnRequest 返回的 NewReturnRequestID 依赖于 SCOPE_IDENTITY()，
        # 这对于 UNIQUEIDENTIFIER 主键通常返回 NULL。
        # 存储过程应修改为先生成 NEWID()，插入，然后 SELECT 这个已知的ID。
        # 当前DAL实现将按原样返回SP的结果。
        return self._execute_procedure(
            "sp_CreateReturnRequest",
            (order_id, buyer_id, return_reason),
            fetch_mode="one"
        )

    def handle_return_request(self, return_request_id: str, seller_id: str, is_agree: bool, audit_idea: str) -> dict | None:
        """
        调用 sp_HandleReturnRequest 存储过程处理退货请求。
        :param return_request_id: 退货请求ID。
        :param seller_id: 卖家ID。
        :param is_agree: 是否同意 (True/False)。
        :param audit_idea: 处理意见。
        :return: 包含结果的字典或 None。
        """
        return self._execute_procedure(
            "sp_HandleReturnRequest",
            (return_request_id, seller_id, is_agree, audit_idea),
            fetch_mode="one"
        )

    def buyer_request_intervention(self, return_request_id: str, buyer_id: str) -> dict | None:
        """
        调用 sp_BuyerRequestIntervention 存储过程，买家申请介入。
        :param return_request_id: 退货请求ID。
        :param buyer_id: 买家ID。
        :return: 包含结果的字典或 None。
        """
        return self._execute_procedure(
            "sp_BuyerRequestIntervention",
            (return_request_id, buyer_id),
            fetch_mode="one"
        )

    def admin_resolve_return_request(self, return_request_id: str, admin_id: str, new_status: str, audit_idea: str) -> dict | None:
        """
        调用 sp_AdminResolveReturnRequest 存储过程，管理员处理退货请求。
        :param return_request_id: 退货请求ID。
        :param admin_id: 管理员ID。
        :param new_status: 管理员设定的新状态。
        :param audit_idea: 管理员处理意见。
        :return: 包含结果的字典或 None。
        """
        return self._execute_procedure(
            "sp_AdminResolveReturnRequest",
            (return_request_id, admin_id, new_status, audit_idea),
            fetch_mode="one"
        )

    def get_return_request_by_id(self, return_request_id: str) -> dict | None:
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