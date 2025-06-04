from fastapi import APIRouter, Depends, HTTPException
from ..services.product_service import ProductService
from ..dal.product_dal import ProductDAL
from ..dal.product_image_dal import ProductImageDAL
from ..dal.user_favorite_dal import UserFavoriteDAL
from ..dependencies import get_db, get_current_user

router = APIRouter()

@router.post("/api/v1/favorites/{product_id}")
async def add_favorite(product_id: int, user = Depends(get_current_user), db: databases.Database = Depends(get_db)):
    """
    用户收藏商品
    
    Args:
        product_id: 商品ID
        user: 当前认证用户
        db: 数据库连接
    
    Returns:
        操作结果消息
    
    Raises:
        HTTPException: 操作失败时返回400错误
    """
    product_dal = ProductDAL(db)
    product_image_dal = ProductImageDAL(db)
    user_favorite_dal = UserFavoriteDAL(db)
    product_service = ProductService(product_dal, product_image_dal, user_favorite_dal)
    try:
        await product_service.add_favorite(user.id, product_id)
        return {"message": "Product added to favorites successfully"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.delete("/api/v1/favorites/{product_id}")
async def remove_favorite(product_id: int, user = Depends(get_current_user), db: databases.Database = Depends(get_db)):
    """
    用户取消收藏商品
    
    Args:
        product_id: 商品ID
        user: 当前认证用户
        db: 数据库连接
    
    Returns:
        操作结果消息
    
    Raises:
        HTTPException: 操作失败时返回400错误
    """
    product_dal = ProductDAL(db)
    product_image_dal = ProductImageDAL(db)
    user_favorite_dal = UserFavoriteDAL(db)
    product_service = ProductService(product_dal, product_image_dal, user_favorite_dal)
    try:
        await product_service.remove_favorite(user.id, product_id)
        return {"message": "Product removed from favorites successfully"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/api/v1/favorites")
async def get_user_favorites(user = Depends(get_current_user), db: databases.Database = Depends(get_db)):
    """
    获取用户收藏的商品列表
    
    Args:
        user: 当前认证用户
        db: 数据库连接
    
    Returns:
        用户收藏的商品列表
    """
    product_dal = ProductDAL(db)
    product_image_dal = ProductImageDAL(db)
    user_favorite_dal = UserFavoriteDAL(db)
    product_service = ProductService(product_dal, product_image_dal, user_favorite_dal)
    favorites = await product_service.get_user_favorites(user.id)
    return favorites