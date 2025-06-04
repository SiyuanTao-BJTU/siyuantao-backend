import pytest
import pytest_mock
from httpx import AsyncClient

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4, UUID
from datetime import datetime, timezone

from app.services.user_service import UserService
from app.dal.user_dal import UserDAL
from app.schemas.user_schemas import UserRegisterSchema, UserLoginSchema, UserPasswordUpdate, UserProfileUpdateSchema, UserStatusUpdateSchema, UserCreditAdjustmentSchema, UserResponseSchema # Import necessary schemas
from app.exceptions import NotFoundError, IntegrityError, DALError, AuthenticationError, ForbiddenError # Import necessary exceptions

# Mock Fixture for UserDAL
@pytest.fixture
def mock_user_dal(mocker: pytest_mock.MockerFixture): # Removed spec=UserDAL for flexibility after adding methods
    """Mock the UserDAL dependency."""
    # Create an AsyncMock instance for the UserDAL class methods
    mock_dal = AsyncMock()
    # Manually add methods if not using spec, or ensure spec is up-to-date
    mock_dal.create_user = AsyncMock() # Explicitly mock create_user
    mock_dal.get_user_by_id = AsyncMock() # Explicitly mock get_user_by_id (used in create_user service method)
    # Add other DAL methods as needed by the tests
    mock_dal.get_user_by_username_with_password = AsyncMock()
    mock_dal.update_user_profile = AsyncMock()
    mock_dal.update_user_password = AsyncMock()
    mock_dal.get_user_password_hash_by_id = AsyncMock()
    mock_dal.delete_user = AsyncMock()
    mock_dal.request_verification_link = AsyncMock()
    mock_dal.verify_email = AsyncMock()
    mock_dal.get_system_notifications_by_user_id = AsyncMock()
    mock_dal.mark_system_notification_as_read = AsyncMock()
    mock_dal.set_chat_message_visibility = AsyncMock()
    mock_dal.change_user_status = AsyncMock()
    mock_dal.adjust_user_credit = AsyncMock()
    mock_dal.get_all_users = AsyncMock()
    mock_dal._execute_query = AsyncMock() # Mock the internal method used by other DAL methods
    return mock_dal

# Fixture for UserService with Mocked DAL
@pytest.fixture
def user_service(mock_user_dal: AsyncMock) -> UserService:
    """Provides a UserService instance with a mocked UserDAL."""
    return UserService(user_dal=mock_user_dal)

# Mock Fixture for Database Connection
@pytest.fixture
def mock_db_connection(mocker: pytest_mock.MockerFixture) -> MagicMock:
    """Mock a database connection object."""
    # Use MagicMock for connection as it might have various attributes/methods used by DAL
    return MagicMock()

# Mock Fixture for app.utils.auth
@pytest.fixture
def mock_utils_auth(mocker: pytest_mock.MockerFixture):
    """Mock the utility functions in app.utils.auth."""
    mock_get_password_hash = mocker.patch('app.services.user_service.get_password_hash', return_value="hashed_password") # Patch where it's used in Service
    mock_verify_password = mocker.patch('app.services.user_service.verify_password', return_value=True) # Patch where it's used in Service
    mock_create_access_token = mocker.patch('app.services.user_service.create_access_token', return_value="mock_jwt_token") # Patch where it's used in Service
    return mock_get_password_hash, mock_verify_password, mock_create_access_token # Return mocks if needed for assertions

# --- UserService Unit Tests --- 

@pytest.mark.asyncio
async def test_create_user_success(user_service: UserService, mock_user_dal: AsyncMock, mock_db_connection: MagicMock, mock_utils_auth: tuple[MagicMock, MagicMock, MagicMock], mocker: pytest_mock.MockerFixture):
    # Arrange
    get_password_hash_mock = mock_utils_auth[0]
    
    # Updated user data without email, with phone_number
    user_data = UserRegisterSchema(
        username="testuser",
        password="securepassword",
        major="Computer Science",
        phone_number="1234567890",
    )
    
    hashed_password = "hashed_password_abc"
    get_password_hash_mock.return_value = hashed_password

    # Mock the DAL's create_user method to return a successful creation result.
    # The DAL's create_user calls get_user_by_id internally and returns the result.
    # Simulate the return value of get_user_by_id with Chinese keys as expected by _convert_dal_user_to_schema.
    created_user_dal_data = {
        "用户ID": uuid4(),
        "用户名": user_data.username,
        "账户状态": "Active",
        "信用分": 100,
        "是否管理员": False,
        "是否超级管理员": False, # Added missing key
        "是否已认证": False,
        "专业": user_data.major,
        "头像URL": None,
        "个人简介": None,
        "手机号码": user_data.phone_number,
        "注册时间": datetime.now(timezone.utc), # Use timezone-aware datetime
        "邮箱": None
    }
    mock_user_dal.create_user.return_value = created_user_dal_data # DAL create_user now returns the fetched data

    # Act
    created_user = await user_service.create_user(mock_db_connection, user_data)

    # Assert the returned user data is a UserResponseSchema instance and has expected values
    assert isinstance(created_user, UserResponseSchema)
    assert created_user.username == user_data.username
    assert created_user.email is None
    assert created_user.status == "Active"
    assert created_user.credit == 100
    assert created_user.is_staff is False
    assert created_user.is_super_admin is False # Assert is_super_admin
    assert created_user.is_verified is False
    assert created_user.major == user_data.major
    assert created_user.phone_number == user_data.phone_number
    assert isinstance(created_user.user_id, UUID)
    assert isinstance(created_user.join_time, datetime) and created_user.join_time.tzinfo is not None # Assert timezone-aware datetime type

    # Verify the DAL method was called with the correct data
    mock_user_dal.create_user.assert_called_once_with(
        mock_db_connection,
        user_data.username,
        hashed_password,
        user_data.phone_number,
        major=user_data.major
    )
    # get_user_profile_by_id should NOT be called directly by the service's create_user method anymore
    mock_user_dal.get_user_by_id.assert_not_called()

@pytest.mark.asyncio
async def test_create_user_duplicate_username(user_service: UserService, mock_user_dal: AsyncMock, mock_db_connection: MagicMock, mock_utils_auth: tuple[MagicMock, MagicMock, MagicMock], mocker: pytest_mock.MockerFixture):
    # Arrange
    get_password_hash_mock = mock_utils_auth[0]

    # Updated user data without email, with phone_number
    user_data = UserRegisterSchema(
        username="existinguser", # Use a username that is simulated to exist
        password="securepassword",
        major="Physics",
        phone_number="9876543210", # Added phone_number
    )

    hashed_password = "hashed_password_def"
    get_password_hash_mock.return_value = hashed_password

    # Configure the DAL mock to raise IntegrityError when create_user is called
    # Simulate duplicate username error from the DAL layer
    mock_user_dal.create_user.side_effect = IntegrityError("Duplicate username")

    # Act & Assert
    # Expect an IntegrityError when calling the service method
    with pytest.raises(IntegrityError, match="Duplicate username") as excinfo:
        await user_service.create_user(mock_db_connection, user_data)

    # Assert the error message (adjust based on expected error message from DAL)
    assert "Duplicate username" in str(excinfo.value)

    # Assert that get_password_hash was called correctly
    get_password_hash_mock.assert_called_once_with(user_data.password)

    # Assert that user_dal.create_user was called with the correct parameters
    # The order should match the DAL method signature: username, hashed_password, phone_number, major (optional)
    mock_user_dal.create_user.assert_called_once_with(
        mock_db_connection,
        user_data.username,
        hashed_password,
        user_data.phone_number, # Added phone_number
        major=user_data.major,       # major is optional - Use keyword argument
    )
    
    # Ensure get_user_profile_by_id was NOT called
    mock_user_dal.get_user_profile_by_id.assert_not_called()

@pytest.mark.asyncio
async def test_create_user_dal_error(user_service: UserService, mock_user_dal: AsyncMock, mock_db_connection: MagicMock, mock_utils_auth: tuple[MagicMock, MagicMock, MagicMock], mocker: pytest_mock.MockerFixture):
    # Arrange
    # Updated user data with phone_number
    user_data = UserRegisterSchema(
        username="error_user",
        password="password",
        phone_number="1112223333", # Added phone_number
        major="Chemistry" # Optional field
    )

    hashed_password = "hashed_password_error"
    mock_utils_auth[0].return_value = hashed_password # Mock get_password_hash

    # Configure the DAL mock to raise a general DALError when create_user is called
    mock_user_dal.create_user.side_effect = DALError("Simulated database error")

    # Act & Assert
    # Expect a DALError to be raised by the service method
    with pytest.raises(DALError, match="数据库错误：Simulated database error") as excinfo: # Match the error message wrapped by service
        await user_service.create_user(mock_db_connection, user_data)

    # Assert that get_password_hash was called correctly
    mock_utils_auth[0].assert_called_once_with(user_data.password)

    # Assert that user_dal.create_user was called with the correct parameters
    mock_user_dal.create_user.assert_called_once_with(
        mock_db_connection,
        user_data.username,
        hashed_password,
        user_data.phone_number,
        major=user_data.major # Use keyword argument
    )

@pytest.mark.asyncio
async def test_get_user_profile_by_id_found(user_service: UserService, mock_user_dal: AsyncMock, mock_db_connection: MagicMock, mock_utils_auth: tuple[MagicMock, MagicMock, MagicMock], mocker: pytest_mock.MockerFixture):
    test_user_id = uuid4()
    # Simulate DAL returning user data with Chinese keys as expected by _convert_dal_user_to_schema
    dal_return_data = {
        "用户ID": test_user_id,
        "用户名": "testuser",
        "账户状态": "Active",
        "信用分": 100,
        "是否管理员": False,
        "是否超级管理员": False, # Added missing key
        "是否已认证": True,
        "专业": "Computer Science",
        "头像URL": "http://example.com/avatar.jpg",
        "个人简介": "A test user.",
        "手机号码": "1234567890",
        "注册时间": datetime(2023, 1, 1, 12, 0, 0, tzinfo=timezone.utc), # Use timezone-aware datetime
        "邮箱": "test@example.com"
    }
    mock_user_dal.get_user_by_id.return_value = dal_return_data

    # Call the service function
    user_profile = await user_service.get_user_profile_by_id(mock_db_connection, test_user_id)

    # Assertions on the service function's return value
    assert isinstance(user_profile, UserResponseSchema)
    assert user_profile.user_id == test_user_id
    assert user_profile.username == "testuser"
    assert user_profile.email == "test@example.com"
    assert user_profile.status == "Active"
    assert user_profile.credit == 100
    assert user_profile.is_staff is False
    assert user_profile.is_super_admin is False # Assert is_super_admin
    assert user_profile.is_verified is True
    assert user_profile.major == "Computer Science"
    assert user_profile.avatar_url == "http://example.com/avatar.jpg"
    assert user_profile.bio == "A test user."
    assert user_profile.phone_number == "1234567890"
    assert isinstance(user_profile.join_time, datetime) and user_profile.join_time.tzinfo is not None # Assert timezone-aware datetime type
    assert user_profile.join_time == datetime(2023, 1, 1, 12, 0, 0, tzinfo=timezone.utc) # Compare with timezone-aware datetime object

    # Verify DAL method was called with correct arguments
    mock_user_dal.get_user_by_id.assert_called_once_with(
        mock_db_connection,
        test_user_id
    )

@pytest.mark.asyncio
async def test_get_user_profile_by_id_not_found(user_service: UserService, mock_user_dal: AsyncMock, mock_db_connection: MagicMock, mock_utils_auth: tuple[MagicMock, MagicMock, MagicMock], mocker: pytest_mock.MockerFixture):
    test_user_id = uuid4()
    # Simulate DAL returning None
    mock_user_dal.get_user_by_id.return_value = None

    # Call the service function and assert it raises NotFoundError
    with pytest.raises(NotFoundError, match="User not found."):
        await user_service.get_user_profile_by_id(mock_db_connection, test_user_id)

    # Verify DAL method was called
    mock_user_dal.get_user_by_id.assert_called_once_with(mock_db_connection, test_user_id)

@pytest.mark.asyncio
async def test_authenticate_user_and_create_token_success(user_service: UserService, mock_user_dal: AsyncMock, mock_db_connection: MagicMock, mock_utils_auth: tuple[MagicMock, MagicMock, MagicMock], mocker: pytest_mock.MockerFixture):
    username = "loginuser"
    password = "correctpassword"
    test_user_id = uuid4()
    
    # Simulate DAL returning user data with password hash
    dal_return_data = {
        "UserID": test_user_id,
        "UserName": username,
        "Password": "hashed_password", # Must match the return value of mock_utils_auth[0]
        "Status": "Active",
        "IsStaff": False,
        "IsVerified": True,
        # Include other fields expected by token creation or later steps if necessary
    }
    mock_user_dal.get_user_by_username_with_password.return_value = dal_return_data

    # Configure mock_utils_auth[1] (verify_password) to return True
    mock_utils_auth[1].return_value = True

    # Call the service function
    token = await user_service.authenticate_user_and_create_token(mock_db_connection, username, password)

    # Assertions
    assert isinstance(token, str)
    assert token == "mock_jwt_token" # Should match the return value of mock_utils_auth[2]

    # Verify DAL method was called
    mock_user_dal.get_user_by_username_with_password.assert_called_once_with(mock_db_connection, username)
    # Verify password verification utility was called
    mock_utils_auth[1].assert_called_once_with(password, "hashed_password")
    # Verify token creation utility was called
    # Check the data passed to create_access_token
    mock_utils_auth[2].assert_called_once()
    # Check the first argument (data payload) of the create_access_token call
    called_args, called_kwargs = mock_utils_auth[2].call_args
    token_payload = called_kwargs.get('data') or called_args[0]
    assert token_payload["user_id"] == str(test_user_id)
    assert token_payload["is_staff"] is False
    assert token_payload["is_verified"] is True
    # Check the second argument (expires_delta)
    assert "expires_delta" in called_kwargs or len(called_args) > 1 # Ensure expires_delta is passed

@pytest.mark.asyncio
async def test_authenticate_user_and_create_token_invalid_password(user_service: UserService, mock_user_dal: AsyncMock, mock_db_connection: MagicMock, mock_utils_auth: tuple[MagicMock, MagicMock, MagicMock], mocker: pytest_mock.MockerFixture):
    username = "loginuser"
    password = "wrongpassword"
    test_user_id = uuid4()

    # Simulate DAL returning user data with password hash
    dal_return_data = {
        "UserID": test_user_id,
        "UserName": username,
        "Password": "hashed_password",
        "Status": "Active",
        "IsStaff": False,
        "IsVerified": True,
    }
    mock_user_dal.get_user_by_username_with_password.return_value = dal_return_data

    # Configure mock_utils_auth[1] (verify_password) to return False
    mock_utils_auth[1].return_value = False

    # Call the service function and assert it raises AuthenticationError
    with pytest.raises(AuthenticationError, match="用户名或密码不正确"):
        await user_service.authenticate_user_and_create_token(mock_db_connection, username, password)

    # Verify DAL method was called
    mock_user_dal.get_user_by_username_with_password.assert_called_once_with(mock_db_connection, username)
    # Verify password verification utility was called
    mock_utils_auth[1].assert_called_once_with(password, "hashed_password")
    # Verify token creation utility was NOT called
    mock_utils_auth[2].assert_not_called()

@pytest.mark.asyncio
async def test_authenticate_user_and_create_token_user_not_found(user_service: UserService, mock_user_dal: AsyncMock, mock_db_connection: MagicMock, mock_utils_auth: tuple[MagicMock, MagicMock, MagicMock], mocker: pytest_mock.MockerFixture):
    username = "nonexistentuser"
    password = "anypassword"

    # Simulate DAL returning None (user not found)
    mock_user_dal.get_user_by_username_with_password.return_value = None

    # Call the service function and assert it raises AuthenticationError
    with pytest.raises(AuthenticationError, match="用户不存在。"):
        await user_service.authenticate_user_and_create_token(mock_db_connection, username, password)

    # Verify DAL method was called
    mock_user_dal.get_user_by_username_with_password.assert_called_once_with(mock_db_connection, username)
    # Verify password verification utility was NOT called
    mock_utils_auth[1].assert_not_called()
    # Verify token creation utility was NOT called
    mock_utils_auth[2].assert_not_called()

@pytest.mark.asyncio
async def test_authenticate_user_and_create_token_disabled_account(user_service: UserService, mock_user_dal: AsyncMock, mock_db_connection: MagicMock, mock_utils_auth: tuple[MagicMock, MagicMock, MagicMock], mocker: pytest_mock.MockerFixture):
    username = "disableduser"
    password = "correctpassword"
    test_user_id = uuid4()

    # Simulate DAL returning user data with status Disabled
    dal_return_data = {
        "UserID": test_user_id,
        "UserName": username,
        "Password": "hashed_password",
        "Status": "Disabled", # User is disabled
        "IsStaff": False,
        "IsVerified": True,
    }
    mock_user_dal.get_user_by_username_with_password.return_value = dal_return_data

    # Configure mock_utils_auth[1] (verify_password) to return True
    mock_utils_auth[1].return_value = True

    # Call the service function and assert it raises ForbiddenError
    with pytest.raises(ForbiddenError, match="账户已被禁用。"):
        await user_service.authenticate_user_and_create_token(mock_db_connection, username, password)

    # Verify DAL method was called
    mock_user_dal.get_user_by_username_with_password.assert_called_once_with(mock_db_connection, username)
    # Verify password verification utility was called
    mock_utils_auth[1].assert_called_once_with(password, "hashed_password")
    # Verify token creation utility was NOT called
    mock_utils_auth[2].assert_not_called()

@pytest.mark.asyncio
async def test_update_user_profile_success_with_updates(user_service: UserService, mock_user_dal: AsyncMock, mock_db_connection: MagicMock, mock_utils_auth: tuple[MagicMock, MagicMock, MagicMock], mocker: pytest_mock.MockerFixture):
    # Arrange
    test_user_id = uuid4()
    update_data = UserProfileUpdateSchema(
        major="Updated Major",
        bio="New bio content",
        phone_number="9876543210",
        avatar_url="http://example.com/updated_avatar.jpg",
        # email="updated@example.com" # Assuming email update is not part of this schema
    )
    
    # Simulate DAL returning the updated user data with Chinese keys
    updated_dal_data = {
        "用户ID": test_user_id,
        "用户名": "testuser",
        "账户状态": "Active",
        "信用分": 100,
        "是否管理员": False,
        "是否超级管理员": False, # Added missing key
        "是否已认证": True,
        "专业": update_data.major,
        "头像URL": update_data.avatar_url,
        "个人简介": update_data.bio,
        "手机号码": update_data.phone_number,
        "注册时间": datetime(2023, 1, 1, 12, 0, 0, tzinfo=timezone.utc), # Use timezone-aware datetime
        "邮箱": "test@example.com" # Email remains unchanged in this test
    }
    # The update_user_profile DAL method now returns the updated data directly
    mock_user_dal.update_user_profile.return_value = updated_dal_data

    # Act
    updated_user = await user_service.update_user_profile(mock_db_connection, test_user_id, update_data)

    # Assertions
    assert isinstance(updated_user, UserResponseSchema)
    assert updated_user.user_id == test_user_id
    assert updated_user.major == update_data.major
    assert updated_user.bio == update_data.bio
    assert updated_user.phone_number == update_data.phone_number
    assert updated_user.avatar_url == update_data.avatar_url
    # Assert other fields remain unchanged
    assert updated_user.username == "testuser"
    assert updated_user.email == "test@example.com"
    assert updated_user.status == "Active"

    # Verify DAL method was called with correct arguments
    mock_user_dal.update_user_profile.assert_called_once_with(
        mock_db_connection,
        test_user_id,
        major=update_data.major,
        avatar_url=update_data.avatar_url,
        bio=update_data.bio,
        phone_number=update_data.phone_number,
        email=None # Email is None as it's not updated via this schema/method
    )

@pytest.mark.asyncio
async def test_update_user_profile_success_no_updates(user_service: UserService, mock_user_dal: AsyncMock, mock_db_connection: MagicMock, mock_utils_auth: tuple[MagicMock, MagicMock, MagicMock], mocker: pytest_mock.MockerFixture):
    # Arrange
    test_user_id = uuid4()
    # Simulate no updates being provided in the schema
    update_data = UserProfileUpdateSchema()

    # Simulate DAL returning the current user data (as no updates were applied)
    # Use Chinese keys
    current_dal_data = {
        "用户ID": test_user_id,
        "用户名": "testuser_no_update",
        "账户状态": "Active",
        "信用分": 150,
        "是否管理员": False,
        "是否超级管理员": False, # Added missing key
        "是否已认证": True,
        "专业": "Original Major",
        "头像URL": "http://example.com/original_avatar.jpg",
        "个人简介": "Original bio",
        "手机号码": "1111111111",
        "注册时间": datetime(2022, 5, 10, 9, 30, 0, tzinfo=timezone.utc), # Use timezone-aware datetime
        "邮箱": "original@example.com"
    }
    # When no update data is provided, service calls get_user_profile_by_id
    mock_user_dal.get_user_by_id.return_value = current_dal_data
    # update_user_profile should not be called in this case
    mock_user_dal.update_user_profile.assert_not_called()

    # Act
    updated_user = await user_service.update_user_profile(mock_db_connection, test_user_id, update_data)

    # Assertions
    assert isinstance(updated_user, UserResponseSchema)
    assert updated_user.user_id == test_user_id
    # Assert that fields retain their original values
    assert updated_user.major == "Original Major"
    assert updated_user.bio == "Original bio"
    assert updated_user.phone_number == "1111111111"
    assert updated_user.avatar_url == "http://example.com/original_avatar.jpg"
    # Assert other fields
    assert updated_user.username == "testuser_no_update"
    assert updated_user.email == "original@example.com"
    assert updated_user.status == "Active"

    # Verify get_user_by_id was called to fetch current profile
    mock_user_dal.get_user_by_id.assert_called_once_with(mock_db_connection, test_user_id)
    # Verify update_user_profile was NOT called
    mock_user_dal.update_user_profile.assert_not_called()

@pytest.mark.asyncio
async def test_update_user_profile_not_found(user_service: UserService, mock_user_dal: AsyncMock, mock_db_connection: MagicMock, mock_utils_auth: tuple[MagicMock, MagicMock, MagicMock], mocker: pytest_mock.MockerFixture):
    test_user_id = uuid4()
    update_data = UserProfileUpdateSchema(major="New Major")

    # Simulate DAL raising NotFoundError
    mock_user_dal.update_user_profile.side_effect = NotFoundError(f"User with ID {test_user_id} not found for update.")

    # Call the service function and assert it raises NotFoundError
    with pytest.raises(NotFoundError, match="用户未找到。"):
        await user_service.update_user_profile(mock_db_connection, test_user_id, update_data)

    # Verify DAL method was called
    mock_user_dal.update_user_profile.assert_called_once_with(
        mock_db_connection,
        test_user_id,
        major="New Major",
        avatar_url=mocker.ANY,
        bio=mocker.ANY,
        phone_number=mocker.ANY
    )

@pytest.mark.asyncio
async def test_update_user_profile_duplicate_phone(user_service: UserService, mock_user_dal: AsyncMock, mock_db_connection: MagicMock, mock_utils_auth: tuple[MagicMock, MagicMock, MagicMock], mocker: pytest_mock.MockerFixture):
    test_user_id = uuid4()
    update_data = UserProfileUpdateSchema(phone_number="999888777")

    # Simulate DAL raising IntegrityError
    mock_user_dal.update_user_profile.side_effect = IntegrityError("Phone number already in use by another user.")

    # Call the service function and assert it raises IntegrityError
    with pytest.raises(IntegrityError, match="手机号已被注册。"):
        await user_service.update_user_profile(mock_db_connection, test_user_id, update_data)

    # Verify DAL method was called
    mock_user_dal.update_user_profile.assert_called_once_with(
        mock_db_connection,
        test_user_id,
        major=mocker.ANY,
        avatar_url=mocker.ANY,
        bio=mocker.ANY,
        phone_number="999888777"
    )

@pytest.mark.asyncio
async def test_update_user_password_success(user_service: UserService, mock_user_dal: AsyncMock, mock_db_connection: MagicMock, mock_utils_auth: tuple[MagicMock, MagicMock, MagicMock], mocker: pytest_mock.MockerFixture):
    # Arrange
    test_user_id = uuid4()
    old_password = "oldpassword"
    new_password = "newpassword"
    password_update_data = UserPasswordUpdate(
        old_password=old_password,
        new_password=new_password
    )

    # Simulate DAL returning the current hashed password
    mock_user_dal.get_user_password_hash_by_id.return_value = "old_hashed_password"

    # Simulate verify_password returning True (old password is correct)
    mock_utils_auth[1].return_value = True

    # Simulate get_password_hash returning the new hashed password
    mock_utils_auth[0].return_value = "new_hashed_password_from_util"

    # Simulate DAL returning True for successful password update
    mock_user_dal.update_user_password.return_value = True

    # Act
    update_success = await user_service.update_user_password(mock_db_connection, test_user_id, password_update_data)

    # Assertions
    assert update_success is True

    # Verify DAL methods and utility functions were called with correct arguments
    mock_user_dal.get_user_password_hash_by_id.assert_called_once_with(mock_db_connection, test_user_id)
    mock_utils_auth[1].assert_called_once_with(old_password, "old_hashed_password")
    mock_utils_auth[0].assert_called_once_with(new_password)
    mock_user_dal.update_user_password.assert_called_once_with(
        mock_db_connection,
        test_user_id,
        "new_hashed_password_from_util" # Should be the hashed new password
    )

@pytest.mark.asyncio
async def test_update_user_password_wrong_old_password(user_service: UserService, mock_user_dal: AsyncMock, mock_db_connection: MagicMock, mock_utils_auth: tuple[MagicMock, MagicMock, MagicMock], mocker: pytest_mock.MockerFixture):
    # Arrange
    test_user_id = uuid4()
    old_password = "wrongpassword"
    new_password = "newpassword"
    password_update_data = UserPasswordUpdate(
        old_password=old_password,
        new_password=new_password
    )

    # Simulate DAL returning the current hashed password
    mock_user_dal.get_user_password_hash_by_id.return_value = "correct_old_hashed_password"

    # Simulate verify_password returning False (old password is incorrect)
    mock_utils_auth[1].return_value = False

    # Act & Assert
    # Expect an AuthenticationError to be raised
    with pytest.raises(AuthenticationError, match="旧密码不正确。"):
        await user_service.update_user_password(mock_db_connection, test_user_id, password_update_data)

    # Verify methods were called
    mock_user_dal.get_user_password_hash_by_id.assert_called_once_with(mock_db_connection, test_user_id)
    mock_utils_auth[1].assert_called_once_with(old_password, "correct_old_hashed_password")
    # Ensure other methods were NOT called
    mock_utils_auth[0].assert_not_called()
    mock_user_dal.update_user_password.assert_not_called()

@pytest.mark.asyncio
async def test_update_user_password_user_not_found(user_service: UserService, mock_user_dal: AsyncMock, mock_db_connection: MagicMock, mock_utils_auth: tuple[MagicMock, MagicMock, MagicMock], mocker: pytest_mock.MockerFixture):
    # Arrange
    test_user_id = uuid4()
    old_password = "oldpassword"
    new_password = "newpassword"
    password_update_data = UserPasswordUpdate(
        old_password=old_password,
        new_password=new_password
    )

    # Simulate DAL returning None for the password hash (user not found)
    mock_user_dal.get_user_password_hash_by_id.return_value = None

    # Act & Assert
    # Expect a NotFoundError to be raised
    with pytest.raises(NotFoundError, match="用户未找到。"):
        await user_service.update_user_password(mock_db_connection, test_user_id, password_update_data)

    # Verify get_user_password_hash_by_id was called
    mock_user_dal.get_user_password_hash_by_id.assert_called_once_with(mock_db_connection, test_user_id)
    # Ensure other methods were NOT called
    mock_utils_auth[1].assert_not_called()
    mock_utils_auth[0].assert_not_called()
    mock_user_dal.update_user_password.assert_not_called()

@pytest.mark.asyncio
async def test_delete_user_success(user_service: UserService, mock_user_dal: AsyncMock, mock_db_connection: MagicMock, mock_utils_auth: tuple[MagicMock, MagicMock, MagicMock], mocker: pytest_mock.MockerFixture):
    test_user_id = uuid4()

    # Simulate DAL delete_user returning True on success
    mock_user_dal.delete_user.return_value = True

    # Act
    delete_success = await user_service.delete_user(mock_db_connection, test_user_id)

    # Assertions
    assert delete_success is True

    # Verify DAL method was called
    mock_user_dal.delete_user.assert_called_once_with(mock_db_connection, test_user_id)

@pytest.mark.asyncio
async def test_delete_user_not_found(user_service: UserService, mock_user_dal: AsyncMock, mock_db_connection: MagicMock, mock_utils_auth: tuple[MagicMock, MagicMock, MagicMock], mocker: pytest_mock.MockerFixture):
    test_user_id = uuid4()

    # Simulate DAL delete_user raising NotFoundError
    mock_user_dal.delete_user.side_effect = NotFoundError(f"User with ID {test_user_id} not found for deletion.")

    # Act & Assert
    with pytest.raises(NotFoundError, match="用户不存在。"):
        await user_service.delete_user(mock_db_connection, test_user_id)

    # Verify DAL method was called
    mock_user_dal.delete_user.assert_called_once_with(mock_db_connection, test_user_id)

@pytest.mark.asyncio
async def test_request_verification_email_success(user_service: UserService, mock_user_dal: AsyncMock, mock_db_connection: MagicMock, mock_utils_auth: tuple[MagicMock, MagicMock, MagicMock], mocker: pytest_mock.MockerFixture):
    test_user_id = uuid4()
    test_email = "test@example.com"

    # Simulate DAL returning success result for request_verification_link
    # This result might contain token, user_id etc. The service layer just passes it through.
    dal_return_data = {"VerificationToken": "mock_token", "UserID": str(test_user_id), "IsNewUser": False}
    mock_user_dal.request_verification_link.return_value = dal_return_data

    # Act
    result = await user_service.request_verification_email(mock_db_connection, user_id=test_user_id, email=test_email) # Pass email argument

    # Assertions
    assert result == dal_return_data

    # Verify DAL method was called with correct arguments
    mock_user_dal.request_verification_link.assert_called_once_with(mock_db_connection, user_id=test_user_id, email=test_email) # Verify email is passed

@pytest.mark.asyncio
async def test_request_verification_email_disabled_account(user_service: UserService, mock_user_dal: AsyncMock, mock_db_connection: MagicMock, mock_utils_auth: tuple[MagicMock, MagicMock, MagicMock], mocker: pytest_mock.MockerFixture):
    test_user_id = uuid4()
    test_email = "disabled@example.com"

    # Simulate DAL raising ForbiddenError for disabled account
    mock_user_dal.request_verification_link.side_effect = ForbiddenError("Account is disabled.")

    # Act & Assert
    with pytest.raises(ForbiddenError, match="账户已被禁用。"):
        await user_service.request_verification_email(mock_db_connection, user_id=test_user_id, email=test_email) # Pass email argument

    # Verify DAL method was called
    mock_user_dal.request_verification_link.assert_called_once_with(mock_db_connection, user_id=test_user_id, email=test_email) # Verify email is passed

@pytest.mark.asyncio
async def test_verify_email_success(user_service: UserService, mock_user_dal: AsyncMock, mock_db_connection: MagicMock, mock_utils_auth: tuple[MagicMock, MagicMock, MagicMock], mocker: pytest_mock.MockerFixture):
    test_token = uuid4()

    # Simulate DAL returning success result for verify_email
    # This result might contain UserID, IsVerified etc. The service layer just passes it through.
    dal_return_data = {"UserID": str(uuid4()), "IsVerified": True}
    mock_user_dal.verify_email.return_value = dal_return_data

    # Act
    result = await user_service.verify_email(mock_db_connection, test_token)

    # Assertions
    assert result == dal_return_data

    # Verify DAL method was called
    mock_user_dal.verify_email.assert_called_once_with(mock_db_connection, test_token)

@pytest.mark.asyncio
async def test_verify_email_invalid_or_expired_token(user_service: UserService, mock_user_dal: AsyncMock, mock_db_connection: MagicMock, mock_utils_auth: tuple[MagicMock, MagicMock, MagicMock], mocker: pytest_mock.MockerFixture):
    test_token = uuid4()

    # Simulate DAL raising DALError for invalid/expired token
    mock_user_dal.verify_email.side_effect = DALError("邮箱验证失败: 魔术链接无效或已过期。")

    # Act & Assert
    with pytest.raises(DALError, match="邮箱验证失败: 魔术链接无效或已过期。"):
        await user_service.verify_email(mock_db_connection, test_token)

    # Verify DAL method was called
    mock_user_dal.verify_email.assert_called_once_with(mock_db_connection, test_token)

@pytest.mark.asyncio
async def test_verify_email_disabled_account(user_service: UserService, mock_user_dal: AsyncMock, mock_db_connection: MagicMock, mock_utils_auth: tuple[MagicMock, MagicMock, MagicMock], mocker: pytest_mock.MockerFixture):
    test_token = uuid4()

    # Simulate DAL raising ForbiddenError for disabled account
    mock_user_dal.verify_email.side_effect = ForbiddenError("邮箱验证失败: 账户已被禁用。")

    # Act & Assert
    with pytest.raises(ForbiddenError, match="邮箱验证失败: 账户已被禁用。"):
        await user_service.verify_email(mock_db_connection, test_token)

    # Verify DAL method was called
    mock_user_dal.verify_email.assert_called_once_with(mock_db_connection, test_token)

@pytest.mark.asyncio
async def test_get_system_notifications_success(user_service: UserService, mock_user_dal: AsyncMock, mock_db_connection: MagicMock, mock_utils_auth: tuple[MagicMock, MagicMock, MagicMock], mocker: pytest_mock.MockerFixture):
    test_user_id = uuid4()
    # Simulate DAL returning a list of notification dictionaries
    dal_return_data = [
        {"NotificationID": uuid4(), "UserID": test_user_id, "Message": "Test notification 1", "IsRead": False, "CreatedAt": datetime.now(timezone.utc)},
        {"NotificationID": uuid4(), "UserID": test_user_id, "Message": "Test notification 2", "IsRead": True, "CreatedAt": datetime.now(timezone.utc)},
    ]
    mock_user_dal.get_system_notifications_by_user_id.return_value = dal_return_data

    # Act
    notifications = await user_service.get_system_notifications(mock_db_connection, test_user_id)

    # Assertions
    assert isinstance(notifications, list)
    assert len(notifications) == len(dal_return_data)
    # Further assertions on the structure and content of notifications if needed
    assert notifications == dal_return_data # Assuming service passes through the raw dicts for now

    # Verify DAL method was called
    mock_user_dal.get_system_notifications_by_user_id.assert_called_once_with(mock_db_connection, test_user_id)

@pytest.mark.asyncio
async def test_get_system_notifications_no_notifications(user_service: UserService, mock_user_dal: AsyncMock, mock_db_connection: MagicMock, mock_utils_auth: tuple[MagicMock, MagicMock, MagicMock], mocker: pytest_mock.MockerFixture):
    test_user_id = uuid4()
    # Simulate DAL returning an empty list
    mock_user_dal.get_system_notifications_by_user_id.return_value = []

    # Act
    notifications = await user_service.get_system_notifications(mock_db_connection, test_user_id)

    # Assertions
    assert isinstance(notifications, list)
    assert len(notifications) == 0
    assert notifications == []

    # Verify DAL method was called
    mock_user_dal.get_system_notifications_by_user_id.assert_called_once_with(mock_db_connection, test_user_id)

@pytest.mark.asyncio
async def test_mark_system_notification_as_read_success(user_service: UserService, mock_user_dal: AsyncMock, mock_db_connection: MagicMock, mock_utils_auth: tuple[MagicMock, MagicMock, MagicMock], mocker: pytest_mock.MockerFixture):
    test_notification_id = uuid4()
    test_user_id = uuid4()

    # Simulate DAL returning True for success
    mock_user_dal.mark_system_notification_as_read.return_value = True

    # Act
    success = await user_service.mark_system_notification_as_read(mock_db_connection, test_notification_id, test_user_id)

    # Assertions
    assert success is True

    # Verify DAL method was called
    mock_user_dal.mark_system_notification_as_read.assert_called_once_with(mock_db_connection, test_notification_id, test_user_id)

@pytest.mark.asyncio
async def test_mark_system_notification_as_read_not_found(user_service: UserService, mock_user_dal: AsyncMock, mock_db_connection: MagicMock, mock_utils_auth: tuple[MagicMock, MagicMock, MagicMock], mocker: pytest_mock.MockerFixture):
    test_notification_id = uuid4()
    test_user_id = uuid4()

    # Simulate DAL returning False (indicating not found or not owned)
    mock_user_dal.mark_system_notification_as_read.return_value = False

    # Act
    success = await user_service.mark_system_notification_as_read(mock_db_connection, test_notification_id, test_user_id)

    # Assertions - Service should return False if DAL returns False
    assert success is False

    # Verify DAL method was called
    mock_user_dal.mark_system_notification_as_read.assert_called_once_with(mock_db_connection, test_notification_id, test_user_id)

@pytest.mark.asyncio
async def test_mark_system_notification_as_read_forbidden(user_service: UserService, mock_user_dal: AsyncMock, mock_db_connection: MagicMock, mock_utils_auth: tuple[MagicMock, MagicMock, MagicMock], mocker: pytest_mock.MockerFixture):
    test_notification_id = uuid4()
    test_user_id = uuid4()

    # Simulate DAL raising DALError which Service catches and re-raises as DALError
    # Updated to simulate DAL returning False and service logic handling it as not found/forbidden scenario now
    mock_user_dal.mark_system_notification_as_read.return_value = False

    # Act
    success = await user_service.mark_system_notification_as_read(mock_db_connection, test_notification_id, test_user_id)

    # Assertions - Service should return False based on the new logic
    assert success is False

    # Verify DAL method was called
    mock_user_dal.mark_system_notification_as_read.assert_called_once_with(mock_db_connection, test_notification_id, test_user_id)

@pytest.mark.asyncio
async def test_change_user_status_success(user_service: UserService, mock_user_dal: AsyncMock, mock_db_connection: MagicMock, mock_utils_auth: tuple[MagicMock, MagicMock, MagicMock], mocker: pytest_mock.MockerFixture):
    test_user_id = uuid4()
    test_admin_id = uuid4()
    new_status = "Disabled"

    # Simulate DAL returning True for success
    mock_user_dal.change_user_status.return_value = True

    # Act
    success = await user_service.change_user_status(mock_db_connection, test_user_id, new_status, test_admin_id)

    # Assertions
    assert success is True

    # Verify DAL method was called
    mock_user_dal.change_user_status.assert_called_once_with(mock_db_connection, test_user_id, new_status, test_admin_id)

@pytest.mark.asyncio
async def test_adjust_user_credit_success(user_service: UserService, mock_user_dal: AsyncMock, mock_db_connection: MagicMock, mock_utils_auth: tuple[MagicMock, MagicMock, MagicMock], mocker: pytest_mock.MockerFixture):
    test_user_id = uuid4()
    test_admin_id = uuid4()
    credit_adjustment = 50
    reason = "Reward for good behavior"

    # Simulate DAL returning True for success
    mock_user_dal.adjust_user_credit.return_value = True

    # Act
    success = await user_service.adjust_user_credit(mock_db_connection, test_user_id, credit_adjustment, test_admin_id, reason)

    # Assertions
    assert success is True

    # Verify DAL method was called
    mock_user_dal.adjust_user_credit.assert_called_once_with(mock_db_connection, test_user_id, credit_adjustment, test_admin_id, reason)

@pytest.mark.asyncio
async def test_get_all_users_success(user_service: UserService, mock_user_dal: AsyncMock, mock_db_connection: MagicMock, mock_utils_auth: tuple[MagicMock, MagicMock, MagicMock], mocker: pytest_mock.MockerFixture):
    test_admin_id = uuid4()
    # Simulate DAL returning a list of user dictionaries with Chinese keys
    dal_return_data = [
        {
            "用户ID": uuid4(),
            "用户名": "user1",
            "账户状态": "Active",
            "信用分": 100,
            "是否管理员": False,
            "是否超级管理员": False, # Added missing key
            "是否已认证": True,
            "专业": "Arts",
            "头像URL": None,
            "个人简介": None,
            "手机号码": "111",
            "注册时间": datetime.now(timezone.utc),
            "邮箱": None
        },
        {
            "用户ID": uuid4(),
            "用户名": "admin1",
            "账户状态": "Active",
            "信用分": 200,
            "是否管理员": True,
            "是否超级管理员": False, # Added missing key
            "是否已认证": True,
            "专业": "Science",
            "头像URL": "url",
            "个人简介": "bio",
            "手机号码": "222",
            "注册时间": datetime.now(timezone.utc),
            "邮箱": "admin@example.com"
        },
    ]
    mock_user_dal.get_all_users.return_value = dal_return_data

    # Act
    users = await user_service.get_all_users(mock_db_connection, test_admin_id)

    # Assertions
    assert isinstance(users, list)
    assert len(users) == len(dal_return_data)
    # Assert that each item in the list is a UserResponseSchema instance
    for user in users:
        assert isinstance(user, UserResponseSchema)

    # Verify DAL method was called
    mock_user_dal.get_all_users.assert_called_once_with(mock_db_connection, test_admin_id)

@pytest.mark.asyncio
async def test_admin_get_all_users_forbidden(user_service: UserService, mock_user_dal: AsyncMock, mock_db_connection: MagicMock, mock_utils_auth: tuple[MagicMock, MagicMock, MagicMock], mocker: pytest_mock.MockerFixture):
    test_admin_id = uuid4()

    # Simulate DAL raising ForbiddenError
    mock_user_dal.get_all_users.side_effect = ForbiddenError("只有超级管理员可以查看所有用户。")

    # Act & Assert
    with pytest.raises(ForbiddenError, match="只有超级管理员可以查看所有用户。"):
        await user_service.get_all_users(mock_db_connection, test_admin_id)

    # Verify DAL method was called
    mock_user_dal.get_all_users.assert_called_once_with(mock_db_connection, test_admin_id)

@pytest.mark.asyncio
async def test_update_user_avatar_success(user_service: UserService, mock_user_dal: AsyncMock, mock_db_connection: MagicMock, mock_utils_auth: tuple[MagicMock, MagicMock, MagicMock], mocker: pytest_mock.MockerFixture):
    test_user_id = uuid4()
    new_avatar_url = "http://example.com/new_avatar.png"

    # Simulate DAL returning the updated user data with Chinese keys
    updated_dal_data = {
        "用户ID": test_user_id,
        "用户名": "avatar_user",
        "账户状态": "Active",
        "信用分": 100,
        "是否管理员": False,
        "是否超级管理员": False, # Added missing key
        "是否已认证": True,
        "专业": "Arts",
        "头像URL": new_avatar_url,
        "个人简介": "Original bio",
        "手机号码": "111",
        "注册时间": datetime.now(timezone.utc),
        "邮箱": "avatar@example.com"
    }
    mock_user_dal.update_user_profile.return_value = updated_dal_data

    # Act
    updated_user = await user_service.update_user_avatar(mock_db_connection, test_user_id, new_avatar_url)

    # Assertions
    assert isinstance(updated_user, UserResponseSchema)
    assert updated_user.user_id == test_user_id
    assert updated_user.avatar_url == new_avatar_url
    # Assert other fields are correctly mapped
    assert updated_user.username == "avatar_user"
    assert updated_user.status == "Active"

    # Verify DAL method was called with correct arguments
    mock_user_dal.update_user_profile.assert_called_once_with(
        mock_db_connection,
        test_user_id,
        None, # major
        new_avatar_url,
        None, # bio
        None, # phone_number
        None, # email
        None # password_reset_token
    )