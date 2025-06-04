import pytest
import pytest_mock
from unittest.mock import AsyncMock, MagicMock, ANY, patch
from app.dal.product_dal import ProductDAL, ProductImageDAL, UserFavoriteDAL
from uuid import UUID, uuid4
from app.exceptions import DALError, NotFoundError, IntegrityError, ForbiddenError, DatabaseError
from datetime import datetime, timezone

@pytest.fixture
def mock_execute_query_func(mocker: pytest_mock.MockerFixture) -> AsyncMock:
    """Provides a mock for the execute_query_func injected into DALs."""
    return AsyncMock()

@pytest.fixture
def product_dal(mock_execute_query_func: AsyncMock) -> ProductDAL:
    """Provides a ProductDAL instance with a mocked execute_query_func."""
    return ProductDAL(mock_execute_query_func)

@pytest.fixture
def product_image_dal(mock_execute_query_func: AsyncMock) -> ProductImageDAL:
    """Provides a ProductImageDAL instance with a mocked execute_query_func."""
    return ProductImageDAL(mock_execute_query_func)

@pytest.fixture
def user_favorite_dal(mock_execute_query_func: AsyncMock) -> UserFavoriteDAL:
    """Provides a UserFavoriteDAL instance with a mocked execute_query_func."""
    return UserFavoriteDAL(mock_execute_query_func)

@pytest.mark.asyncio
async def test_sp_batch_review_products(product_dal: ProductDAL, mock_execute_query_func: AsyncMock):
    product_ids = [uuid4(), uuid4()]
    admin_id = uuid4()
    new_status = "Active"
    reason = ""
    
    mock_conn = MagicMock()
    
    mock_execute_query_func.return_value = MagicMock()
    mock_execute_query_func.return_value.get.return_value = len(product_ids)
    
    affected_count = await product_dal.batch_activate_products(
        conn=mock_conn,
        product_ids=product_ids,
        admin_id=admin_id,
    )
    
    mock_execute_query_func.assert_called_once_with(
        mock_conn,
        "EXEC sp_BatchReviewProducts @productIds = :product_ids, @adminId = :admin_id, @action = :action",
        {
            "product_ids": ",".join(map(str, product_ids)),
            "admin_id": str(admin_id),
            "action": "Activate"
        },
        fetchone=False
    )
    assert affected_count == len(product_ids)

@pytest.mark.asyncio
async def test_add_user_favorite_dal(
    user_favorite_dal: UserFavoriteDAL,
    mock_execute_query_func: AsyncMock
):
    user_id = uuid4()
    product_id = uuid4()

    mock_conn = MagicMock()

    await user_favorite_dal.add_user_favorite(mock_conn, user_id, product_id)

    mock_execute_query_func.assert_called_once_with(
        mock_conn,
        "EXEC sp_AddFavoriteProduct @userId = :user_id, @productId = :product_id",
        {"user_id": str(user_id), "product_id": str(product_id)},
        fetchone=False,
        fetchall=False
    )

@pytest.mark.asyncio
async def test_remove_user_favorite_dal(
    user_favorite_dal: UserFavoriteDAL,
    mock_execute_query_func: AsyncMock
):
    user_id = uuid4()
    product_id = uuid4()

    mock_conn = MagicMock()

    await user_favorite_dal.remove_user_favorite(mock_conn, user_id, product_id)

    mock_execute_query_func.assert_called_once_with(
        mock_conn,
        "EXEC sp_RemoveFavoriteProduct @userId = :user_id, @productId = :product_id",
        {"user_id": str(user_id), "product_id": str(product_id)},
        fetchone=False,
        fetchall=False
    )

@pytest.mark.asyncio
async def test_get_user_favorite_products_dal(
    user_favorite_dal: UserFavoriteDAL,
    mock_execute_query_func: AsyncMock
):
    user_id = uuid4()

    mock_conn = MagicMock()

    mock_return_value = [
        {"商品ID": str(uuid4()), "商品名称": "商品A"},
        {"商品ID": str(uuid4()), "商品名称": "商品B"},
    ]
    mock_execute_query_func.return_value = mock_return_value

    favorites = await user_favorite_dal.get_user_favorite_products(mock_conn, user_id)

    mock_execute_query_func.assert_called_once_with(
        mock_conn,
        "EXEC sp_GetUserFavoriteProducts @userId = :user_id",
        {"user_id": str(user_id)},
        fetchone=False,
        fetchall=True
    )

    assert favorites == mock_return_value
    assert isinstance(favorites, list)
    assert len(favorites) == 2
    assert "商品名称" in favorites[0]

@pytest.mark.asyncio
async def test_decrease_product_quantity_dal(
    product_dal: ProductDAL,
    mock_execute_query_func: AsyncMock
):
    product_id = uuid4()
    quantity_to_decrease = 5

    mock_conn = MagicMock()

    await product_dal.decrease_product_quantity(mock_conn, product_id, quantity_to_decrease)

    mock_execute_query_func.assert_called_once_with(
        mock_conn,
        "EXEC sp_DecreaseProductQuantity @productId = :product_id, @quantityToDecrease = :quantity_to_decrease",
        {"product_id": str(product_id), "quantity_to_decrease": quantity_to_decrease},
        fetchone=False,
        fetchall=False
    )

@pytest.mark.asyncio
async def test_increase_product_quantity_dal(
    product_dal: ProductDAL,
    mock_execute_query_func: AsyncMock
):
    product_id = uuid4()
    quantity_to_increase = 10

    mock_conn = MagicMock()

    await product_dal.increase_product_quantity(mock_conn, product_id, quantity_to_increase)

    mock_execute_query_func.assert_called_once_with(
        mock_conn,
        "EXEC sp_IncreaseProductQuantity @productId = :product_id, @quantityToIncrease = :quantity_to_increase",
        {"product_id": str(product_id), "quantity_to_increase": quantity_to_increase},
        fetchone=False,
        fetchall=False
    )

@pytest.mark.asyncio
async def test_create_product_dal(
    product_dal: ProductDAL,
    mock_execute_query_func: AsyncMock
):
    owner_id = uuid4()
    category_name = "Electronics"
    product_name = "Laptop"
    description = "A test laptop"
    quantity = 10
    price = 1200.50

    mock_conn = MagicMock()
    mock_new_product_id = uuid4()
    
    mock_execute_query_func.return_value = {"ProductId": str(mock_new_product_id)}

    new_product_id = await product_dal.create_product(
        mock_conn,
        owner_id,
        category_name,
        product_name,
        description,
        quantity,
        price
    )

    mock_execute_query_func.assert_called_once_with(
        mock_conn,
        "EXEC sp_CreateProduct @ownerId = :owner_id, @categoryName = :category_name, @productName = :product_name, @description = :description, @quantity = :quantity, @price = :price",
        {
            "owner_id": str(owner_id),
            "category_name": category_name,
            "product_name": product_name,
            "description": description,
            "quantity": quantity,
            "price": price
        },
        fetchone=True
    )
    assert isinstance(new_product_id, UUID)
    assert new_product_id == mock_new_product_id

@pytest.mark.asyncio
async def test_update_product_dal(
    product_dal: ProductDAL,
    mock_execute_query_func: AsyncMock
):
    product_id = uuid4()
    owner_id = uuid4()
    category_name = "Updated Category"
    product_name = "Updated Product"
    description = "Updated Description"
    quantity = 5
    price = 99.99

    mock_conn = MagicMock()

    mock_execute_query_func.return_value = {'OperationResultCode': 0, '': 'Update successful.'}

    update_success = await product_dal.update_product(
        mock_conn,
        product_id,
        owner_id,
        category_name,
        product_name,
        description,
        quantity,
        price
    )

    mock_execute_query_func.assert_called_once_with(
        mock_conn,
        "EXEC sp_UpdateProduct @productId = :product_id, @ownerId = :owner_id, @categoryName = :category_name, @productName = :product_name, @description = :description, @quantity = :quantity, @price = :price",
        {
            "product_id": str(product_id),
            "owner_id": str(owner_id),
            "category_name": category_name,
            "product_name": product_name,
            "description": description,
            "quantity": quantity,
            "price": price
        },
        fetchone=True
    )
    assert update_success is True

@pytest.mark.asyncio
async def test_delete_product_dal(
    product_dal: ProductDAL,
    mock_execute_query_func: AsyncMock
):
    product_id = uuid4()
    owner_id = uuid4()

    mock_conn = MagicMock()

    mock_execute_query_func.return_value = {'OperationResultCode': 0, '': 'Delete successful.'}

    delete_success = await product_dal.delete_product(mock_conn, product_id, owner_id)

    mock_execute_query_func.assert_called_once_with(
        mock_conn,
        "EXEC sp_DeleteProduct @productId = :product_id, @ownerId = :owner_id",
        {
            "product_id": str(product_id),
            "owner_id": str(owner_id)
        },
        fetchone=True
    )
    assert delete_success is True

@pytest.mark.asyncio
async def test_activate_product_dal(
    product_dal: ProductDAL,
    mock_execute_query_func: AsyncMock
):
    product_id = uuid4()
    admin_id = uuid4()

    mock_conn = MagicMock()

    mock_execute_query_func.return_value = {'OperationResultCode': 0, '': 'Activation successful.'}

    activate_success = await product_dal.activate_product(mock_conn, product_id, admin_id)

    mock_execute_query_func.assert_called_once_with(
        mock_conn,
        "EXEC sp_ActivateProduct @productId = :product_id, @adminId = :admin_id",
        {
            "product_id": str(product_id),
            "admin_id": str(admin_id)
        },
        fetchone=True
    )
    assert activate_success is True

@pytest.mark.asyncio
async def test_reject_product_dal(
    product_dal: ProductDAL,
    mock_execute_query_func: AsyncMock
):
    product_id = uuid4()
    admin_id = uuid4()
    reason = "Rejected for inappropriate content"

    mock_conn = MagicMock()

    mock_execute_query_func.return_value = {'OperationResultCode': 0, '': 'Rejection successful.'}

    reject_success = await product_dal.reject_product(mock_conn, product_id, admin_id, reason)

    mock_execute_query_func.assert_called_once_with(
        mock_conn,
        "EXEC sp_RejectProduct @productId = :product_id, @adminId = :admin_id, @reason = :reason",
        {
            "product_id": str(product_id),
            "admin_id": str(admin_id),
            "reason": reason
        },
        fetchone=True
    )
    assert reject_success is True

@pytest.mark.asyncio
async def test_withdraw_product_dal(
    product_dal: ProductDAL,
    mock_execute_query_func: AsyncMock
):
    product_id = uuid4()
    owner_id = uuid4()

    mock_conn = MagicMock()

    mock_execute_query_func.return_value = {'OperationResultCode': 0, '': 'Withdrawal successful.'}

    withdraw_success = await product_dal.withdraw_product(mock_conn, product_id, owner_id)

    mock_execute_query_func.assert_called_once_with(
        mock_conn,
        "EXEC sp_WithdrawProduct @productId = :product_id, @ownerId = :owner_id",
        {
            "product_id": str(product_id),
            "owner_id": str(owner_id)
        },
        fetchone=True
    )
    assert withdraw_success is True

@pytest.mark.asyncio
async def test_get_product_list_dal(
    product_dal: ProductDAL,
    mock_execute_query_func: AsyncMock
):
    mock_conn = MagicMock()

    mock_return_value = [
        {
            "商品ID": UUID("11111111-1111-1111-1111-111111111111"),
            "商品名称": "Product A", 
            "状态": "Active", 
            "价格": 100.0,
            "库存": 50,
            "图片URL": "http://example.com/imgA.jpg",
            "发布时间": datetime.now(timezone.utc)
        },
        {
            "商品ID": UUID("22222222-2222-2222-2222-222222222222"),
            "商品名称": "Product B", 
            "状态": "PendingReview", 
            "价格": 200.0,
            "库存": 20,
            "图片URL": None,
            "发布时间": datetime.now(timezone.utc)
        },
    ]
    mock_execute_query_func.return_value = mock_return_value

    products = await product_dal.get_product_list(
        mock_conn, 
        category_id=1, 
        status="Active", 
        keyword="Product", 
        min_price=50.0, 
        max_price=250.0,
        order_by="价格",
        page_number=1,
        page_size=10
    )

    mock_execute_query_func.assert_called_once_with(
        mock_conn,
        "EXEC sp_GetProductList @categoryId = :category_id, @status = :status, @keyword = :keyword, @minPrice = :min_price, @maxPrice = :max_price, @orderBy = :order_by, @pageNumber = :page_number, @pageSize = :page_size",
        {
            "category_id": 1,
            "status": "Active",
            "keyword": "Product",
            "min_price": 50.0,
            "max_price": 250.0,
            "order_by": "价格",
            "page_number": 1,
            "page_size": 10
        },
        fetchone=False,
        fetchall=True
    )

    assert products == mock_return_value
    assert isinstance(products, list)
    assert len(products) == 2
    assert isinstance(products[0], dict)
    assert "商品名称" in products[0]
    assert isinstance(products[0]["商品ID"], UUID)
    assert isinstance(products[0]["发布时间"], datetime) and products[0]["发布时间"].tzinfo is not None

@pytest.mark.asyncio
async def test_get_product_by_id_dal_found(
    product_dal: ProductDAL,
    mock_execute_query_func: AsyncMock
):
    product_id = uuid4()

    mock_conn = MagicMock()

    mock_return_value = {
        "商品ID": product_id,
        "商品名称": "Test Product",
        "状态": "Active",
        "价格": 100.0,
        "库存": 50,
        "卖家ID": uuid4(),
        "分类名称": "Category",
        "描述": "Description",
        "发布时间": datetime.now(timezone.utc),
        "更新时间": datetime.now(timezone.utc),
        "图片URL": "http://example.com/image.jpg", 
        "排序": 0
    }
    mock_execute_query_func.return_value = mock_return_value

    product = await product_dal.get_product_by_id(mock_conn, product_id)

    mock_execute_query_func.assert_called_once_with(
        mock_conn,
        "EXEC sp_GetProductDetail @productId = :product_id",
        {"product_id": str(product_id)},
        fetchone=True
    )

    assert product == mock_return_value
    assert isinstance(product, dict)
    assert "商品名称" in product
    assert isinstance(product["商品ID"], UUID)
    assert isinstance(product["卖家ID"], UUID)
    assert isinstance(product["发布时间"], datetime) and product["发布时间"].tzinfo is not None
    assert isinstance(product["更新时间"], datetime) and product["更新时间"].tzinfo is not None

@pytest.mark.asyncio
async def test_get_product_by_id_dal_not_found(
    product_dal: ProductDAL,
    mock_execute_query_func: AsyncMock
):
    product_id = uuid4()

    mock_conn = MagicMock()

    mock_execute_query_func.return_value = None

    product = await product_dal.get_product_by_id(mock_conn, product_id)

    mock_execute_query_func.assert_called_once_with(
        mock_conn,
        "EXEC sp_GetProductDetail @productId = :product_id",
        {"product_id": str(product_id)},
        fetchone=True
    )
    assert product is None

@pytest.mark.asyncio
async def test_add_product_image_dal(
    product_image_dal: ProductImageDAL,
    mock_execute_query_func: AsyncMock
):
    product_id = uuid4()
    image_url = "http://example.com/new_image.jpg"
    sort_order = 1

    mock_conn = MagicMock()

    mock_execute_query_func.return_value = {'ImageId': 1}

    await product_image_dal.add_product_image(mock_conn, product_id, image_url, sort_order)

    mock_execute_query_func.assert_called_once_with(
        mock_conn,
        "EXEC sp_AddProductImage @productId = :product_id, @imageUrl = :image_url, @sortOrder = :sort_order",
        {
            "product_id": str(product_id),
            "image_url": image_url,
            "sort_order": sort_order
        },
        fetchone=True
    )

@pytest.mark.asyncio
async def test_get_images_by_product_id_dal(
    product_image_dal: ProductImageDAL,
    mock_execute_query_func: AsyncMock
):
    product_id = uuid4()

    mock_conn = MagicMock()

    mock_return_value = [
        {"ImageID": 1, "商品ID": product_id, "图片URL": "url1", "排序": 0},
        {"ImageID": 2, "商品ID": product_id, "图片URL": "url2", "排序": 1},
    ]
    mock_execute_query_func.return_value = mock_return_value

    images = await product_image_dal.get_images_by_product_id(mock_conn, product_id)

    mock_execute_query_func.assert_called_once_with(
        mock_conn,
        "EXEC sp_GetProductImagesByProductId @productId = :product_id",
        {"product_id": str(product_id)},
        fetchone=False,
        fetchall=True
    )

    assert images == mock_return_value
    assert isinstance(images, list)
    assert len(images) == 2
    assert isinstance(images[0], dict)
    assert "图片URL" in images[0]
    assert isinstance(images[0]["商品ID"], UUID)

@pytest.mark.asyncio
async def test_delete_product_image_dal(
    product_image_dal: ProductImageDAL,
    mock_execute_query_func: AsyncMock
):
    image_id = uuid4()

    mock_conn = MagicMock()

    mock_execute_query_func.return_value = {'OperationResultCode': 0, '': 'Delete successful.'}

    delete_success = await product_image_dal.delete_product_image(mock_conn, image_id)

    mock_execute_query_func.assert_called_once_with(
        mock_conn,
        "EXEC sp_DeleteProductImage @imageId = :image_id",
        {"image_id": str(image_id)},
        fetchone=True
    )
    assert delete_success is True

@pytest.mark.asyncio
async def test_delete_product_images_by_product_id_dal(
    product_image_dal: ProductImageDAL,
    mock_execute_query_func: AsyncMock
):
    product_id = uuid4()

    mock_conn = MagicMock()

    mock_execute_query_func.return_value = {'OperationResultCode': 0, '': 'Images deleted.'}

    delete_success = await product_image_dal.delete_product_images_by_product_id(mock_conn, product_id)

    mock_execute_query_func.assert_called_once_with(
        mock_conn,
        "EXEC sp_DeleteProductImagesByProductId @productId = :product_id",
        {
            "product_id": str(product_id)
        },
        fetchone=True
    )
    assert delete_success is True

@pytest.mark.asyncio
async def test_batch_reject_products_dal(product_dal: ProductDAL, mock_execute_query_func: AsyncMock):
    admin_id = uuid4()
    product_ids = [uuid4() for _ in range(3)]

    mock_conn = MagicMock()

    mock_execute_query_func.return_value = {'OperationResultCode': 0, '': 'Batch rejection successful.'}

    reject_success_count = await product_dal.batch_reject_products(mock_conn, product_ids, admin_id, reason="Test reason")

    mock_execute_query_func.assert_called_once_with(
        mock_conn,
        "EXEC sp_BatchRejectProducts @productIds = :product_ids, @adminId = :admin_id, @reason = :reason",
        {
            "product_ids": ",".join(map(str, product_ids)),
            "admin_id": str(admin_id),
            "reason": "Test reason"
        },
        fetchone=False
    )
    assert reject_success_count == len(product_ids)