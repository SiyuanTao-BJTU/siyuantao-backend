import pytest
import pytest_mock
from unittest.mock import AsyncMock, patch, MagicMock, ANY
from app.dal.orders_dal import OrdersDAL
from app.schemas.order_schemas import OrderCreateSchema, OrderResponseSchema, OrderStatusUpdateSchema
from uuid import UUID, uuid4
from datetime import datetime, timezone
import pyodbc
from app.exceptions import DALError, NotFoundError, ForbiddenError, IntegrityError

# Mock data
TEST_BUYER_ID = uuid4()
TEST_SELLER_ID = uuid4()
TEST_PRODUCT_ID = uuid4()
TEST_ORDER_ID = uuid4()

# 模拟数据库连接 (不需要游标)
@pytest.fixture
def mock_db_connection() -> MagicMock:
    """Fixture for a mock database connection."""
    return MagicMock(spec=pyodbc.Connection)

# 模拟 execute_query_func
@pytest.fixture
def mock_execute_query_func(mocker: pytest_mock.MockerFixture) -> AsyncMock:
    """Fixture for a mock execute_query function."""
    return AsyncMock()

@pytest.fixture
def orders_dal(mock_execute_query_func: AsyncMock) -> OrdersDAL:
    """Fixture to create an OrdersDAL instance with a mocked execute_query function."""
    return OrdersDAL(execute_query_func=mock_execute_query_func)

# 模拟 OrderCreateSchema 实例
@pytest.fixture
def mock_order_create_schema():
    return OrderCreateSchema(
        product_id=TEST_PRODUCT_ID,
        quantity=2,
        shipping_address="123 Main St",
        contact_phone="555-1234",
        total_price=25.50
    )

# 模拟 OrderResponseSchema 实例
@pytest.fixture
def mock_order_response_schema():
    return OrderResponseSchema(
        order_id=TEST_ORDER_ID,
        seller_id=TEST_SELLER_ID,
        buyer_id=TEST_BUYER_ID,
        product_id=TEST_PRODUCT_ID,
        quantity=2,
        shipping_address="123 Main St",
        contact_phone="555-1234",
        total_price=25.50,
        status="Pending",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        complete_time=None,
        cancel_time=None,
        cancel_reason=None
    )

# 模拟 OrderStatusUpdateSchema 实例
@pytest.fixture
def mock_order_status_update_schema():
    return OrderStatusUpdateSchema(
        status="Cancelled",
        cancel_reason="Buyer changed mind"
    )


# --- 保留的测试用例 (共 10 个) ---

# create_order 方法
@pytest.mark.asyncio
async def test_create_order_success(
    orders_dal: OrdersDAL, # Update type hint
    mock_order_create_schema: OrderCreateSchema, # Use fixture
    mock_db_connection: MagicMock, # Inject mock_db_connection fixture
    mock_execute_query_func: AsyncMock # Inject execute_query mock
):
    """Test successful order creation."""
    # Arrange
    buyer_id = uuid4()

    # Simulate execute_query_func successfully executing the SP and returning the new order ID
    # Assuming SP sp_CreateOrder returns a dictionary with OrderID on success
    new_order_id = uuid4()
    mock_execute_query_func.return_value = {'OrderID': str(new_order_id)} # Simulate dictionary return with OrderID as string

    # Act
    # Call the DAL method, passing the mock connection and parameters from the schema
    returned_order_id = await orders_dal.create_order(
        mock_db_connection, # Pass mock_db_connection
        buyer_id,
        mock_order_create_schema.product_id,
        mock_order_create_schema.quantity,
        mock_order_create_schema.shipping_address,
        mock_order_create_schema.contact_phone
    )

    # Assert that the method returned the expected UUID
    assert isinstance(returned_order_id, UUID)
    assert returned_order_id == new_order_id

    # Verify the injected execute_query_func was called with the correct parameters
    mock_execute_query_func.assert_called_once_with(
        mock_db_connection, # Verify conn is passed
        "{CALL sp_CreateOrder (?, ?, ?, ?, ?)}", # Updated SQL format
        (
            str(buyer_id), # Pass UUID as string
            str(mock_order_create_schema.product_id), # Pass UUID as string
            mock_order_create_schema.quantity,
            mock_order_create_schema.shipping_address,
            mock_order_create_schema.contact_phone
        ),
        fetchone=True # Assuming SP returns a single row result
    )

@pytest.mark.asyncio
async def test_create_order_db_error(
    orders_dal: OrdersDAL, # Update type hint
    mock_order_create_schema: OrderCreateSchema, # Use fixture
    mock_db_connection: MagicMock, # Inject mock_db_connection fixture
    mock_execute_query_func: AsyncMock # Inject execute_query mock
):
    """Test order creation failing due to a database error."""
    # Arrange
    buyer_id = uuid4()

    # Simulate execute_query_func raising a pyodbc error
    mock_execute_query_func.side_effect = pyodbc.Error("Database connection failed")

    # Act & Assert
    # Expecting DALError with a specific message
    with pytest.raises(DALError, match="Error creating order: Database connection failed"):
        await orders_dal.create_order(
             mock_db_connection, # Pass mock_db_connection
             buyer_id,
             mock_order_create_schema.product_id,
             mock_order_create_schema.quantity,
             mock_order_create_schema.shipping_address,
             mock_order_create_schema.contact_phone
         )

    # Verify the injected execute_query_func was called with the correct parameters
    mock_execute_query_func.assert_called_once_with(
        mock_db_connection, # Verify conn is passed
        "{CALL sp_CreateOrder (?, ?, ?, ?, ?)}", # Updated SQL format
        (
            str(buyer_id), # Pass UUID as string
            str(mock_order_create_schema.product_id), # Pass UUID as string
            mock_order_create_schema.quantity,
            mock_order_create_schema.shipping_address,
            mock_order_create_schema.contact_phone
        ),
        fetchone=True # Assuming SP returns a single row result
    )

# get_order_by_id 方法
@pytest.mark.asyncio
async def test_get_order_by_id_found(
    orders_dal: OrdersDAL, # Update type hint
    mock_order_response_schema: OrderResponseSchema, # Use fixture
    mock_db_connection: MagicMock, # Inject mock_db_connection fixture
    mock_execute_query_func: AsyncMock # Inject execute_query mock
):
    """Test fetching an order by ID when the order exists."""
    # Arrange
    order_id = mock_order_response_schema.order_id

    # Simulate execute_query_func returning the order data as a dictionary
    # Assuming SP sp_GetOrderByID returns a single row dictionary
    mock_dal_return_data = {
        'OrderID': str(order_id),
        'SellerID': str(mock_order_response_schema.seller_id),
        'BuyerID': str(mock_order_response_schema.buyer_id),
        'ProductID': str(mock_order_response_schema.product_id),
        'Quantity': mock_order_response_schema.quantity,
        'ShippingAddress': mock_order_response_schema.shipping_address,
        'ContactPhone': mock_order_response_schema.contact_phone,
        'TotalPrice': float(mock_order_response_schema.total_price), # Ensure float
        'Status': mock_order_response_schema.status,
        'CreatedAt': mock_order_response_schema.created_at.replace(tzinfo=None), # Remove timezone for comparison if DAL doesn't handle it
        'UpdatedAt': mock_order_response_schema.updated_at.replace(tzinfo=None), # Remove timezone for comparison
        'CompleteTime': None, # Or a datetime object if applicable
        'CancelTime': None, # Or a datetime object if applicable
        'CancelReason': None # Or a string if applicable
    }
    mock_execute_query_func.return_value = mock_dal_return_data # Simulate dictionary return

    # Act
    # Call the DAL method, passing the mock connection and order ID
    order = await orders_dal.get_order_by_id(mock_db_connection, order_id) # Pass mock_db_connection

    # Assert that the method returned the expected dictionary
    assert order == mock_dal_return_data

    # Verify the injected execute_query_func was called with the correct parameters
    mock_execute_query_func.assert_called_once_with(
        mock_db_connection, # Verify conn is passed
        "{CALL sp_GetOrderById (?)}", # Corrected SP name
        (order_id,), # Pass UUID object directly
        fetchone=True # Assuming SP returns a single row result
    )

@pytest.mark.asyncio
async def test_get_order_by_id_not_found(
    orders_dal: OrdersDAL, # Update type hint
    mock_db_connection: MagicMock, # Inject mock_db_connection fixture
    mock_execute_query_func: AsyncMock # Inject execute_query mock
):
    """Test fetching an order by ID when the order does not exist."""
    # Arrange
    order_id = uuid4()

    # Simulate execute_query_func returning None (no order found)
    mock_execute_query_func.return_value = None

    # Act
    # Call the DAL method, passing the mock connection and order ID
    order = await orders_dal.get_order_by_id(mock_db_connection, order_id) # Pass mock_db_connection

    # Assert that the method returned None
    assert order is None

    # Verify the injected execute_query_func was called with the correct parameters
    mock_execute_query_func.assert_called_once_with(
        mock_db_connection, # Verify conn is passed
        "{CALL sp_GetOrderById (?)}", # Corrected SP name
        (order_id,), # Pass UUID object directly
        fetchone=True # Assuming SP returns a single row result
    )

@pytest.mark.asyncio
async def test_get_order_by_id_db_error(
    orders_dal: OrdersDAL,
    mock_db_connection: MagicMock,
    mock_execute_query_func: AsyncMock
):
    """Test fetching an order by ID failing due to a database error."""
    order_id = uuid4()
    error_msg = "[SQLSTATE 08S01] DB connection error"
    mock_execute_query_func.side_effect = pyodbc.Error(error_msg)

    with pytest.raises(DALError) as excinfo:
        await orders_dal.get_order_by_id(mock_db_connection, order_id)
    assert "数据库操作失败" in str(excinfo.value)
    mock_execute_query_func.assert_called_once_with(
        mock_db_connection,
        "{CALL sp_GetOrderById (?)}",
        (str(order_id),), # Ensure UUID is converted to string for DAL call
        fetchone=True
    )

# get_orders_by_user 方法
@pytest.mark.asyncio
async def test_get_orders_by_user_buyer_found(
    orders_dal: OrdersDAL, # Update type hint
    mock_order_response_schema: OrderResponseSchema, # Use fixture
    mock_db_connection: MagicMock, # Inject mock_db_connection fixture
    mock_execute_query_func: AsyncMock # Inject execute_query mock
):
    """Test fetching orders by buyer ID when orders exist."""
    # Arrange
    user_id = mock_order_response_schema.buyer_id
    is_seller = False

    # Simulate execute_query_func returning a list of order dictionaries
    mock_dal_return_value = [
        {
            'OrderID': str(uuid4()),
            'SellerID': str(uuid4()),
            'BuyerID': str(user_id),
            'ProductID': str(uuid4()),
            'Quantity': 1,
            'ShippingAddress': 'Addr1',
            'ContactPhone': '111',
            'TotalPrice': 10.00,
            'Status': 'Pending',
            'CreatedAt': datetime.now(timezone.utc).replace(tzinfo=None),
            'UpdatedAt': datetime.now(timezone.utc).replace(tzinfo=None),
            'CompleteTime': None,
            'CancelTime': None,
            'CancelReason': None
        },
        {
            'OrderID': str(uuid4()),
            'SellerID': str(uuid4()),
            'BuyerID': str(user_id),
            'ProductID': str(uuid4()),
            'Quantity': 3,
            'ShippingAddress': 'Addr2',
            'ContactPhone': '222',
            'TotalPrice': 30.00,
            'Status': 'Completed',
            'CreatedAt': datetime.now(timezone.utc).replace(tzinfo=None),
            'UpdatedAt': datetime.now(timezone.utc).replace(tzinfo=None),
            'CompleteTime': datetime.now(timezone.utc).replace(tzinfo=None),
            'CancelTime': None,
            'CancelReason': None
        }
    ]
    mock_execute_query_func.return_value = mock_dal_return_value # Simulate list of dictionaries return

    # Act
    # Call the DAL method, passing the mock connection and parameters
    orders = await orders_dal.get_orders_by_user(mock_db_connection, user_id, is_seller) # Pass mock_db_connection

    # Assert that the method returned the expected list of dictionaries
    assert orders == mock_dal_return_value

    # Verify the injected execute_query_func was called with the correct parameters
    mock_execute_query_func.assert_called_once_with(
        mock_db_connection, # Verify conn is passed
        "{CALL sp_GetOrdersByUser (?, ?, ?, ?, ?)}", # Updated SQL format
        (
            user_id, # Pass UUID object directly
            is_seller,
            None, # Default status is None
            1, # Default page_number is 1
            10 # Default page_size is 10
        ),
        fetchall=True # Assuming SP returns multiple rows
    )

@pytest.mark.asyncio
async def test_get_orders_by_user_seller_found(
    orders_dal: OrdersDAL,
    mock_db_connection: MagicMock,
    mock_execute_query_func: AsyncMock
):
    user_id = uuid4()
    mock_orders = [
        {
            "OrderID": str(uuid4()),
            "SellerID": str(user_id),
            "BuyerID": str(uuid4()),
            "ProductID": str(uuid4()),
            "Quantity": 1,
            "ShippingAddress": "123 Seller St",
            "ContactPhone": "555-SELL",
            "TotalPrice": 200.0,
            "Status": "Confirmed",
            "CreatedAt": datetime.now(timezone.utc).isoformat(),
            "UpdatedAt": datetime.now(timezone.utc).isoformat(),
            "CompleteTime": None,
            "CancelTime": None,
            "CancelReason": None
        }
    ]
    mock_execute_query_func.return_value = mock_orders

    orders = await orders_dal.get_orders_by_user(
        mock_db_connection, user_id, is_seller=True, status="Confirmed", page_number=1, page_size=10
    )

    assert orders == mock_orders
    mock_execute_query_func.assert_called_once_with(
        mock_db_connection,
        "{CALL sp_GetOrdersByUser (?, ?, ?, ?, ?)}",
        (str(user_id), True, "Confirmed", 1, 10),
        fetchall=True
    )

@pytest.mark.asyncio
async def test_get_orders_by_user_seller_not_found(
    orders_dal: OrdersDAL,
    mock_db_connection: MagicMock,
    mock_execute_query_func: AsyncMock
):
    user_id = uuid4()
    mock_execute_query_func.return_value = [] # No orders found

    orders = await orders_dal.get_orders_by_user(
        mock_db_connection, user_id, is_seller=True, status="Pending", page_number=1, page_size=10
    )

    assert orders == []
    mock_execute_query_func.assert_called_once_with(
        mock_db_connection,
        "{CALL sp_GetOrdersByUser (?, ?, ?, ?, ?)}",
        (str(user_id), True, "Pending", 1, 10),
        fetchall=True
    )

@pytest.mark.asyncio
async def test_get_orders_by_user_seller_db_error(
    orders_dal: OrdersDAL,
    mock_db_connection: MagicMock,
    mock_execute_query_func: AsyncMock
):
    user_id = uuid4()
    error_msg = "[SQLSTATE 08S01] Another DB error for get_orders_by_user"
    mock_execute_query_func.side_effect = pyodbc.Error(error_msg)

    with pytest.raises(DALError) as excinfo:
        await orders_dal.get_orders_by_user(
            mock_db_connection, user_id, is_seller=True, status="Confirmed", page_number=1, page_size=10
        )
    assert "数据库操作失败" in str(excinfo.value)
    mock_execute_query_func.assert_called_once()

# update_order_status 方法 (涵盖 confirm, complete)
# @pytest.mark.asyncio
# async def test_update_order_status_success(orders_dal):
#     # 模拟 execute_non_query 成功执行，返回影响行数
#     with patch('app.dal.base.execute_non_query', new_callable=AsyncMock) as mock_execute_non_query:
#         mock_execute_non_query.return_value = 1
#         order_id = uuid4()
#         status_update_schema = OrderStatusUpdateSchema(status="confirmed")
#         rows_affected = await orders_dal.update_order_status(order_id, status_update_schema)
#         assert rows_affected == 1
#         mock_execute_non_query.assert_called_once()

# @pytest.mark.asyncio
# async def test_update_order_status_not_found(orders_dal):
#     # 模拟 execute_non_query 影响0行
#     with patch('app.dal.base.execute_non_query', new_callable=AsyncMock) as mock_execute_non_query:
#         mock_execute_non_query.return_value = 0
#         order_id = uuid4()
#         status_update_schema = OrderStatusUpdateSchema(status="completed")
#         rows_affected = await orders_dal.update_order_status(order_id, status_update_schema)
#         assert rows_affected == 0
#         mock_execute_non_query.assert_called_once()

# cancel_order 方法
@pytest.mark.asyncio
async def test_cancel_order_success(
    orders_dal: OrdersDAL, # Update type hint
    mock_order_status_update_schema: OrderStatusUpdateSchema, # Use fixture
    mock_db_connection: MagicMock, # Inject mock_db_connection fixture
    mock_execute_query_func: AsyncMock # Inject execute_query mock
):
    """Test successful order cancellation."""
    # Arrange
    order_id = uuid4()
    user_id = uuid4()
    cancel_reason = mock_order_status_update_schema.cancel_reason

    # Simulate execute_query_func returning success indicator (e.g., OperationResultCode 0)
    # Assuming SP sp_CancelOrder returns a dictionary like {'OperationResultCode': 0, '': 'Order cancelled successfully.'}
    mock_execute_query_func.return_value = {'OperationResultCode': 0, '': 'Order cancelled successfully.'} # Simulate success dictionary

    # Act
    # Call the DAL method, passing the mock connection and parameters
    success = await orders_dal.cancel_order(
        mock_db_connection, # Pass mock_db_connection
        order_id,
        user_id,
        cancel_reason
    )

    # Assert that the method returned True
    assert success is True

    # Verify the injected execute_query_func was called with the correct parameters
    mock_execute_query_func.assert_called_once_with(
        mock_db_connection, # Verify conn is passed
        "{CALL sp_CancelOrder(?, ?, ?)}",
        (order_id, user_id, cancel_reason), # Pass UUID objects directly
        fetchone=True # Assuming SP returns a single row result
    )

@pytest.mark.asyncio
async def test_cancel_order_not_found(
    orders_dal: OrdersDAL, # Update type hint
    mock_order_status_update_schema: OrderStatusUpdateSchema, # Use fixture
    mock_db_connection: MagicMock, # Inject mock_db_connection fixture
    mock_execute_query_func: AsyncMock # Inject execute_query mock
):
    """Test order cancellation when the order does not exist or doesn't belong to the user."""
    # Arrange
    order_id = uuid4()
    user_id = uuid4()
    cancel_reason = mock_order_status_update_schema.cancel_reason

    # Simulate execute_query_func returning not found error (e.g., OperationResultCode -1)
    mock_execute_query_func.return_value = {'OperationResultCode': -1, '': 'Order not found or unauthorized.'} # Simulate error dictionary

    # Act & Assert: Expecting NotFoundError (as per the DAL's error mapping) with a specific message.
    with pytest.raises(NotFoundError, match=f"Order with ID {order_id} not found for cancellation."):
         await orders_dal.cancel_order(
              mock_db_connection, # Pass mock_db_connection
              order_id,
              user_id,
              cancel_reason
          )

    # Verify the injected execute_query_func was called with the correct parameters
    mock_execute_query_func.assert_called_once_with(
        mock_db_connection, # Verify conn is passed
        "{CALL sp_CancelOrder(?, ?, ?)}",
        (order_id, user_id, cancel_reason), # Pass UUID objects directly
        fetchone=True
    )

@pytest.mark.asyncio
async def test_cancel_order_db_error(
    orders_dal: OrdersDAL, # Update type hint
    mock_order_status_update_schema: OrderStatusUpdateSchema, # Use fixture
    mock_db_connection: MagicMock, # Inject mock_db_connection fixture
    mock_execute_query_func: AsyncMock # Inject execute_query mock
):
    """Test order cancellation failing due to a database error."""
    # Arrange
    order_id = uuid4()
    user_id = uuid4()
    cancel_reason = mock_order_status_update_schema.cancel_reason

    # Simulate execute_query_func raising a pyodbc error
    mock_execute_query_func.side_effect = pyodbc.Error("Database connection failed")

    # Act & Assert
    # Expecting DALError with a specific message
    with pytest.raises(DALError, match="Error cancelling order: Database connection failed"):
        await orders_dal.cancel_order(
             mock_db_connection, # Pass mock_db_connection
             order_id,
             user_id,
             cancel_reason
         )

    # Verify the injected execute_query_func was called with the correct parameters
    mock_execute_query_func.assert_called_once_with(
        mock_db_connection, # Verify conn is passed
        "{CALL sp_CancelOrder(?, ?, ?)}",
        (order_id, user_id, cancel_reason), # Pass UUID objects directly
        fetchone=True
    )

# delete_order 方法 (已移除，因为 OrdersDAL 中没有 delete_order 方法，改为测试 complete_order)
@pytest.mark.asyncio
async def test_complete_order_success(
    orders_dal: OrdersDAL,
    mock_db_connection: MagicMock,
    mock_execute_query_func: AsyncMock
):
    order_id = uuid4()
    actor_id = uuid4() # Could be buyer or admin
    mock_execute_query_func.return_value = None

    await orders_dal.complete_order(mock_db_connection, order_id, actor_id)

    mock_execute_query_func.assert_called_once_with(
        mock_db_connection,
        "{CALL sp_CompleteOrder (?, ?)}",
        (str(order_id), str(actor_id)),
        fetchone=False
    )

@pytest.mark.asyncio
async def test_complete_order_not_found(
    orders_dal: OrdersDAL,
    mock_db_connection: MagicMock,
    mock_execute_query_func: AsyncMock
):
    order_id = uuid4()
    actor_id = uuid4()
    error_msg = "[SQLSTATE 50006] 订单不存在"
    mock_execute_query_func.side_effect = pyodbc.Error(error_msg)

    with pytest.raises(NotFoundError) as excinfo:
        await orders_dal.complete_order(mock_db_connection, order_id, actor_id)
    assert error_msg in str(excinfo.value)
    mock_execute_query_func.assert_called_once()

@pytest.mark.asyncio
async def test_complete_order_forbidden(
    orders_dal: OrdersDAL,
    mock_db_connection: MagicMock,
    mock_execute_query_func: AsyncMock
):
    order_id = uuid4()
    actor_id = uuid4()
    error_msg = "[SQLSTATE 50007] 您无权完成此订单"
    mock_execute_query_func.side_effect = pyodbc.Error(error_msg)

    with pytest.raises(ForbiddenError) as excinfo:
        await orders_dal.complete_order(mock_db_connection, order_id, actor_id)
    assert error_msg in str(excinfo.value)
    mock_execute_query_func.assert_called_once()

@pytest.mark.asyncio
async def test_complete_order_invalid_status(
    orders_dal: OrdersDAL,
    mock_db_connection: MagicMock,
    mock_execute_query_func: AsyncMock
):
    order_id = uuid4()
    actor_id = uuid4()
    error_msg = "[SQLSTATE 50008] 订单状态不正确"
    mock_execute_query_func.side_effect = pyodbc.Error(error_msg)

    with pytest.raises(IntegrityError) as excinfo:
        await orders_dal.complete_order(mock_db_connection, order_id, actor_id)
    assert error_msg in str(excinfo.value)
    mock_execute_query_func.assert_called_once()

@pytest.mark.asyncio
async def test_complete_order_db_error(
    orders_dal: OrdersDAL,
    mock_db_connection: MagicMock,
    mock_execute_query_func: AsyncMock
):
    order_id = uuid4()
    actor_id = uuid4()
    error_msg = "[SQLSTATE 08S01] General DB error"
    mock_execute_query_func.side_effect = pyodbc.Error(error_msg)

    with pytest.raises(DALError) as excinfo:
        await orders_dal.complete_order(mock_db_connection, order_id, actor_id)
    assert "数据库操作失败" in str(excinfo.value)
    mock_execute_query_func.assert_called_once()

# Add tests for get_orders_by_user for seller
@pytest.mark.asyncio
async def test_get_orders_by_user_seller_found(
    orders_dal: OrdersDAL,
    mock_db_connection: MagicMock,
    mock_execute_query_func: AsyncMock
):
    user_id = uuid4()
    mock_orders = [
        {
            "OrderID": str(uuid4()),
            "SellerID": str(user_id),
            "BuyerID": str(uuid4()),
            "ProductID": str(uuid4()),
            "Quantity": 1,
            "ShippingAddress": "123 Seller St",
            "ContactPhone": "555-SELL",
            "TotalPrice": 200.0,
            "Status": "Confirmed",
            "CreatedAt": datetime.now(timezone.utc).isoformat(),
            "UpdatedAt": datetime.now(timezone.utc).isoformat(),
            "CompleteTime": None,
            "CancelTime": None,
            "CancelReason": None
        }
    ]
    mock_execute_query_func.return_value = mock_orders

    orders = await orders_dal.get_orders_by_user(
        mock_db_connection, user_id, is_seller=True, status="Confirmed", page_number=1, page_size=10
    )

    assert orders == mock_orders
    mock_execute_query_func.assert_called_once_with(
        mock_db_connection,
        "{CALL sp_GetOrdersByUser (?, ?, ?, ?, ?)}",
        (str(user_id), True, "Confirmed", 1, 10),
        fetchall=True
    )

@pytest.mark.asyncio
async def test_get_orders_by_user_seller_not_found(
    orders_dal: OrdersDAL,
    mock_db_connection: MagicMock,
    mock_execute_query_func: AsyncMock
):
    user_id = uuid4()
    mock_execute_query_func.return_value = [] # No orders found

    orders = await orders_dal.get_orders_by_user(
        mock_db_connection, user_id, is_seller=True, status="Pending", page_number=1, page_size=10
    )

    assert orders == []
    mock_execute_query_func.assert_called_once_with(
        mock_db_connection,
        "{CALL sp_GetOrdersByUser (?, ?, ?, ?, ?)}",
        (str(user_id), True, "Pending", 1, 10),
        fetchall=True
    )

@pytest.mark.asyncio
async def test_get_orders_by_user_seller_db_error(
    orders_dal: OrdersDAL,
    mock_db_connection: MagicMock,
    mock_execute_query_func: AsyncMock
):
    user_id = uuid4()
    error_msg = "[SQLSTATE 08S01] Another DB error for get_orders_by_user"
    mock_execute_query_func.side_effect = pyodbc.Error(error_msg)

    with pytest.raises(DALError) as excinfo:
        await orders_dal.get_orders_by_user(
            mock_db_connection, user_id, is_seller=True, status="Confirmed", page_number=1, page_size=10
        )
    assert "数据库操作失败" in str(excinfo.value)
    mock_execute_query_func.assert_called_once()

# Corrected tests with fixtures and conn
@pytest.mark.asyncio
async def test_create_order_with_minimum_quantity(orders_dal: OrdersDAL, mock_order_create_schema: OrderCreateSchema, mock_db_connection: MagicMock, mock_execute_query_func: AsyncMock):
    """测试数量为1的订单创建。"""
    buyer_id = uuid4()
    # Modify schema for this test case
    min_quantity_schema = mock_order_create_schema.model_copy(update={'quantity': 1}) # Use model_copy
    new_order_id = uuid4()
    mock_execute_query_func.return_value = {'OrderID': str(new_order_id)}

    returned_order_id = await orders_dal.create_order(
        mock_db_connection,
        buyer_id,
        min_quantity_schema.product_id,
        min_quantity_schema.quantity,
        min_quantity_schema.shipping_address,
        min_quantity_schema.contact_phone
    )

    assert isinstance(returned_order_id, UUID)
    assert returned_order_id == new_order_id

    mock_execute_query_func.assert_called_once_with(
        mock_db_connection, # Verify conn is passed
        "{CALL sp_CreateOrder (?, ?, ?, ?, ?)}", # Updated SQL format
        (
            str(buyer_id), # Pass UUID as string
            str(mock_order_create_schema.product_id), # Pass UUID as string
            mock_order_create_schema.quantity,
            mock_order_create_schema.shipping_address,
            mock_order_create_schema.contact_phone
        ),
        fetchone=True
    )

@pytest.mark.asyncio
async def test_create_order_with_large_quantity(orders_dal: OrdersDAL, mock_order_create_schema: OrderCreateSchema, mock_db_connection: MagicMock, mock_execute_query_func: AsyncMock):
    """测试数量较大的订单创建。"""
    buyer_id = uuid4()
    # Modify schema for this test case
    large_quantity_schema = mock_order_create_schema.model_copy(update={'quantity': 1000}) # Use model_copy
    new_order_id = uuid4()
    mock_execute_query_func.return_value = {'OrderID': str(new_order_id)}

    returned_order_id = await orders_dal.create_order(
        mock_db_connection,
        buyer_id,
        large_quantity_schema.product_id,
        large_quantity_schema.quantity,
        large_quantity_schema.shipping_address,
        large_quantity_schema.contact_phone
    )

    assert isinstance(returned_order_id, UUID)
    assert returned_order_id == new_order_id

    mock_execute_query_func.assert_called_once_with(
        mock_db_connection,
        "{CALL sp_CreateOrder (?, ?, ?, ?, ?)}",
        (
            str(buyer_id),
            str(large_quantity_schema.product_id),
            large_quantity_schema.quantity,
            large_quantity_schema.shipping_address,
            large_quantity_schema.contact_phone
        ),
        fetchone=True
    )

@pytest.mark.asyncio
async def test_create_order_with_zero_total_price(orders_dal: OrdersDAL, mock_order_create_schema: OrderCreateSchema, mock_db_connection: MagicMock, mock_execute_query_func: AsyncMock):
    """测试总价为0的订单创建（如果SP允许）。"""
    buyer_id = uuid4()
    # Modify schema for this test case
    zero_price_schema = mock_order_create_schema.model_copy(update={'total_price': 0.0}) # Use model_copy
    new_order_id = uuid4()
    mock_execute_query_func.return_value = {'OrderID': str(new_order_id)}

    # Assuming SP allows 0 total price, or validation is elsewhere.
    # If SP rejects, this test would need to expect an error.
    # Based on the previous error, it seems the DAL is trying to access 'OrderID' on a non-dictionary result.
    # Let's assume the SP *should* return a dict with OrderID, but previous mock was wrong or SP failed.
    # Re-simulating successful SP call returning OrderID.

    returned_order_id = await orders_dal.create_order(
        mock_db_connection,
        buyer_id,
        zero_price_schema.product_id,
        zero_price_schema.quantity,
        zero_price_schema.shipping_address,
        zero_price_schema.contact_phone
    )

    assert isinstance(returned_order_id, UUID)
    assert returned_order_id == new_order_id

    mock_execute_query_func.assert_called_once_with(
        mock_db_connection,
        "{CALL sp_CreateOrder (?, ?, ?, ?, ?)}",
        (
            str(buyer_id),
            str(zero_price_schema.product_id),
            zero_price_schema.quantity,
            zero_price_schema.shipping_address,
            zero_price_schema.contact_phone
        ),
        fetchone=True
    )

@pytest.mark.asyncio
async def test_create_order_with_negative_total_price_raises_value_error(orders_dal: OrdersDAL, mock_order_create_schema: OrderCreateSchema, mock_db_connection: MagicMock, mock_execute_query_func: AsyncMock):
    """测试总价为负数的情况，应抛出ValueError（如果SP层面检查）。"""
    buyer_id = uuid4()
    # Modify schema for this test case
    negative_price_schema = mock_order_create_schema.model_copy(update={'total_price': -10.0}) # Use model_copy

    # Simulate SP returning an error for invalid total price
    mock_execute_query_func.return_value = {'OperationResultCode': -1, '': 'Total price cannot be negative.'} # Simulate error dictionary

    with pytest.raises(DALError, match="Error creating order: Total price cannot be negative."):
        await orders_dal.create_order(
            mock_db_connection,
            buyer_id,
            negative_price_schema.product_id,
            negative_price_schema.quantity,
            negative_price_schema.shipping_address,
            negative_price_schema.contact_phone
        )
    
    mock_execute_query_func.assert_called_once_with(
        mock_db_connection,
        "{CALL sp_CreateOrder (?, ?, ?, ?, ?)}",
        (
            str(buyer_id),
            str(negative_price_schema.product_id),
            negative_price_schema.quantity,
            negative_price_schema.shipping_address,
            negative_price_schema.contact_phone
        ),
        fetchone=True
    )

@pytest.mark.asyncio
async def test_create_order_with_empty_shipping_address_raises_value_error(orders_dal: OrdersDAL, mock_order_create_schema: OrderCreateSchema, mock_db_connection: MagicMock, mock_execute_query_func: AsyncMock):
    """测试空收货地址，应抛出ValueError（如果SP层面检查）。"""
    buyer_id = uuid4()
    # Modify schema for this test case
    empty_address_schema = mock_order_create_schema.model_copy(update={'shipping_address': ""}) # Use model_copy

    # Simulate SP returning an error for empty shipping address
    mock_execute_query_func.return_value = {'OperationResultCode': -1, '': 'Shipping address cannot be empty.'} # Simulate error dictionary

    with pytest.raises(DALError, match="Error creating order: Shipping address cannot be empty."):
        await orders_dal.create_order(
            mock_db_connection,
            buyer_id,
            empty_address_schema.product_id,
            empty_address_schema.quantity,
            empty_address_schema.shipping_address,
            empty_address_schema.contact_phone
        )
    
    mock_execute_query_func.assert_called_once_with(
        mock_db_connection,
        "{CALL sp_CreateOrder (?, ?, ?, ?, ?)}",
        (
            str(buyer_id),
            str(empty_address_schema.product_id),
            empty_address_schema.quantity,
            empty_address_schema.shipping_address,
            empty_address_schema.contact_phone
        ),
        fetchone=True
    )

@pytest.mark.asyncio
async def test_create_order_with_empty_contact_phone_raises_value_error(orders_dal: OrdersDAL, mock_order_create_schema: OrderCreateSchema, mock_db_connection: MagicMock, mock_execute_query_func: AsyncMock):
    """测试空联系电话，应抛出ValueError（如果SP层面检查）。"""
    buyer_id = uuid4()
    # Modify schema for this test case
    empty_phone_schema = mock_order_create_schema.model_copy(update={'contact_phone': ""}) # Use model_copy

    # Simulate SP returning an error for empty contact phone
    mock_execute_query_func.return_value = {'OperationResultCode': -1, '': 'Contact phone cannot be empty.'} # Simulate error dictionary

    with pytest.raises(DALError, match="Error creating order: Contact phone cannot be empty."):
        await orders_dal.create_order(
            mock_db_connection,
            buyer_id,
            empty_phone_schema.product_id,
            empty_phone_schema.quantity,
            empty_phone_schema.shipping_address,
            empty_phone_schema.contact_phone
        )
    
    mock_execute_query_func.assert_called_once_with(
        mock_db_connection,
        "{CALL sp_CreateOrder (?, ?, ?, ?, ?)}",
        (
            str(buyer_id),
            str(empty_phone_schema.product_id),
            empty_phone_schema.quantity,
            empty_phone_schema.shipping_address,
            empty_phone_schema.contact_phone
        ),
        fetchone=True
    )

@pytest.mark.asyncio
async def test_create_order_with_invalid_product_id_raises_value_error(orders_dal: OrdersDAL, mock_db_connection: MagicMock, mock_execute_query_func: AsyncMock):
    """测试无效的产品ID格式，应抛出ValueError（如果DAL/SP层面检查）。"""
    buyer_id = uuid4()
    invalid_product_id_str = "not-a-uuid"
    
    # Simulate execute_query_func raising an error due to invalid parameter type for product_id
    mock_execute_query_func.side_effect = pyodbc.ProgrammingError("Invalid parameter type for product_id")

    with pytest.raises(DALError, match="Error creating order: Invalid parameter type for product_id"):
        await orders_dal.create_order(
            mock_db_connection,
            buyer_id,
            invalid_product_id_str, # Pass invalid string
            1,
            "address",
            "phone"
        )

    mock_execute_query_func.assert_called_once_with(
        mock_db_connection,
        "{CALL sp_CreateOrder (?, ?, ?, ?, ?)}",
        (
            str(buyer_id),
            invalid_product_id_str, # Assert with the invalid string passed
            1,
            "address",
            "phone"
        ),
        fetchone=True
    )

@pytest.mark.asyncio
async def test_create_order_with_invalid_buyer_id_raises_value_error(orders_dal: OrdersDAL, mock_db_connection: MagicMock, mock_execute_query_func: AsyncMock):
    """测试无效的买家ID格式，应抛出ValueError（如果DAL/SP层面检查）。"""
    invalid_buyer_id_str = "not-a-uuid"
    product_id = uuid4()

    # Simulate execute_query_func raising an error due to invalid parameter type for buyer_id
    mock_execute_query_func.side_effect = pyodbc.ProgrammingError("Invalid parameter type for buyer_id")

    with pytest.raises(DALError, match="Error creating order: Invalid parameter type for buyer_id"):
        await orders_dal.create_order(
            mock_db_connection,
            invalid_buyer_id_str, # Pass invalid string
            product_id,
            1,
            "address",
            "phone"
        )

    mock_execute_query_func.assert_called_once_with(
        mock_db_connection,
        "{CALL sp_CreateOrder (?, ?, ?, ?, ?)}",
        (
            invalid_buyer_id_str, # Assert with the invalid string passed
            str(product_id),
            1,
            "address",
            "phone"
        ),
        fetchone=True
    )

@pytest.mark.asyncio
async def test_create_order_db_connection_error(orders_dal: OrdersDAL, mock_order_create_schema: OrderCreateSchema, mock_db_connection: MagicMock, mock_execute_query_func: AsyncMock):
    """测试创建订单时发生数据库连接错误。"""
    buyer_id = uuid4()

    # Simulate execute_query_func raising a pyodbc error
    mock_execute_query_func.side_effect = pyodbc.Error("Connection refused")

    with pytest.raises(DALError, match="Error creating order: Connection refused"):
        await orders_dal.create_order(
            mock_db_connection,
            buyer_id,
            mock_order_create_schema.product_id,
            mock_order_create_schema.quantity,
            mock_order_create_schema.shipping_address,
            mock_order_create_schema.contact_phone
        )
    
    mock_execute_query_func.assert_called_once_with(
        mock_db_connection,
        "{CALL sp_CreateOrder (?, ?, ?, ?, ?)}",
        (
            str(buyer_id),
            str(mock_order_create_schema.product_id),
            mock_order_create_schema.quantity,
            mock_order_create_schema.shipping_address,
            mock_order_create_schema.contact_phone
        ),
        fetchone=True
    )

@pytest.mark.asyncio
async def test_create_order_db_insert_error(orders_dal: OrdersDAL, mock_order_create_schema: OrderCreateSchema, mock_db_connection: MagicMock, mock_execute_query_func: AsyncMock):
    """测试创建订单时发生数据库插入错误（例如，数据验证失败在SP内）。"""
    buyer_id = uuid4()

    # Simulate SP returning an error due to insert issue
    mock_execute_query_func.return_value = {'OperationResultCode': -1, '': 'Data validation failed.'} # Simulate error dictionary

    with pytest.raises(DALError, match="Error creating order: Data validation failed."):
         await orders_dal.create_order(
            mock_db_connection,
            buyer_id,
            mock_order_create_schema.product_id,
            mock_order_create_schema.quantity,
            mock_order_create_schema.shipping_address,
            mock_order_create_schema.contact_phone
        )
    
    mock_execute_query_func.assert_called_once_with(
        mock_db_connection,
        "{CALL sp_CreateOrder(?, ?, ?, ?, ?)}",
        (
            str(buyer_id),
            str(mock_order_create_schema.product_id),
            mock_order_create_schema.quantity,
            mock_order_create_schema.shipping_address,
            mock_order_create_schema.contact_phone
        ),
        fetchone=True
    )

@pytest.mark.asyncio
async def test_reject_order_success(
    orders_dal: OrdersDAL, # Update type hint
    mock_db_connection: MagicMock, # Inject mock_db_connection fixture
    mock_execute_query_func: AsyncMock # Inject execute_query mock
):
    """Test successful order rejection."""
    # Arrange
    order_id = uuid4()
    seller_id = uuid4()
    rejection_reason = "Product out of stock."

    # Simulate execute_query_func returning success indicator (e.g., OperationResultCode 0)
    # Assuming SP sp_RejectOrder returns a dictionary like {'OperationResultCode': 0, '': 'Order rejected successfully.'}
    mock_execute_query_func.return_value = {'OperationResultCode': 0, '': 'Order rejected successfully.'} # Simulate success dictionary

    # Act
    # Call the DAL method, passing the mock connection and parameters
    success = await orders_dal.reject_order(
        mock_db_connection, # Pass mock_db_connection
        order_id,
        seller_id,
        rejection_reason
    )

    # Assert that the method returned True
    assert success is True

    # Verify the injected execute_query_func was called with the correct parameters
    mock_execute_query_func.assert_called_once_with(
        mock_db_connection, # Verify conn is passed
        "{CALL sp_RejectOrder(?, ?, ?)}",
        (order_id, seller_id, rejection_reason), # Pass UUID objects directly
        fetchone=True # Assuming SP returns a single row result
    )

@pytest.mark.asyncio
async def test_reject_order_not_found(
    orders_dal: OrdersDAL, # Update type hint
    mock_db_connection: MagicMock, # Inject mock_db_connection fixture
    mock_execute_query_func: AsyncMock # Inject execute_query mock
):
    """Test order rejection when the order does not exist or unauthorized."""
    # Arrange
    order_id = uuid4()
    seller_id = uuid4()
    rejection_reason = "Not the seller."

    # Simulate execute_query_func returning not found error (e.g., OperationResultCode -1)
    mock_execute_query_func.return_value = {'OperationResultCode': -1, '': 'Order not found or unauthorized.'} # Simulate error dictionary

    # Act & Assert: Expecting NotFoundError (as per the DAL's error mapping) with a specific message.
    with pytest.raises(NotFoundError, match=f"Order with ID {order_id} not found or unauthorized for rejection."):
         await orders_dal.reject_order(
              mock_db_connection, # Pass mock_db_connection
              order_id,
              seller_id,
              rejection_reason
          )

    # Verify the injected execute_query_func was called with the correct parameters
    mock_execute_query_func.assert_called_once_with(
        mock_db_connection, # Verify conn is passed
        "{CALL sp_RejectOrder(?, ?, ?)}",
        (order_id, seller_id, rejection_reason), # Pass UUID objects directly
        fetchone=True
    )

@pytest.mark.asyncio
async def test_reject_order_db_error(
    orders_dal: OrdersDAL, # Update type hint
    mock_db_connection: MagicMock, # Inject mock_db_connection fixture
    mock_execute_query_func: AsyncMock # Inject execute_query mock
):
    """Test order rejection failing due to a database error."""
    # Arrange
    order_id = uuid4()
    seller_id = uuid4()
    rejection_reason = "DB issue."

    # Simulate execute_query_func raising a pyodbc error
    mock_execute_query_func.side_effect = pyodbc.Error("Database connection failed")

    # Act & Assert
    # Expecting DALError with a specific message
    with pytest.raises(DALError, match="Error rejecting order: Database connection failed"):
        await orders_dal.reject_order(
             mock_db_connection, # Pass mock_db_connection
             order_id,
             seller_id,
             rejection_reason
         )

    # Verify the injected execute_query_func was called with the correct parameters
    mock_execute_query_func.assert_called_once_with(
        mock_db_connection, # Verify conn is passed
        "{CALL sp_RejectOrder(?, ?, ?)}",
        (order_id, seller_id, rejection_reason), # Pass UUID objects directly
        fetchone=True
    )

@pytest.mark.asyncio
async def test_create_order_invalid_quantity(orders_dal: OrdersDAL, mock_order_create_schema: OrderCreateSchema, mock_db_connection: MagicMock, mock_execute_query_func: AsyncMock):
    """测试数量为0或负数的情况应抛出ValueError。"""
    buyer_id = uuid4()
    # Modify schema for this test case
    invalid_quantity_schema = mock_order_create_schema.model_copy(update={'quantity': 0}) # Use model_copy

    # Simulate the SP returning an error for invalid quantity
    mock_execute_query_func.side_effect = pyodbc.Error("[SQLSTATE 50003] 商品库存不足") # Simulate error from SP

    with pytest.raises(IntegrityError) as excinfo: # Expect IntegrityError for stock issues
         await orders_dal.create_order(
             mock_db_connection, # Pass mock_db_connection
             buyer_id,
             invalid_quantity_schema.product_id,
             invalid_quantity_schema.quantity,
             invalid_quantity_schema.shipping_address,
             invalid_quantity_schema.contact_phone
         )
    assert "商品库存不足" in str(excinfo.value)

    mock_execute_query_func.assert_called_once_with(
        mock_db_connection,
        "{CALL sp_CreateOrder (?, ?, ?, ?, ?)}",
        (
            str(buyer_id),
            str(invalid_quantity_schema.product_id),
            invalid_quantity_schema.quantity,
            invalid_quantity_schema.shipping_address,
            invalid_quantity_schema.contact_phone
        ),
        fetchone=True
    )