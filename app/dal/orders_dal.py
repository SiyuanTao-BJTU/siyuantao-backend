import pyodbc
from typing import List, Optional, Dict, Any, Callable, Awaitable
from app.dal.base import execute_query, execute_non_query
from app.exceptions import DALError, NotFoundError, IntegrityError, ForbiddenError
from uuid import UUID # 导入 UUID
from datetime import datetime # 导入 datetime
import asyncio
import logging # 确保导入 logging

logger = logging.getLogger(__name__) # 初始化 logger

class OrdersDAL:
    """
    Data Access Layer for Order operations.
    Uses a generic database query execution function.
    """
    def __init__(self, execute_query_func: Callable[..., Awaitable[Optional[List[Dict]]]]) -> None:
        """
        Initializes OrdersDAL instance.
        
        Args:
            execute_query_func: A generic async function to execute database queries.
                                It should handle both SELECT and non-SELECT queries
                                and manage error mapping. Signature is flexible.
        """
        self._execute_query = execute_query_func # Store the generic execution function

    async def create_order(
        self, 
        conn: pyodbc.Connection, # Add conn parameter
        buyer_id: UUID, 
        product_id: UUID, 
        quantity: int, 
        trade_time: datetime, # 移除 total_price，新增 trade_time
        trade_location: str # 新增 trade_location
    ) -> UUID:
        """
        Calls the sp_CreateOrder stored procedure to create a new order.
        Assumes sp_CreateOrder is modified to SELECT SCOPE_IDENTITY() AS OrderID at the end.
        """
        sql = "{CALL sp_CreateOrder (?, ?, ?, ?, ?)}" # 更新 SQL，匹配新参数数量
        params = (str(buyer_id), str(product_id), quantity, trade_time, trade_location) # 更新参数列表
        try:
            # Use the stored generic execution function and pass conn
            logger.debug(f"DAL: Executing sp_CreateOrder with SQL: {sql}, Params: {params}") # 添加日志
            result = await self._execute_query(conn, sql, params, fetchone=True) # Assuming fetchone is supported
            logger.debug(f"DAL: sp_CreateOrder returned raw result: {result}") # 添加日志
            if result and result.get("订单ID") is not None: # 检查键名改为 "订单ID"
                return UUID(result["订单ID"]) # 获取键名改为 "订单ID"
            else:
                # 如果存储过程没有返回预期结果，或者OrderID为None
                raise DALError("Stored procedure sp_CreateOrder did not return a valid OrderID.")
        except pyodbc.Error as e:
            # Fallback error handling if the generic function doesn't map all errors
            error_msg = str(e)
            # Add specific error code checks for sp_CreateOrder
            # These specific error codes mapping might ideally live in the generic executor
            if "50001" in error_msg: # 买家不存在或角色不正确
                raise NotFoundError(f"创建订单失败: {error_msg}") from e
            elif "50002" in error_msg: # 商品不存在或已下架
                raise NotFoundError(f"创建订单失败: {error_msg}") from e
            elif "50003" in error_msg: # 商品库存不足
                raise IntegrityError(f"创建订单失败: {error_msg}") from e
            raise DALError(f"无法创建订单: {error_msg}") from e
        except Exception as e:
            # Catch any other unexpected errors during DAL execution
            raise DALError(f"创建订单时发生意外错误: {e}") from e

    async def confirm_order(
        self, 
        conn: pyodbc.Connection, # Add conn parameter
        order_id: UUID, 
        seller_id: UUID
    ) -> None:
        """
        Calls the sp_ConfirmOrder stored procedure for a seller to confirm an order.
        """
        sql = "{CALL sp_ConfirmOrder (?, ?)}"
        params = (str(order_id), str(seller_id)) # 转换为字符串
        try:
            # Use the stored generic execution function and pass conn
            await self._execute_query(conn, sql, params, fetchone=False) # Assuming execute_non_query behavior
        except DALError as e:
            raise e
        except pyodbc.Error as e:
            error_msg = str(e)
            if "50004" in error_msg: # 订单不存在或您不是该订单的卖家
                raise NotFoundError(f"确认订单失败: {error_msg}") from e
            elif "50005" in error_msg: # 订单状态不是"待处理"
                raise IntegrityError(f"确认订单失败: {error_msg}") from e
            raise DALError(f"无法确认订单 {order_id}: {error_msg}") from e
        except Exception as e:
            raise DALError(f"确认订单 {order_id} 时发生意外错误: {e}") from e

    async def complete_order(
        self, 
        conn: pyodbc.Connection, # Add conn parameter
        order_id: UUID, 
        actor_id: UUID
    ) -> None:
        """
        Calls the sp_CompleteOrder stored procedure to mark an order as completed.
        ActorID can be the buyer or an admin.
        """
        sql = "{CALL sp_CompleteOrder (?, ?)}"
        params = (str(order_id), str(actor_id)) # 转换为字符串
        try:
            # Use the stored generic execution function and pass conn
            await self._execute_query(conn, sql, params, fetchone=False) # Assuming execute_non_query behavior
        except DALError as e:
            raise e
        except pyodbc.Error as e:
            error_msg = str(e)
            if "50006" in error_msg: # 订单不存在
                raise NotFoundError(f"完成订单失败: {error_msg}") from e
            elif "50007" in error_msg: # 您无权完成此订单
                raise ForbiddenError(f"完成订单失败: {error_msg}") from e
            elif "50008" in error_msg: # 订单状态不正确
                raise IntegrityError(f"完成订单失败: {error_msg}") from e
            raise DALError(f"完成订单 {order_id} 时发生意外错误: {e}") from e
        except Exception as e:
            raise DALError(f"完成订单 {order_id} 时发生意外错误: {e}") from e

    async def reject_order(
        self, 
        conn: pyodbc.Connection, # Add conn parameter
        order_id: UUID, 
        seller_id: UUID, 
        rejection_reason: Optional[str] = None
    ) -> None:
        """
        Calls the sp_RejectOrder stored procedure for a seller to reject an order.
        (Assumes sp_RejectOrder might take an optional @RejectionReason parameter)
        """
        # Adjust SQL and params if @RejectionReason is definitively part of sp_RejectOrder
        if rejection_reason:
            sql = "{CALL sp_RejectOrder (?, ?, ?)}"
            params = (str(order_id), str(seller_id), rejection_reason) # 转换为字符串
        else:
            sql = "{CALL sp_RejectOrder (?, ?)}" # Assuming SP handles NULL or has default for reason if not provided
            params = (str(order_id), str(seller_id)) # 转换为字符串
        
        try:
            # Use the stored generic execution function and pass conn
            await self._execute_query(conn, sql, params, fetchone=False) # Assuming execute_non_query behavior
        except DALError as e:
            raise e
        except pyodbc.Error as e:
            error_msg = str(e)
            # Add specific error code checks for sp_RejectOrder if available
            # These specific error codes mapping might ideally live in the generic executor
            raise DALError(f"无法拒绝订单 {order_id}: {error_msg}") from e
        except Exception as e:
            raise DALError(f"拒绝订单 {order_id} 时发生意外错误: {e}") from e

    async def cancel_order(
        self,
        conn: pyodbc.Connection, # Add conn parameter
        order_id: UUID,
        user_id: UUID,
        cancel_reason: str
    ) -> None:
        """
        Calls the sp_CancelOrder stored procedure to cancel an order.
        (Assumes sp_CancelOrder exists as per documentation)
        """
        sql = "{CALL sp_CancelOrder (?, ?, ?)}"
        params = (str(order_id), str(user_id), cancel_reason) # 转换为字符串
        try:
            # Use the stored generic execution function and pass conn
            await self._execute_query(conn, sql, params, fetchone=False) # Assuming execute_non_query behavior
        except DALError as e:
            raise e
        except pyodbc.Error as e:
            error_msg = str(e)
            # Add specific error code checks for sp_CancelOrder if available
            raise DALError(f"无法取消订单 {order_id}: {error_msg}") from e
        except Exception as e:
            raise DALError(f"取消订单 {order_id} 时发生意外错误: {e}") from e

    async def get_orders_by_user(
        self, 
        conn: pyodbc.Connection, # Add conn parameter
        user_id: UUID, 
        is_seller: bool, 
        status: Optional[str] = None, 
        page_number: int = 1, 
        page_size: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Calls sp_GetOrdersByUser to retrieve a list of orders for a user (either as buyer or seller).
        (Assumes sp_GetOrdersByUser exists as per documentation)
        """
        sql = "{CALL sp_GetOrdersByUser (?, ?, ?, ?, ?)}"
        
        # Convert is_seller boolean to the string role expected by the stored procedure
        user_role_str = "Seller" if is_seller else "Buyer"
        
        params = (str(user_id), user_role_str, status, page_number, page_size) # Use user_role_str
        try:
            # Use the stored generic execution function and pass conn
            orders = await self._execute_query(conn, sql, params, fetchall=True) # Assuming fetchall is supported
            return orders
        except DALError as e:
            raise e
        except pyodbc.Error as e:
            error_msg = str(e)
            raise DALError(f"无法获取用户 {user_id} 的订单: {error_msg}") from e
        except Exception as e:
            raise DALError(f"获取用户 {user_id} 订单时发生意外错误: {e}") from e

    async def get_order_by_id(
        self, 
        conn: pyodbc.Connection, # Add conn parameter
        order_id: UUID
    ) -> Optional[Dict[str, Any]]:
        """
        Calls sp_GetOrderById to retrieve a specific order by its ID.
        (Assumes sp_GetOrderById exists as per documentation)
        """
        sql = "{CALL sp_GetOrderById (?)}"
        params = (str(order_id),) # 转换为字符串
        try:
            # Use the stored generic execution function and pass conn
            result = await self._execute_query(conn, sql, params, fetchone=True) # Assuming fetchone is supported
            # The generic execute_query should ideally raise NotFoundError if no result
            return result # Return the result directly, let service handle None/NotFoundError mapping
        except DALError as e:
            # Re-raise DALErrors mapped by the generic function
            raise e
        except pyodbc.Error as e:
            error_msg = str(e)
            # Add specific error code checks if sp_GetOrderById throws errors on not found
            raise DALError(f"无法获取订单 {order_id}: {error_msg}") from e
        except Exception as e:
            raise DALError(f"获取订单 {order_id} 时发生意外错误: {e}") from e
        

    async def get_all_orders(
        self,
        conn: pyodbc.Connection,
        status: Optional[str] = None,
        page_number: int = 1,
        page_size: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Calls sp_GetAllOrders (或类似名称) to retrieve a list of all orders for admin view.
        Supports status filtering and pagination.
        """
        sql = "{CALL sp_GetAllOrders (?, ?, ?)}" # Stored procedure for getting all orders
        params = (status, page_number, page_size)
        try:
            orders = await self._execute_query(conn, sql, params, fetchall=True)
            return orders
        except DALError as e:
            raise DALError(f"无法获取所有订单: {e}") from e
        except pyodbc.Error as e:
            error_msg = str(e)
            raise DALError(f"数据库错误，无法获取所有订单: {error_msg}") from e
        except Exception as e:
            raise DALError(f"获取所有订单时发生意外错误: {e}") from e
