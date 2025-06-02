import pyodbc
from uuid import UUID
from typing import List, Optional, Dict, Any

from app.dal.orders_dal import OrdersDAL
from app.dal.product_dal import ProductDAL
from app.schemas.order_schemas import (
    OrderCreateSchema, 
    OrderResponseSchema,
    OrderStatusUpdateSchema
)
from app.schemas.user_schemas import UserResponseSchema
from app.exceptions import DALError, NotFoundError, ForbiddenError

class OrderService:
    """Service layer for order management."""

    def __init__(self, order_dal: OrdersDAL, product_dal: ProductDAL):
        self.order_dal = order_dal
        self.product_dal = product_dal

    async def create_order(
        self, 
        conn: pyodbc.Connection, 
        order_data: OrderCreateSchema, 
        buyer_id: UUID
    ) -> OrderResponseSchema:
        try:
            created_order_id = await self.order_dal.create_order(
                conn=conn,
                product_id=order_data.product_id,
                buyer_id=buyer_id,
                quantity=order_data.quantity,
                trade_time=order_data.trade_time,
                trade_location=order_data.trade_location
            )
            
            if created_order_id is None:
                raise ValueError("Failed to create order, stored procedure did not return an order ID.")

            order = await self.order_dal.get_order_by_id(conn, created_order_id)
            if not order:
                raise NotFoundError(f"Order with ID {created_order_id} not found after creation.")
            
            return order
        except pyodbc.Error as db_err:
            raise DALError(f"Database error during order creation: {db_err}") from db_err
        except DALError:
            raise
        except NotFoundError:
            raise
        except ValueError:
            raise
        except Exception as e:
            raise DALError(f"An unexpected error occurred during order creation: {e}") from e

    async def confirm_order(
        self, 
        conn: pyodbc.Connection, 
        order_id: UUID, # 修改为 UUID
        user_id: UUID # Typically seller_id
    ) -> OrderResponseSchema:
        try:
            order_to_update = await self.order_dal.get_order_by_id(conn, order_id)
            if not order_to_update:
                raise NotFoundError(f"Order with ID {order_id} not found.")

            await self.order_dal.confirm_order(conn, order_id, user_id)
            
            updated_order = await self.order_dal.get_order_by_id(conn, order_id)
            if not updated_order:
                 raise NotFoundError(f"Order with ID {order_id} not found after confirmation.")
            return updated_order
        except pyodbc.Error as db_err:
            raise DALError(f"Database error confirming order {order_id}: {db_err}") from db_err
        except (NotFoundError, ForbiddenError, ValueError, DALError):
            raise
        except Exception as e:
            raise DALError(f"An unexpected error occurred confirming order {order_id}: {e}") from e

    async def complete_order(
        self, 
        conn: pyodbc.Connection, 
        order_id: UUID, # 修改为 UUID
        user_id: UUID # Typically buyer_id or system
    ) -> OrderResponseSchema:
        try:
            await self.order_dal.complete_order(conn, order_id, user_id)
            updated_order = await self.order_dal.get_order_by_id(conn, order_id)
            if not updated_order:
                 raise NotFoundError(f"Order with ID {order_id} not found after completion.")
            return updated_order
        except pyodbc.Error as db_err:
            raise DALError(f"Database error completing order {order_id}: {db_err}") from db_err
        except (NotFoundError, ForbiddenError, ValueError, DALError):
            raise
        except Exception as e:
            raise DALError(f"An unexpected error occurred completing order {order_id}: {e}") from e

    async def reject_order(
        self, 
        conn: pyodbc.Connection, 
        order_id: UUID, # 修改为 UUID
        user_id: UUID, # Typically seller_id
        reason: Optional[str] = None # Optional reason for rejection
    ) -> OrderResponseSchema:
        try:
            await self.order_dal.reject_order(conn, order_id, user_id, reason)
            updated_order = await self.order_dal.get_order_by_id(conn, order_id)
            if not updated_order:
                 raise NotFoundError(f"Order with ID {order_id} not found after rejection.")
            return updated_order
        except pyodbc.Error as db_err:
            raise DALError(f"Database error rejecting order {order_id}: {db_err}") from db_err
        except (NotFoundError, ForbiddenError, ValueError, DALError):
            raise
        except Exception as e:
            raise DALError(f"An unexpected error occurred rejecting order {order_id}: {e}") from e

    async def cancel_order(
        self,
        conn: pyodbc.Connection,
        order_id: UUID,
        user_id: UUID,
        cancel_reason: str
    ) -> None:
        try:
            order_to_update = await self.order_dal.get_order_by_id(conn, order_id)
            if not order_to_update:
                raise NotFoundError(f"Order with ID {order_id} not found.")

            await self.order_dal.cancel_order(conn, order_id, user_id, cancel_reason)

        except pyodbc.Error as db_err:
            raise DALError(f"Database error canceling order {order_id}: {db_err}") from db_err
        except (NotFoundError, ForbiddenError, ValueError, DALError):
            raise
        except Exception as e:
            raise DALError(f"An unexpected error occurred canceling order {order_id}: {e}") from e

    async def delete_order(
        self,
        conn: pyodbc.Connection,
        order_id: UUID,
        user_id: UUID
    ) -> None:
        try:
            await self.order_dal.delete_order(conn, order_id, user_id)
        except pyodbc.Error as db_err:
            raise DALError(f"Database error deleting order {order_id}: {db_err}") from db_err
        except (NotFoundError, ForbiddenError, ValueError, DALError):
            raise
        except Exception as e:
            raise DALError(f"An unexpected error occurred deleting order {order_id}: {e}") from e

    async def get_orders_by_user(
        self,
        conn: pyodbc.Connection,
        user_id: UUID, # 修改为 UUID
        is_seller: bool,
        status: Optional[str] = None,
        page_number: int = 1,
        page_size: int = 10
    ) -> List[Dict[str, Any]]:
        try:
            # Fetch orders by user from DAL. DAL should handle pagination and status filtering
            orders = await self.order_dal.get_orders_by_user(conn, user_id, is_seller, status, page_number, page_size)
            return orders # Assuming DAL returns a list of dicts directly convertible
        except DALError as e:
            raise DALError(f"Error fetching orders for user {user_id}: {e}") from e
        except Exception as e:
            raise DALError(f"An unexpected error occurred fetching orders for user {user_id}: {e}") from e

    async def get_order_by_id(
        self,
        conn: pyodbc.Connection,
        order_id: UUID, # 修改为 UUID
        requesting_user_id: UUID # ID of the user requesting this order, for authorization
    ) -> Optional[OrderResponseSchema]:
        try:
            order = await self.order_dal.get_order_by_id(conn, order_id)
            if not order:
                raise NotFoundError(f"Order with ID {order_id} not found.")
            
            # Authorization check: only seller, buyer, or admin can view the order
            if order.get('BuyerID') != requesting_user_id and \
               order.get('SellerID') != requesting_user_id and \
               not (await self.order_dal.is_admin(conn, requesting_user_id)): # Assuming an admin check in DAL
                raise ForbiddenError("You are not authorized to view this order.")

            return order # Assuming DAL returns data compatible with OrderResponseSchema
        except pyodbc.Error as db_err:
            raise DALError(f"Database error getting order {order_id}: {db_err}") from db_err
        except (NotFoundError, ForbiddenError, DALError):
            raise
        except Exception as e:
            raise DALError(f"An unexpected error occurred getting order {order_id}: {e}") from e

    async def update_order_status(
        self,
        conn: pyodbc.Connection,
        order_id: UUID,
        new_status: str,
        user_id: UUID,
        cancel_reason: Optional[str] = None
    ) -> OrderResponseSchema:
        """
        Updates the status of an order.
        This method is a generic update, other specific methods (confirm, complete, reject, cancel) 
        should call this after their specific business logic.
        """
        try:
            # Basic validation for new_status
            valid_statuses = ['PendingSellerConfirmation', 'ConfirmedBySeller', 'Completed', 'Cancelled']
            if new_status not in valid_statuses:
                raise ValueError(f"Invalid order status: {new_status}. Must be one of {valid_statuses}.")

            # Fetch order to check current status and authorization
            order_to_update = await self.order_dal.get_order_by_id(conn, order_id)
            if not order_to_update:
                raise NotFoundError(f"Order with ID {order_id} not found.")

            current_status = order_to_update.get('Status')
            buyer_id = order_to_update.get('BuyerID')
            seller_id = order_to_update.get('SellerID')

            # Authorization: Only buyer, seller, or admin can update status
            is_admin = await self.order_dal.is_admin(conn, user_id)
            if user_id != buyer_id and user_id != seller_id and not is_admin:
                raise ForbiddenError("您无权修改此订单状态。")

            # State transition validation (example, extend as needed)
            if new_status == 'ConfirmedBySeller' and current_status != 'PendingSellerConfirmation':
                raise ValueError("订单必须处于'待卖家确认'状态才能被确认。")
            elif new_status == 'Completed' and current_status != 'ConfirmedBySeller':
                raise ValueError("订单必须处于'卖家已确认'状态才能被完成。")
            elif new_status == 'Cancelled' and current_status not in ['PendingSellerConfirmation', 'ConfirmedBySeller']:
                raise ValueError("订单必须处于'待卖家确认'或'卖家已确认'状态才能被取消。")
            
            # Ensure cancel_reason is provided if status is 'Cancelled'
            if new_status == 'Cancelled' and (cancel_reason is None or not cancel_reason.strip()):
                raise ValueError("取消订单必须提供取消原因。")

            await self.order_dal.update_order_status(conn, order_id, new_status, user_id, cancel_reason)
            
            updated_order = await self.order_dal.get_order_by_id(conn, order_id)
            if not updated_order:
                 raise NotFoundError(f"Order with ID {order_id} not found after status update.")
            return updated_order
        except pyodbc.Error as db_err:
            raise DALError(f"Database error updating order status for order {order_id}: {db_err}") from db_err
        except (NotFoundError, ForbiddenError, ValueError, DALError):
            raise
        except Exception as e:
            raise DALError(f"An unexpected error occurred updating order status for order {order_id}: {e}") from e

# Note: 
# 1. Pydantic Schemas (OrderCreateSchema, OrderResponseSchema, etc.) need to be defined in `app.schemas.order_schemas.py`.
# 2. OrderDAL needs to be implemented in `app.dal.order_dal.py` with methods like `create_order`, `confirm_order`, etc., that call the respective stored procedures.
# 3. The actual parameters and return values of DAL methods and stored procedures should be verified against their definitions.
# 4. Business logic within service methods (e.g., status checks, more detailed authorization) should be expanded based on specific requirements.
# 5. Error handling can be further refined, potentially raising more specific custom exceptions.