from uuid import UUID
from typing import Optional
from datetime import datetime
from pydantic import BaseModel, Field

class ProductResponseSchema(BaseModel):
    """
    用于返回商品详情的 Schema。
    字段名与 SQL 存储过程返回的中文列名一致。
    """
    商品ID: UUID = Field(..., alias="product_id", description="商品唯一ID")
    商品名称: str = Field(..., alias="product_name", description="商品名称")
    描述: Optional[str] = Field(None, alias="description", description="商品描述")
    价格: float = Field(..., alias="price", gt=0, description="商品价格")
    数量: Optional[int] = Field(None, alias="quantity", description="商品数量")
    发布时间: Optional[datetime] = Field(None, alias="post_time", description="发布时间")
    商品状态: Optional[str] = Field(None, alias="status", description="商品状态")
    卖家ID: Optional[UUID] = Field(None, alias="owner_id", description="卖家ID")
    卖家用户名: Optional[str] = Field(None, alias="owner_username", description="卖家用户名")
    分类名称: Optional[str] = Field(None, alias="category_name", description="分类名称")
    成色: Optional[str] = Field(None, alias="condition", description="商品成色")
    主图URL: Optional[str] = Field(None, alias="main_image_url", description="主图URL")
    图片URL列表: Optional[str] = Field(None, alias="image_urls", description="图片URL列表 (逗号分隔)")
    总商品数: Optional[int] = Field(None, alias="total_products", description="总商品数 (用于列表视图中，指示分页查询的总条目数)")
    审核拒绝原因: Optional[str] = Field(None, alias="audit_reason", description="审核拒绝原因")

    class Config:
        from_attributes = True
        populate_by_name = True
        # orm_mode = True # Pydantic v1 equivalent, use from_attributes for Pydantic v2