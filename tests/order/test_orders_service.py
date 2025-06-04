import pytest
import pyodbc
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4
from datetime import datetime, timezone
from fastapi.testclient import TestClient
import pytest_mock

from app.services.order_service import OrderService
from app.dal.orders_dal import OrdersDAL # 假设 OrderDAL 在 app.dal.order_dal 中
from app.schemas.order_schemas import (
    OrderCreateSchema,
    OrderResponseSchema,
    OrderStatusUpdateSchema
)
from app.schemas.product_schemas import ProductResponseSchema # 假设用于产品信息
from app.schemas.user_schemas import UserResponseSchema # 假设用于用户信息
from app.exceptions import DALError, NotFoundError, ForbiddenError # 移除 ValueError 的导入

# Mock数据
TEST_BUYER_ID = uuid4()
TEST_SELLER_ID = uuid4()
TEST_PRODUCT_ID = uuid4()
TEST_ORDER_ID = uuid4() # 将 TEST_ORDER_ID 修改为 UUID 类型

@pytest.fixture
def mock_order_dal(mocker) -> AsyncMock:
    """Fixture to mock OrderDAL."""
    return mocker.AsyncMock(spec=OrdersDAL)

@pytest.fixture
def order_service(mock_order_dal: AsyncMock) -> OrderService:
    """Fixture to create OrderService with mocked DAL."""
    return OrderService(order_dal=mock_order_dal)

@pytest.fixture
def mock_db_connection() -> MagicMock:
    """Fixture for a mock database connection."""
    return MagicMock(spec=pyodbc.Connection)

# 模拟 OrderCreateSchema 实例
@pytest.fixture
def mock_order_create_schema():
    return OrderCreateSchema(
        product_id=TEST_PRODUCT_ID, 
        quantity=1,
        shipping_address="123 Main St",
        contact_phone="555-1234",
        total_price=100.00 # 添加 total_price 字段
    )

# 模拟 OrderResponseSchema 实例 (基础)
@pytest.fixture
def base_mock_order_response_schema():
    return OrderResponseSchema(
        order_id=TEST_ORDER_ID,
        product_id=TEST_PRODUCT_ID,
        buyer_id=TEST_BUYER_ID,
        seller_id=TEST_SELLER_ID, 
        quantity=1,
        total_price=100.00,
        status="PendingConfirmation",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        shipping_address="123 Main St", # 添加 shipping_address 字段
        contact_phone="555-1234" # 添加 contact_phone 字段
    )

@pytest.fixture
def mock_orders_list(base_mock_order_response_schema):
    """Fixture to mock a list of OrderResponseSchema instances."""
    return [
        base_mock_order_response_schema.model_copy(update={"order_id": uuid4(), "status": "PendingConfirmation"}),
        base_mock_order_response_schema.model_copy(update={"order_id": uuid4(), "status": "Confirmed"})
    ]

@pytest.mark.asyncio
async def test_get_order_by_id_not_found(client: TestClient, mock_order_service: AsyncMock, mocker: pytest_mock.MockerFixture):
    """
    测试获取不存在的订单。
    """
    order_id = uuid4()
    # Mock DAL get_order_by_id to return None
    mock_order_dal.get_order_by_id.return_value = None

    with pytest.raises(NotFoundError, match=f"Order with ID {order_id} not found."):
        await order_service.get_order_by_id(mock_db_connection, order_id, client.test_user_id) # Pass requesting_user_id

    mock_order_dal.get_order_by_id.assert_called_once_with(mock_db_connection, order_id)

# --- Test create_order ---
@pytest.mark.asyncio
async def test_create_order_success(
    order_service: OrderService, 
    mock_order_dal: AsyncMock, 
    mock_db_connection: MagicMock,
    mock_order_create_schema: OrderCreateSchema, # 使用 fixture
    base_mock_order_response_schema: OrderResponseSchema # 使用 fixture
):
    expected_order_id = TEST_ORDER_ID
    
    # Mock DAL create_order to return an order ID
    mock_order_dal.create_order.return_value = expected_order_id

    # Mock DAL get_order_by_id to return a complete order schema
    # This is called after successful creation to fetch the full order details
    # 使用 base_mock_order_response_schema 并更新状态
    mock_created_order = base_mock_order_response_schema.model_copy(update={
        "order_id": expected_order_id, # 确保使用返回的订单ID
        "status": "PendingConfirmation" # 确保状态正确
    })
    # Mock get_order_by_id to return a dictionary, not a schema instance
    mock_order_dal.get_order_by_id.return_value = mock_created_order.model_dump(mode='json')

    created_order = await order_service.create_order(mock_db_connection, mock_order_create_schema, TEST_BUYER_ID)

    assert created_order == mock_created_order
    mock_order_dal.create_order.assert_called_once_with(
        conn=mock_db_connection,
        product_id=mock_order_create_schema.product_id,
        buyer_id=TEST_BUYER_ID,
        quantity=mock_order_create_schema.quantity,
        shipping_address=mock_order_create_schema.shipping_address,
        contact_phone=mock_order_create_schema.contact_phone
    )
    mock_order_dal.get_order_by_id.assert_called_once_with(mock_db_connection, expected_order_id)

@pytest.mark.asyncio
async def test_create_order_dal_fails_to_return_id(
    order_service: OrderService, 
    mock_order_dal: AsyncMock, 
    mock_db_connection: MagicMock,
    mock_order_create_schema: OrderCreateSchema # 使用 fixture
):
    mock_order_dal.create_order.return_value = None # Simulate SP not returning ID

    with pytest.raises(ValueError, match="Failed to create order, stored procedure did not return an order ID."):
        await order_service.create_order(mock_db_connection, mock_order_create_schema, TEST_BUYER_ID)
    
    mock_order_dal.create_order.assert_called_once_with(
        conn=mock_db_connection,
        product_id=mock_order_create_schema.product_id,
        buyer_id=TEST_BUYER_ID,
        quantity=mock_order_create_schema.quantity,
        shipping_address=mock_order_create_schema.shipping_address,
        contact_phone=mock_order_create_schema.contact_phone
    )
    mock_order_dal.get_order_by_id.assert_not_called() # Should not be called if create_order fails

@pytest.mark.asyncio
async def test_create_order_not_found_after_creation(
    order_service: OrderService, 
    mock_order_dal: AsyncMock, 
    mock_db_connection: MagicMock,
    mock_order_create_schema: OrderCreateSchema # 使用 fixture
):
    expected_order_id = TEST_ORDER_ID
    mock_order_dal.create_order.return_value = expected_order_id
    # Mock get_order_by_id to return None, simulating not found
    mock_order_dal.get_order_by_id.return_value = None

    with pytest.raises(NotFoundError, match=f"Order with ID {expected_order_id} not found after creation."):
        await order_service.create_order(mock_db_connection, mock_order_create_schema, TEST_BUYER_ID)

    mock_order_dal.create_order.assert_called_once_with(
        conn=mock_db_connection,
        product_id=mock_order_create_schema.product_id,
        buyer_id=TEST_BUYER_ID,
        quantity=mock_order_create_schema.quantity,
        shipping_address=mock_order_create_schema.shipping_address,
        contact_phone=mock_order_create_schema.contact_phone
    )
    mock_order_dal.get_order_by_id.assert_called_once_with(mock_db_connection, expected_order_id)

@pytest.mark.asyncio
async def test_create_order_dal_exception(
    order_service: OrderService, 
    mock_order_dal: AsyncMock, 
    mock_db_connection: MagicMock,
    mock_order_create_schema: OrderCreateSchema # 使用 fixture
):
    mock_order_dal.create_order.side_effect = DALError("DB create error")

    with pytest.raises(DALError, match="DB create error"):
        await order_service.create_order(mock_db_connection, mock_order_create_schema, TEST_BUYER_ID)
    
    mock_order_dal.create_order.assert_called_once_with(
        conn=mock_db_connection,
        product_id=mock_order_create_schema.product_id,
        buyer_id=TEST_BUYER_ID,
        quantity=mock_order_create_schema.quantity,
        shipping_address=mock_order_create_schema.shipping_address,
        contact_phone=mock_order_create_schema.contact_phone
    )
    mock_order_dal.get_order_by_id.assert_not_called() # Should not be called if create_order fails

@pytest.mark.asyncio
async def test_create_order_pyodbc_error(
    order_service: OrderService, 
    mock_order_dal: AsyncMock, 
    mock_db_connection: MagicMock,
    mock_order_create_schema: OrderCreateSchema # 使用 fixture
):
    # Simulate pyodbc.Error during the first DAL call (create_order)
    mock_order_dal.create_order.side_effect = pyodbc.Error("Simulated DB connection error")

    with pytest.raises(DALError, match="Database error during order creation: Simulated DB connection error"):
        await order_service.create_order(mock_db_connection, mock_order_create_schema, TEST_BUYER_ID)

    mock_order_dal.create_order.assert_called_once_with(
        conn=mock_db_connection,
        product_id=mock_order_create_schema.product_id,
        buyer_id=TEST_BUYER_ID,
        quantity=mock_order_create_schema.quantity,
        shipping_address=mock_order_create_schema.shipping_address,
        contact_phone=mock_order_create_schema.contact_phone
    )
    mock_order_dal.get_order_by_id.assert_not_called() # Should not be called if create_order fails


# --- Test confirm_order ---
@pytest.mark.asyncio
async def test_confirm_order_success(
    order_service: OrderService, 
    mock_order_dal: AsyncMock, 
    mock_db_connection: MagicMock,
    base_mock_order_response_schema: OrderResponseSchema # 使用 fixture
):
    # Mock get_order_by_id for pre-check and post-update fetch
    initial_order_state = base_mock_order_response_schema.model_copy(update={
        "status": "PendingConfirmation"
    })
    confirmed_order_state = base_mock_order_response_schema.model_copy(update={
        "status": "Confirmed", # Status updated
        "updated_at": datetime.now(timezone.utc) # 模拟更新时间
    })
    
    # First call to get_order_by_id (pre-check), second call (post-update fetch)
    mock_order_dal.get_order_by_id.side_effect = [initial_order_state, confirmed_order_state]
    mock_order_dal.confirm_order.return_value = None # confirm_order SP might not return anything

    updated_order = await order_service.confirm_order(mock_db_connection, TEST_ORDER_ID, TEST_SELLER_ID)

    assert updated_order == confirmed_order_state
    assert mock_order_dal.get_order_by_id.call_count == 2
    mock_order_dal.get_order_by_id.assert_any_call(mock_db_connection, TEST_ORDER_ID)
    mock_order_dal.confirm_order.assert_called_once_with(mock_db_connection, TEST_ORDER_ID, TEST_SELLER_ID) # 添加 seller_id 参数

@pytest.mark.asyncio
async def test_confirm_order_not_found_initial_fetch(
    order_service: OrderService, 
    mock_order_dal: AsyncMock, 
    mock_db_connection: MagicMock
):
    mock_order_dal.get_order_by_id.return_value = None # Order not found initially

    with pytest.raises(NotFoundError, match=f"Order with ID {TEST_ORDER_ID} not found."):
        await order_service.confirm_order(mock_db_connection, TEST_ORDER_ID, TEST_SELLER_ID)
    
    mock_order_dal.confirm_order.assert_not_called()

@pytest.mark.asyncio
async def test_confirm_order_not_found_after_confirmation(
    order_service: OrderService, 
    mock_order_dal: AsyncMock, 
    mock_db_connection: MagicMock,
    base_mock_order_response_schema: OrderResponseSchema # 使用 fixture
):
    initial_order_state = base_mock_order_response_schema.model_copy(update={
        "status": "PendingConfirmation"
    })
    mock_order_dal.get_order_by_id.side_effect = [initial_order_state, None] # Simulate order not found after confirmation
    mock_order_dal.confirm_order.return_value = None

    with pytest.raises(NotFoundError, match=f"Order with ID {TEST_ORDER_ID} not found after confirmation."):
        await order_service.confirm_order(mock_db_connection, TEST_ORDER_ID, TEST_SELLER_ID)

    assert mock_order_dal.get_order_by_id.call_count == 2
    mock_order_dal.confirm_order.assert_called_once_with(mock_db_connection, TEST_ORDER_ID, TEST_SELLER_ID) # 添加 seller_id 参数

@pytest.mark.asyncio
async def test_confirm_order_dal_exception_on_confirm(
    order_service: OrderService, 
    mock_order_dal: AsyncMock, 
    mock_db_connection: MagicMock
):
    initial_order_state = OrderResponseSchema(
        order_id=TEST_ORDER_ID, product_id=TEST_PRODUCT_ID, buyer_id=TEST_BUYER_ID, 
        seller_id=TEST_SELLER_ID, quantity=1, total_price=100.0, status="PendingConfirmation",
        created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc),
        shipping_address="123 Main St", # 添加 shipping_address 字段
        contact_phone="555-1234" # 添加 contact_phone 字段
    )
    mock_order_dal.get_order_by_id.return_value = initial_order_state
    mock_order_dal.confirm_order.side_effect = DALError("DB confirm error")

    with pytest.raises(DALError, match="DB confirm error"):
        await order_service.confirm_order(mock_db_connection, TEST_ORDER_ID, TEST_SELLER_ID)

# --- Test complete_order --- (Similar structure to confirm_order tests)
@pytest.mark.asyncio
async def test_complete_order_success(
    order_service: OrderService, 
    mock_order_dal: AsyncMock, 
    mock_db_connection: MagicMock
):
    initial_order_state = OrderResponseSchema(
        order_id=TEST_ORDER_ID, product_id=TEST_PRODUCT_ID, buyer_id=TEST_BUYER_ID, 
        seller_id=TEST_SELLER_ID, quantity=1, total_price=100.0, status="Confirmed",
        created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc),
        shipping_address="123 Main St", 
        contact_phone="555-1234" 
    )
    completed_order_state = OrderResponseSchema(
        order_id=TEST_ORDER_ID, product_id=TEST_PRODUCT_ID, buyer_id=TEST_BUYER_ID, 
        seller_id=TEST_SELLER_ID, quantity=1, total_price=100.0, status="Completed",
        created_at=initial_order_state.created_at, updated_at=datetime.now(timezone.utc),
        shipping_address="123 Main St", 
        contact_phone="555-1234" 
    )
    mock_order_dal.get_order_by_id.side_effect = [initial_order_state, completed_order_state] 
    mock_order_dal.complete_order.return_value = None

    updated_order = await order_service.complete_order(mock_db_connection, TEST_ORDER_ID, TEST_BUYER_ID)

    # 比较除了 updated_at 之外的所有字段
    assert updated_order.model_dump(exclude={'updated_at'}) == completed_order_state.model_dump(exclude={'updated_at'})
    assert updated_order.updated_at >= initial_order_state.updated_at
    mock_order_dal.complete_order.assert_called_once_with(mock_db_connection, TEST_ORDER_ID)
    mock_order_dal.get_order_by_id.assert_called_once_with(mock_db_connection, TEST_ORDER_ID)

# --- Test reject_order --- (Similar structure to confirm_order tests)
@pytest.mark.asyncio
async def test_reject_order_success(
    order_service: OrderService, 
    mock_order_dal: AsyncMock, 
    mock_db_connection: MagicMock
):
    rejection_reason = "Item out of stock"
    initial_order_state = OrderResponseSchema(
        order_id=TEST_ORDER_ID, product_id=TEST_PRODUCT_ID, buyer_id=TEST_BUYER_ID, 
        seller_id=TEST_SELLER_ID, quantity=1, total_price=100.0, status="PendingConfirmation",
        created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc),
        shipping_address="123 Main St", 
        contact_phone="555-1234" 
    )
    rejected_order_state = OrderResponseSchema(
        order_id=TEST_ORDER_ID, product_id=TEST_PRODUCT_ID, buyer_id=TEST_BUYER_ID, 
        seller_id=TEST_SELLER_ID, quantity=1, total_price=100.0, status="Rejected",
        created_at=initial_order_state.created_at, updated_at=datetime.now(timezone.utc),
        rejection_reason=rejection_reason, 
        shipping_address="123 Main St", 
        contact_phone="555-1234" 
    )
    mock_order_dal.get_order_by_id.side_effect = [initial_order_state, rejected_order_state]
    mock_order_dal.reject_order.return_value = None

    updated_order = await order_service.reject_order(mock_db_connection, TEST_ORDER_ID, TEST_SELLER_ID, reason=rejection_reason)

    # 比较除了 updated_at 之外的所有字段
    assert updated_order.model_dump(exclude={'updated_at'}) == rejected_order_state.model_dump(exclude={'updated_at'})
    assert updated_order.updated_at >= initial_order_state.updated_at
    mock_order_dal.reject_order.assert_called_once_with(mock_db_connection, TEST_ORDER_ID, rejection_reason)
    mock_order_dal.get_order_by_id.assert_called_once_with(mock_db_connection, TEST_ORDER_ID)

# --- Test get_orders_by_user ---
@pytest.mark.asyncio
async def test_get_orders_by_user_buyer_success(
    order_service: OrderService,
    mock_order_dal: AsyncMock,
    mock_db_connection: MagicMock,
    mock_orders_list: list[OrderResponseSchema]
):
    """Test successfully getting orders by buyer ID."""
    # Arrange
    user_id = uuid4()

    # Simulate mock_order_dal returning a list of order dictionaries
    mock_dal_return_value = [order.model_dump(mode='json') for order in mock_orders_list]
    mock_order_dal.get_orders_by_user.return_value = mock_dal_return_value

    orders = await order_service.get_orders_by_user(mock_db_connection, user_id, is_seller=False)

    # The Service should convert the dictionaries to schemas
    assert len(orders) == len(mock_orders_list)
    assert all(isinstance(order, OrderResponseSchema) for order in orders)
    # Compare the returned schemas with the expected schemas
    assert orders == mock_orders_list

    mock_order_dal.get_orders_by_user.assert_called_once_with(
        mock_db_connection,
        user_id=user_id,
        is_seller=False,
        status=None, # Default status
        page_number=1, # Default page
        page_size=10 # Default size
    )

@pytest.mark.asyncio
async def test_get_orders_by_user_seller_success(
    order_service: OrderService,
    mock_order_dal: AsyncMock,
    mock_db_connection: MagicMock,
    mock_orders_list: list[OrderResponseSchema]
):
    """Test successfully getting orders by seller ID."""
    # Arrange
    user_id = uuid4()

    # Simulate mock_order_dal returning a list of order dictionaries
    mock_dal_return_value = [order.model_dump(mode='json') for order in mock_orders_list]
    mock_order_dal.get_orders_by_user.return_value = mock_dal_return_value

    orders = await order_service.get_orders_by_user(mock_db_connection, user_id, is_seller=True)

    # The Service should convert the dictionaries to schemas
    assert len(orders) == len(mock_orders_list)
    assert all(isinstance(order, OrderResponseSchema) for order in orders)
    # Compare the returned schemas with the expected schemas
    assert orders == mock_orders_list

    mock_order_dal.get_orders_by_user.assert_called_once_with(
        mock_db_connection,
        user_id=user_id,
        is_seller=True,
        status=None, # Default status
        page_number=1, # Default page
        page_size=10 # Default size
    )

@pytest.mark.asyncio
async def test_get_orders_by_user_no_orders(
    order_service: OrderService,
    mock_order_dal: AsyncMock,
    mock_db_connection: MagicMock
):
    """Test getting no orders for a user."""
    # Arrange
    user_id = uuid4()

    # Simulate mock_order_dal returning an empty list
    mock_order_dal.get_orders_by_user.return_value = []

    result = await order_service.get_orders_by_user(mock_db_connection, user_id, is_seller=False)
    assert result == []
    mock_order_dal.get_orders_by_user.assert_called_once_with(mock_db_connection, user_id, is_seller=False)

@pytest.mark.asyncio
async def test_get_orders_by_user_dal_exception(
    order_service: OrderService,
    mock_order_dal: AsyncMock,
    mock_db_connection: MagicMock
):
    """Test getting orders by user failing due to a DAL exception."""
    # Arrange
    user_id = uuid4()

    # Simulate mock_order_dal raising a DALError
    mock_order_dal.get_orders_by_user.side_effect = DALError("Database error")

    with pytest.raises(DALError, match="Database error"):
        await order_service.get_orders_by_user(mock_db_connection, user_id, is_seller=False)
    mock_order_dal.get_orders_by_user.assert_called_once_with(mock_db_connection, user_id, is_seller=False)