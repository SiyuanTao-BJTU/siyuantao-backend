from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime
from uuid import UUID

class ProductImage(BaseModel):
    image_url: str
    upload_time: datetime = Field(default_factory=datetime.now)
    sort_order: int = 0

class ProductBase(BaseModel):
    category_name: Optional[str]
    product_name: str
    description: Optional[str]
    quantity: int
    price: float
    status: str = "PendingReview"

class ProductCreate(ProductBase):
    image_urls: List[str] = Field(default_factory=list)

class ProductUpdate(BaseModel):
    category_name: Optional[str] = None
    product_name: Optional[str] = None
    description: Optional[str] = None
    quantity: Optional[int] = None
    price: Optional[float] = None
    condition: Optional[str] = None
    image_urls: Optional[List[str]] = Field(None)

class Product(ProductBase):
    product_id: UUID
    owner_id: UUID
    post_time: datetime = Field(default_factory=datetime.now)
    images: List[ProductImage] = Field(default_factory=list)

    class Config:
        orm_mode = True