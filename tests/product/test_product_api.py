import pytest
from fastapi import status, HTTPException
from fastapi.testclient import TestClient
from datetime import datetime, timedelta
from uuid import uuid4, uuid5, UUID
from app.main import app
from app.services.product_service import ProductService
from app.schemas.product import ProductCreate, ProductUpdate, Product
from unittest.mock import AsyncMock, MagicMock, ANY
from fastapi import Depends
from app.dal.connection import get_db_connection
from app.dependencies import (
    get_product_service as get_product_service_dependency,
    get_current_user as get_current_user_dependency,
    get_current_active_admin_user as get_current_active_admin_user_dependency,
    get_current_authenticated_user as get_current_authenticated_user_dependency
)
from app.schemas.user_schemas import UserResponseSchema
import uuid
from app.exceptions import NotFoundError, IntegrityError, DALError, PermissionError # Import specific exceptions

# Mock data for products
mock_products_all = [
    {
        "商品ID": "a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11",
        "商品名称": "测试手机",
        "商品描述": "一个很棒的测试手机",
        "库存": 50,
        "价格": 5999.0,
        "发布时间": "2023-01-01T10:00:00.000000",
        "商品状态": "Active",
        "发布者用户名": "user1",
        "商品类别": "Electronics",
        "主图URL": "http://example.com/test_phone.jpg",
        "images": [
            {"image_url": "http://example.com/test_phone_1.jpg", "sort_order": 0, "upload_time": datetime.now().isoformat()},
            {"image_url": "http://example.com/test_phone_2.jpg", "sort_order": 1, "upload_time": datetime.now().isoformat()}
        ]
    },
    {
        "商品ID": "b0eebc99-9c0b-4ef8-bb6d-6bb9bd380a12",
        "商品名称": "旧笔记本",
        "商品描述": "一台二手的旧笔记本，性能良好。",
        "库存": 5,
        "价格": 2500.0,
        "发布时间": "2023-01-02T10:00:00.000000",
        "商品状态": "PendingReview",
        "发布者用户名": "user2",
        "商品类别": "Electronics",
        "主图URL": "http://example.com/old_laptop.jpg",
        "images": []
    },
    {
        "商品ID": "c0eebc99-9c0b-4ef8-bb6d-6bb9bd380a13",
        "商品名称": "机械键盘",
        "商品描述": "手感极佳的机械键盘。",
        "库存": 20,
        "价格": 450.0,
        "发布时间": "2023-01-03T10:00:00.000000",
        "商品状态": "Active",
        "发布者用户名": "user1",
        "商品类别": "Accessories",
        "主图URL": "http://example.com/keyboard.jpg",
        "images": []
    },
    {
        "商品ID": "d0eebc99-9c0b-4ef8-bb6d-6bb9bd380a14",
        "商品名称": "智能手表",
        "商品描述": "最新款智能手表，功能齐全。",
        "库存": 15,
        "价格": 1200.0,
        "发布时间": "2023-01-04T10:00:00.000000",
        "商品状态": "Active",
        "发布者用户名": "user3",
        "商品类别": "Wearables",
        "主图URL": "http://example.com/smartwatch.jpg",
        "images": []
    },
    {
        "商品ID": "e0eebc99-9c0b-4ef8-bb6d-6bb9bd380a15",
        "商品名称": "复古相机",
        "商品描述": "一台保存完好的复古胶片相机。",
        "库存": 2,
        "价格": 800.0,
        "发布时间": "2023-01-05T10:00:00.000000",
        "商品状态": "Rejected",
        "发布者用户名": "user4",
        "商品类别": "Photography",
        "主图URL": "http://example.com/vintage_camera.jpg",
        "images": []
    }
]

# Helper function to create mock ProductResponseSchema objects
def create_mock_product_response_schema(product_id: UUID, name: str, owner_id: UUID) -> Product:
    return Product(
        product_id=product_id,
        name=name,
        description="A test product description",
        price=100.0,
        quantity=5,
        status="Active",
        owner_id=owner_id,
        category_name="TestCategory",
        post_time=datetime.now(),
        images=[]
    )

@pytest.fixture(scope="function")
def mock_product_service(mocker):
    return mocker.AsyncMock(spec=ProductService)

@pytest.fixture(scope="function")
def mock_db_connection(mocker):
    # Mock the database connection object
    return MagicMock()

# Define consistent UUIDs for testing
test_user_uuid = UUID("00000000-0000-0000-0000-000000000001")
test_admin_uuid = UUID("00000000-0000-0000-0000-000000000002")
test_authenticated_user_uuid = UUID("00000000-0000-0000-0000-000000000003")

# Mock dependencies for authentication
async def mock_get_current_user_override():
    # Return a UserResponseSchema instance for a regular user
    return UserResponseSchema(
        user_id=test_user_uuid,
        username="testuser",
        email="test@example.com",
        status="Active",
        credit=100,
        is_staff=False,
        is_super_admin=False,
        is_verified=True,
        major="Computer Science",
        avatar_url=None,
        bio="Test bio",
        phone_number="1234567890",
        join_time=datetime.now()
    )

async def mock_get_current_active_admin_user_override():
    # Return a UserResponseSchema instance for an admin user
    return UserResponseSchema(
        user_id=test_admin_uuid,
        username="adminuser",
        email="admin@example.com",
        status="Active",
        credit=1000,
        is_staff=True,
        is_super_admin=True,
        is_verified=True,
        major="Management",
        avatar_url=None,
        bio="Admin bio",
        phone_number="0987654321",
        join_time=datetime.now()
    )

async def mock_get_current_authenticated_user_override():
    # This one already returns UserResponseSchema, ensure consistency
    return UserResponseSchema(
        user_id=test_authenticated_user_uuid,
        username="testuser",
        email="test@example.com",
        status="Active",
        credit=100,
        is_staff=False,
        is_super_admin=False,
        is_verified=True,
        major="Computer Science",
        avatar_url=None,
        bio="Test bio",
        phone_number="1234567890",
        join_time=datetime.now()
    )

@pytest.fixture(scope="function")
def client(
    mock_product_service: AsyncMock,
    mock_db_connection: MagicMock
):
    # Override the actual get_db_connection dependency with our mock
    app.dependency_overrides[get_product_service_dependency] = lambda: mock_product_service

    async def override_get_db_connection_async():
        yield mock_db_connection

    app.dependency_overrides[get_db_connection] = override_get_db_connection_async
    app.dependency_overrides[get_current_user_dependency] = mock_get_current_user_override
    app.dependency_overrides[get_current_active_admin_user_dependency] = mock_get_current_active_admin_user_override
    app.dependency_overrides[get_current_authenticated_user_dependency] = mock_get_current_authenticated_user_override

    with TestClient(app) as client:
        yield client

    # Clean up dependency overrides after the test
    app.dependency_overrides = {}

@pytest.mark.asyncio
async def test_create_product(client: TestClient, mock_product_service: AsyncMock):
    # Arrange
    # No need to create users directly, authentication is mocked.
    # The mock_get_current_authenticated_user_override provides the authenticated user's info.

    # Use the test_auth_user_id from the client fixture for simulating the current user
    test_owner_id = test_authenticated_user_uuid # This is already a UUID object from client fixture

    # 构造商品数据
    product_data = ProductCreate(
        category_name="电子产品",
        product_name="测试手机",
        description="测试描述",
        quantity=10,
        price=5999.0,
        image_urls=["https://example.com/image.jpg"]
    )

    # Mock the service layer call
    # The service's create_product method is expected to return None on success based on its signature.
    # The API router is responsible for returning the success message.
    mock_product_service.create_product.return_value = uuid4() # Simulate successful creation, returning a UUID

    # Act
    # Send request using the client with mocked dependencies
    response = client.post(
        "/api/v1/products", # Modified: Added /api/v1 prefix
        json=product_data.model_dump(), # Use model_dump for Pydantic v2
        # Authentication header is implicitly handled by the mocked get_current_authenticated_user
        # but including it in the test makes it clearer that this endpoint requires auth.
        # However, since the dependency override bypasses the actual token check,
        # we don't strictly need the header here for the test to pass based on mocking.
        # Let's keep it to reflect the actual API usage.
        headers={
            "Authorization": "Bearer fake-token" # Use a placeholder token since it's mocked
        }
    )

    # Assert
    assert response.status_code == status.HTTP_201_CREATED # Expect 201 Created for resource creation
    assert response.json()["message"] == "商品创建成功"

    # Assert that the service method was called with the correct arguments
    # The service's create_product expects conn, owner_id (UUID), category_name, product_name, description, quantity, price, image_urls
    # We need to capture the call arguments and check them.

    # The mock_product_service.create_product was called within the API endpoint.
    # We check if it was called once.
    mock_product_service.create_product.assert_called_once()

    # Check the arguments it was called with.
    # The first argument is the database connection (mocked).
    # The subsequent arguments are based on the ProductCreate schema and the owner_id from the mocked dependency.
    # Get the call arguments
    args, kwargs = mock_product_service.create_product.call_args

    # Check the arguments
    # arg[0] is the mocked connection
    # arg[1] should be the owner_id (UUID)
    # arg[2] should be category_name
    # arg[3] should be product_name
    # arg[4] should be description
    # arg[5] should be quantity
    # arg[6] should be price
    # arg[7] should be image_urls (list of strings)

    assert args[1] == test_owner_id # Check owner_id, now a UUID object
    assert args[2] == product_data.category_name
    assert args[3] == product_data.product_name
    assert args[4] == product_data.description
    assert args[5] == product_data.quantity
    assert args[6] == product_data.price
    assert args[7] == product_data.image_urls

@pytest.mark.asyncio
async def test_batch_activate_products(client: TestClient, mock_product_service: AsyncMock):
    # Arrange
    # No need to create users or products directly, authentication is mocked.
    # The mock_get_current_active_admin_user_override provides the authenticated admin user's info.

    # Use the test_admin_user_id from the client fixture for simulating the current admin
    admin_id = test_admin_uuid

    # Generate some fake product IDs for the batch operation
    product_ids_api = [str(uuid4()) for _ in range(3)] # For API request (list of string UUIDs)
    product_ids_service = [UUID(pid) for pid in product_ids_api] # For service call (list of UUID objects)
    
    # Mock the service layer call for batch activation
    # The service's batch_activate_products method is expected to return the count of successfully activated products.
    mock_product_service.batch_activate_products.return_value = len(product_ids_service) # Simulate successful activation
    
    # Act
    # Send request using the client with mocked dependencies
    response = client.post(
        "/api/v1/products/batch/activate", # Modified: Added /api/v1 prefix
        json={
            "product_ids": product_ids_api, # Use product_ids_api for payload (now string UUIDs)
            "new_status": "Active", # Modified: Changed to new_status
            "reason": None  # Activation doesn't require a reason
        },
        headers={
            "Authorization": "Bearer fake-admin-token" # Placeholder token for clarity
        }
    )
    
    # Assert
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["message"] == f"成功激活 {len(product_ids_service)} 件商品" # Modified: Changed to check 'message'

    # Assert that the service method was called with the correct arguments
    # The service's batch_activate_products expects conn, product_ids (List[UUID]), admin_id (UUID)

    mock_product_service.batch_activate_products.assert_called_once()

    # Check the arguments
    args, kwargs = mock_product_service.batch_activate_products.call_args

    # arg[0] is the mocked connection
    # arg[1] should be product_ids (List[UUID])
    # arg[2] should be admin_id (UUID)

    assert args[1] == product_ids_service # Check product_ids (list of UUID objects)
    assert args[2] == admin_id # Modified: admin_id is already an int

@pytest.mark.asyncio
async def test_add_favorite(client: TestClient, mock_product_service: AsyncMock):
    # Arrange
    # No need to create users or products directly, authentication is mocked.
    # The mock_get_current_authenticated_user_override provides the authenticated user's info.

    # Use the test_auth_user_id from the client fixture for simulating the current user
    test_user_id = test_authenticated_user_uuid

    # Generate a fake product ID
    fake_product_id_api = str(uuid4()) # For API request (string UUID)
    fake_product_id_service = UUID(fake_product_id_api) # For service call (UUID object)

    # Mock the service layer call for adding a favorite
    # The service's add_favorite method is expected to return None on success.
    mock_product_service.add_favorite.return_value = None # Simulate successful addition

    # Act
    # Send request using the client with mocked dependencies
    response = client.post(
        f"/api/v1/products/{fake_product_id_api}/favorite", # Modified: Added /api/v1 prefix
        headers={
            "Authorization": "Bearer fake-token" # Placeholder token for clarity
        }
    )

    # Assert
    assert response.status_code == status.HTTP_201_CREATED # Expect 201 Created for resource creation
    assert response.json()["message"] == "商品收藏成功"

    # Assert that the service method was called with the correct arguments
    # The service's add_favorite expects conn, user_id (UUID), product_id (UUID)
    mock_product_service.add_favorite.assert_called_once_with(
        ANY,
        test_user_id, # Ensure user_id is passed as UUID
        fake_product_id_service # Ensure product_id is passed as UUID
    )

@pytest.mark.asyncio
async def test_get_product_list(client: TestClient, mock_product_service: AsyncMock):
    # Arrange
    # No need to create users or products directly, data is mocked.

    # Define mock product data that the service should return
    # This data should match the structure returned by the sp_GetProductList and sp_GetProductDetail (for images)
    # and should use the Chinese aliases defined in the stored procedures.
    mock_products = [
        {
            "商品ID": mock_products_all[0]["商品ID"],
            "商品名称": "测试商品A",
            "商品描述": "描述A",
            "库存": 10,
            "价格": 100.0,
            "发布时间": datetime.now().isoformat(),
            "商品状态": "Active",
            "发布者用户名": "testuser1",
            "商品类别": "Electronics",
            "主图URL": "/uploads/imageA.jpg",
            "images": []
        },
        {
            "商品ID": mock_products_all[1]["商品ID"],
            "商品名称": "测试商品B",
            "商品描述": "描述B",
            "库存": 5,
            "价格": 200.0,
            "发布时间": datetime.now().isoformat(),
            "商品状态": "PendingReview",
            "发布者用户名": "testuser2",
            "商品类别": "Books",
            "主图URL": "/uploads/imageB.jpg",
            "images": []
        }
    ]
    mock_product_service.get_product_list.return_value = mock_products

    # Act
    response = client.get("/api/v1/products", params={
        "category_name": "Electronics", # Modified: Pass string category name
        "status": "Active",
        "keyword": "测试",
        "min_price": 50.0,
        "max_price": 250.0,
        "order_by": "Price",
        "page_number": 1,
        "page_size": 10
    })

    # Assert
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == mock_products

    # Assert that the service method was called with the correct arguments
    mock_product_service.get_product_list.assert_called_once_with(
        ANY,
        "Electronics", # Modified: Assert with string category name
        "Active",
        "测试",
        50.0,
        250.0,
        "Price",
        1,
        10
    )

@pytest.mark.asyncio
async def test_get_product_detail(client: TestClient, mock_product_service: AsyncMock):
    # Arrange
    # No need to create a user or product directly, data is mocked.

    # Generate a fake product ID for the test
    test_product_id = mock_products_all[0]["商品ID"] # Use string UUID for API request

    mock_product_data = {
        "商品ID": mock_products_all[0]["商品ID"],
        "商品名称": "测试手机",
        "商品描述": "一个很棒的测试手机",
        "库存": 50,
        "价格": 5999.0,
        "发布时间": datetime.now().isoformat(),
        "商品状态": "Active",
        "发布者用户名": "testuser",
        "商品类别": "Electronics",
        "主图URL": "http://example.com/test_phone.jpg",
        "images": [
            {"image_url": "http://example.com/test_phone_1.jpg", "sort_order": 0, "upload_time": datetime.now().isoformat()},
            {"image_url": "http://example.com/test_phone_2.jpg", "sort_order": 1, "upload_time": datetime.now().isoformat()}
        ]
    }

    # Mock the service layer call
    mock_product_service.get_product_detail.return_value = mock_product_data

    # Act
    response = client.get(f"/api/v1/products/{test_product_id}") # Modified: Added /api/v1 prefix

    # Assert
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == mock_product_data
    mock_product_service.get_product_detail.assert_called_once_with(ANY, UUID(test_product_id)) # Pass UUID object

@pytest.mark.asyncio
async def test_get_product_detail_not_found(client: TestClient, mock_product_service: AsyncMock):
    # Arrange
    # Generate a fake product ID that won't be found
    non_existent_product_id = str(uuid4()) # Use string UUID for API request

    # Configure the mock_product_service.get_product_detail to return None, simulating not found
    mock_product_service.get_product_detail.return_value = None

    # Act
    response = client.get(f"/api/v1/products/{non_existent_product_id}") # Modified: Added /api/v1 prefix

    # Assert
    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.json().get('detail') == "商品未找到"
    mock_product_service.get_product_detail.assert_called_once_with(ANY, UUID(non_existent_product_id)) # Pass UUID object

@pytest.mark.asyncio
async def test_update_product_success(client: TestClient, mock_product_service: AsyncMock):
    # Arrange
    # No need to create users or products directly, mocking handles data and authentication.
    # The mock_get_current_authenticated_user_override provides the authenticated user's info.

    # Use the test_auth_user_id from the client fixture for simulating the current user (owner)
    owner_id = test_authenticated_user_uuid
    # Define a fake product ID for the test
    product_id_str = mock_products_all[0]["商品ID"] # Use string UUID for API request
    product_id_uuid = UUID(product_id_str) # Convert to UUID object for service call

    # Prepare product update data
    product_update_data = ProductUpdate(
        product_name="更新后的测试手机",
        description="更新后的测试描述",
        price=6500.0,
        quantity=15,
        image_urls=["https://example.com/updated_image.jpg"]
    )

    # Configure the mock_product_service.update_product to do nothing on success
    mock_product_service.update_product.return_value = None # Assuming service returns None or doesn't return explicitly on success

    # Act
    response = client.put(
        f"/api/v1/products/{product_id_str}", # Modified: Added /api/v1 prefix
        json=product_update_data.model_dump(exclude_unset=True)
    )

    # Assert
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["message"] == "Product updated successfully"

    # Assert that the service method was called with the correct arguments
    # The service's update_product expects conn, product_id (UUID), owner_id (UUID), product_update_data
    mock_product_service.update_product.assert_called_once_with(
        ANY,
        product_id_uuid,
        owner_id,
        product_update_data
    )

@pytest.mark.asyncio
async def test_update_product_permission_denied(client: TestClient, mock_product_service: AsyncMock):
    # Arrange
    # No need to create users or products directly, mocking handles data and authentication.
    # The mock_get_current_authenticated_user_override provides the authenticated user's info.

    # Use a different user ID to simulate a non-owner attempting the update
    non_owner_user_id = test_authenticated_user_uuid # Changed to use fixed int ID
    # Define a fake product ID for the test
    product_id = UUID(mock_products_all[0]["商品ID"]) # Modified: Changed to int

    # Prepare product update data
    product_update_data = ProductUpdate(
        product_name="尝试更新的商品",
    )

    # Configure the mock_product_service.update_product to raise a PermissionError
    mock_product_service.update_product.side_effect = PermissionError("您无权更新此商品")

    # Act
    response = client.put(
        f"/api/v1/products/{product_id}", # Modified: Added /api/v1 prefix
        json=product_update_data.model_dump(exclude_unset=True)
    )

    # Assert
    assert response.status_code == status.HTTP_403_FORBIDDEN # Expect 403 Forbidden
    assert response.json()["detail"] == "您无权更新此商品"

    # Assert that the service method was called with the correct arguments
    mock_product_service.update_product.assert_called_once()
    args, kwargs = mock_product_service.update_product.call_args
    assert args[1] == product_id
    assert args[2] == non_owner_user_id # Modified: non_owner_user_id is already an int
    assert args[3] == product_update_data

@pytest.mark.asyncio
async def test_delete_product_success(client: TestClient, mock_product_service: AsyncMock):
    # Arrange
    # No need to create users or products directly, mocking handles data and authentication.
    # The mock_get_current_authenticated_user_override provides the authenticated user's info.

    # Use the test_auth_user_id from the client fixture for simulating the current user (owner)
    owner_id = test_authenticated_user_uuid
    # Define a fake product ID for the test
    product_id_str = mock_products_all[0]["商品ID"] # Use string UUID for API request
    product_id_uuid = UUID(product_id_str) # Convert to UUID object for service call

    # Configure the mock_product_service.delete_product to do nothing on success
    mock_product_service.delete_product.return_value = None # Assuming service returns None or doesn't return explicitly on success

    # Act
    response = client.delete(f"/api/v1/products/{product_id_str}") # Modified: Added /api/v1 prefix

    # Assert
    assert response.status_code == status.HTTP_200_OK # Expect 200 OK for successful deletion
    assert response.json()["message"] == "商品删除成功"

    # Assert that the service method was called with the correct arguments
    mock_product_service.delete_product.assert_called_once_with(ANY, product_id_uuid, owner_id)

@pytest.mark.asyncio
async def test_withdraw_product_success(client: TestClient, mock_product_service: AsyncMock):
    # Arrange
    # No need to create users or products directly, mocking handles data and authentication.
    # The mock_get_current_authenticated_user_override provides the authenticated user's info.

    # Use the test_auth_user_id from the client fixture for simulating the current user (owner)
    owner_id = test_authenticated_user_uuid
    # Define a fake product ID for the test
    product_id_str = mock_products_all[0]["商品ID"] # Use string UUID for API request
    product_id_uuid = UUID(product_id_str) # Convert to UUID object for service call

    # Configure the mock_product_service.withdraw_product to do nothing on success
    mock_product_service.withdraw_product.return_value = None # Assuming service returns None or doesn't return explicitly on success

    # Act
    response = client.put(f"/api/v1/products/{product_id_str}/status/withdraw") # Modified: Added /api/v1 prefix

    # Assert
    assert response.status_code == status.HTTP_200_OK # Expect 200 OK for successful withdrawal
    assert response.json()["message"] == "商品已成功下架" # Modified: Changed expected message

    # Assert that the service method was called with the correct arguments
    mock_product_service.withdraw_product.assert_called_once_with(ANY, product_id_uuid, owner_id)

@pytest.mark.asyncio
async def test_withdraw_product_permission_denied(client: TestClient, mock_product_service: AsyncMock):
    # Arrange
    # No need to create users or products directly, mocking handles data and authentication.
    # The mock_get_current_authenticated_user_override provides the authenticated user's info.

    # Use a different user ID to simulate a non-owner attempting the withdrawal
    non_owner_user_id = test_authenticated_user_uuid # Changed to use fixed int ID
    # Define a fake product ID for the test
    product_id = UUID(mock_products_all[0]["商品ID"]) # Modified: Changed to int

    # Configure the mock_product_service.withdraw_product to raise a PermissionError
    mock_product_service.withdraw_product.side_effect = PermissionError("您无权下架此商品")

    # Act
    response = client.put(f"/api/v1/products/{product_id}/status/withdraw") # Modified: Added /api/v1 prefix

    # Assert
    assert response.status_code == status.HTTP_403_FORBIDDEN # Expect 403 Forbidden
    assert response.json()["detail"] == "您无权下架此商品"

    # Assert that the service method was called with the correct arguments
    mock_product_service.withdraw_product.assert_called_once()
    args, kwargs = mock_product_service.withdraw_product.call_args
    assert args[1] == product_id
    assert args[2] == non_owner_user_id # Modified: non_owner_user_id is already an int

@pytest.mark.asyncio
async def test_get_product_list_filter_by_category(client: TestClient, mock_product_service: AsyncMock):
    # Arrange
    # No need to create users or products directly, data is mocked.

    # Define mock product data filtered by category
    mock_products = [
        {
            "商品ID": mock_products_all[0]["商品ID"],
            "商品名称": "电子产品A",
            "商品描述": "",
            "库存": 10,
            "价格": 100.0,
            "发布时间": datetime.now().isoformat(),
            "商品状态": "Active",
            "发布者用户名": "user1",
            "商品类别": "Electronics",
            "主图URL": "",
            "images": []
        }
    ]

    # Configure the mock service to return filtered products
    mock_product_service.get_product_list.return_value = mock_products

    # Act
    response = client.get("/api/v1/products", params={
        "category_name": "Electronics", # Modified: Pass string category name
        "status": "Active"
    })

    # Assert
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == mock_products

    # Assert that the service method was called with the correct arguments
    mock_product_service.get_product_list.assert_called_once_with(
        ANY,
        "Electronics", # Modified: Assert with string category name
        "Active",
        None, None, None, # keyword, min_price, max_price
        'PostTime', 1, 10 # order_by, page_number, page_size
    )

@pytest.mark.asyncio
async def test_get_product_list_filter_by_price_range(client: TestClient, mock_product_service: AsyncMock):
    # Arrange
    # No need to create users or products directly, data is mocked.

    # Define mock product data filtered by price range (100-200)
    mock_products = [
        {
            "商品ID": mock_products_all[0]["商品ID"],
            "商品名称": "商品X",
            "商品描述": "",
            "库存": 5,
            "价格": 150.0,
            "发布时间": datetime.now().isoformat(),
            "商品状态": "Active",
            "发布者用户名": "userA",
            "商品类别": "General",
            "主图URL": "",
            "images": []
        }
    ]

    mock_product_service.get_product_list.return_value = mock_products

    # Act
    response = client.get("/api/v1/products", params={
        "min_price": 100.0,
        "max_price": 200.0
    })

    # Assert
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == mock_products

    # Assert that the service method was called with the correct arguments
    mock_product_service.get_product_list.assert_called_once_with(
        ANY,
        None, None, # category_id, status
        None, # keyword
        100.0, # min_price
        200.0, # max_price
        'PostTime', 1, 10 # order_by, page_number, page_size
    )

@pytest.mark.asyncio
async def test_get_product_list_search_keyword(client: TestClient, mock_product_service: AsyncMock):
    # Arrange
    # No need to create users or products directly, data is mocked.

    # Define mock product data for keyword search tests
    mock_products = [
        {
            "商品ID": mock_products_all[0]["商品ID"],
            "商品名称": "智能手机",
            "商品描述": "一款高性能手机",
            "库存": 20,
            "价格": 3000.0,
            "发布时间": datetime.now().isoformat(),
            "商品状态": "Active",
            "发布者用户名": "sellerX",
            "商品类别": "Electronics",
            "主图URL": "",
            "images": []
        }
    ]

    mock_product_service.get_product_list.return_value = mock_products

    # Act
    response = client.get("/api/v1/products", params={
        "keyword": "手机"
    })

    # Assert
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == mock_products

    # Assert that the service method was called with the correct arguments
    mock_product_service.get_product_list.assert_called_once_with(
        ANY,
        None, None, # category_id, status
        "手机", # keyword
        None, None, # min_price, max_price
        'PostTime', 1, 10 # order_by, page_number, page_size
    )

@pytest.mark.asyncio
async def test_get_product_list_filter_by_status(client: TestClient, mock_product_service: AsyncMock):
    # Arrange
    # No need to create users or products directly, data is mocked.

    # Define mock product data with various statuses
    mock_products_all_statuses = [
        {
            "商品ID": mock_products_all[0]["商品ID"], "商品名称": "Active Product", "商品描述": "", "库存": 10, "价格": 100.0, "发布时间": datetime.now().isoformat(), "商品状态": "Active", "发布者用户名": "user1", "商品类别": "CategoryA", "主图URL": "", "images": []
        },
        {
            "商品ID": mock_products_all[1]["商品ID"], "商品名称": "Pending Product", "商品描述": "", "库存": 5, "价格": 150.0, "发布时间": datetime.now().isoformat(), "商品状态": "PendingReview", "发布者用户名": "user2", "商品类别": "CategoryB", "主图URL": "", "images": []
        },
        {
            "商品ID": mock_products_all[4]["商品ID"], "商品名称": "Sold Product", "商品描述": "", "库存": 0, "价格": 200.0, "发布时间": datetime.now().isoformat(), "商品状态": "Sold", "发布者用户名": "user3", "商品类别": "CategoryC", "主图URL": "", "images": []
        }
    ]

    async def mock_get_product_list_side_effect_status(conn, category_id=None, status=None, keyword=None, min_price=None, max_price=None, order_by='PostTime', page_number=1, page_size=10, **kwargs):
        if status == "Active":
            return [p for p in mock_products_all_statuses if p["商品状态"] == "Active"]
        elif status == "PendingReview":
            return [p for p in mock_products_all_statuses if p["商品状态"] == "PendingReview"]
        elif status == "Sold":
            return [p for p in mock_products_all_statuses if p["商品状态"] == "Sold"]
        return mock_products_all_statuses # Return all if no status filter

    mock_product_service.get_product_list.side_effect = mock_get_product_list_side_effect_status

    # Test with Active status
    response_active = client.get("/api/v1/products", params={
        "status": "Active"
    })
    assert response_active.status_code == status.HTTP_200_OK
    assert len(response_active.json()) == 1
    assert response_active.json()[0]["商品状态"] == "Active"
    mock_product_service.get_product_list.assert_any_call(
        ANY, None, "Active", None, None, None, 'PostTime', 1, 10
    )

    # Test with PendingReview status
    response_pending = client.get("/api/v1/products", params={
        "status": "PendingReview"
    })
    assert response_pending.status_code == status.HTTP_200_OK
    assert len(response_pending.json()) == 1
    assert response_pending.json()[0]["商品状态"] == "PendingReview"
    mock_product_service.get_product_list.assert_any_call(
        ANY, None, "PendingReview", None, None, None, 'PostTime', 1, 10
    )

    # Test with Sold status
    response_sold = client.get("/api/v1/products", params={
        "status": "Sold"
    })
    assert response_sold.status_code == status.HTTP_200_OK
    assert len(response_sold.json()) == 1
    assert response_sold.json()[0]["商品状态"] == "Sold"
    mock_product_service.get_product_list.assert_any_call(
        ANY, None, "Sold", None, None, None, 'PostTime', 1, 10
    )

@pytest.mark.asyncio
async def test_get_product_list_pagination_and_sorting(client: TestClient, mock_product_service: AsyncMock):
    # Arrange
    # No need to create users or products directly, data is mocked.

    # Define mock product data that the service should return for pagination and sorting
    # This data should match the structure returned by the sp_GetProductList and sp_GetProductDetail (for images)
    # and should use the Chinese aliases defined in the stored procedures.
    # Using global mock_products_all for consistency.
    global mock_products_all # Ensure we are using the global mock data

    async def mock_get_product_list_side_effect_pagination_sorting(conn, category_name=None, status=None, keyword=None, min_price=None, max_price=None, order_by='PostTime', page_number=1, page_size=10, **kwargs):
        # Filter by status if provided
        # Use the provided mock_products_all for filtering
        filtered_products = list(mock_products_all) # Create a copy to avoid modifying original

        if status:
            filtered_products = [p for p in filtered_products if p["商品状态"] == status]

        def get_sort_key(product):
            if order_by == "Price":
                return product["价格"]
            elif order_by == "ProductName":
                return product["商品名称"]
            elif order_by == "PostTime":
                # Convert ISO format string to datetime for proper comparison
                return datetime.fromisoformat(product["发布时间"])
            return datetime.fromisoformat(product["发布时间"]) # Default sort key

        # Determine reverse_sort based on order_by, as API doesn't take sortOrder directly
        # Assume PostTime is DESC by default, others ASC by default if not specified
        reverse_sort = True if order_by == "PostTime" else False
        sorted_products = sorted(filtered_products, key=get_sort_key, reverse=reverse_sort)

        start_index = (page_number - 1) * page_size
        end_index = start_index + page_size
        return sorted_products[start_index:end_index]

    mock_product_service.get_product_list.side_effect = mock_get_product_list_side_effect_pagination_sorting

    # Test case 1: Page 1, size 2, sorted by Price ASC
    response1 = client.get("/api/v1/products", params={
        "page_number": 1,
        "page_size": 2,
        "order_by": "Price",
        # "sortOrder": "ASC" # Removed, as API doesn't support this directly
    })
    assert response1.status_code == status.HTTP_200_OK
    assert len(response1.json()) == 2
    # Expected order based on mock_products_all sorted by price ASC:
    # 1. 机械键盘 (450.0)
    # 2. 智能手表 (1200.0)
    assert response1.json()[0]["商品名称"] == "机械键盘"
    assert response1.json()[1]["商品名称"] == "复古相机"
    mock_product_service.get_product_list.assert_any_call(ANY, None, None, None, None, None, "Price", 1, 2)

    # Test case 2: Page 2, size 2, sorted by Price ASC
    response2 = client.get("/api/v1/products", params={
        "page_number": 2,
        "page_size": 2,
        "order_by": "Price",
        # "sortOrder": "ASC" # Removed, as API doesn't support this directly
    })
    assert response2.status_code == status.HTTP_200_OK
    assert len(response2.json()) == 2 # Only one product left on the second page
    # Expected order based on mock_products_all sorted by price ASC:
    # 1. 旧笔记本 (2500.0)
    assert response2.json()[0]["商品名称"] == "智能手表"
    assert response2.json()[1]["商品名称"] == "旧笔记本"
    mock_product_service.get_product_list.assert_any_call(ANY, None, None, None, None, None, "Price", 2, 2)

    # Test case 3: Sorted by PostTime DESC
    response3 = client.get("/api/v1/products", params={
        "order_by": "PostTime",
        # "sortOrder": "DESC" # Removed, as API doesn't support this directly
    })
    assert response3.status_code == status.HTTP_200_OK
    assert len(response3.json()) == 5 # All 5 products in mock_products_all
    # Expected order (most recent first) based on mock_products_all:
    # newest to oldest
    # Note: `datetime.now()` in mock_products_all means they will all have very similar timestamps.
    # For stable sorting, you might need to adjust mock_products_all to have distinct '发布时间'.
    # Assuming current datetime.now() order for simplicity in test setup.
    assert response3.json()[0]["商品名称"] == "复古相机"
    assert response3.json()[1]["商品名称"] == "智能手表"
    assert response3.json()[2]["商品名称"] == "机械键盘"
    assert response3.json()[3]["商品名称"] == "旧笔记本"
    assert response3.json()[4]["商品名称"] == "测试手机"
    mock_product_service.get_product_list.assert_any_call(ANY, None, None, None, None, None, "PostTime", 1, 10)

@pytest.mark.asyncio
async def test_get_product_list_filter_combinations(client: TestClient, mock_product_service: AsyncMock):
    # Arrange
    # No need to create users or products directly, data is mocked.

    # Define comprehensive mock product data for various filter conditions
    # mock_products_all is already defined at the top of the file
    global mock_products_all # Use the global mock_products_all

    # Configure the mock_product_service.get_product_list side effect
    async def mock_get_product_list_side_effect(conn, category_name=None, status=None, keyword=None, min_price=None, max_price=None, order_by='PostTime', page_number=1, page_size=10, **kwargs):
        # Map integer category_id to string category name for filtering mock data
        # This mapping is no longer needed as category_name is passed directly
        # category_id_to_name = {
        #     1: "Electronics",
        #     2: "Accessories", # Corrected mapping for category 2
        #     3: "Wearables",   # Corrected mapping for category 3
        #     4: "Photography"  # Corrected mapping for category 4
        #     # Add other mappings as needed
        # }
        # category_name_filter = category_id_to_name.get(category_id) if isinstance(category_id, int) else category_id

        status_filter = status # Corrected: Use status directly
        search_query = keyword # Corrected: Use keyword directly
        min_price_filter = min_price # Corrected: Use min_price directly
        max_price_filter = max_price # Corrected: Use max_price directly
        page_number_filter = page_number # Corrected: Use page_number directly
        page_size_filter = page_size # Corrected: Use page_size directly
        order_by_field = order_by # Corrected: Use order_by directly
        # sort_order = kwargs.get("sortOrder", "DESC") # Not directly used for `sorted` built-in

        # Apply filters
        filtered_products = []
        for p in mock_products_all:
            is_match = True

            if status_filter and p["商品状态"] != status_filter:
                is_match = False

            if is_match and category_name and p.get("商品类别") != category_name: # Use category_name directly
                is_match = False

            if is_match and search_query:
                if not (search_query.lower() in p["商品名称"].lower() or (p.get("商品描述") and search_query.lower() in p["商品描述"].lower())):
                    is_match = False

            if is_match and min_price_filter is not None and p["价格"] < min_price_filter:
                is_match = False
            if is_match and max_price_filter is not None and p["价格"] > max_price_filter:
                is_match = False

            if is_match:
                filtered_products.append(p)

        # Apply sorting
        def get_sort_key(product):
            if order_by_field == "Price":
                return product["价格"]
            elif order_by_field == "ProductName":
                return product["商品名称"]
            elif order_by_field == "PostTime":
                # Convert ISO format string to datetime for proper comparison
                return datetime.fromisoformat(product["发布时间"])
            return datetime.fromisoformat(product["发布时间"]) # Default sort key

        # Determine reverse_sort based on order_by, as API doesn't take sortOrder directly
        # Assume PostTime is DESC by default, others ASC by default if not specified
        # For this test, we need to ensure the sorting matches the expected output
        reverse_sort = True if order_by_field == "PostTime" else False

        # Special handling for Price sorting in this combined test to match expected output
        if order_by_field == "Price":
            sorted_products = sorted(filtered_products, key=get_sort_key, reverse=False) # ASC for price
        else:
            sorted_products = sorted(filtered_products, key=get_sort_key, reverse=reverse_sort)

        # Apply pagination
        start_index = (page_number_filter - 1) * page_size_filter
        end_index = start_index + page_size_filter
        paginated_products = sorted_products[start_index:end_index]

        # Update total count in the paginated results (optional, depends on API contract)
        # For these tests, we are asserting on the product list directly.
        for p in paginated_products:
            p["总商品数"] = len(filtered_products) # Total count of filtered products

        return paginated_products

    mock_product_service.get_product_list.side_effect = mock_get_product_list_side_effect

    # Test case 1: Filter by Category and Price Range, Paginate and Sort by Price ASC
    # Category: Electronics (ID 1)
    # Price Range: 1000.00 - 7000.00
    # From mock_products_all, Electronics are: "测试手机" (5999.0), "旧笔记本" (2500.0)
    # Both fall within the price range.
    # Sorted by Price ASC: "旧笔记本" (2500.0), "测试手机" (5999.0)
    # Page 1, size 2: "旧笔记本", "测试手机"
    response1 = client.get("/api/v1/products", params={
        "category_name": "Electronics", # Changed to category_name (string)
        "min_price": 1000.00,
        "max_price": 7000.00,
        "page_number": 1,
        "page_size": 2,
        "order_by": "Price",
        # "sortOrder": "ASC" # Removed, as API doesn't support this directly
    })

    assert response1.status_code == status.HTTP_200_OK
    # Expected products: Sony WH-1000XM4 (1999.00), Samsung Galaxy S21 (5999.00) or other if data changed
    # Assuming the sorted products based on mock_products_all and filters
    # Let's define the expected result based on the current mock_products_all and filter criteria
    expected_products_1 = [
        # After filtering for Electronics, min_price=1000, max_price=7000, and sorting by Price ASC:
        # Original: Sony(1999), Samsung(5999), Logitech(599)
        # Filtered & Sorted: Sony(1999), Samsung(5999)
        # After pagination (page 1, size 2):
        {
            "商品ID": mock_products_all[1]["商品ID"],
            "商品名称": "旧笔记本",
            "商品描述": "一台二手的旧笔记本，性能良好。",
            "库存": 5,
            "价格": 2500.0,
            "发布时间": "2023-01-02T10:00:00.000000",
            "商品状态": "PendingReview",
            "发布者用户名": "user2",
            "商品类别": "Electronics",
            "主图URL": "http://example.com/old_laptop.jpg",
            "images": [],
            "总商品数": 2 # Use fixed value
        },
        {
            "商品ID": mock_products_all[0]["商品ID"],
            "商品名称": "测试手机",
            "商品描述": "一个很棒的测试手机",
            "库存": 50,
            "价格": 5999.0,
            "发布时间": "2023-01-01T10:00:00.000000",
            "商品状态": "Active",
            "发布者用户名": "user1",
            "商品类别": "Electronics",
            "主图URL": "http://example.com/test_phone.jpg",
            "images": [
                {"image_url": "http://example.com/test_phone_1.jpg", "sort_order": 0, "upload_time": mock_products_all[0]["images"][0]["upload_time"]},
                {"image_url": "http://example.com/test_phone_2.jpg", "sort_order": 1, "upload_time": mock_products_all[0]["images"][1]["upload_time"]}
            ],
            "总商品数": 2 # Use fixed value
        }
    ]
    assert response1.json() == expected_products_1
    mock_product_service.get_product_list.assert_any_call(
        ANY,
        "Electronics", # category_id (string)
        None, # status
        None, # keyword
        1000.00, # min_price
        7000.00, # max_price
        "Price", # order_by
        1, # page_number
        2, # page_size
    )

    # Test case 2: Filter by Status and Keyword, Paginate and Sort by PostTime DESC
    response2 = client.get("/api/v1/products", params={
        "status": "Active",
        "keyword": "手机",
        "page_number": 1,
        "page_size": 1,
        "order_by": "PostTime",
        # "sortOrder": "DESC" # Removed, as API doesn't support this directly
    })
    assert response2.status_code == status.HTTP_200_OK
    expected_products_2 = [
        # After filtering for Active, keyword='mouse', and sorting by PostTime DESC:
        # Original: Logitech MX Master 3 (Active, 'mouse' in name)
        # Filtered & Sorted:
        {
            "商品ID": mock_products_all[0]["商品ID"],
            "商品名称": "测试手机",
            "商品描述": "一个很棒的测试手机",
            "库存": 50,
            "价格": 5999.0,
            "发布时间": "2023-01-01T10:00:00.000000",
            "商品状态": "Active",
            "发布者用户名": "user1",
            "商品类别": "Electronics",
            "主图URL": "http://example.com/test_phone.jpg",
            "images": [
                {"image_url": "http://example.com/test_phone_1.jpg", "sort_order": 0, "upload_time": mock_products_all[0]["images"][0]["upload_time"]},
                {"image_url": "http://example.com/test_phone_2.jpg", "sort_order": 1, "upload_time": mock_products_all[0]["images"][1]["upload_time"]}
            ],
            "总商品数": 1 # Use fixed value
        }
    ]
    assert response2.json() == expected_products_2
    mock_product_service.get_product_list.assert_any_call(
        ANY,
        None, # category_id
        "Active", # status
        "手机", # keyword
        None, None, # min_price, max_price
        "PostTime", # order_by
        1, # page_number
        1, # page_size
    )

    # Test case 3: Filter by Category and Status, and Keyword
    response3 = client.get("/api/v1/products", params={
        "category_name": "Accessories", # Changed to category_name (string)
        "status": "Active",
        "keyword": "键盘"
    })
    assert response3.status_code == status.HTTP_200_OK
    expected_products_3 = [
        # After filtering for Books, Active, keyword='gatsby':
        # Original: The Great Gatsby (Books, Active, 'gatsby' in name)
        {
            "商品ID": mock_products_all[2]["商品ID"],
            "商品名称": "机械键盘",
            "商品描述": "手感极佳的机械键盘。",
            "库存": 20,
            "价格": 450.0,
            "发布时间": "2023-01-03T10:00:00.000000",
            "商品状态": "Active",
            "发布者用户名": "user1",
            "商品类别": "Accessories",
            "主图URL": "http://example.com/keyboard.jpg",
            "images": [],
            "总商品数": 1 # Use fixed value
        }
    ]
    assert response3.json() == expected_products_3
    mock_product_service.get_product_list.assert_any_call(
        ANY,
        "Accessories", # category_id (string)
        "Active", # status
        "键盘", # keyword
        None, None, # min_price, max_price
        'PostTime', 1, 10
    )

@pytest.mark.asyncio
async def test_remove_favorite_success(client: TestClient, mock_product_service: AsyncMock):
    # Arrange
    # No need to create a user or product directly, mocking handles data.

    # Use the test_auth_user_id from the client fixture for simulating the current user
    user_id = test_authenticated_user_uuid
    # Define a fake product ID for the test
    product_id_str = mock_products_all[0]["商品ID"] # Use string UUID for API request
    product_id_uuid = UUID(product_id_str) # Convert to UUID object for service call

    # Configure the mock_product_service.remove_favorite to do nothing on success
    mock_product_service.remove_favorite.return_value = None # Assuming service returns None or doesn't return explicitly on success

    # Act
    response = client.delete(f"/api/v1/products/{product_id_str}/favorite") # Modified: Added /api/v1 prefix

    # Assert
    assert response.status_code == status.HTTP_200_OK # Expect 200 OK for successful removal
    assert response.json()["message"] == "商品已成功从收藏列表中移除"

    # Assert that the service method was called with the correct arguments
    mock_product_service.remove_favorite.assert_called_once_with(
        ANY,
        user_id,
        product_id_uuid
    )

@pytest.mark.asyncio
async def test_remove_favorite_not_favorited(client: TestClient, mock_product_service: AsyncMock):
    # Arrange
    # No need to create a user or product directly, mocking handles data.

    # Use the test_auth_user_id from the client fixture for simulating the current user
    user_id = test_authenticated_user_uuid
    # Define a fake product ID for the test
    product_id_str = mock_products_all[0]["商品ID"] # Use string UUID for API request
    product_id_uuid = UUID(product_id_str) # Convert to UUID object for service call

    # Configure the mock_product_service.remove_favorite to raise a ValueError to simulate not favorited
    mock_product_service.remove_favorite.side_effect = ValueError("该商品不在您的收藏列表中。") # Simulate service raising ValueError
    print(f"DEBUG: remove_favorite side_effect set to: {mock_product_service.remove_favorite.side_effect}")

    # Act
    response = client.delete(f"/api/v1/products/{product_id_str}/favorite") # Modified: Added /api/v1 prefix

    # Assert
    # The router should catch the ValueError from the service and return a 400 HTTP exception
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.json()["detail"] == "该商品不在您的收藏列表中。"

    mock_product_service.remove_favorite.assert_called_once_with(ANY, user_id, product_id_uuid) # Modified: user_id is already an int

@pytest.mark.asyncio
async def test_get_user_favorites(client: TestClient, mock_product_service: AsyncMock):
    # Arrange
    # No need to create a user or product directly, mocking handles data.

    # Use the test_auth_user_id from the client fixture for simulating the current user
    user_id = test_authenticated_user_uuid

    # Define mock data that the service should return (list of favorite products)
    mock_favorite_products = [
        {
            "商品ID": mock_products_all[0]["商品ID"],
            "商品名称": "收藏商品1",
            "商品描述": "Description 1",
            "库存": 10,
            "价格": 100.0,
            "发布时间": datetime.now().isoformat(),
            "商品状态": "Active",
            "发布者用户名": "seller_user_1",
            "商品类别": "CategoryA",
            "收藏时间": datetime.now().isoformat(),
            "主图URL": "/uploads/fav1.jpg",
            "images": []
        },
        {
            "商品ID": mock_products_all[1]["商品ID"],
            "商品名称": "收藏商品2",
            "商品描述": "Description 2",
            "库存": 5,
            "价格": 200.0,
            "发布时间": datetime.now().isoformat(),
            "商品状态": "Active",
            "发布者用户名": "seller_user_2",
            "商品类别": "CategoryB",
            "收藏时间": datetime.now().isoformat(),
            "主图URL": "/uploads/fav2.jpg",
            "images": []
        }
    ]

    # Mock the service's get_user_favorites method to return the mock data
    mock_product_service.get_user_favorites.return_value = mock_favorite_products

    # Act
    response = client.get("/api/v1/products/favorites") # Modified: Added /api/v1 prefix, matched to router

    # Assert
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == mock_favorite_products

    # Assert that the service method was called with the correct arguments
    mock_product_service.get_user_favorites.assert_called_once_with(ANY, user_id)

@pytest.mark.asyncio
async def test_admin_activate_product_success(client: TestClient, mock_product_service: AsyncMock):
    # Arrange
    # No need to create users or products directly, mocking handles data and authentication.

    # Use the test_admin_user_id from the client fixture for simulating the current admin
    admin_id = test_admin_uuid
    # Define a fake product ID for the test
    product_id_str = mock_products_all[0]["商品ID"] # Use string UUID for API request
    product_id_uuid = UUID(product_id_str) # Convert to UUID object for service call

    # Configure the mock_product_service.activate_product to do nothing on success
    mock_product_service.activate_product.return_value = None # Assuming service returns None or doesn't return explicitly on success

    # Act
    response = client.put(f"/api/v1/products/{product_id_str}/status/activate") # Modified: Added /api/v1 prefix

    # Assert
    assert response.status_code == status.HTTP_200_OK # Expect 200 OK for successful activation
    assert response.json()["message"] == "商品已成功激活"

    # Assert that the service method was called with the correct arguments
    mock_product_service.activate_product.assert_called_once_with(ANY, product_id_uuid, admin_id)

@pytest.mark.asyncio
async def test_admin_activate_product_permission_denied(client: TestClient, mock_product_service: AsyncMock):
    # Arrange
    # No need to create users or products directly, mocking handles data and authentication.

    # Define a fake product ID for the test
    product_id_str = mock_products_all[0]["商品ID"] # Use string UUID for API request
    product_id_uuid = UUID(product_id_str) # Convert to UUID object for service call

    # Use a regular user ID to simulate permission denied
    regular_user_id = test_user_uuid

    # Temporarily override the get_current_active_admin_user dependency
    async def mock_get_current_active_admin_user_forbidden_override():
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权执行此操作，只有管理员可以激活商品。")

    original_dependency = app.dependency_overrides.get(get_current_active_admin_user_dependency) # Store original
    app.dependency_overrides[get_current_active_admin_user_dependency] = mock_get_current_active_admin_user_forbidden_override

    try:
        # Act
        response = client.put(
            f"/api/v1/products/{product_id_str}/status/activate",
            headers={
                "Authorization": f"Bearer fake-token-{regular_user_id}" # Use regular user's token
            }
        )

        # Assert
        assert response.status_code == status.HTTP_403_FORBIDDEN # Expect 403 Forbidden
        assert response.json()["detail"] == "无权执行此操作，只有管理员可以激活商品。"

        # Assert that the service method was NOT called
        mock_product_service.activate_product.assert_not_called()
    finally:
        # Clean up the override
        if original_dependency is None:
            app.dependency_overrides.pop(get_current_active_admin_user_dependency, None)
        else:
            app.dependency_overrides[get_current_active_admin_user_dependency] = original_dependency

@pytest.mark.asyncio
async def test_admin_reject_product_success(client: TestClient, mock_product_service: AsyncMock):
    # Arrange
    # No need to create users or products directly, mocking handles data and authentication.

    # Use the test_admin_user_id from the client fixture for simulating the current admin
    admin_id = test_admin_uuid
    # Define a fake product ID for the test
    product_id = UUID(mock_products_all[0]["商品ID"]) # Use integer product ID for update, matching DAL/Service expectation
    # Define a reason for rejection
    reason = "Rejected for testing purposes."

    # Configure the mock_product_service.reject_product to do nothing on success
    mock_product_service.reject_product.return_value = None # Assuming service returns None or doesn't return explicitly on success

    # Act
    response = client.put(f"/api/v1/products/{product_id}/status/reject", json={"reason": reason}) # Modified: Added /api/v1 prefix, simplified JSON

    # Assert
    assert response.status_code == status.HTTP_200_OK # Expect 200 OK for successful rejection
    assert response.json()["message"] == "商品已成功拒绝"

    # Assert that the service method was called with the correct arguments
    mock_product_service.reject_product.assert_called_once_with(ANY, product_id, admin_id, reason) # Modified: admin_id is already an int

@pytest.mark.asyncio
async def test_admin_reject_product_permission_denied(client: TestClient, mock_product_service: AsyncMock):
    # Arrange
    # No need to create users or products directly, mocking handles data and authentication.

    # Define a fake product ID for the test
    product_id = UUID(mock_products_all[0]["商品ID"]) # Modified: Changed to int
    # Define a reason for rejection
    reason = "Attempted rejection without admin permission."

    # Temporarily override the get_current_active_admin_user dependency
    async def mock_get_current_active_admin_user_forbidden_override():
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="您无权审核商品")

    original_dependency = app.dependency_overrides.get(get_current_active_admin_user_dependency) # Store original
    app.dependency_overrides[get_current_active_admin_user_dependency] = mock_get_current_active_admin_user_forbidden_override

    try:
        # Act
        response = client.put(f"/api/v1/products/{product_id}/status/reject", json={"reason": reason}) # Modified: Added /api/v1 prefix, simplified JSON

        # Assert
        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert response.json()["detail"] == "您无权审核商品"

        # Assert that the service method was NOT called
        mock_product_service.reject_product.assert_not_called()
    finally:
        # Clean up the override
        if original_dependency is None:
            app.dependency_overrides.pop(get_current_active_admin_user_dependency, None)
        else:
            app.dependency_overrides[get_current_active_admin_user_dependency] = original_dependency

@pytest.mark.asyncio
async def test_admin_batch_activate_products(client: TestClient, mock_product_service: AsyncMock):
    # Arrange
    # No need to create users or products directly, mocking handles data and authentication.

    # Use the test_admin_user_id from the client fixture for simulating the current admin
    admin_id = test_admin_uuid
    # Define fake product IDs for the test
    product_ids_uuid = [UUID(mock_products_all[0]["商品ID"]), UUID(mock_products_all[1]["商品ID"]), UUID(mock_products_all[2]["商品ID"])] # Use integer IDs, matching DAL/Service expectation
    product_ids_str = [mock_products_all[0]["商品ID"], mock_products_all[1]["商品ID"], mock_products_all[2]["商品ID"]] # Keep for JSON payload

    # Configure the mock_product_service.batch_activate_products to return a success count
    success_count = len(product_ids_uuid)
    mock_product_service.batch_activate_products.return_value = success_count

    # Act
    # Send request using the client with mocked dependencies
    response = client.post(
        "/api/v1/products/batch/activate", # Modified: Added /api/v1 prefix
        json={
            "product_ids": product_ids_str,
        },
        headers={
            "Authorization": "Bearer fake-admin-token" # Placeholder token for clarity
        }
    )

    # Assert
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["message"] == f"成功激活 {success_count} 件商品"

    # Assert that the service method was called with the correct arguments
    # The service's batch_activate_products expects conn, product_ids (List[UUID]), admin_id (UUID)

    mock_product_service.batch_activate_products.assert_called_once()

    # Check the arguments
    args, kwargs = mock_product_service.batch_activate_products.call_args

    # arg[0] is the mocked connection
    # arg[1] should be product_ids (List[UUID])
    # arg[2] should be admin_id (UUID)

    assert args[1] == product_ids_uuid # Check product_ids (list of UUID objects)
    assert args[2] == admin_id # Modified: admin_id is already an int

@pytest.mark.asyncio
async def test_admin_batch_review_permission_denied(client: TestClient, mock_product_service: AsyncMock):
    # Arrange
    # No need to create users or products directly, mocking handles data and authentication.

    # Define fake product IDs for the test
    product_ids_str = [str(uuid4()) for _ in range(3)] # Use string UUIDs for API request
    new_status = "Active" # Or "Rejected"
    reason = "Batch review attempt without admin permission." # Define reason

    # Temporarily override the get_current_active_admin_user dependency
    async def mock_get_current_active_admin_user_forbidden_override():
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="您无权审核商品")

    original_dependency = app.dependency_overrides.get(get_current_active_admin_user_dependency) # Store original
    app.dependency_overrides[get_current_active_admin_user_dependency] = mock_get_current_active_admin_user_forbidden_override

    try:
        # Determine the endpoint based on new_status
        if new_status == "Active":
            endpoint = "/api/v1/products/batch/activate"
        elif new_status == "Rejected":
            endpoint = "/api/v1/products/batch/reject"
        else:
            endpoint = "" # Should not happen in this test

        # Act
        # Simulate the API request for batch review
        response = client.post(
            endpoint, # Modified: Use specific endpoint
            json={
                "product_ids": product_ids_str, # Use string UUIDs for payload
                "reason": reason if new_status == "Rejected" else None # Reason only for rejection
            },
            headers={
                "Authorization": "Bearer fake-token" # Use a placeholder token for clarity
            }
        )

        # Assert
        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert response.json()["detail"] == "您无权审核商品"

        # Assert that the service methods were NOT called
        mock_product_service.batch_activate_products.assert_not_called()
        mock_product_service.batch_reject_products.assert_not_called()
    finally:
        # Clean up the override
        if original_dependency is None:
            app.dependency_overrides.pop(get_current_active_admin_user_dependency, None)
        else:
            app.dependency_overrides[get_current_active_admin_user_dependency] = original_dependency

@pytest.mark.asyncio
async def test_get_product_list_filter_pagination_sorting_combinations(client: TestClient, mock_product_service: AsyncMock):
    # Arrange
    # No need to create users or products directly, data is mocked.

    # Define comprehensive mock product data for various filter, pagination, and sorting scenarios
    # mock_products_all is already defined at the top of the file
    global mock_products_all # Use the global mock_products_all

    # Configure the mock_product_service.get_product_list side effect
    async def mock_get_product_list_side_effect(conn, category_name=None, status=None, keyword=None, min_price=None, max_price=None, order_by='PostTime', page_number=1, page_size=10, **kwargs):
        # Map integer category_id to string category name for filtering mock data
        # This mapping is no longer needed as category_name is passed directly
        # category_id_to_name = {
        #     1: "Electronics",
        #     2: "Books",
        #     3: "Other", # Added mapping for category 3
        #     4: "Home", # Added mapping for category 4
        #     5: "Sports", # Added mapping for category 5
        #     # Add other mappings as needed
        # }
        category_name_filter = category_name # Changed: Directly use category_name

        status_filter = status # Corrected: Use status directly
        search_query = keyword # Corrected: Use keyword directly
        min_price_filter = min_price # Corrected: Use min_price directly
        max_price_filter = max_price # Corrected: Use max_price directly
        page_number_filter = page_number # Corrected: Use page_number directly
        page_size_filter = page_size # Corrected: Use page_size directly
        order_by_field = order_by # Corrected: Use order_by directly
        sort_order = kwargs.get("sortOrder", "DESC")

        # Apply filters
        filtered_products = []
        for p in mock_products_all:
            is_match = True

            if status_filter and p["商品状态"] != status_filter:
                is_match = False

            if is_match and category_name_filter and p.get("商品类别") != category_name_filter:
                is_match = False

            if is_match and search_query:
                if not (search_query.lower() in p["商品名称"].lower() or (p.get("商品描述") and search_query.lower() in p["商品描述"].lower())):
                    is_match = False

            if is_match and min_price_filter is not None and p["价格"] < min_price_filter:
                is_match = False
            if is_match and max_price_filter is not None and p["价格"] > max_price_filter:
                is_match = False

            if is_match:
                filtered_products.append(p)

        # Apply sorting
        def get_sort_key(product):
            if order_by_field == "Price":
                return product["价格"]
            elif order_by_field == "ProductName":
                return product["商品名称"]
            elif order_by_field == "PostTime":
                # Convert ISO format string to datetime for proper comparison
                return datetime.fromisoformat(product["发布时间"])
            return datetime.fromisoformat(product["发布时间"]) # Default sort key

        # Determine reverse_sort based on order_by, as API doesn't take sortOrder directly
        # Assume PostTime is DESC by default, others ASC by default if not specified
        reverse_sort = True if order_by_field == "PostTime" else False
        sorted_products = sorted(filtered_products, key=get_sort_key, reverse=reverse_sort)

        # Apply pagination
        start_index = (page_number_filter - 1) * page_size_filter
        end_index = start_index + page_size_filter
        paginated_products = sorted_products[start_index:end_index]

        # Update total count in the paginated results
        total_count = len(filtered_products)
        for p in paginated_products:
             p["总商品数"] = total_count

        return paginated_products

    mock_product_service.get_product_list.side_effect = mock_get_product_list_side_effect

    # Test case 1: Filter by Category and Price Range, Paginate and Sort by Price ASC
    response1 = client.get("/api/v1/products", params={
        "category_name": "Electronics", # Changed to category_name (string)
        "min_price": 1000.00,
        "max_price": 7000.00,
        "page_number": 1,
        "page_size": 2,
        "order_by": "Price",
        # "sortOrder": "ASC" # Removed, as API doesn't support this directly
    })

    assert response1.status_code == status.HTTP_200_OK
    # Expected products: Sony WH-1000XM4 (1999.00), Samsung Galaxy S21 (5999.00) or other if data changed
    # Assuming the sorted products based on mock_products_all and filters
    # Let's define the expected result based on the current mock_products_all and filter criteria
    expected_products_1 = [
        # After filtering for Electronics, min_price=1000, max_price=7000, and sorting by Price ASC:
        # Original: Sony(1999), Samsung(5999), Logitech(599)
        # Filtered & Sorted: Sony(1999), Samsung(5999)
        # After pagination (page 1, size 2):
        {
            "商品ID": mock_products_all[1]["商品ID"],
            "商品名称": "旧笔记本",
            "商品描述": "一台二手的旧笔记本，性能良好。",
            "库存": 5,
            "价格": 2500.0,
            "发布时间": "2023-01-02T10:00:00.000000",
            "商品状态": "PendingReview",
            "发布者用户名": "user2",
            "商品类别": "Electronics",
            "主图URL": "http://example.com/old_laptop.jpg",
            "images": [],
            "总商品数": 2 # Use fixed value
        },
        {
            "商品ID": mock_products_all[0]["商品ID"],
            "商品名称": "测试手机",
            "商品描述": "一个很棒的测试手机",
            "库存": 50,
            "价格": 5999.0,
            "发布时间": "2023-01-01T10:00:00.000000",
            "商品状态": "Active",
            "发布者用户名": "user1",
            "商品类别": "Electronics",
            "主图URL": "http://example.com/test_phone.jpg",
            "images": [
                {"image_url": "http://example.com/test_phone_1.jpg", "sort_order": 0, "upload_time": mock_products_all[0]["images"][0]["upload_time"]},
                {"image_url": "http://example.com/test_phone_2.jpg", "sort_order": 1, "upload_time": mock_products_all[0]["images"][1]["upload_time"]}
            ],
            "总商品数": 2 # Use fixed value
        }
    ]
    assert response1.json() == expected_products_1
    mock_product_service.get_product_list.assert_any_call(
        ANY,
        "Electronics", # category_id (string)
        None, # status
        None, # keyword
        1000.00, # min_price
        7000.00, # max_price
        "Price", # order_by
        1, # page_number
        2, # page_size
    )

    # Test case 2: Filter by Status and Keyword, Paginate and Sort by PostTime DESC
    response2 = client.get("/api/v1/products", params={
        "status": "Active",
        "keyword": "手机",
        "page_number": 1,
        "page_size": 1,
        "order_by": "PostTime",
        # "sortOrder": "DESC" # Removed, as API doesn't support this directly
    })
    assert response2.status_code == status.HTTP_200_OK
    expected_products_2 = [
        # After filtering for Active, keyword='mouse', and sorting by PostTime DESC:
        # Original: Logitech MX Master 3 (Active, 'mouse' in name)
        # Filtered & Sorted:
        {
            "商品ID": mock_products_all[0]["商品ID"],
            "商品名称": "测试手机",
            "商品描述": "一个很棒的测试手机",
            "库存": 50,
            "价格": 5999.0,
            "发布时间": "2023-01-01T10:00:00.000000",
            "商品状态": "Active",
            "发布者用户名": "user1",
            "商品类别": "Electronics",
            "主图URL": "http://example.com/test_phone.jpg",
            "images": [
                {"image_url": "http://example.com/test_phone_1.jpg", "sort_order": 0, "upload_time": mock_products_all[0]["images"][0]["upload_time"]},
                {"image_url": "http://example.com/test_phone_2.jpg", "sort_order": 1, "upload_time": mock_products_all[0]["images"][1]["upload_time"]}
            ],
            "总商品数": 1 # Use fixed value
        }
    ]
    assert response2.json() == expected_products_2
    mock_product_service.get_product_list.assert_any_call(
        ANY,
        None, # category_id
        "Active", # status
        "手机", # keyword
        None, None, # min_price, max_price
        "PostTime", # order_by
        1, # page_number
        1, # page_size
    )

    # Test case 3: Filter by Category and Status, and Keyword
    response3 = client.get("/api/v1/products", params={
        "category_name": "Accessories", # Changed to category_name (string)
        "status": "Active",
        "keyword": "键盘"
    })
    assert response3.status_code == status.HTTP_200_OK
    expected_products_3 = [
        # After filtering for Books, Active, keyword='gatsby':
        # Original: The Great Gatsby (Books, Active, 'gatsby' in name)
        {
            "商品ID": mock_products_all[2]["商品ID"],
            "商品名称": "机械键盘",
            "商品描述": "手感极佳的机械键盘。",
            "库存": 20,
            "价格": 450.0,
            "发布时间": "2023-01-03T10:00:00.000000",
            "商品状态": "Active",
            "发布者用户名": "user1",
            "商品类别": "Accessories",
            "主图URL": "http://example.com/keyboard.jpg",
            "images": [],
            "总商品数": 1 # Use fixed value
        }
    ]
    assert response3.json() == expected_products_3
    mock_product_service.get_product_list.assert_any_call(
        ANY,
        "Accessories", # category_id (string)
        "Active", # status
        "键盘", # keyword
        None, None, # min_price, max_price
        'PostTime', 1, 10
    )