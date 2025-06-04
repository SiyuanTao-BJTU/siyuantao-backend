from typing import List, Dict, Optional
from uuid import UUID # Correct import for UUID
from ..schemas.product import ProductUpdate
from ..dal.product_dal import ProductDAL, ProductImageDAL, UserFavoriteDAL
import pyodbc
from app.exceptions import DALError, NotFoundError, IntegrityError, PermissionError, InternalServerError
import logging # Import logging
from app.schemas.user_schemas import UserResponseSchema # 添加导入
from app.schemas.product import ProductCreate, ProductUpdate

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
                            description: str, quantity: int, price: float, condition: Optional[str], image_urls: List[str]) -> None:
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
            condition: 商品条件
            image_urls: 商品图片URL列表 (List[str])
        
        Raises:
            ValueError: 输入数据验证失败时抛出
            DatabaseError: 数据库操作失败时抛出
        """
        # 数据验证
        if quantity < 0 or price < 0:
            raise ValueError("Quantity and price must be non-negative.")
        
        # 创建商品 (DAL层现在会处理图片)
        logger.info(f"Service: Creating product with: owner_id={owner_id}, category_name={category_name}, product_name={product_name}, description={description}, quantity={quantity}, price={price}, condition={condition}, image_urls={image_urls}")
        await self.product_dal.create_product(conn, owner_id, category_name, product_name, description, quantity, price, condition, image_urls)
        logger.info(f"Service: Product created successfully")
        # 移除此处对 product_image_dal.add_product_image 的循环调用
        # 因为图片的插入已由 sp_CreateProduct 存储过程在数据库层统一处理

    async def update_product(self, conn: pyodbc.Connection, product_id: UUID, current_user: dict, product_update_data: ProductUpdate) -> None:
        """
        更新商品信息

        Args:
            conn: 数据库连接对象
            product_id: 要更新的商品ID
            current_user: 当前操作用户 (字典类型，包含 用户ID, 是否管理员 等中文键名)
            product_update_data: 包含要更新的商品信息的 ProductUpdate schema
        
        Raises:
            NotFoundError: 商品未找到
            PermissionError: 无权限操作
            DatabaseError: 数据库操作失败
        """
        logger.info(f"SERVICE: User {current_user.get('用户ID')} attempting to update product {product_id} with data: {product_update_data.model_dump(exclude_none=True)}")
        
        existing_product = await self.product_dal.get_product_by_id(conn, product_id)
        if not existing_product:
            logger.warning(f"SERVICE: Product {product_id} not found for update.")
            raise NotFoundError(f"商品 (ID: {product_id}) 未找到。")

        is_admin_request = current_user.get('是否管理员', False) # 使用中文键
        owner_id_from_db = existing_product.get('卖家ID')
        
        try:
            if isinstance(owner_id_from_db, str):
                owner_id_from_db_uuid = UUID(owner_id_from_db)
            elif isinstance(owner_id_from_db, UUID):
                owner_id_from_db_uuid = owner_id_from_db
            else:
                owner_id_from_db_uuid = None
        except ValueError:
            logger.error(f"SERVICE: Invalid OwnerID format '{owner_id_from_db}' for product {product_id}.")
            raise PermissionError("无法验证商品所有权。")

        current_user_id = current_user.get('用户ID') # 使用中文键
        if not is_admin_request and owner_id_from_db_uuid != current_user_id:
            logger.warning(f"SERVICE: User {current_user_id} (not owner or admin) attempted to update product {product_id} owned by {owner_id_from_db_uuid}.")
            raise PermissionError("无权修改此商品。")

        should_re_review = False
        current_status = existing_product.get('商品状态')

        # 只有在商品当前状态为 'Active' 或 'Withdrawn' 且不是管理员请求时才触发重新审核
        if not is_admin_request and current_status in ['Active', 'Withdrawn']:
            # 定义关键信息字段（与 ProductResponseSchema 中的中文键对应）
            critical_fields = {
                'product_name': '商品名称',
                'description': '描述',
                'price': '价格',
                'category_name': '分类名称',
                'condition': '成色'
            }

            # 比较关键信息是否发生变化
            for new_field, old_field_chinese in critical_fields.items():
                new_value = getattr(product_update_data, new_field, None)
                old_value = existing_product.get(old_field_chinese)

                # 对于浮点数，转换为字符串进行比较，避免精度问题
                if isinstance(new_value, float) and isinstance(old_value, (float, int)):
                    new_value_str = f"{new_value:.2f}"
                    old_value_str = f"{float(old_value):.2f}"
                    if new_value_str != old_value_str:
                        logger.info(f"SERVICE: Critical field '{old_field_chinese}' changed from '{old_value_str}' to '{new_value_str}'. Re-review required.")
                        should_re_review = True
                        break
                elif new_value is not None and str(new_value) != str(old_value) and old_value is not None: # 只有新值非空且与旧值不同时才算改变
                    logger.info(f"SERVICE: Critical field '{old_field_chinese}' changed from '{old_value}' to '{new_value}'. Re-review required.")
                    should_re_review = True
                    break
                elif new_value is not None and old_value is None: # 旧值为None，新值非None
                    logger.info(f"SERVICE: Critical field '{old_field_chinese}' changed from 'None' to '{new_value}'. Re-review required.")
                    should_re_review = True
                    break

            # 检查图片URL列表是否发生变化
            if product_update_data.image_urls is not None:
                existing_image_urls_str = existing_product.get('图片URL列表')
                # 将逗号分隔的字符串转换为列表，并去除空格
                existing_image_urls_list = [url.strip() for url in existing_image_urls_str.split(',')] if existing_image_urls_str else []
                new_image_urls_list = [url.strip() for url in product_update_data.image_urls]

                # 比较排序后的列表，忽略顺序差异
                if sorted(existing_image_urls_list) != sorted(new_image_urls_list):
                    logger.info("SERVICE: Image URLs changed. Re-review required.")
                    should_re_review = True

        if product_update_data.image_urls is not None:
            logger.info(f"SERVICE: Updating images for product {product_id}. New URLs: {product_update_data.image_urls}")
            await self.product_image_dal.delete_product_images_by_product_id(conn, product_id)
            for i, url in enumerate(product_update_data.image_urls):
                await self.product_image_dal.add_product_image(conn, product_id, url, sort_order=i)
        
        update_args = product_update_data.model_dump(exclude_unset=True, exclude={'image_urls'})

        await self.product_dal.update_product(
            conn,
            product_id=product_id,
            current_operator_id=current_user_id,
            category_name=update_args.get('category_name'),
            product_name=update_args.get('product_name'),
            description=update_args.get('description'),
            quantity=update_args.get('quantity'),
            price=update_args.get('price'),
            condition=update_args.get('condition'),
            is_admin_request=is_admin_request
        )
        logger.info(f"SERVICE: Product {product_id} updated successfully by user {current_user_id} (Admin: {is_admin_request}).")

        # 如果关键信息被修改，并且是非管理员操作，则将商品状态重置为 PendingReview
        if should_re_review:
            logger.info(f"SERVICE: Critical information changed for product {product_id} by non-admin. Setting status to PendingReview.")
            await self.product_dal.update_product_status(conn, product_id, 'PendingReview')

    async def delete_product(self, conn: pyodbc.Connection, product_id: UUID, current_user: dict) -> None:
        """
        删除商品

        Args:
            conn: 数据库连接对象
            product_id: 要删除的商品ID
            current_user: 当前操作用户 (字典类型，包含 用户ID, 是否管理员 等中文键名)

        Raises:
            NotFoundError: 商品未找到
            PermissionError: 无权限操作
            DatabaseError: 数据库操作失败
        """
        logger.info(f"SERVICE: User {current_user.get('用户ID')} attempting to delete product {product_id}")
        
        existing_product = await self.product_dal.get_product_by_id(conn, product_id)
        if not existing_product:
            logger.warning(f"SERVICE: Product {product_id} not found for deletion.")
            raise NotFoundError(f"商品 (ID: {product_id}) 未找到。")

        is_admin_request = current_user.get('是否管理员', False) # 使用中文键
        owner_id_from_db = existing_product.get('卖家ID')

        try:
            if isinstance(owner_id_from_db, str):
                owner_id_from_db_uuid = UUID(owner_id_from_db)
            elif isinstance(owner_id_from_db, UUID):
                 owner_id_from_db_uuid = owner_id_from_db
            else:
                owner_id_from_db_uuid = None
        except ValueError:
            logger.error(f"SERVICE: Invalid OwnerID format '{owner_id_from_db}' for product {product_id} during delete.")
            raise PermissionError("无法验证商品所有权以进行删除。")

        current_user_id = current_user.get('用户ID') # 使用中文键
        if not is_admin_request and owner_id_from_db_uuid != current_user_id:
            logger.warning(f"SERVICE: User {current_user_id} (not owner or admin) attempted to delete product {product_id} owned by {owner_id_from_db_uuid}.")
            raise PermissionError("无权删除此商品。")
        
        await self.product_dal.delete_product(conn, product_id, current_user_id, is_admin_request)
        logger.info(f"SERVICE: Product {product_id} deleted successfully by user {current_user_id} (Admin: {is_admin_request}).")

    async def activate_product(self, conn: pyodbc.Connection, product_id: UUID, current_user: dict) -> None:
        # 路由层已经处理了管理员权限验证，服务层不需要重复此检查。
        # if not await self.check_admin_permission(conn, admin_id): # 传入UUID
        #     raise PermissionError("无权执行此操作，只有管理员可以激活商品。")

        is_admin_request = current_user.get('是否管理员', False) # 获取是否管理员状态
        operator_id = current_user.get('用户ID') # 获取操作者ID

        try:
            await self.product_dal.activate_product(conn, product_id, operator_id, is_admin_request)
            logger.info(f"Product {product_id} activated by user {operator_id} (Admin: {is_admin_request})")
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

    async def withdraw_product(self, conn: pyodbc.Connection, product_id: UUID, current_user: dict) -> None:
        """
        卖家或管理员下架商品 (将状态改为 Withdrawn)

        Args:
            conn: 数据库连接对象
            product_id: 商品ID
            current_user: 当前操作用户 (字典类型，包含 用户ID, 是否管理员 等中文键名)

        Raises:
            NotFoundError: 商品未找到
            PermissionError: 无权限操作
            DatabaseError: 数据库操作失败
        """
        logger.info(f"SERVICE: User {current_user.get('用户ID')} attempting to withdraw product {product_id}")

        existing_product = await self.product_dal.get_product_by_id(conn, product_id)
        if not existing_product:
            logger.warning(f"SERVICE: Product {product_id} not found for withdrawal.")
            raise NotFoundError(f"商品 (ID: {product_id}) 未找到。")

        is_admin_request = current_user.get('是否管理员', False) # 使用中文键
        owner_id_from_db = existing_product.get('卖家ID')
        
        try:
            if isinstance(owner_id_from_db, str):
                owner_id_from_db_uuid = UUID(owner_id_from_db)
            elif isinstance(owner_id_from_db, UUID):
                owner_id_from_db_uuid = owner_id_from_db
            else:
                owner_id_from_db_uuid = None
        except ValueError:
            logger.error(f"SERVICE: Invalid OwnerID format '{owner_id_from_db}' for product {product_id} during withdraw.")
            raise PermissionError("无法验证商品所有权以下架商品。")

        current_user_id = current_user.get('用户ID') # 使用中文键
        if not is_admin_request and owner_id_from_db_uuid != current_user_id:
            logger.warning(f"SERVICE: User {current_user_id} (not owner or admin) attempted to withdraw product {product_id} owned by {owner_id_from_db_uuid}.")
            raise PermissionError("无权下架此商品。")
            
        current_status = existing_product.get('商品状态')
        if current_status not in ['Active', 'PendingReview', 'Rejected']:
            logger.warning(f"SERVICE: Product {product_id} is in status '{current_status}' and cannot be withdrawn.")
            raise PermissionError(f"商品当前状态 ({current_status}) 不允许下架。")

        await self.product_dal.withdraw_product(conn, product_id, current_user_id, is_admin_request)
        logger.info(f"SERVICE: Product {product_id} withdrawn successfully by user {current_user_id} (Admin: {is_admin_request}).")

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

    async def get_product_status_counts(self, conn: pyodbc.Connection) -> Dict[str, int]:
        """
        获取商品状态统计数量。
        """
        try:
            stats = await self.product_dal.get_product_status_counts(conn)
            logger.info(f"Service: get_product_status_counts returning: {stats}")
            return stats
        except DALError as e:
            raise DALError(f"获取商品状态统计失败: {e}") from e
        except Exception as e:
            raise DALError(f"获取商品状态统计时发生意外错误: {e}") from e