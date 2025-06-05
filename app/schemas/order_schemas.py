from typing import Optional
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel, Field, ValidationError, model_validator

# 根据 SQL Server 的 UNIQUEIDENTIFIER 类型，使用 UUID
# 根据 SQL Server 的 NVARCHAR 类型，使用 str
# 根据 SQL Server 的 INT 类型，使用 int
# 根据 SQL Server 的 DECIMAL(10, 2) 类型，使用 float 或 Decimal (这里使用 float 简化)
# 根据 SQL Server 的 DATETIME 类型，使用 datetime

class OrderCreateSchema(BaseModel):
    """
    Schema for creating a new order.
    Based on sp_CreateOrder procedure parameters and Order table fields.
    """
    product_id: UUID = Field(..., description="ID of the product being ordered")
    quantity: int = Field(..., gt=0, description="Quantity of the product")
    trade_time: datetime = Field(..., description="Offline trade time") # 新增交易时间
    trade_location: str = Field(..., max_length=255, description="Offline trade location") # 新增交易地点

    class Config:
        orm_mode = True # 允许从 ORM 模型创建 Schema 实例

class OrderResponseSchema(BaseModel):
    """
    Schema for returning order details.
    Based on Order table fields.
    """
    订单ID: UUID = Field(..., alias="order_id", description="Unique ID of the order")
    卖家ID: UUID = Field(..., alias="seller_id", description="ID of the seller")
    买家ID: UUID = Field(..., alias="buyer_id", description="ID of the buyer")
    商品ID: UUID = Field(..., alias="product_id", description="ID of the product ordered")
    数量: int = Field(..., alias="quantity", description="Quantity of the product")
    交易时间: datetime = Field(..., alias="trade_time", description="Offline trade time")
    交易地点: str = Field(..., alias="trade_location", description="Offline trade location")
    订单状态: str = Field(..., alias="status", description="Current status of the order")
    创建时间: datetime = Field(..., alias="created_at", description="Timestamp when the order was created")
    更新时间: datetime = Field(..., alias="updated_at", description="Timestamp when the order was last updated")
    完成时间: Optional[datetime] = Field(None, alias="complete_time", description="Timestamp when the order was completed")
    取消时间: Optional[datetime] = Field(None, alias="cancel_time", description="Timestamp when the order was cancelled")
    取消原因: Optional[str] = Field(None, alias="cancel_reason", description="Reason for order cancellation")
    商品名称: Optional[str] = Field(None, alias="product_name", description="Name of the product ordered")
    卖家用户名: Optional[str] = Field(None, alias="seller_username", description="Username of the seller")
    买家用户名: Optional[str] = Field(None, alias="buyer_username", description="Username of the buyer")
    是否已评价: Optional[bool] = Field(None, alias="has_evaluated", description="是否已评价")

    class Config:
        orm_mode = True
        populate_by_name = True # Pydantic v2: 允许通过别名填充模型

class OrderStatusUpdateSchema(BaseModel):
    """
    Schema for updating the status of an order.
    Based on potential status update operations (e.g., confirm, complete, cancel).
    """
    status: str = Field(..., description="New status for the order")
    cancel_reason: Optional[str] = Field(None, description="Reason for cancellation, required if status is 'Cancelled'")

    @model_validator(mode='after')
    def validate_cancellation_reason(self) -> 'OrderStatusUpdateSchema':
        if self.status == 'Cancelled' and not self.cancel_reason:
            raise ValueError("取消原因不能为空")
        return self

    class Config:
        orm_mode = True

class RejectionReasonSchema(BaseModel):
    """
    Schema for providing a rejection reason.
    """
    rejection_reason: str = Field(..., min_length=1, description="Reason for rejecting the order.")

    class Config:
        orm_mode = True