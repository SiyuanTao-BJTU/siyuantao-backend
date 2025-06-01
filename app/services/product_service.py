from typing import List, Dict, Optional
from uuid import UUID # Correct import for UUID
from ..schemas.product import ProductUpdate
from ..dal.product_dal import ProductDAL, ProductImageDAL, UserFavoriteDAL
import pyodbc
from app.exceptions import DALError, NotFoundError, IntegrityError, PermissionError, InternalServerError
import logging # Import logging

logger = logging.getLogger(__name__) # Initialize logger

class ProductService:
    """
    商品服务层，处理商品相关的业务逻辑，协调DAL层完成复杂操作
    """
    def __init__(self, product_dal: ProductDAL, product_image_dal: ProductImageDAL, user_favorite_dal: UserFavoriteDAL):
        """
        初始化ProductService实例
        
        Args:
            product_dal: ProductDAL 实例
            product_image_dal: ProductImageDAL 实例
            user_favorite_dal: UserFavoriteDAL 实例
        """
        self.product_dal = product_dal
        self.product_image_dal = product_image_dal
        self.user_favorite_dal = user_favorite_dal

    async def create_product(self, conn: pyodbc.Connection, owner_id: UUID, category_name: str, product_name: str, 
                            description: str, quantity: int, price: float, image_urls: List[str]) -> None:
        """
        创建商品及其图片
        
        Args:
            conn: 数据库连接对象
            owner_id: 商品所有者ID
            category_name: 商品分类名称
            product_name: 商品名称
            description: 商品描述
            quantity: 商品数量
            price: 商品价格
            image_urls: 商品图片URL列表 (List[str])
        
        Raises:
            ValueError: 输入数据验证失败时抛出
            DatabaseError: 数据库操作失败时抛出
        """
        # 数据验证
        if quantity < 0 or price < 0:
            raise ValueError("Quantity and price must be non-negative.")
        
        # 创建商品 (DAL层现在会处理图片)
        logger.info(f"Service: Creating product with: owner_id={owner_id}, category_name={category_name}, product_name={product_name}, description={description}, quantity={quantity}, price={price}, image_urls={image_urls}")
        await self.product_dal.create_product(conn, owner_id, category_name, product_name, description, quantity, price, image_urls)
        logger.info(f"Service: Product created successfully")
        # 移除此处对 product_image_dal.add_product_image 的循环调用
        # 因为图片的插入已由 sp_CreateProduct 存储过程在数据库层统一处理

    async def update_product(self, conn: pyodbc.Connection, product_id: UUID, owner_id: UUID, product_update_data: ProductUpdate) -> None:
        """
        更新商品及其图片
        
        Args:
            conn: 数据库连接对象
            product_id: 商品ID (UUID)
            owner_id: 商品所有者ID (UUID)
            product_update_data: 商品更新数据 Pydantic Schema
        
        Raises:
            ValueError: 输入数据验证失败时抛出
            PermissionError: 非商品所有者尝试更新时抛出
            DatabaseError: 数据库操作失败时抛出
        """
        # 获取商品信息进行权限检查
        product = await self.product_dal.get_product_by_id(conn, product_id)
        if not product:
            raise ValueError("Product not found")
        
        # 权限检查
        if product.get("发布者用户ID") != owner_id:
            raise PermissionError("您无权更新此商品")
        
        try:
            # Only update fields that are provided in product_update_data
            update_data = product_update_data.model_dump(exclude_unset=True)

            # Retrieve current product details to fill missing fields in update_data
            current_category_name = product.get("商品类别") if "商品类别" in product else None
            current_product_name = product.get("商品名称") if "商品名称" in product else ""
            current_description = product.get("商品描述") if "商品描述" in product else None
            current_quantity = product.get("库存") if "库存" in product and product["库存"] is not None else 0
            current_price = product.get("价格") if "价格" in product and product["价格"] is not None else 0.0
            current_condition = product.get("商品成色") if "商品成色" in product else None
            
            # Use provided data or fallback to current data
            category_name = update_data.get("category_name", current_category_name)
            product_name = update_data.get("product_name", current_product_name)
            description = update_data.get("description", current_description)
            quantity = update_data.get("quantity", current_quantity)
            price = update_data.get("price", current_price)
            condition = update_data.get("condition", current_condition)

            await self.product_dal.update_product(conn, product_id, owner_id, 
                                                category_name, product_name, description, quantity, price, condition)
            logger.info(f"Product {product_id} updated by owner {owner_id}")

            # Handle image updates if image_urls is provided
            if product_update_data.image_urls is not None:
                # First, delete existing images for this product
                await self.product_image_dal.delete_product_images_by_product_id(conn, product_id)
                
                # Then, add new images
                for i, image_url in enumerate(product_update_data.image_urls):
                    await self.product_image_dal.add_product_image(conn, product_id, image_url, i)
                    logger.debug(f"Added image {image_url} for product {product_id} during update")
        except NotFoundError:
            raise
        except PermissionError:
            raise
        except DALError as e:
            logger.error(f"DAL error updating product {product_id}: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error updating product {product_id}: {e}", exc_info=True)
            raise InternalServerError("更新商品失败")

    async def delete_product(self, conn: pyodbc.Connection, product_id: UUID, owner_id: UUID) -> None:
        """
        删除商品
        
        Args:
            conn: 数据库连接对象
            product_id: 商品ID (UUID)
            owner_id: 商品所有者ID或管理员ID (UUID)
        
        Raises:
            NotFoundError: 商品未找到时抛出
            PermissionError: 非商品所有者或管理员尝试删除时抛出
            DatabaseError: 数据库操作失败时抛出
        """
        # Check if the product exists and belongs to the owner or if the user is an admin
        existing_product = await self.product_dal.get_product_by_id(conn, product_id)
        if not existing_product:
            raise NotFoundError(f"Product with ID {product_id} not found.")

        # Check if the user is the owner
        if existing_product["发布者用户ID"] != owner_id:
            raise PermissionError("您无权删除此商品")
        
        try:
            await self.product_dal.delete_product(conn, product_id, owner_id)
            logger.info(f"Product {product_id} deleted by owner {owner_id}")

            # Optionally delete associated images
            await self.product_image_dal.delete_product_images_by_product_id(conn, product_id)
            logger.debug(f"Deleted images for product {product_id}")
        except NotFoundError:
            raise
        except PermissionError:
            raise
        except DALError as e:
            logger.error(f"DAL error deleting product {product_id}: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error deleting product {product_id}: {e}", exc_info=True)
            raise InternalServerError("删除商品失败")

    async def activate_product(self, conn: pyodbc.Connection, product_id: UUID, admin_id: UUID) -> None:
        # 路由层已经处理了管理员权限验证，服务层不需要重复此检查。
        # if not await self.check_admin_permission(conn, admin_id): # 传入UUID
        #     raise PermissionError("无权执行此操作，只有管理员可以激活商品。")
        
        try:
            await self.product_dal.activate_product(conn, product_id, admin_id)
            logger.info(f"Product {product_id} activated by admin {admin_id}")
        except NotFoundError:
            raise
        except DALError as e:
            logger.error(f"DAL error activating product {product_id}: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error activating product {product_id}: {e}", exc_info=True)
            raise InternalServerError("激活商品失败") # Modified: Specific error message

    async def reject_product(self, conn: pyodbc.Connection, product_id: UUID, admin_id: UUID, reason: Optional[str] = None) -> None:
        # 路由层已经处理了管理员权限验证，服务层不需要重复此检查。
        # if not await self.check_admin_permission(conn, admin_id): # 传入UUID
        #     raise PermissionError("无权执行此操作，只有管理员可以拒绝商品。")

        try:
            await self.product_dal.reject_product(conn, product_id, admin_id, reason)
            logger.info(f"Product {product_id} rejected by admin {admin_id} with reason: {reason}")
        except NotFoundError:
            raise
        except DALError as e:
            logger.error(f"DAL error rejecting product {product_id}: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error rejecting product {product_id}: {e}", exc_info=True)
            raise InternalServerError("拒绝商品失败") # Modified: Specific error message

    async def withdraw_product(self, conn: pyodbc.Connection, product_id: UUID, owner_id: UUID) -> None:
        """
        商品所有者下架商品
        
        Args:
            conn: 数据库连接对象
            product_id: 商品ID (UUID)
            owner_id: 商品所有者ID (UUID)
        
        Raises:
            PermissionError: 非商品所有者尝试操作时抛出
            DatabaseError: 数据库操作失败时抛出
        """
        # Check if the product exists and belongs to the owner before attempting to withdraw
        existing_product = await self.product_dal.get_product_by_id(conn, product_id)
        if not existing_product:
            raise NotFoundError(f"Product with ID {product_id} not found.")
        
        if existing_product["发布者用户ID"] != owner_id:
            raise PermissionError("您无权下架此商品")

        try:
            await self.product_dal.withdraw_product(conn, product_id, owner_id)
            logger.info(f"Product {product_id} withdrawn by owner {owner_id}")
        except NotFoundError:
            raise
        except DALError as e:
            logger.error(f"DAL error withdrawing product {product_id}: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error withdrawing product {product_id}: {e}", exc_info=True)
            raise InternalServerError("下架商品失败") # Modified: Specific error message

    async def get_product_list(self, conn: pyodbc.Connection, category_name: Optional[str] = None, status: Optional[str] = None, 
                              keyword: Optional[str] = None, min_price: Optional[float] = None, 
                              max_price: Optional[float] = None, order_by: str = 'PostTime', 
                              page_number: int = 1, page_size: int = 10, owner_id: Optional[UUID] = None) -> List[Dict]: # 添加 owner_id 参数
        """
        获取商品列表，支持多种筛选条件和分页
        
        Args:
            conn: 数据库连接对象
            category_name: 商品分类名称 (可选)
            status: 商品状态 (可选)
            keyword: 搜索关键词 (可选)
            min_price: 最低价格 (可选)
            max_price: 最高价格 (可选)
            order_by: 排序字段 (可选，默认PostTime)
            page_number: 页码 (默认1)
            page_size: 每页数量 (默认10)
            owner_id: 商品所有者ID (可选)
        
        Returns:
            商品列表 (List[Dict])
        
        Raises:
            DatabaseError: 数据库操作失败时抛出
        """
        try:
            logger.info(f"Service: Calling DAL.get_product_list with: category_name={category_name}, status={status}, keyword={keyword}, min_price={min_price}, max_price={max_price}, order_by={order_by}, page_number={page_number}, page_size={page_size}, owner_id={owner_id}")
            products_data = await self.product_dal.get_product_list(conn, category_name, status, keyword, min_price, max_price, order_by, page_number, page_size, owner_id)

            return products_data
        except DALError as e:
            logger.error(f"DAL error getting product list: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error getting product list: {e}", exc_info=True)
            raise InternalServerError("获取商品列表失败") # Modified: Specific error message

    async def get_product_detail(self, conn: pyodbc.Connection, product_id: UUID) -> Optional[Dict]:
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
        try:
            product_data = await self.product_dal.get_product_by_id(conn, product_id)
            
            if product_data:
                return product_data
            return None
        except DALError as e:
            logger.error(f"DAL error getting product detail for {product_id}: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error getting product detail for {product_id}: {e}", exc_info=True)
            raise InternalServerError("获取商品详情失败") # Modified: Specific error message

    async def add_favorite(self, conn: pyodbc.Connection, user_id: UUID, product_id: UUID) -> None:
        """
        添加用户收藏
        
        Args:
            conn: 数据库连接对象
            user_id: 用户ID (UUID)
            product_id: 商品ID (UUID)
        
        Raises:
            IntegrityError: 重复收藏时抛出
            DatabaseError: 数据库操作失败时抛出
        """
        try:
            await self.user_favorite_dal.add_user_favorite(conn, user_id, product_id)
            logger.info(f"User {user_id} added favorite product {product_id}")
        except IntegrityError:
            raise # Re-raise IntegrityError for API layer to handle as 409 Conflict
        except DALError as e:
            logger.error(f"DAL error adding favorite for user {user_id}, product {product_id}: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error adding favorite for user {user_id}, product {product_id}: {e}", exc_info=True)
            raise InternalServerError("添加收藏失败") # Modified: Specific error message

    async def remove_favorite(self, conn: pyodbc.Connection, user_id: UUID, product_id: UUID) -> None:
        """
        移除用户收藏
        
        Args:
            conn: 数据库连接对象
            user_id: 用户ID (UUID)
            product_id: 商品ID (UUID)
        
        Raises:
            NotFoundError: 收藏不存在时抛出
            DatabaseError: 数据库操作失败时抛出
        """
        try:
            await self.user_favorite_dal.remove_user_favorite(conn, user_id, product_id)
            logger.info(f"User {user_id} removed favorite product {product_id}")
        except NotFoundError:
            raise # Re-raise NotFoundError for API layer to handle as 404
        except DALError as e:
            logger.error(f"DAL error removing favorite for user {user_id}, product {product_id}: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error removing favorite for user {user_id}, product {product_id}: {e}", exc_info=True)
            raise InternalServerError("移除收藏失败") # Modified: Specific error message

    async def get_user_favorites(self, conn: pyodbc.Connection, user_id: UUID) -> List[Dict]:
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
        try:
            favorites_data = await self.user_favorite_dal.get_user_favorite_products(conn, user_id)
            
            return favorites_data
        except DALError as e:
            logger.error(f"DAL error getting user favorites for user {user_id}: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error getting user favorites for user {user_id}: {e}", exc_info=True)
            raise InternalServerError("获取用户收藏失败") # Modified: Specific error message

    async def batch_activate_products(self, conn: pyodbc.Connection, product_ids: List[UUID], admin_id: UUID) -> int:
        # 路由层已经处理了管理员权限验证，服务层不需要重复此检查。
        # if not await self.check_admin_permission(conn, admin_id): # 传入UUID
        #     raise PermissionError("无权执行此操作，只有管理员可以批量激活商品。")

        try:
            affected_count = await self.product_dal.batch_activate_products(conn, product_ids, admin_id)
            logger.info(f"Batch activated {affected_count} products by admin {admin_id}")
            return affected_count
        except DALError as e:
            logger.error(f"DAL error batch activating products: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error batch activating products: {e}", exc_info=True)
            raise InternalServerError("批量激活商品失败") # Modified: Specific error message

    async def batch_reject_products(self, conn: pyodbc.Connection, product_ids: List[UUID], admin_id: UUID, reason: Optional[str] = None) -> int:
        # 路由层已经处理了管理员权限验证，服务层不需要重复此检查。
        # if not await self.check_admin_permission(conn, admin_id): # 传入UUID
        #     raise PermissionError("无权执行此操作，只有管理员可以批量拒绝商品。")

        try:
            affected_count = await self.product_dal.batch_reject_products(conn, product_ids, admin_id, reason)
            logger.info(f"Batch rejected {affected_count} products by admin {admin_id}")
            return affected_count
        except DALError as e:
            logger.error(f"DAL error batch rejecting products: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error batch rejecting products: {e}", exc_info=True)
            raise InternalServerError("批量拒绝商品失败") # Modified: Specific error message