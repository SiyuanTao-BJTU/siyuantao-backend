# import databases # Remove this import
from typing import List, Dict, Optional
import pyodbc # Import pyodbc for type hinting conn
from uuid import UUID # Import UUID
import logging

from app.exceptions import DALError, NotFoundError, IntegrityError, PermissionError, DatabaseError # Import DatabaseError

logger = logging.getLogger(__name__)

class ProductDAL:
    """
    商品数据访问层，负责与数据库进行交互，执行商品相关的CRUD操作
    """
    def __init__(self, execute_query_func):
        """
        初始化ProductDAL实例
        
        Args:
            execute_query_func: 通用的数据库执行函数，接收 conn, sql, params, fetchone/fetchall 等参数
        """
        self._execute_query = execute_query_func

    async def create_product(self, conn: pyodbc.Connection, owner_id: UUID, category_name: str, product_name: str, 
                            description: str, quantity: int, price: float, image_urls: List[str]) -> UUID: # Added image_urls
        """
        创建新商品
        
        Args:
            conn: 数据库连接对象
            owner_id: 商品所有者ID (UUID)
            category_name: 商品分类名称
            product_name: 商品名称
            description: 商品描述
            quantity: 商品数量
            price: 商品价格
            image_urls: 图片URL列表
        
        Returns:
            新商品ID (UUID)
        
        Raises:
            DatabaseError: 数据库操作失败时抛出
        """
        # Convert list of image URLs to a comma-separated string
        image_urls_str = ",".join(image_urls) if image_urls else None
        
        sql = "{CALL sp_CreateProduct(?, ?, ?, ?, ?, ?, ?)}" # Added one more ? for image_urls
        params = (
            owner_id, # Passed as UUID
            product_name, # Changed order to match SP
            description,
            price,
            quantity,
            category_name,
            image_urls_str # Added image_urls_str
        )
    async def update_product(self, conn: pyodbc.Connection, product_id: UUID, owner_id: UUID, category_name: str, product_name: str, 
                            description: str, quantity: int, price: float) -> None:
        """
        更新商品信息
        
        Args:
            conn: 数据库连接对象
            product_id: 商品ID (UUID)
            owner_id: 商品所有者ID (UUID)
            category_name: 商品分类名称
            product_name: 商品名称
            description: 商品描述
            quantity: 商品数量
            price: 商品价格
        
        Raises:
            DatabaseError: 数据库操作失败时抛出
            PermissionError: 非商品所有者尝试更新时抛出
        """
        sql = "{CALL sp_UpdateProduct(?, ?, ?, ?, ?, ?, ?)}"
        params = (
            product_id, # Passed as UUID
            owner_id, # Passed as UUID
            category_name,
            product_name,
            description,
            quantity,
            price
        )
        try:
            # Use execute_query for update, check rowcount for success
            rowcount = await self._execute_query(conn, sql, params, fetchone=False, fetchall=False)
            if rowcount == 0:
                logger.warning(f"DAL: Update product {product_id} returned 0 rows affected, possibly not found or no changes.")
                # Consider raising NotFoundError or similar if 0 rows affected implies no such product was found for update
                # For now, let's assume service layer will handle the product existence check before calling DAL update.
        except pyodbc.Error as e:
            logger.error(f"DAL Error updating product {product_id}: {e}")
            raise DALError(f"Database error updating product {product_id}: {e}") from e
        except Exception as e:
            logger.error(f"Unexpected Error updating product {product_id}: {e}")
            raise e

    async def delete_product(self, conn: pyodbc.Connection, product_id: UUID, owner_id: UUID) -> None:
        """
        删除商品
        
        Args:
            conn: 数据库连接对象
            product_id: 商品ID (UUID)
            owner_id: 商品所有者ID或管理员ID (UUID)
        
        Raises:
            DatabaseError: 数据库操作失败时抛出
            PermissionError: 非商品所有者或管理员尝试删除时抛出
        """
        sql = "{CALL sp_DeleteProduct(?, ?)}"
        params = (
            product_id, # Passed as UUID
            owner_id # Passed as UUID
        )
        try:
            rowcount = await self._execute_query(conn, sql, params, fetchone=False, fetchall=False)
            if rowcount == 0:
                 logger.warning(f"DAL: Delete product {product_id} returned 0 rows affected, possibly not found or no changes.")
                 raise NotFoundError(f"Product with ID {product_id} not found for deletion or not owned by user {owner_id}.")
            # Consider specific error messages from SP if available
        except pyodbc.Error as e:
            logger.error(f"DAL Error deleting product {product_id}: {e}")
            raise DALError(f"Database error deleting product {product_id}: {e}") from e
        except Exception as e:
            logger.error(f"Unexpected Error deleting product {product_id}: {e}")
            raise e

    async def activate_product(self, conn: pyodbc.Connection, product_id: UUID, admin_id: UUID) -> None:
        """
        管理员审核通过商品，将商品状态设为Active
        
        Args:
            conn: 数据库连接对象
            product_id: 商品ID (UUID)
            admin_id: 管理员ID (UUID)
        
        Raises:
            DatabaseError: 数据库操作失败时抛出
            PermissionError: 非管理员尝试操作时抛出
        """
        sql = "{CALL sp_ActivateProduct(?, ?)}"
        params = (
            product_id, # Passed as UUID
            admin_id # Passed as UUID
        )
        try:
            rowcount = await self._execute_query(conn, sql, params, fetchone=False, fetchall=False)
            if rowcount == 0: # This might indicate product not found or no permission etc.
                logger.warning(f"DAL: Activate product {product_id} returned 0 rows affected. Admin {admin_id}.")
                # The SP should ideally return specific codes/messages for not found/permission denied.
                # Assuming 0 rows affected indicates failure for the given product_id/admin_id combo.
                # For now, rely on service layer to check permissions and product existence prior.
                raise DALError(f"Failed to activate product {product_id}. Check product ID and admin permissions.")
        except pyodbc.Error as e:
            logger.error(f"DAL Error activating product {product_id}: {e}")
            raise DALError(f"Database error activating product {product_id}: {e}") from e
        except Exception as e:
            logger.error(f"Unexpected Error activating product {product_id}: {e}")
            raise e

    async def reject_product(self, conn: pyodbc.Connection, product_id: UUID, admin_id: UUID, reason: Optional[str] = None) -> None:
        """
        管理员拒绝商品，将商品状态设为Rejected
        
        Args:
            conn: 数据库连接对象
            product_id: 商品ID (UUID)
            admin_id: 管理员ID (UUID)
            reason: 拒绝原因，可选
        
        Raises:
            DatabaseError: 数据库操作失败时抛出
            PermissionError: 非管理员尝试操作时抛出
        """
        # Add logging
        logger.debug(f"DAL: Admin {admin_id} rejecting product {product_id} with reason: {reason}")
        # Modify query to include reason
        sql = "{CALL sp_RejectProduct(?, ?, ?)}"
        params = (
            product_id, # Passed as UUID
            admin_id, # Passed as UUID
            reason
        )
        try:
            rowcount = await self._execute_query(conn, sql, params, fetchone=False, fetchall=False)
            if rowcount == 0:
                 logger.warning(f"DAL: Reject product {product_id} returned 0 rows affected. Admin {admin_id}.")
                 raise DALError(f"Failed to reject product {product_id}. Check product ID and admin permissions.")
            # Add logging for success
            logger.info(f"DAL: Product {product_id} rejected successfully by admin {admin_id}")
        except pyodbc.Error as e:
            logger.error(f"DAL: Database error rejecting product {product_id}: {e}")
            raise DALError(f"Database error rejecting product {product_id}: {e}") from e
        except Exception as e:
            # Catch other potential exceptions during execution
            logger.error(f"DAL: Unexpected error rejecting product {product_id}: {e}")
            raise DALError(f"Unexpected error rejecting product {product_id}: {e}") from e

    async def withdraw_product(self, conn: pyodbc.Connection, product_id: UUID, owner_id: UUID) -> None:
        """
        商品所有者下架商品，将商品状态设为Withdrawn
        
        Args:
            conn: 数据库连接对象
            product_id: 商品ID (UUID)
            owner_id: 商品所有者ID (UUID)
        
        Raises:
            DatabaseError: 数据库操作失败时抛出
            PermissionError: 非商品所有者尝试操作时抛出
        """
        sql = "{CALL sp_WithdrawProduct(?, ?)}"
        params = (
            product_id, # Passed as UUID
            owner_id # Passed as UUID
        )
        try:
            rowcount = await self._execute_query(conn, sql, params, fetchone=False, fetchall=False)
            if rowcount == 0:
                 logger.warning(f"DAL: Withdraw product {product_id} returned 0 rows affected. Owner {owner_id}.")
                 raise NotFoundError(f"Product with ID {product_id} not found for withdrawal or not owned by user {owner_id}.")
        except pyodbc.Error as e:
            logger.error(f"DAL Error withdrawing product {product_id}: {e}")
            raise DALError(f"Database error withdrawing product {product_id}: {e}") from e
        except Exception as e:
            logger.error(f"Unexpected Error withdrawing product {product_id}: {e}")
            raise e

    async def get_product_list(self, conn: pyodbc.Connection, category_name: Optional[str] = None, status: Optional[str] = None, 
                                  keyword: Optional[str] = None, min_price: Optional[float] = None, 
                                  max_price: Optional[float] = None, order_by: str = 'PostTime', 
                                  page_number: int = 1, page_size: int = 10, owner_id: Optional[UUID] = None) -> List[Dict]: # 添加 owner_id 参数
        """
        获取商品列表，支持多种筛选条件和分页
        """
        # 修改：使用 CALL 语句调用存储过程，使用位置参数的问号占位符
        sql = "{CALL sp_GetProductList(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)}"
            
        # 确保 status 为空字符串时为 None
        processed_status = status if status != '' else None
            
        # 重新添加：owner_id 的显式字符串转换，解决 pyodbc 在某些环境下的UUID绑定问题
        processed_owner_id = str(owner_id) if owner_id else None

        params = (
            keyword,         # @searchQuery
            category_name,   # @categoryName
            min_price,       # @minPrice
            max_price,       # @maxPrice
            page_number,     # @page
            page_size,       # @pageSize
            order_by,        # @sortBy
            "DESC",          # @sortOrder
            processed_status,# @status
            processed_owner_id # @ownerId - 现在是字符串或None
        )

        try:
            result = await self._execute_query(conn, sql, params, fetchall=True)
            return result if result is not None else []
        except pyodbc.Error as e:
            logger.error(f"DAL Error getting product list: {e}")
            raise DALError(f"Database error getting product list: {e}") from e
        except Exception as e:
            logger.error(f"Unexpected Error getting product list: {e}")
            raise e
    async def get_product_by_id(self, conn: pyodbc.Connection, product_id: UUID) -> Optional[Dict]:
        """
        根据商品ID获取商品详情
        
        Args:
            conn: 数据库连接对象
            product_id: 商品ID (UUID)
        
        Returns:
            商品详情字典，如果未找到则返回None
        
        Raises:
            DatabaseError: 数据库操作失败时抛出
        """
        sql = "{CALL sp_GetProductById(?)}"
        params = (product_id,) # Passed as UUID
        try:
            result = await self._execute_query(conn, sql, params, fetchone=True)
            return result
        except pyodbc.Error as e:
            logger.error(f"DAL Error getting product by ID {product_id}: {e}")
            raise DALError(f"Database error getting product by ID {product_id}: {e}") from e
        except Exception as e:
            logger.error(f"Unexpected Error getting product by ID {product_id}: {e}")
            raise e

    async def decrease_product_quantity(self, conn: pyodbc.Connection, product_id: UUID, quantity_to_decrease: int) -> None:
        """
        减少商品库存
        
        Args:
            conn: 数据库连接对象
            product_id: 商品ID (UUID)
            quantity_to_decrease: 减少的数量
        
        Raises:
            DatabaseError: 数据库操作失败时抛出
        """
        sql = "{CALL sp_DecreaseProductQuantity(?, ?)}"
        params = (product_id, quantity_to_decrease) # Passed as UUID
        try:
            rowcount = await self._execute_query(conn, sql, params, fetchone=False, fetchall=False)
            if rowcount == 0:
                logger.warning(f"DAL: Decrease product quantity for {product_id} returned 0 rows affected.")
                # Consider specific error message if the SP returns one for insufficient quantity etc.
                raise DALError(f"Failed to decrease quantity for product {product_id}. Possibly insufficient stock or product not found.")
        except pyodbc.Error as e:
            logger.error(f"DAL Error decreasing product quantity for {product_id}: {e}")
            raise DALError(f"Database error decreasing product quantity: {e}") from e
        except Exception as e:
            logger.error(f"Unexpected Error decreasing product quantity for {product_id}: {e}")
            raise e

    async def increase_product_quantity(self, conn: pyodbc.Connection, product_id: UUID, quantity_to_increase: int) -> None:
        """
        增加商品库存
        
        Args:
            conn: 数据库连接对象
            product_id: 商品ID (UUID)
            quantity_to_increase: 增加的数量
        
        Raises:
            DatabaseError: 数据库操作失败时抛出
        """
        sql = "{CALL sp_IncreaseProductQuantity(?, ?)}"
        params = (product_id, quantity_to_increase) # Passed as UUID
        try:
            rowcount = await self._execute_query(conn, sql, params, fetchone=False, fetchall=False)
            if rowcount == 0:
                logger.warning(f"DAL: Increase product quantity for {product_id} returned 0 rows affected.")
                raise DALError(f"Failed to increase quantity for product {product_id}. Product not found.")
        except pyodbc.Error as e:
            logger.error(f"DAL Error increasing product quantity for {product_id}: {e}")
            raise DALError(f"Database error increasing product quantity: {e}") from e
        except Exception as e:
            logger.error(f"Unexpected Error increasing product quantity for {product_id}: {e}")
            raise e

    async def batch_activate_products(self, conn: pyodbc.Connection, product_ids: List[UUID], admin_id: UUID) -> int:
        """
        批量激活商品
        
        Args:
            conn: 数据库连接对象
            product_ids: 商品ID列表 (List[UUID])
            admin_id: 管理员ID (UUID)
        
        Returns:
            成功激活的商品数量
        
        Raises:
            DatabaseError: 数据库操作失败时抛出
            PermissionError: 非管理员尝试操作时抛出
        """
        # Convert list of UUIDs to a comma-separated string for the stored procedure
        product_ids_str = ",".join(map(str, product_ids)) # Convert UUIDs to strings
        sql = "{CALL sp_BatchActivateProducts(?, ?)}"
        params = (product_ids_str, admin_id) # admin_id passed as UUID
        try:
            result = await self._execute_query(conn, sql, params, fetchone=True) # Assuming SP returns count
            activated_count = result.get('ActivatedCount', 0) if result else 0 # Check for 'ActivatedCount' key
            logger.info(f"DAL: Batch activated {activated_count} products by admin {admin_id}")
            return activated_count
        except pyodbc.Error as e:
            logger.error(f"DAL Error batch activating products: {e}")
            raise DALError(f"Database error batch activating products: {e}") from e
        except Exception as e:
            logger.error(f"Unexpected Error batch activating products: {e}")
            raise e

    async def batch_reject_products(self, conn: pyodbc.Connection, product_ids: List[UUID], admin_id: UUID, reason: Optional[str] = None) -> int:
        """
        批量拒绝商品
        
        Args:
            conn: 数据库连接对象
            product_ids: 商品ID列表 (List[UUID])
            admin_id: 管理员ID (UUID)
            reason: 拒绝原因，可选
        
        Returns:
            成功拒绝的商品数量
        
        Raises:
            DatabaseError: 数据库操作失败时抛出
            PermissionError: 非管理员尝试操作时抛出
        """
        product_ids_str = ",".join(map(str, product_ids)) # Convert UUIDs to strings
        sql = "{CALL sp_BatchRejectProducts(?, ?, ?)}"
        params = (product_ids_str, admin_id, reason) # admin_id passed as UUID
        try:
            result = await self._execute_query(conn, sql, params, fetchone=True) # Assuming SP returns count
            rejected_count = result.get('RejectedCount', 0) if result else 0 # Check for 'RejectedCount' key
            logger.info(f"DAL: Batch rejected {rejected_count} products by admin {admin_id}")
            return rejected_count
        except pyodbc.Error as e:
            logger.error(f"DAL Error batch rejecting products: {e}")
            raise DALError(f"Database error batch rejecting products: {e}") from e
        except Exception as e:
            logger.error(f"Unexpected Error batch rejecting products: {e}")
            raise e


class ProductImageDAL:
    """
    商品图片数据访问层，负责与数据库进行交互，执行商品图片相关的操作
    """
    def __init__(self, execute_query_func):
        """
        初始化ProductImageDAL实例
        
        Args:
            execute_query_func: 通用的数据库执行函数
        """
        self._execute_query = execute_query_func

    async def add_product_image(self, conn: pyodbc.Connection, product_id: UUID, image_url: str, sort_order: int) -> None:
        """
        为商品添加图片记录。
        
        Args:
            conn: 数据库连接对象
            product_id: 商品ID (UUID)
            image_url: 图片URL
            sort_order: 图片排序顺序
        
        Raises:
            DatabaseError: 数据库操作失败时抛出
        """
        # This method should call sp_CreateImage, not sp_AddProductImage
        sql = "{CALL sp_CreateImage(?, ?, ?)}" 
        params = (
            product_id, # Passed as UUID
            image_url,
            sort_order
        )
        try:
            await self._execute_query(conn, sql, params, fetchone=False, fetchall=False) # No return expected
            logger.info(f"DAL: Added image {image_url} for product {product_id}.")
        except pyodbc.Error as e:
            logger.error(f"DAL Error adding product image for product {product_id}: {e}")
            raise DALError(f"Database error adding product image: {e}") from e
        except Exception as e:
            logger.error(f"Unexpected Error adding product image for product {product_id}: {e}")
            raise e
        
    async def get_images_by_product_id(self, conn: pyodbc.Connection, product_id: UUID) -> List[Dict]:
        """
        获取指定商品的所有图片
        
        Args:
            conn: 数据库连接对象
            product_id: 商品ID (UUID)
        
        Returns:
            图片URL列表
        
        Raises:
            DatabaseError: 数据库操作失败时抛出
        """
        sql = "{CALL sp_GetProductImagesByProductId(?)}"
        params = (product_id,) # Passed as UUID
        try:
            result = await self._execute_query(conn, sql, params, fetchall=True)
            return result if result is not None else []
        except pyodbc.Error as e:
            logger.error(f"DAL Error getting product images for product {product_id}: {e}")
            raise DALError(f"Database error getting product images: {e}") from e
        except Exception as e:
            logger.error(f"Unexpected Error getting product images for product {product_id}: {e}")
            raise e

    async def delete_product_image(self, conn: pyodbc.Connection, image_id: int) -> None:
        """
        删除指定图片
        
        Args:
            conn: 数据库连接对象
            image_id: 图片ID
        
        Raises:
            DatabaseError: 数据库操作失败时抛出
        """
        sql = "{CALL sp_DeleteProductImage(?)}"
        params = (image_id,)
        try:
            rowcount = await self._execute_query(conn, sql, params, fetchone=False, fetchall=False)
            if rowcount == 0:
                logger.warning(f"DAL: Delete product image {image_id} returned 0 rows affected, possibly not found.")
                raise NotFoundError(f"Product image with ID {image_id} not found for deletion.")
        except pyodbc.Error as e:
            logger.error(f"DAL Error deleting product image {image_id}: {e}")
            raise DALError(f"Database error deleting product image: {e}") from e
        except Exception as e:
            logger.error(f"Unexpected Error deleting product image {image_id}: {e}")
            raise e

    async def delete_product_images_by_product_id(self, conn: pyodbc.Connection, product_id: UUID) -> None:
        """
        删除指定商品的所有图片
        
        Args:
            conn: 数据库连接对象
            product_id: 商品ID (UUID)
        
        Raises:
            DatabaseError: 数据库操作失败时抛出
        """
        sql = "{CALL sp_DeleteProductImagesByProductId(?)}"
        params = (product_id,) # Passed as UUID
        try:
            await self._execute_query(conn, sql, params, fetchone=False, fetchall=False)
            logger.info(f"DAL: All images for product {product_id} deleted.")
        except pyodbc.Error as e:
            logger.error(f"DAL Error deleting product images for product {product_id}: {e}")
            raise DALError(f"Database error deleting product images: {e}") from e
        except Exception as e:
            logger.error(f"Unexpected Error deleting product images for product {product_id}: {e}")
            raise e


class UserFavoriteDAL:
    """
    用户收藏数据访问层，负责与数据库进行交互，执行用户收藏相关的操作
    """
    def __init__(self, execute_query_func):
        """
        初始化UserFavoriteDAL实例
        
        Args:
            execute_query_func: 通用的数据库执行函数
        """
        self._execute_query = execute_query_func

    async def add_user_favorite(self, conn: pyodbc.Connection, user_id: UUID, product_id: UUID) -> None:
        """
        添加用户收藏
        
        Args:
            conn: 数据库连接对象
            user_id: 用户ID (UUID)
            product_id: 商品ID (UUID)
        
        Raises:
            DatabaseError: 数据库操作失败时抛出
            IntegrityError: 重复收藏时抛出
        """
        sql = "{CALL sp_AddUserFavorite(?, ?)}"
        params = (user_id, product_id) # Passed as UUID
        try:
            await self._execute_query(conn, sql, params, fetchone=False, fetchall=False)
            logger.info(f"DAL: User {user_id} added favorite product {product_id}")
        except pyodbc.IntegrityError as e:
            logger.warning(f"DAL: User {user_id} already favorited product {product_id}")
            raise IntegrityError("Product already in favorites.") from e
        except pyodbc.Error as e:
            logger.error(f"DAL Error adding user favorite for user {user_id}, product {product_id}: {e}")
            raise DALError(f"Database error adding user favorite: {e}") from e
        except Exception as e:
            logger.error(f"Unexpected Error adding user favorite for user {user_id}, product {product_id}: {e}")
            raise e

    async def remove_user_favorite(self, conn: pyodbc.Connection, user_id: UUID, product_id: UUID) -> None:
        """
        移除用户收藏
        
        Args:
            conn: 数据库连接对象
            user_id: 用户ID (UUID)
            product_id: 商品ID (UUID)
        
        Raises:
            DatabaseError: 数据库操作失败时抛出
        """
        sql = "{CALL sp_RemoveUserFavorite(?, ?)}"
        params = (user_id, product_id) # Passed as UUID
        try:
            rowcount = await self._execute_query(conn, sql, params, fetchone=False, fetchall=False)
            if rowcount == 0:
                logger.warning(f"DAL: Remove favorite for user {user_id}, product {product_id} returned 0 rows affected, possibly not found.")
                raise NotFoundError("Favorite not found.")
            logger.info(f"DAL: User {user_id} removed favorite product {product_id}")
        except pyodbc.Error as e:
            logger.error(f"DAL Error removing user favorite for user {user_id}, product {product_id}: {e}")
            raise DALError(f"Database error removing user favorite: {e}") from e
        except Exception as e:
            logger.error(f"Unexpected Error removing user favorite for user {user_id}, product {product_id}: {e}")
            raise e

    async def get_user_favorite_products(self, conn: pyodbc.Connection, user_id: UUID) -> List[Dict]:
        """
        获取用户收藏的商品列表
        
        Args:
            conn: 数据库连接对象
            user_id: 用户ID (UUID)
        
        Returns:
            收藏商品列表 (List[Dict])
        
        Raises:
            DatabaseError: 数据库操作失败时抛出
        """
        sql = "{CALL sp_GetUserFavoriteProducts(?)}"
        params = (user_id,) # Passed as UUID
        try:
            result = await self._execute_query(conn, sql, params, fetchall=True)
            return result if result is not None else []
        except pyodbc.Error as e:
            logger.error(f"DAL Error getting user favorite products for user {user_id}: {e}")
            raise DALError(f"Database error getting user favorite products: {e}") from e
        except Exception as e:
            logger.error(f"Unexpected Error getting user favorite products for user {user_id}: {e}")
            raise e  