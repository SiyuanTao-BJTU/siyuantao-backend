import uuid # 用于类型提示，尽管通常以字符串形式传递UUID
from typing import Optional, Tuple, List, Dict, Any # Added Optional, Tuple, List, Dict, Any for clarity

class ChatMessageDAL:
    def __init__(self, db_pool):
        """
        初始化 ChatMessageDAL，注入数据库连接池。
        :param db_pool: 数据库连接池实例。
                        连接池应具有 getconn() 和 putconn() 方法。
                        连接应符合 DB-API 2.0 规范。
        """
        self.db_pool = db_pool

    def _execute_procedure(self, procedure_name: str, params: tuple, 
                           fetch_mode: str = "one", expect_results: bool = True):
        """
        辅助函数，用于执行存储过程并获取结果。
        :param procedure_name: 存储过程的名称。
        :param params: 存储过程的参数元组。
        :param fetch_mode: "one" 获取单行, "all" 获取所有行, "none" 不获取结果。
        :param expect_results: 是否期望存储过程返回可描述的结果集。
        :return: 字典 (对于 "one"), 字典列表 (对于 "all"), 或 None。
        """
        conn = None
        cursor = None
        try:
            conn = self.db_pool.getconn()
            cursor = conn.cursor()
            
            # SQL Server 调用存储过程的参数通常使用 ?
            placeholders = ", ".join(["?"] * len(params))
            sql = f"EXEC {procedure_name} {placeholders}"
            
            cursor.execute(sql, params)

            if not expect_results or fetch_mode == "none":
                # 对于不返回SELECT结果集的存储过程，或者我们不关心其返回时
                # (注意：此处所有目标SP都通过SELECT返回结果)
                # SQL Server 的 XACT_ABORT ON 和存储过程内部的事务处理通常意味着不需要从Python进行显式提交。
                return None

            if not cursor.description: # 没有结果集描述，可能意味着没有行返回或非查询操作
                return None if fetch_mode == "one" else []

            columns = [column[0] for column in cursor.description]

            if fetch_mode == "one":
                row = cursor.fetchone()
                return dict(zip(columns, row)) if row else None
            elif fetch_mode == "all":
                rows = cursor.fetchall()
                return [dict(zip(columns, row)) for row in rows]
            
            return None # 默认情况，如果 fetch_mode 无效

        except Exception as e:
            # 在实际应用中，这里应该使用更完善的日志记录机制
            print(f"数据库错误 (执行 {procedure_name}): {e}")
            raise # 重新抛出异常，由上层处理
        finally:
            if cursor:
                cursor.close()
            if conn:
                self.db_pool.putconn(conn)

    def send_message(self, sender_id: str, receiver_id: str, product_id: str, content: str, client_message_id: Optional[str] = None) -> Tuple[uuid.UUID, bool]:
        """
        调用 sp_SendMessage 存储过程发送消息。
        现在还处理 client_message_id 用于幂等性，并返回 (message_id, is_newly_created)。
        """
        params = (
            sender_id, 
            receiver_id, 
            product_id, 
            content,
            client_message_id #  None会被正确处理为SQL NULL by pyodbc/most drivers
        )
        try:
            result_dict = self._execute_procedure(
                procedure_name="sp_SendMessage",
                params=params,
                fetch_mode="one",
                expect_results=True
            )

            if not result_dict or 'MessageIdOutput' not in result_dict or 'IsNewlyCreated' not in result_dict:
                # Log this error appropriately
                print(f"DAL Error: sp_SendMessage did not return expected columns. Result: {result_dict}")
                raise Exception("Failed to send message due to unexpected database response.") # Or a custom DAL exception

            message_id_str = result_dict['MessageIdOutput']
            is_newly_created_val = result_dict['IsNewlyCreated']

            # Convert to appropriate types
            message_id = uuid.UUID(str(message_id_str)) # Ensure it's a UUID object
            is_newly_created = bool(is_newly_created_val) # Convert bit/int to boolean
            
            return message_id, is_newly_created

        except Exception as e:
            # Log error e
            print(f"Error in ChatMessageDAL.send_message: {e}")
            # Consider re-raising a DAL-specific exception or a more generic one if not already handled by _execute_procedure
            # For now, assume _execute_procedure might raise, or we raise a new one here.
            # If _execute_procedure re-raises, this catch might be for additional logging/wrapping.
            raise # Re-raise the caught exception or a wrapped one

    def get_user_conversations(self, user_id: str) -> list[dict] | None:
        """
        调用 sp_GetUserConversations 存储过程获取用户的会话列表。
        :param user_id: 用户ID。
        :return: 包含会话字典的列表，或在错误时为 None。
        """
        return self._execute_procedure(
            "sp_GetUserConversations",
            (user_id,),
            fetch_mode="all"
        )

    def get_chat_messages_by_product_and_users(
        self, product_id: str, user_id1: str, user_id2: str, 
        page_number: int = 1, page_size: int = 20
    ) -> tuple[list[dict] | None, int | None]:
        """
        调用 sp_GetChatMessagesByProductAndUsers 存储过程。
        此过程返回两个结果集：消息列表和总消息数。
        :param product_id: 商品ID。
        :param user_id1: 用户1的ID。
        :param user_id2: 用户2的ID。
        :param page_number: 分页页码。
        :param page_size: 每页消息数。
        :return: 元组 (消息字典列表, 总消息数)，或在错误时为 (None, None)。
        """
        conn = None
        cursor = None
        messages = None
        total_count = None
        try:
            conn = self.db_pool.getconn()
            cursor = conn.cursor()
            sql = "EXEC sp_GetChatMessagesByProductAndUsers ?, ?, ?, ?, ?"
            cursor.execute(sql, (product_id, user_id1, user_id2, page_number, page_size))
            
            # 第一个结果集：消息列表
            messages = []
            if cursor.description:
                columns = [column[0] for column in cursor.description]
                for row in cursor.fetchall():
                    messages.append(dict(zip(columns, row)))
            
            # 第二个结果集：总消息数
            total_count = 0 # 默认为0
            if cursor.nextset(): # 移动到下一个结果集
                if cursor.description:
                    row = cursor.fetchone()
                    if row:
                        # 假设存储过程返回 SELECT COUNT(*) AS TotalMessages
                        count_columns = [col[0] for col in cursor.description]
                        count_dict = dict(zip(count_columns, row))
                        total_count = count_dict.get('TotalMessages', 0)
            
            return messages, total_count
        except Exception as e:
            print(f"数据库错误 (get_chat_messages_by_product_and_users): {e}")
            raise 
        finally:
            if cursor:
                cursor.close()
            if conn:
                self.db_pool.putconn(conn)
        # 如果在 try 块中提前通过 raise 退出了，这里不会执行。
        # 如果 try 块正常完成，会返回 messages, total_count。
        # 为确保函数总有返回值路径（即使理论上不应到达）：
        return messages, total_count


    def mark_message_as_read(self, message_id: str, user_id: str) -> dict | None:
        """
        调用 sp_MarkMessageAsRead 存储过程将消息标记为已读。
        :param message_id: 要标记为已读的消息ID。
        :param user_id: 标记消息的用户ID (接收者)。
        :return: 包含结果的字典，例如 {'MarkedAsReadMessageID': 'uuid', 'Result': '...'}，或在错误时为 None。
        """
        return self._execute_procedure(
            "sp_MarkMessageAsRead",
            (message_id, user_id),
            fetch_mode="one"
        )

    def hide_conversation(self, product_id: str, user_id: str) -> dict | None:
        """
        调用 sp_HideConversation 存储过程隐藏会话。
        :param product_id: 与要隐藏的会话关联的商品ID。
        :param user_id: 隐藏会话的用户ID。
        :return: 包含结果的字典，例如 {'Result': '...', 'ProductID': 'uuid', 'UserID': 'uuid'}，或在错误时为 None。
        """
        return self._execute_procedure(
            "sp_HideConversation",
            (product_id, user_id),
            fetch_mode="one"
        ) 