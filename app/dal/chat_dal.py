from uuid import UUID
from typing import Optional, List, Dict, Any, Union
from datetime import datetime
import pyodbc

import hashlib # For generating ConversationIdentifier
import uuid # For generating ConversationIdentifier

class ChatDAL:
    def __init__(self, execute_query_func, execute_non_query_func):
        self.execute_query_func = execute_query_func
        self.execute_non_query_func = execute_non_query_func

    def _generate_conversation_id(self, user_id1: UUID, user_id2: UUID, product_id: UUID) -> UUID:
        """
        Generates a consistent ConversationIdentifier for a given pair of users and a product.
        Ensures that the order of user IDs does not affect the generated ID.
        """
        # Sort user IDs to ensure consistency regardless of who is sender/receiver
        sorted_user_ids = sorted([str(user_id1), str(user_id2)])
        
        # Combine sorted user IDs and product ID
        unique_string = f"{sorted_user_ids[0]}-{sorted_user_ids[1]}-{product_id}"
        
        # Use SHA-256 hash to create a consistent UUID (consistent with ChatService)
        hash_object = hashlib.sha256(unique_string.encode('utf-8')) # Changed to sha256
        hex_dig = hash_object.hexdigest()
        conversation_uuid = UUID(hex_dig[:32])
        print(f"ChatDAL: _generate_conversation_id generated: {conversation_uuid} for {unique_string}")
        return conversation_uuid

    async def create_chat_message(self, conn: pyodbc.Connection, message_id: UUID, sender_id: UUID, 
                                  receiver_id: UUID, product_id: UUID, content: str) -> Dict[str, Any]:
        """
        创建新的聊天消息。
        现在包含 ConversationIdentifier。
        """
        conversation_id = self._generate_conversation_id(sender_id, receiver_id, product_id)

        sql = """
        INSERT INTO [ChatMessage] (MessageID, ConversationIdentifier, SenderID, ReceiverID, ProductID, Content, SendTime, IsRead, SenderVisible, ReceiverVisible)
        VALUES (?, ?, ?, ?, ?, ?, GETDATE(), 0, 1, 1)
        """
        params = (str(message_id), str(conversation_id), str(sender_id), str(receiver_id), str(product_id), content)
        await self.execute_non_query_func(conn, sql, params)
        
        # DEBUG: Verify message insertion
        check_sql = "SELECT COUNT(*) AS count FROM [ChatMessage] WHERE MessageID = ?"
        check_params = (str(message_id),)
        check_result = await self.execute_query_func(conn, check_sql, check_params, fetchone=True)
        if check_result and check_result['count'] == 1:
            print(f"ChatDAL: Verified message {message_id} inserted successfully.")
        else:
            print(f"ChatDAL: WARNING - Message {message_id} might not have been inserted. Check result: {check_result}")

        # 返回创建的消息的完整详情，包括关联的用户和商品信息
        return await self.get_message_by_id(conn, message_id)

    async def get_message_by_id(self, conn: pyodbc.Connection, message_id: UUID) -> Optional[Dict[str, Any]]:
        """
        根据消息ID获取单个消息的详情（内部使用）。
        """
        sql = """
        SELECT
            cm.MessageID AS 消息ID,
            cm.ConversationIdentifier AS 会话标识符, -- 新增
            cm.SenderID AS 发送者ID,
            s.UserName AS 发送者用户名,
            cm.ReceiverID AS 接收者ID,
            r.UserName AS 接收者用户名,
            cm.ProductID AS 商品ID,
            p.ProductName AS 商品名称,
            cm.Content AS 消息内容,
            cm.SendTime AS 发送时间,
            cm.IsRead AS 是否已读,
            cm.SenderVisible AS 发送者可见,
            cm.ReceiverVisible AS 接收者可见
        FROM [ChatMessage] cm
        LEFT JOIN [User] s ON cm.SenderID = s.UserID
        LEFT JOIN [User] r ON cm.ReceiverID = r.UserID
        LEFT JOIN [Product] p ON cm.ProductID = p.ProductID
        WHERE cm.MessageID = ?
        """
        params = (str(message_id),)
        return await self.execute_query_func(conn, sql, params, fetchone=True)

    async def get_chat_messages(self, conn: pyodbc.Connection, user_id: UUID, other_user_id: UUID, product_id: UUID) -> List[Dict[str, Any]]:
        """
        获取特定用户与特定对方用户在特定商品上的聊天消息历史。
        """
        conversation_id = self._generate_conversation_id(user_id, other_user_id, product_id)

        sql = """
        SELECT
            cm.MessageID AS 消息ID,
            cm.ConversationIdentifier AS 会话标识符,
            cm.SenderID AS 发送者ID,
            s.UserName AS 发送者用户名,
            cm.ReceiverID AS 接收者ID,
            r.UserName AS 接收者用户名,
            cm.ProductID AS 商品ID,
            p.ProductName AS 商品名称,
            cm.Content AS 消息内容,
            cm.SendTime AS 发送时间,
            cm.IsRead AS 是否已读,
            cm.SenderVisible AS 发送者可见,
            cm.ReceiverVisible AS 接收者可见
        FROM [ChatMessage] cm
        LEFT JOIN [User] s ON cm.SenderID = s.UserID
        LEFT JOIN [User] r ON cm.ReceiverID = r.UserID
        LEFT JOIN [Product] p ON cm.ProductID = p.ProductID
        WHERE cm.ConversationIdentifier = ?
          AND (
                (cm.SenderID = ? AND cm.SenderVisible = 1) OR -- Message is visible to current user as sender
                (cm.ReceiverID = ? AND cm.ReceiverVisible = 1) -- Message is visible to current user as receiver
              )
        ORDER BY cm.SendTime ASC;
        """
        params = (str(conversation_id), str(user_id), str(user_id)) # Added user_id twice for visibility check
        return await self.execute_query_func(conn, sql, params, fetchall=True)

    async def get_chat_sessions_for_user(self, conn: pyodbc.Connection, user_id: UUID) -> List[Dict[str, Any]]:
        """
        获取某个用户的所有聊天会话列表，包括每个会话的最新消息、未读消息数量、对方用户信息和商品图片。
        """
        sql = """
        WITH LatestMessages AS (
            SELECT
                cm.ConversationIdentifier,
                cm.SenderID,
                cm.ReceiverID,
                cm.ProductID,
                cm.Content AS LatestMessageContent,
                cm.SendTime AS LatestMessageTime,
                cm.IsRead, -- Keep IsRead for potential use, though unread count is separate
                ROW_NUMBER() OVER (PARTITION BY cm.ConversationIdentifier ORDER BY cm.SendTime DESC) as rn
            FROM ChatMessage cm
            WHERE (cm.SenderID = ? AND cm.SenderVisible = 1) OR (cm.ReceiverID = ? AND cm.ReceiverVisible = 1)
        ),
        UnreadCounts AS (
            SELECT
                ConversationIdentifier,
                COUNT(MessageID) as UnreadMessageCount
            FROM ChatMessage
            WHERE ReceiverID = ? AND IsRead = 0
                  AND ((SenderID = ? AND SenderVisible = 1) OR (ReceiverID = ? AND ReceiverVisible = 1)) -- Ensure messages are visible to current user
            GROUP BY ConversationIdentifier
        )
        SELECT
            lm.ConversationIdentifier AS 会话ID,
            CASE
                WHEN lm.SenderID = ? THEN lm.ReceiverID
                ELSE lm.SenderID
            END AS 对方用户ID,
            ou.UserName AS 对方用户名,
            ou.AvatarUrl AS 对方头像URL,
            lm.ProductID AS 相关商品ID,
            p.ProductName AS 相关商品名称,
            -- Prefer the ProductImage with SortOrder 1 if available
            (SELECT TOP 1 pi.ImageUrl FROM ProductImage pi WHERE pi.ProductID = p.ProductID ORDER BY pi.SortOrder ASC) AS 相关商品图片URL,
            lm.LatestMessageContent AS 最近一条消息,
            lm.LatestMessageTime AS 最近消息时间,
            COALESCE(uc.UnreadMessageCount, 0) AS 未读消息数
        FROM LatestMessages lm
        JOIN [User] ou ON ou.UserID = (CASE WHEN lm.SenderID = ? THEN lm.ReceiverID ELSE lm.SenderID END)
        JOIN [Product] p ON p.ProductID = lm.ProductID
        LEFT JOIN UnreadCounts uc ON lm.ConversationIdentifier = uc.ConversationIdentifier
        WHERE lm.rn = 1
        ORDER BY lm.LatestMessageTime DESC;
        """
        # Parameters:
        # For LatestMessages WHERE: user_id, user_id
        # For UnreadCounts WHERE ReceiverID: user_id
        # For UnreadCounts WHERE (SenderID OR ReceiverID): user_id, user_id
        # For SELECT CASE (SenderID): user_id
        # For JOIN [User] ou ON (CASE WHEN lm.SenderID): user_id
        params = (user_id, user_id, user_id, user_id, user_id, user_id, user_id)
        # logging.debug(f"ChatDAL: get_chat_sessions_for_user SQL (Optimized): \n{sql}")
        # logging.debug(f"ChatDAL: get_chat_sessions_for_user Params (Optimized): {params}")
        return await self.execute_query_func(conn, sql, params, fetchall=True)

    async def mark_messages_read(self, conn: pyodbc.Connection, user_id: UUID, message_ids: List[UUID]) -> int:
        """
        标记指定消息为已读。只有当消息的接收者是当前用户时才能标记为已读。
        """
        if not message_ids:
            return 0
        
        # Convert UUIDs to strings for SQL parameters
        message_id_strings = [str(mid) for mid in message_ids]
        placeholders = ','.join(['?'] * len(message_id_strings))
        
        sql = f"""
        UPDATE [ChatMessage]
        SET IsRead = 1
        WHERE MessageID IN ({placeholders}) AND ReceiverID = ? AND IsRead = 0;
        """
        params = tuple(message_id_strings + [str(user_id)])
        return await self.execute_non_query_func(conn, sql, params)
    
    async def mark_session_messages_invisible(self, conn: pyodbc.Connection, user_id: UUID, other_user_id: UUID, product_id: UUID, visible: bool) -> int:
        """
        将特定会话中与用户相关的消息标记为可见或不可见。
        需要考虑用户是发送者还是接收者。
        """
        conversation_id = self._generate_conversation_id(user_id, other_user_id, product_id)
        
        # Determine the visibility value (1 for visible, 0 for invisible)
        visibility_value = 1 if visible else 0

        sql = """
        UPDATE [ChatMessage]
        SET SenderVisible = CASE WHEN SenderID = ? THEN ? ELSE SenderVisible END,
            ReceiverVisible = CASE WHEN ReceiverID = ? THEN ? ELSE ReceiverVisible END
        WHERE ConversationIdentifier = ?
          AND (SenderID = ? OR ReceiverID = ?);
        """
        params = (str(user_id), visibility_value, str(user_id), visibility_value, str(conversation_id), str(user_id), str(user_id))
        return await self.execute_non_query_func(conn, sql, params)

    async def get_all_chat_messages_for_admin(self, conn: pyodbc.Connection, page_number: int, page_size: int, search_query: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        管理员获取所有聊天消息。
        """
        offset = (page_number - 1) * page_size
        sql = """
        SELECT
            cm.MessageID AS 消息ID,
            cm.ConversationIdentifier AS 会话标识符, -- 新增
            cm.SenderID AS 发送者ID,
            s.UserName AS 发送者用户名,
            cm.ReceiverID AS 接收者ID,
            r.UserName AS 接收者用户名,
            cm.ProductID AS 商品ID,
            p.ProductName AS 商品名称,
            cm.Content AS 消息内容,
            cm.SendTime AS 发送时间,
            cm.IsRead AS 是否已读,
            cm.SenderVisible AS 发送者可见,
            cm.ReceiverVisible AS 接收者可见
        FROM [ChatMessage] cm
        JOIN [User] s ON cm.SenderID = s.UserID
        JOIN [User] r ON cm.ReceiverID = r.UserID
        JOIN [Product] p ON cm.ProductID = p.ProductID
        WHERE 1 = 1 -- 占位符，方便后续添加 AND 条件
        """
        params = []

        if search_query:
            # 在内容、发送者用户名、接收者用户名中进行模糊搜索
            sql += " AND (cm.Content LIKE ? OR s.UserName LIKE ? OR r.UserName LIKE ?)"
            search_param = f"%{search_query}%"
            params.extend([search_param, search_param, search_param])

        sql += " ORDER BY cm.SendTime DESC OFFSET ? ROWS FETCH NEXT ? ROWS ONLY;"
        params.extend([offset, page_size])
        
        return await self.execute_query_func(conn, sql, tuple(params), fetchall=True)

    async def get_total_chat_messages_count_for_admin(self, conn: pyodbc.Connection, search_query: Optional[str] = None) -> int:
        """
        管理员获取所有聊天消息的总数。
        """
        sql = """
        SELECT COUNT(cm.MessageID) AS TotalCount
        FROM [ChatMessage] cm
        JOIN [User] s ON cm.SenderID = s.UserID
        JOIN [User] r ON cm.ReceiverID = r.UserID
        WHERE (cm.SenderVisible = 1 OR cm.ReceiverVisible = 1)
        """
        params = []

        if search_query:
            sql += " AND (cm.Content LIKE ? OR s.UserName LIKE ? OR r.UserName LIKE ?)"
            search_param = f"%{search_query}%"
            params.extend([search_param, search_param, search_param])

        result = await self.execute_query_func(conn, sql, tuple(params), fetchone=True)
        return result['TotalCount'] if result and 'TotalCount' in result else 0 # Adjust based on how pyodbc returns COUNT(*)

    async def get_messages_between_users_for_product(self, conn: pyodbc.Connection, user1_id: UUID, user2_id: UUID, product_id: UUID) -> List[Dict[str, Any]]:
        """
        获取特定商品下，两个用户之间的所有聊天消息。
        消息必须在发送者和接收者任一方可见。
        """
        sql = """
        SELECT
            cm.MessageID AS 消息ID,
            cm.SenderID AS 发送者ID,
            s.UserName AS 发送者用户名,
            cm.ReceiverID AS 接收者ID,
            r.UserName AS 接收者用户名,
            cm.ProductID AS 商品ID,
            p.ProductName AS 商品名称,
            cm.Content AS 消息内容,
            cm.SendTime AS 发送时间,
            cm.IsRead AS 是否已读,
            cm.SenderVisible AS 发送者可见,
            cm.ReceiverVisible AS 接收者可见
        FROM [ChatMessage] cm
        JOIN [User] s ON cm.SenderID = s.UserID
        JOIN [User] r ON cm.ReceiverID = r.UserID
        JOIN [Product] p ON cm.ProductID = p.ProductID
        WHERE cm.ProductID = ?
          AND ((cm.SenderID = ? AND cm.ReceiverID = ?) OR (cm.SenderID = ? AND cm.ReceiverID = ?))
          AND (
                (cm.SenderID = ? AND cm.SenderVisible = 1) OR
                (cm.ReceiverID = ? AND cm.ReceiverVisible = 1)
              )
        ORDER BY cm.SendTime ASC
        """
        params = (str(product_id), str(user1_id), str(user2_id), str(user2_id), str(user1_id),
                  str(user1_id), str(user1_id)) # Check for user1_id's visibility
        result = await self.execute_query_func(conn, sql, params, fetchall=True)
        return result

    async def mark_messages_as_read(self, conn: pyodbc.Connection, receiver_id: UUID, sender_id: UUID, product_id: UUID) -> None:
        """
        将特定用户（receiver_id）接收到的，来自特定发送者（sender_id），关于特定商品（product_id）的消息标记为已读。
        """
        sql = """
        UPDATE [ChatMessage]
        SET IsRead = 1
        WHERE ReceiverID = ? AND SenderID = ? AND ProductID = ? AND IsRead = 0
        """
        params = (str(receiver_id), str(sender_id), str(product_id))
        await self.execute_non_query_func(conn, sql, params)

    async def update_message_visibility(self, conn: pyodbc.Connection, message_id: UUID, user_id: UUID, is_sender: bool, visible: bool) -> None:
        """
        更新特定消息对特定用户的可见性。
        """
        if is_sender:
            sql = "UPDATE [ChatMessage] SET SenderVisible = ? WHERE MessageID = ? AND SenderID = ?"
        else:
            sql = "UPDATE [ChatMessage] SET ReceiverVisible = ? WHERE MessageID = ? AND ReceiverID = ?"
        params = (1 if visible else 0, str(message_id), str(user_id))
        await self.execute_non_query_func(conn, sql, params)

    async def update_messages_visibility_in_session(self, conn: pyodbc.Connection, user_id: UUID, other_user_id: UUID, product_id: UUID, visible: bool) -> None:
        """
        更新特定会话中所有消息对特定用户的可见性。
        当用户隐藏整个会话时使用。
        """
        sql = """
        UPDATE [ChatMessage]
        SET
            SenderVisible = CASE WHEN SenderID = ? THEN ? ELSE SenderVisible END,
            ReceiverVisible = CASE WHEN ReceiverID = ? THEN ? ELSE ReceiverVisible END
        WHERE ProductID = ?
          AND (
                (SenderID = ? AND ReceiverID = ?) OR
                (SenderID = ? AND ReceiverID = ?)
              )
        """
        params = (str(user_id), 1 if visible else 0, str(user_id), 1 if visible else 0, 
                  str(product_id), str(user_id), str(other_user_id), str(other_user_id), str(user_id))
        await self.execute_non_query_func(conn, sql, params)

    async def update_single_message_visibility_for_admin(self, conn: pyodbc.Connection, message_id: UUID, sender_visible: bool, receiver_visible: bool) -> int:
        """
        管理员更新单条消息的发送者和接收者可见性。
        """
        sql = """
        UPDATE [ChatMessage]
        SET SenderVisible = ?, ReceiverVisible = ?
        WHERE MessageID = ?;
        """
        params = (1 if sender_visible else 0, 1 if receiver_visible else 0, str(message_id))
        return await self.execute_non_query_func(conn, sql, params)

    async def delete_chat_message_by_id(self, conn: pyodbc.Connection, message_id: UUID) -> int:
        """
        根据消息ID物理删除单条聊天消息。此操作仅供超级管理员使用。
        """
        sql = "DELETE FROM [ChatMessage] WHERE MessageID = ?;"
        params = (str(message_id),)
        return await self.execute_non_query_func(conn, sql, params) 