from fastapi import APIRouter, Depends, HTTPException
from ..services.product_service import ProductService
from ..dal.product_dal import ProductDAL
from ..schemas.product import ProductCreate, ProductUpdate
from ..dependencies import get_current_authenticated_user, get_current_active_admin_user, get_product_service, get_db_connection
import pyodbc
from fastapi import status
from typing import List, Optional
import os # Import os for file operations
from fastapi import UploadFile, File # Import UploadFile and File
from app.exceptions import NotFoundError, IntegrityError, DALError, ForbiddenError, PermissionError # Import specific exceptions
import logging # Import logging
import uuid # Import uuid for UUID conversion
from uuid import UUID

# Configure logging for this module
logger = logging.getLogger(__name__)

router = APIRouter()

@router.get("/favorites", status_code=status.HTTP_200_OK)
async def get_user_favorites(
    user = Depends(get_current_authenticated_user),
    product_service: ProductService = Depends(get_product_service),
    conn: pyodbc.Connection = Depends(get_db_connection)
):
    """
    获取当前用户收藏的商品列表
    
    Args:
        user: 当前认证用户
        product_service: 商品服务依赖
        conn: 数据库连接
    
    Returns:
        用户收藏的商品列表
    
    Raises:
        HTTPException: 获取失败时返回相应的HTTP错误
    """
    user_id = user.user_id # Directly access user_id
    try:
        favorites = await product_service.get_user_favorites(conn, user_id)
        return favorites
    except NotFoundError as e:
        logger.error(f"User favorites not found for user {user_id}: {e}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except (ValueError, DALError) as e:
        logger.error(f"Error getting user favorites for user {user_id}: {e}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        # user_id might be None if the HTTPException is raised before it's assigned
        # or if user.get() returns None for both keys.
        # Check if user_id is assigned before logging.
        log_user_id = user_id if user_id is not None else "N/A"
        logger.error(f"An unexpected error occurred while getting user favorites for user {log_user_id}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"服务器内部错误: {e}")

@router.get("/", response_model=List[dict], summary="获取商品列表", tags=["Products"])
@router.get("", response_model=List[dict], summary="获取商品列表 (无斜杠)", include_in_schema=False)
async def get_product_list(category_name: str = None, status: str = None, keyword: str = None, min_price: float = None, max_price: float = None, order_by: str = 'PostTime', page_number: int = 1, page_size: int = 10,
                            product_service: ProductService = Depends(get_product_service),
                            conn: pyodbc.Connection = Depends(get_db_connection)):
    """
    获取商品列表，支持多种筛选条件和分页
    
    Args:
        category_name: 商品分类名称
        status: 商品状态
        keyword: 搜索关键词
        min_price: 最低价格
        max_price: 最高价格
        order_by: 排序字段
        page_number: 页码
        page_size: 每页数量
        product_service: 商品服务依赖
        conn: 数据库连接
    
    Returns:
        商品列表
    
    Raises:
        HTTPException: 获取失败时返回相应的HTTP错误
    """
    try:
        products = await product_service.get_product_list(conn, category_name, status, keyword, min_price, max_price, order_by, page_number, page_size)
        return products
    except (ValueError, DALError) as e:
        logger.error(f"Error getting product list: {e}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"An unexpected error occurred while getting product list: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"服务器内部错误: {e}")

@router.post("", status_code=status.HTTP_201_CREATED)
async def create_product(product: ProductCreate, user = Depends(get_current_authenticated_user),
                          product_service: ProductService = Depends(get_product_service),
                          conn: pyodbc.Connection = Depends(get_db_connection)):
    """
    创建新商品
    
    Args:
        product: 商品创建请求体
        user: 当前认证用户
        product_service: 商品服务依赖
        conn: 数据库连接
    
    Returns:
        操作结果消息
    
    Raises:
        HTTPException: 创建失败时返回相应的HTTP错误
    """
    owner_id = user.user_id # Directly access user_id
    try:
        await product_service.create_product(conn, owner_id, product.category_name, product.product_name, 
                                            product.description, product.quantity, product.price, product.image_urls)
        return {"message": "商品创建成功"}
    except (ValueError, IntegrityError, DALError) as e: # Group ValueError, IntegrityError, DALError for 400
        logger.error(f"Error creating product: {e}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        log_owner_id = owner_id if owner_id is not None else "N/A"
        logger.error(f"An unexpected error occurred while creating product for owner {log_owner_id}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"服务器内部错误: {e}")

@router.put("/{product_id}")
async def update_product(
    product_id: UUID,
    product_update_data: ProductUpdate,
    current_user = Depends(get_current_authenticated_user),
    product_service: ProductService = Depends(get_product_service),
    conn: pyodbc.Connection = Depends(get_db_connection)
):
    """
    更新商品信息
    
    Args:
        product_id: 商品ID
        product_update_data: 商品更新请求体 (ProductUpdate Schema)
        current_user: 当前认证用户
        product_service: 商品服务依赖
        conn: 数据库连接
    
    Returns:
        操作结果消息
    
    Raises:
        HTTPException: 更新失败时返回相应的HTTP错误
    """
    owner_id = current_user.user_id # Directly access user_id
    try:
        await product_service.update_product(conn, product_id, owner_id, product_update_data)
        return {"message": "Product updated successfully"}
    except NotFoundError as e:
        logger.error(f"Error updating product {product_id}: {e}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except PermissionError as e:
        logger.error(f"Permission denied for updating product {product_id}: {e}")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except (ValueError, DALError) as e: # Group ValueError and DALError for 400
        logger.error(f"Validation error updating product {product_id}: {e}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        log_owner_id = owner_id if owner_id is not None else "N/A"
        logger.error(f"An unexpected error occurred while updating product {product_id} for owner {log_owner_id}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"服务器内部错误: {e}")

@router.delete("/{product_id}")
async def delete_product(product_id: UUID, user = Depends(get_current_authenticated_user),
                          product_service: ProductService = Depends(get_product_service),
                          conn: pyodbc.Connection = Depends(get_db_connection)):
    """
    删除商品
    
    Args:
        product_id: 商品ID
        user: 当前认证用户
        product_service: 商品服务依赖
        conn: 数据库连接
    
    Returns:
        操作结果消息
    
    Raises:
        HTTPException: 删除失败时返回相应的HTTP错误
    """
    owner_id = user.user_id # Directly access user_id
    try:
        await product_service.delete_product(conn, product_id, owner_id)
        return {"message": "商品删除成功"}
    except NotFoundError as e:
        logger.error(f"Error deleting product {product_id}: {e}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except PermissionError as e:
        logger.error(f"Permission denied for deleting product {product_id}: {e}")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except (ValueError, DALError) as e: # Group ValueError and DALError for 400
        logger.error(f"DAL Error deleting product {product_id}: {e}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        log_owner_id = owner_id if owner_id is not None else "N/A"
        logger.error(f"An unexpected error occurred while deleting product {product_id} for owner {log_owner_id}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"服务器内部错误: {e}")

@router.post("/batch/activate")
async def batch_activate_products(
    request_data: dict,
    admin = Depends(get_current_active_admin_user),
    product_service: ProductService = Depends(get_product_service),
    conn: pyodbc.Connection = Depends(get_db_connection)
):
    """
    管理员批量激活商品
    
    Args:
        request_data: 包含 product_ids 的字典
        admin: 当前认证的管理员用户
        product_service: 商品服务依赖
        conn: 数据库连接
    
    Returns:
        成功激活的商品数量
    
    Raises:
        HTTPException: 批量激活失败时返回相应的HTTP错误
    """
    admin_id = admin.user_id # Directly access user_id
    try:
        product_ids_str = request_data.get("product_ids")
        if not product_ids_str or not isinstance(product_ids_str, list):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="商品ID列表缺失或格式不正确")
        
        # Convert string UUIDs to UUID objects for the service layer
        product_ids_uuid = []
        for pid_str in product_ids_str:
            try:
                product_ids_uuid.append(UUID(pid_str))
            except ValueError:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"无效的商品ID格式: {pid_str}")

        affected_count = await product_service.batch_activate_products(conn, product_ids_uuid, admin_id)
        return {"message": f"成功激活 {affected_count} 件商品"}
    except NotFoundError as e:
        logger.error(f"Error activating product(s) during batch activation: {e}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except PermissionError as e:
        logger.error(f"Permission denied during batch activation: {e}")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except (ValueError, DALError) as e: # Group ValueError and DALError for 400
        logger.error(f"Error during batch activation: {e}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        log_admin_id = admin_id if admin_id is not None else "N/A"
        logger.error(f"An unexpected error occurred while batch activating products for admin {log_admin_id}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"服务器内部错误: {e}")

@router.post("/batch/reject")
async def batch_reject_products(
    request_data: dict,
    admin = Depends(get_current_active_admin_user),
    product_service: ProductService = Depends(get_product_service),
    conn: pyodbc.Connection = Depends(get_db_connection)
):
    """
    管理员批量拒绝商品
    
    Args:
        request_data: 包含 product_ids 和 reason 的字典
        admin: 当前认证的管理员用户
        product_service: 商品服务依赖
        conn: 数据库连接
    
    Returns:
        成功拒绝的商品数量
    
    Raises:
        HTTPException: 批量拒绝失败时返回相应的HTTP错误
    """
    admin_id = admin.user_id # Directly access user_id
    try:
        product_ids_str = request_data.get("product_ids")
        reason = request_data.get("reason") # Extract reason from request_data
        if not product_ids_str or not isinstance(product_ids_str, list):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="商品ID列表缺失或格式不正确")
        
        # Convert string UUIDs to UUID objects for the service layer
        product_ids_uuid = []
        for pid_str in product_ids_str:
            try:
                product_ids_uuid.append(UUID(pid_str))
            except ValueError:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"无效的商品ID格式: {pid_str}")

        affected_count = await product_service.batch_reject_products(conn, product_ids_uuid, admin_id, reason) # Pass reason
        return {"message": f"成功拒绝 {affected_count} 件商品"}
    except NotFoundError as e:
        logger.error(f"Product(s) not found during batch rejection: {e}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except PermissionError as e:
        logger.error(f"Permission denied during batch rejection: {e}")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except (ValueError, DALError) as e: # Group ValueError and DALError for 400
        logger.error(f"Error during batch rejection: {e}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        log_admin_id = admin_id if admin_id is not None else "N/A"
        logger.error(f"An unexpected error occurred while batch rejecting products for admin {log_admin_id}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"服务器内部错误: {e}")

@router.post("/{product_id}/favorite", status_code=status.HTTP_201_CREATED)
async def add_favorite(product_id: UUID, user = Depends(get_current_authenticated_user),
                       product_service: ProductService = Depends(get_product_service),
                       conn: pyodbc.Connection = Depends(get_db_connection)):
    """
    收藏商品
    
    Args:
        product_id: 商品ID
        user: 当前认证用户
        product_service: 商品服务依赖
        conn: 数据库连接
    
    Returns:
        收藏成功的消息
    
    Raises:
        HTTPException: 收藏失败时返回相应的HTTP错误
    """
    user_id = user.user_id # Directly access user_id
    try:
        await product_service.add_favorite(conn, user_id, product_id) # 传入UUID类型
        return {"message": "商品收藏成功"}
    except IntegrityError as e:
        logger.error(f"Error adding favorite for user {user_id}, product {product_id}: {e}")
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except NotFoundError as e:
        logger.error(f"Product or user not found for favorite: {e}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except (ValueError, DALError) as e: # Group ValueError and DALError for 400
        logger.error(f"Error adding favorite for user {user_id}, product {product_id}: {e}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        log_user_id = user_id if user_id is not None else "N/A"
        logger.error(f"An unexpected error occurred while adding favorite for user {log_user_id}, product {product_id}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"服务器内部错误: {e}")

@router.delete("/{product_id}/favorite", status_code=status.HTTP_200_OK)
async def remove_favorite(product_id: UUID, user = Depends(get_current_authenticated_user),
                          product_service: ProductService = Depends(get_product_service),
                          conn: pyodbc.Connection = Depends(get_db_connection)):
    """
    移除商品收藏
    
    Args:
        product_id: 商品ID
        user: 当前认证用户
        product_service: 商品服务依赖
        conn: 数据库连接
    
    Returns:
        操作结果消息
    
    Raises:
        HTTPException: 移除失败时返回相应的HTTP错误
    """
    user_id = user.user_id # Directly access user_id
    try:
        await product_service.remove_favorite(conn, user_id, product_id) # 传入UUID类型
        return {"message": "商品已成功从收藏列表中移除"}
    except NotFoundError as e:
        logger.error(f"Error removing favorite for user {user_id}, product {product_id}: {e}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except (ValueError, DALError) as e: # Group ValueError and DALError for 400
        logger.error(f"Error removing favorite for user {user_id}, product {product_id}: {e}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        log_user_id = user_id if user_id is not None else "N/A"
        logger.error(f"An unexpected error occurred while removing favorite for user {log_user_id}, product {product_id}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"服务器内部错误: {e}")

@router.get("/{product_id}")
async def get_product_detail(product_id: UUID,
                              product_service: ProductService = Depends(get_product_service),
                              conn: pyodbc.Connection = Depends(get_db_connection)):
    """
    根据商品ID获取商品详情
    
    Args:
        product_id: 商品ID
        product_service: 商品服务依赖
        conn: 数据库连接
    
    Returns:
        商品详情
    
    Raises:
        HTTPException: 未找到商品时返回404，获取失败时返回500
    """
    try:
        product = await product_service.get_product_detail(conn, product_id)
        if not product:
            raise NotFoundError("商品未找到")
        return product
    except NotFoundError as e:
        logger.error(f"Product with ID {product_id} not found: {e}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except (ValueError, DALError) as e: # Group ValueError and DALError for 400
        logger.error(f"Error getting product detail for ID {product_id}: {e}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"An unexpected error occurred while getting product detail for ID {product_id}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"服务器内部错误: {e}")

@router.put("/{product_id}/status/activate")
async def activate_product(product_id: UUID, admin = Depends(get_current_active_admin_user),
                            product_service: ProductService = Depends(get_product_service),
                            conn: pyodbc.Connection = Depends(get_db_connection)):
    """
    管理员激活商品
    
    Args:
        product_id: 商品ID
        admin: 当前认证的管理员用户
        product_service: 商品服务依赖
        conn: 数据库连接
    
    Returns:
        操作结果消息
    
    Raises:
        HTTPException: 激活失败时返回相应的HTTP错误
    """
    admin_id = admin.user_id # Directly access user_id
    try:
        await product_service.activate_product(conn, product_id, admin_id) # 传入UUID类型
        return {"message": "商品已成功激活"}
    except NotFoundError as e:
        logger.error(f"Product with ID {product_id} not found for activation: {e}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except PermissionError as e:
        logger.error(f"Permission denied for activating product: {e}")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except (ValueError, DALError) as e: # Group ValueError and DALError for 400
        logger.error(f"Error activating product {product_id}: {e}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        log_admin_id = admin_id if admin_id is not None else "N/A"
        logger.error(f"An unexpected error occurred while activating product for admin {log_admin_id}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"服务器内部错误: {e}")

@router.put("/{product_id}/status/reject")
async def reject_product(product_id: UUID, request_data: dict,
                            admin = Depends(get_current_active_admin_user),
                            product_service: ProductService = Depends(get_product_service),
                            conn: pyodbc.Connection = Depends(get_db_connection)):
    """
    管理员拒绝商品
    
    Args:
        product_id: 商品ID
        request_data: 包含拒绝原因的字典 (e.g., {"reason": "不符合发布规范"})
        admin: 当前认证的管理员用户
        product_service: 商品服务依赖
        conn: 数据库连接
    
    Returns:
        操作结果消息
    
    Raises:
        HTTPException: 拒绝失败时返回相应的HTTP错误
    """
    admin_id = admin.user_id # Directly access user_id
    try:
        reason = request_data.get("reason")
        if reason is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="拒绝原因不可为空")
        
        await product_service.reject_product(conn, product_id, admin_id, reason)
        return {"message": "商品已成功拒绝"}
    except NotFoundError as e:
        logger.error(f"Product with ID {product_id} not found for rejection: {e}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except PermissionError as e:
        logger.error(f"Permission denied for rejecting product: {e}")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except (ValueError, DALError) as e: # Group ValueError and DALError for 400
        logger.error(f"Error rejecting product {product_id}: {e}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        log_admin_id = admin_id if admin_id is not None else "N/A"
        logger.error(f"An unexpected error occurred while rejecting product for admin {log_admin_id}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"服务器内部错误: {e}")

@router.put("/{product_id}/status/withdraw")
async def withdraw_product(product_id: UUID, user = Depends(get_current_authenticated_user),
                            product_service: ProductService = Depends(get_product_service),
                            conn: pyodbc.Connection = Depends(get_db_connection)):
    """
    商品所有者下架商品
    
    Args:
        product_id: 商品ID
        user: 当前认证用户
        product_service: 商品服务依赖
        conn: 数据库连接
    
    Returns:
        操作结果消息
    
    Raises:
        HTTPException: 下架失败时返回相应的HTTP错误
    """
    owner_id = user.user_id # Directly access user_id
    try:
        await product_service.withdraw_product(conn, product_id, owner_id)
        return {"message": "商品已成功下架"}
    except NotFoundError as e:
        logger.error(f"Product with ID {product_id} not found for withdrawal: {e}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except PermissionError as e:
        logger.error(f"Permission denied for withdrawing product {product_id}: {e}")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except (ValueError, DALError) as e: # Group ValueError and DALError for 400
        logger.error(f"Error withdrawing product {product_id}: {e}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        log_owner_id = owner_id if owner_id is not None else "N/A"
        logger.error(f"An unexpected error occurred while withdrawing product {product_id} for owner {log_owner_id}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"服务器内部错误: {e}")