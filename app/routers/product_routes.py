from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status as fastapi_status
from ..services.product_service import ProductService
from ..dal.product_dal import ProductDAL
from ..schemas.product import ProductCreate, ProductUpdate
from app.schemas.product_schemas import ProductResponseSchema
from ..dependencies import get_current_authenticated_user, get_current_active_admin_user, get_product_service, get_db_connection
import pyodbc
from typing import List, Optional
import os # Import os for file operations
from app.schemas.user_schemas import UserResponseSchema # 添加导入
from app.exceptions import NotFoundError, IntegrityError, DALError, ForbiddenError, PermissionError # Import specific exceptions
import logging # Import logging
import uuid # Import uuid for UUID conversion
from uuid import UUID

# Configure logging for this module
logger = logging.getLogger(__name__)

router = APIRouter()

@router.get("/favorites", status_code=fastapi_status.HTTP_200_OK, response_model=List[dict], response_model_by_alias=False)
async def get_user_favorites(
    user: dict = Depends(get_current_authenticated_user),
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
    user_id = user['用户ID'] # Changed to dictionary access
    try:
        favorites = await product_service.get_user_favorites(conn, user_id)
        return favorites
    except NotFoundError as e:
        logger.error(f"User favorites not found for user {user_id}: {e}")
        raise HTTPException(status_code=fastapi_status.HTTP_404_NOT_FOUND, detail=str(e))
    except (ValueError, DALError) as e:
        logger.error(f"Error getting user favorites for user {user_id}: {e}")
        raise HTTPException(status_code=fastapi_status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        # user_id might be None if the HTTPException is raised before it's assigned
        # or if user.get() returns None for both keys.
        # Check if user_id is assigned before logging.
        log_user_id = user['用户ID'] if user and '用户ID' in user else "N/A" # Use Chinese key
        logger.error(f"An unexpected error occurred while getting user favorites for user {log_user_id}: {e}", exc_info=True)
        raise HTTPException(status_code=fastapi_status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"服务器内部错误: {e}")

@router.get("/", response_model=List[dict], summary="获取商品列表", tags=["Products"], response_model_by_alias=False)
@router.get("", response_model=List[dict], summary="获取商品列表 (无斜杠)", include_in_schema=False, response_model_by_alias=False)
async def get_product_list(category_name: str = None, status: str = None, keyword: str = None, min_price: float = None, max_price: float = None, order_by: str = 'PostTime', page_number: int = 1, page_size: int = 10,
                            product_service: ProductService = Depends(get_product_service),
                            conn: pyodbc.Connection = Depends(get_db_connection),
                            owner_id: Optional[UUID] = None): # 添加 owner_id 参数
    logger.info(f"Router: get_product_list called with status={status}, category_name={category_name}, keyword={keyword}")
    try:
        # 如果提供了 owner_id，则忽略 product_status 过滤，只按 owner_id 过滤
        if owner_id:
            products = await product_service.get_product_list(conn, category_name, None, keyword, min_price, max_price, order_by, page_number, page_size, owner_id)
        else:
            products = await product_service.get_product_list(conn, category_name, status, keyword, min_price, max_price, order_by, page_number, page_size, owner_id)
        return products
    except (ValueError, DALError) as e:
        logger.error(f"Error getting product list: {e}")
        raise HTTPException(status_code=fastapi_status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"An unexpected error occurred while getting product list: {e}", exc_info=True)
        raise HTTPException(status_code=fastapi_status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"服务器内部错误: {e}")

@router.post("", status_code=fastapi_status.HTTP_201_CREATED)
async def create_product(product: ProductCreate, user: dict = Depends(get_current_authenticated_user),
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
    return await product_service.create_product(conn, user['用户ID'], product.category_name, product.product_name, 
                                              product.description, product.quantity, product.price, product.condition, product.image_urls)

@router.put("/{product_id}", status_code=fastapi_status.HTTP_204_NO_CONTENT)
async def update_product(
    product_id: UUID,
    product_update_data: ProductUpdate,
    current_user: dict = Depends(get_current_authenticated_user), # Changed type hint to dict
    product_service: ProductService = Depends(get_product_service),
    conn: pyodbc.Connection = Depends(get_db_connection)
):
    """
    Update a product by its ID. 
    Users can update their own products. Admins can update any product.
    """
    try:
        await product_service.update_product(conn, product_id, current_user, product_update_data)
        # For HTTP 204, no content should be returned in the body.
        # FastAPI handles this automatically if the status_code is 204 and no value is returned.
        return 
    except NotFoundError as e:
        logger.error(f"Product not found for update: {product_id}, Error: {e}")
        raise HTTPException(status_code=fastapi_status.HTTP_404_NOT_FOUND, detail=str(e))
    except PermissionError as e:
        logger.error(f"Permission denied for updating product {product_id}: {e}")
        raise HTTPException(status_code=fastapi_status.HTTP_403_FORBIDDEN, detail=str(e))
    except DALError as e:
        logger.error(f"DAL error during product update {product_id}: {e}")
        raise HTTPException(status_code=fastapi_status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"数据库操作失败: {e}")
    except Exception as e:
        logger.error(f"An unexpected error occurred while deleting product {product_id} by user {current_user['用户ID']}: {e}", exc_info=True) # Use Chinese key
        raise HTTPException(status_code=fastapi_status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"服务器内部错误: {e}")

@router.delete("/{product_id}", status_code=fastapi_status.HTTP_204_NO_CONTENT)
async def delete_product(product_id: UUID, 
                         current_user: dict = Depends(get_current_authenticated_user), # Changed type hint to dict
                         product_service: ProductService = Depends(get_product_service),
                         conn: pyodbc.Connection = Depends(get_db_connection)):
    """
    删除商品。管理员可以删除任何商品，普通用户只能删除自己的商品。
    """
    try:
        await product_service.delete_product(conn, product_id, current_user)
        return # HTTP 204 No Content
    except NotFoundError as e:
        logger.error(f"Error deleting product {product_id}: {e}")
        raise HTTPException(status_code=fastapi_status.HTTP_404_NOT_FOUND, detail=str(e))
    except PermissionError as e:
        logger.error(f"Permission denied for deleting product {product_id}: {e}")
        raise HTTPException(status_code=fastapi_status.HTTP_403_FORBIDDEN, detail=str(e))
    except DALError as e: 
        logger.error(f"DAL Error deleting product {product_id}: {e}")
        # 将DALError具体化为500错误，因为SP的RAISERROR通常表示操作层面的问题，但这里DALError是通用包装
        raise HTTPException(status_code=fastapi_status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"数据库操作失败: {e}")
    except Exception as e:
        logger.error(f"An unexpected error occurred while deleting product {product_id} by user {current_user['用户ID']}: {e}", exc_info=True) # Use Chinese key
        raise HTTPException(status_code=fastapi_status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"服务器内部错误: {e}")

@router.post("/batch/activate", response_model_by_alias=False)
async def batch_activate_products(
    request_data: dict,
    admin: dict = Depends(get_current_active_admin_user), # Changed type hint to dict
    product_service: ProductService = Depends(get_product_service),
    conn: pyodbc.Connection = Depends(get_db_connection)
):
    """
    Batch activate products by an admin.
    - **request_data**: Dictionary containing a list of product_ids. Expected key: "product_ids".
    - **admin**: Admin user performing the action.
    """
    product_ids_str = request_data.get("product_ids")
    if not product_ids_str:
        raise HTTPException(status_code=fastapi_status.HTTP_400_BAD_REQUEST, detail="请求体中必须包含 'product_ids' 列表。")

    try:
        # Attempt to convert all product_id strings to UUIDs
        product_ids_uuid = [UUID(pid) for pid in product_ids_str]
    except ValueError:
        raise HTTPException(status_code=fastapi_status.HTTP_400_BAD_REQUEST, detail="一个或多个 'product_ids' 无效。")
    
    logger.info(f"Router: Batch activating products by admin {admin.get('user_id')}: {product_ids_uuid}") # Use .get for safer access
    admin_id_uuid = admin["user_id"] # Use English key


    # Check if product_ids_uuid is empty after validation (though ValueErro might catch it earlier if format is wrong)
    if not product_ids_uuid:
        raise HTTPException(status_code=fastapi_status.HTTP_400_BAD_REQUEST, detail="商品ID列表不能为空。")

    try:
        # Ensure admin_id_uuid is a UUID if it's not already (it should be from the token)
        # admin_id_uuid = UUID(admin.get("user_id"))

        activated_count = await product_service.batch_activate_products(conn, product_ids_uuid, admin_id_uuid) # Pass admin_id_uuid
        return {"message": f"成功激活 {activated_count} 个商品。", "activated_count": activated_count}
    except HTTPException as e: # Re-raise HTTPExceptions
        raise e
    except NotFoundError as e: # Example: if ProductService can raise this for some IDs
        logger.warning(f"NotFoundError in batch_activate_products: {e}")
        raise HTTPException(status_code=fastapi_status.HTTP_404_NOT_FOUND, detail=str(e))
    except PermissionError as e: # Catch specific permission errors
        logger.warning(f"PermissionError in batch_activate_products: {e}")
        raise HTTPException(status_code=fastapi_status.HTTP_403_FORBIDDEN, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error in batch_activate_products: {e}", exc_info=True)
        raise HTTPException(status_code=fastapi_status.HTTP_500_INTERNAL_SERVER_ERROR, detail="批量激活商品时发生内部错误")

@router.post("/batch/reject", response_model_by_alias=False)
async def batch_reject_products(
    request_data: dict,
    admin: dict = Depends(get_current_active_admin_user), # Changed type hint to dict
    product_service: ProductService = Depends(get_product_service),
    conn: pyodbc.Connection = Depends(get_db_connection)
):
    """
    Batch reject products by an admin.
    - **request_data**: Dictionary containing a list of product_ids and a reason.
                      Expected keys: "product_ids", "reason".
    - **admin**: Admin user performing the action.
    """
    product_ids_str = request_data.get("product_ids")
    reason = request_data.get("reason")

    if not product_ids_str:
        raise HTTPException(status_code=fastapi_status.HTTP_400_BAD_REQUEST, detail="请求体中必须包含 'product_ids' 列表。")
    if not reason:
        raise HTTPException(status_code=fastapi_status.HTTP_400_BAD_REQUEST, detail="请求体中必须包含 'reason'。")

    try:
        product_ids_uuid = [UUID(pid) for pid in product_ids_str]
    except ValueError:
        raise HTTPException(status_code=fastapi_status.HTTP_400_BAD_REQUEST, detail="一个或多个 'product_ids' 无效。")

    logger.info(f"Router: Batch rejecting products by admin {admin.get('user_id')} with reason '{reason}': {product_ids_uuid}") # Use .get for safer access
    admin_id_uuid = admin["user_id"] # Use English key

    if not product_ids_uuid: # Check if list is empty after potential filtering or if input was just '[]'
        raise HTTPException(status_code=fastapi_status.HTTP_400_BAD_REQUEST, detail="商品ID列表不能为空。")
    
    try:
        # Ensure admin_id_uuid is a UUID
        # admin_id_uuid = UUID(admin.get("user_id"))

        rejected_count = await product_service.batch_reject_products(conn, product_ids_uuid, admin_id_uuid, reason) # Pass admin_id_uuid
        return {"message": f"成功拒绝 {rejected_count} 个商品。", "rejected_count": rejected_count}
    except HTTPException as e: # Re-raise HTTPExceptions
        raise e
    except NotFoundError as e:
        logger.warning(f"NotFoundError in batch_reject_products: {e}")
        raise HTTPException(status_code=fastapi_status.HTTP_404_NOT_FOUND, detail=str(e))
    except PermissionError as e:
        logger.warning(f"PermissionError in batch_reject_products: {e}")
        raise HTTPException(status_code=fastapi_status.HTTP_403_FORBIDDEN, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error in batch_reject_products: {e}", exc_info=True)
        raise HTTPException(status_code=fastapi_status.HTTP_500_INTERNAL_SERVER_ERROR, detail="批量拒绝商品时发生内部错误")

@router.post("/{product_id}/favorite", status_code=fastapi_status.HTTP_201_CREATED, response_model_by_alias=False)
async def add_favorite(product_id: UUID, user: dict = Depends(get_current_authenticated_user), # Changed type hint to dict
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
    user_id = user['用户ID'] # Use Chinese key
    try:
        await product_service.add_favorite(conn, user_id, product_id) # 传入UUID类型
        return {"message": "商品收藏成功"}
    except IntegrityError as e:
        logger.error(f"Error adding favorite for user {user_id}, product {product_id}: {e}")
        raise HTTPException(status_code=fastapi_status.HTTP_409_CONFLICT, detail=str(e))
    except NotFoundError as e:
        logger.error(f"Product or user not found for favorite: {e}")
        raise HTTPException(status_code=fastapi_status.HTTP_404_NOT_FOUND, detail=str(e))
    except (ValueError, DALError) as e: # Group ValueError and DALError for 400
        logger.error(f"Error adding favorite for user {user_id}, product {product_id}: {e}")
        raise HTTPException(status_code=fastapi_status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        log_user_id = user_id if user_id is not None else "N/A"
        logger.error(f"An unexpected error occurred while adding favorite for user {log_user_id}, product {product_id}: {e}", exc_info=True)
        raise HTTPException(status_code=fastapi_status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"服务器内部错误: {e}")

@router.delete("/{product_id}/favorite", status_code=fastapi_status.HTTP_200_OK, response_model_by_alias=False)
async def remove_favorite(product_id: UUID, user: dict = Depends(get_current_authenticated_user), # Changed type hint to dict
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
    user_id = user['用户ID'] # Use Chinese key
    try:
        await product_service.remove_favorite(conn, user_id, product_id) # 传入UUID类型
        return {"message": "商品已成功从收藏列表中移除"}
    except NotFoundError as e:
        logger.error(f"Error removing favorite for user {user_id}, product {product_id}: {e}")
        raise HTTPException(status_code=fastapi_status.HTTP_404_NOT_FOUND, detail=str(e))
    except (ValueError, DALError) as e: # Group ValueError and DALError for 400
        logger.error(f"Error removing favorite for user {user_id}, product {product_id}: {e}")
        raise HTTPException(status_code=fastapi_status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        log_user_id = user_id if user_id is not None else "N/A"
        logger.error(f"An unexpected error occurred while removing favorite for user {log_user_id}, product {product_id}: {e}", exc_info=True)
        raise HTTPException(status_code=fastapi_status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"服务器内部错误: {e}")

@router.get("/{product_id}", response_model=ProductResponseSchema, response_model_by_alias=False)
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
        raise HTTPException(status_code=fastapi_status.HTTP_404_NOT_FOUND, detail=str(e))
    except (ValueError, DALError) as e: # Group ValueError and DALError for 400
        logger.error(f"Error getting product detail for ID {product_id}: {e}")
        raise HTTPException(status_code=fastapi_status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"An unexpected error occurred while getting product detail for ID {product_id}: {e}", exc_info=True)
        raise HTTPException(status_code=fastapi_status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"服务器内部错误: {e}")

@router.put("/{product_id}/status/activate", response_model_by_alias=False)
async def activate_product(product_id: UUID, 
                            current_user: dict = Depends(get_current_authenticated_user), # 更改依赖为 get_current_authenticated_user
                            product_service: ProductService = Depends(get_product_service),
                            conn: pyodbc.Connection = Depends(get_db_connection)):
    """
    Activate a product by an admin or owner.
    - **product_id**: UUID of the product to activate.
    - **current_user**: Authenticated user performing the action.
    """
    try:
        logger.info(f"Router: Activating product {product_id} by user {current_user.get('用户ID')}") 
        await product_service.activate_product(conn, product_id, current_user) # 传递 current_user 对象
        return {"message": "商品激活成功"}
    except HTTPException as e:
        logger.error(f"HTTPException in activate_product: {e.detail}")
        raise e
    except NotFoundError as e:
        logger.warning(f"NotFoundError in activate_product: {e}")
        raise HTTPException(status_code=fastapi_status.HTTP_404_NOT_FOUND, detail=str(e))
    except PermissionError as e: # Catch specific permission errors if ProductService raises them
        logger.warning(f"PermissionError in activate_product: {e}")
        raise HTTPException(status_code=fastapi_status.HTTP_403_FORBIDDEN, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error in activate_product for product {product_id}: {e}", exc_info=True)
        raise HTTPException(status_code=fastapi_status.HTTP_500_INTERNAL_SERVER_ERROR, detail="激活商品时发生内部错误")

@router.put("/{product_id}/status/reject", response_model_by_alias=False)
async def reject_product(product_id: UUID, request_data: dict,
                            admin: dict = Depends(get_current_active_admin_user), # Changed type hint to dict
                            product_service: ProductService = Depends(get_product_service),
                            conn: pyodbc.Connection = Depends(get_db_connection)):
    """
    Reject a product by an admin.
    - **product_id**: UUID of the product to reject.
    - **request_data**: Dictionary containing the rejection reason. Expected key: "reason".
    - **admin**: Admin user performing the action.
    """
    try:
        reason = request_data.get("reason")
        if not reason:
            raise HTTPException(status_code=fastapi_status.HTTP_400_BAD_REQUEST, detail="拒绝商品必须提供原因")
        logger.info(f"Router: Rejecting product {product_id} by admin {admin.get('user_id')} with reason: {reason}")
        admin_id = admin["user_id"] # Use English key
        await product_service.reject_product(conn, product_id, admin_id, reason) # Pass admin_id (UUID)
        return {"message": "商品拒绝成功"}
    except HTTPException as e:
        logger.error(f"HTTPException in reject_product: {e.detail}")
        raise e
    except NotFoundError as e:
        logger.warning(f"NotFoundError in reject_product: {e}")
        raise HTTPException(status_code=fastapi_status.HTTP_404_NOT_FOUND, detail=str(e))
    except PermissionError as e:
        logger.warning(f"PermissionError in reject_product: {e}")
        raise HTTPException(status_code=fastapi_status.HTTP_403_FORBIDDEN, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error in reject_product for product {product_id}: {e}", exc_info=True)
        raise HTTPException(status_code=fastapi_status.HTTP_500_INTERNAL_SERVER_ERROR, detail="拒绝商品时发生内部错误")

@router.put("/{product_id}/status/withdraw", status_code=fastapi_status.HTTP_204_NO_CONTENT)
async def withdraw_product(product_id: UUID, 
                           current_user: dict = Depends(get_current_authenticated_user), # Changed type hint to dict
                           product_service: ProductService = Depends(get_product_service),
                           conn: pyodbc.Connection = Depends(get_db_connection)):
    """
    下架商品。管理员可以下架任何商品，普通用户只能下架自己的商品。
    """
    try:
        await product_service.withdraw_product(conn, product_id, current_user)
        return # HTTP 204 No Content
    except NotFoundError as e:
        logger.error(f"Error withdrawing product {product_id}: {e}")
        raise HTTPException(status_code=fastapi_status.HTTP_404_NOT_FOUND, detail=str(e))
    except PermissionError as e:
        logger.error(f"Permission denied for withdrawing product {product_id}: {e}")
        raise HTTPException(status_code=fastapi_status.HTTP_403_FORBIDDEN, detail=str(e))
    except DALError as e:
        logger.error(f"DAL Error withdrawing product {product_id}: {e}")
        raise HTTPException(status_code=fastapi_status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"数据库操作失败: {e}")
    except Exception as e:
        logger.error(f"An unexpected error occurred while withdrawing product {product_id} by user {current_user['用户ID']}: {e}", exc_info=True) # Use Chinese key
        raise HTTPException(status_code=fastapi_status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"服务器内部错误: {e}")