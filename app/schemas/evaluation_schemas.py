from uuid import UUID
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field

class EvaluationCreateSchema(BaseModel):
    """
    评价创建Schema
    对应存储过程：[dbo].[CreateEvaluation]
    """
    order_id: UUID = Field(..., description="订单ID")
    rating: int = Field(..., ge=1, le=5, description="评分 (1-5)")
    comment: Optional[str] = Field(None, max_length=500, description="评价内容")

    class Config:
        from_attributes = True

class EvaluationResponseSchema(BaseModel):
    """
    评价响应Schema
    用于返回评价的完整信息
    """
    评价ID: UUID = Field(..., alias="evaluation_id", description="评价ID")
    订单ID: UUID = Field(..., alias="order_id", description="订单ID")
    商品ID: Optional[UUID] = Field(None, alias="product_id", description="商品ID")
    买家ID: UUID = Field(..., alias="buyer_id", description="评价发起人ID，即买家ID")
    卖家ID: UUID = Field(..., alias="seller_id", description="评价对象ID，即卖家ID")
    评分: int = Field(..., alias="rating", description="评分")
    评价内容: Optional[str] = Field(None, alias="comment", description="评价内容")
    创建时间: datetime = Field(..., alias="created_at", description="评价创建时间")

    class Config:
        from_attributes = True
        populate_by_name = True