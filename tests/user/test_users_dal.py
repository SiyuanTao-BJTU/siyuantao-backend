# app/dal/tests/test_users_dal.py
import pytest
import pytest_mock
from uuid import uuid4, UUID
from unittest.mock import AsyncMock, patch, MagicMock
from app.dal.user_dal import UserDAL # Import the new DAL class
from app.dal.base import execute_query # Import the actual execute_query from base.py
from app.exceptions import NotFoundError, IntegrityError, DALError, ForbiddenError
import asyncio # For explicit async calls
from datetime import datetime, timedelta, timezone # Needed for token expiration tests
import pyodbc # Added for pyodbc.Error

# Ensure the fixture scope is function level for isolation
@pytest.fixture(scope="function")
def mock_execute_query(mocker: pytest_mock.MockerFixture) -> AsyncMock:
    """Fixture for a mock execute_query function."""
    mock_execute_query = AsyncMock(spec=execute_query) # Mocks the signature of execute_query
    return mock_execute_query

@pytest.fixture
# Modify the user_dal fixture to accept and use the mock_execute_query fixture
def user_dal(mock_execute_query: AsyncMock) -> UserDAL: # Added type hint
    """Fixture to create a UserDAL instance with a mocked execute_query function."""
    # Instantiate UserDAL with the mocked execute_query_func
    return UserDAL(execute_query_func=mock_execute_query)

# Add a mock for the database connection that DAL methods now expect
@pytest.fixture
def mock_db_connection() -> MagicMock:
    """Fixture for a mock database connection."""
    # Use autospec to ensure the mock behaves like a real pyodbc.Connection
    return MagicMock(spec=pyodbc.Connection)

# Define mock UUIDs for consistent testing across DAL and Service layers
TEST_USER_ID = UUID("a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11") # 示例用户ID
TEST_SELLER_ID = UUID("b0eebc99-9c0b-4ef8-bb6d-6bb9bd380a12") # 示例卖家ID
TEST_BUYER_ID = UUID("c0eebc99-9c0b-4ef8-bb6d-6bb9bd380a13") # 示例买家ID
TEST_ADMIN_USER_ID = UUID("d0eebc99-9c0b-4ef8-bb6d-6bb9bd380a14") # 示例管理员ID

# --- Modified Tests using Mocking ---

@pytest.mark.asyncio
async def test_get_user_by_id_found(
    user_dal: UserDAL, # Update type hint
    mock_execute_query: AsyncMock,
    mock_db_connection: MagicMock # Inject mock_db_connection fixture
):
    """Test fetching a user by ID when the user exists."""
    user_id = TEST_USER_ID
    mock_execute_query.return_value = {
        "user_id": user_id,
        "username": "testuser",
        "email": "test@example.com",
        "status": "Active",
        "credit": 100,
        "is_staff": False,
        "is_super_admin": False,
        "is_verified": True,
        "major": None,
        "avatar_url": None,
        "bio": None,
        "phone_number": "111222333",
        "join_time": datetime.now(timezone.utc) # Ensure timezone-aware datetime
    }

    # Act
    user = await user_dal.get_user_by_id(mock_db_connection, user_id)

    # Assert
    mock_execute_query.assert_called_once_with(
        mock_db_connection,
        "{CALL sp_GetUserProfileById(?)}",
        (user_id,),
        fetchone=True
    )
    assert user is not None
    assert user["user_id"] == user_id
    assert user["username"] == "testuser"
    assert user["email"] == "test@example.com"

@pytest.mark.asyncio
async def test_get_user_by_id_not_found(
    user_dal: UserDAL, # Update type hint
    mock_execute_query: AsyncMock,
    mock_db_connection: MagicMock # Inject mock_db_connection fixture
):
    """Test fetching a user by ID when the user does not exist."""
    user_id = TEST_USER_ID
    mock_execute_query.return_value = None # SP returns None for not found

    # Act
    user = await user_dal.get_user_by_id(mock_db_connection, user_id)

    # Assert
    mock_execute_query.assert_called_once_with(
        mock_db_connection,
        "{CALL sp_GetUserProfileById(?)}",
        (user_id,),
        fetchone=True
    )
    assert user is None

@pytest.mark.asyncio
async def test_get_user_by_username_with_password_found(
    user_dal: UserDAL, # Update type hint
    mock_execute_query: AsyncMock,
    mock_db_connection: MagicMock # Inject mock_db_connection fixture
):
    """Test fetching a user by username with password successfully."""
    username = "testuser"
    password_hash = "hashed_password_123"
    mock_execute_query.return_value = {
        "user_id": TEST_USER_ID,
        "username": username,
        "password": password_hash, # Key name should match SP output
        "status": "Active",
        "is_staff": False
    }

    # Act
    user = await user_dal.get_user_by_username_with_password(mock_db_connection, username)

    # Assert
    mock_execute_query.assert_called_once_with(
        mock_db_connection,
        "{CALL sp_GetUserByUsernameWithPassword(?)}",
        (username,),
        fetchone=True
    )
    assert user is not None
    assert user["username"] == username
    assert user["password"] == password_hash

@pytest.mark.asyncio
async def test_get_user_by_username_with_password_not_found(
    user_dal: UserDAL, # Update type hint
    mock_execute_query: AsyncMock,
    mock_db_connection: MagicMock # Inject mock_db_connection fixture
):
    """Test fetching a user by username with password when user does not exist."""
    username = "nonexistentuser"
    mock_execute_query.return_value = None # SP returns None for not found

    # Act
    user = await user_dal.get_user_by_username_with_password(mock_db_connection, username)

    # Assert
    mock_execute_query.assert_called_once_with(
        mock_db_connection,
        "{CALL sp_GetUserByUsernameWithPassword(?)}",
        (username,),
        fetchone=True
    )
    assert user is None

@pytest.mark.asyncio
async def test_create_user_success(
    user_dal: UserDAL, # Update type hint
    mock_execute_query: AsyncMock,
    mock_db_connection: MagicMock # Inject mock_db_connection fixture
):
    """Test successful user creation."""
    username = "newuser"
    hashed_password = "hashed_password_new"
    phone_number = "999888777"
    major = "Computer Science"
    new_user_id = TEST_USER_ID # Use the defined TEST_USER_ID for consistency

    # Mock the first call to create_user which returns NewUserID and Message
    mock_execute_query.side_effect = [
        # First call: sp_CreateUser
        {"NewUserID": str(new_user_id), "Message": "用户创建成功。", "OperationResultCode": 0},
        # Second call: get_user_by_id (from create_user's internal call)
        {
            "user_id": new_user_id,
            "username": username,
            "email": None,
            "status": "Active",
            "credit": 100,
            "is_staff": False,
            "is_super_admin": False,
            "is_verified": False,
            "major": major,
            "avatar_url": None,
            "bio": None,
            "phone_number": phone_number,
            "join_time": datetime.now(timezone.utc) # Ensure timezone-aware datetime
        }
    ]

    # Act
    created_user = await user_dal.create_user(mock_db_connection, username, hashed_password, phone_number, major)

    # Assert
    # Assert the first call to sp_CreateUser
    mock_execute_query.assert_has_calls([
        call(
            mock_db_connection,
            "{CALL sp_CreateUser(?, ?, ?, ?)}",
            (username, hashed_password, phone_number, major),
            fetchone=True
        ),
        # Assert the second call to sp_GetUserProfileById
        call(
            mock_db_connection,
            "{CALL sp_GetUserProfileById(?)}",
            (new_user_id,),
            fetchone=True
        )
    ])
    assert created_user is not None
    assert created_user["user_id"] == new_user_id
    assert created_user["username"] == username
    assert created_user["phone_number"] == phone_number
    assert created_user["major"] == major
    assert created_user["status"] == "Active"

@pytest.mark.asyncio
async def test_create_user_duplicate_username(
    user_dal: UserDAL, # Update type hint
    mock_execute_query: AsyncMock,
    mock_db_connection: MagicMock # Inject mock_db_connection fixture
):
    """Test user creation with a duplicate username."""
    username = "existinguser"
    hashed_password = "hashed_password_dup"
    phone_number = "999888111"
    mock_execute_query.return_value = {"OperationResultCode": -1, "Message": "用户名已存在。"} # Simulate duplicate username

    # Act & Assert
    with pytest.raises(IntegrityError, match="Username already exists."):
        await user_dal.create_user(mock_db_connection, username, hashed_password, phone_number)
    
    mock_execute_query.assert_called_once_with(
        mock_db_connection,
        "{CALL sp_CreateUser(?, ?, ?, ?)}",
        (username, hashed_password, phone_number, None), # major is None in this test
        fetchone=True
    )

@pytest.mark.asyncio
async def test_update_user_profile_success(
    user_dal: UserDAL, # Update type hint
    mock_execute_query: AsyncMock,
    mock_db_connection: MagicMock # Inject mock_db_connection fixture
):
    """Test successful user profile update."""
    user_id = TEST_USER_ID
    major = "New Major"
    phone_number = "9876543210"
    updated_email = "updated@example.com" # Added email to test update

    mock_execute_query.return_value = {
        "user_id": user_id,
        "username": "testuser",
        "email": updated_email,
        "status": "Active",
        "credit": 100,
        "is_staff": False,
        "is_super_admin": False,
        "is_verified": True,
        "major": major,
        "avatar_url": None,
        "bio": None,
        "phone_number": phone_number,
        "join_time": datetime.now(timezone.utc)
    } # Mock with updated values

    # Act
    updated_user = await user_dal.update_user_profile(
        mock_db_connection, user_id, major=major, phone_number=phone_number, email=updated_email
    )

    # Assert
    mock_execute_query.assert_called_once_with(
        mock_db_connection,
        "{CALL sp_UpdateUserProfile(?, ?, ?, ?, ?, ?)}",
        (user_id, major, None, None, phone_number, updated_email), # None for avatar_url and bio
        fetchone=True
    )
    assert updated_user is not None
    assert updated_user["user_id"] == user_id
    assert updated_user["major"] == major
    assert updated_user["phone_number"] == phone_number
    assert updated_user["email"] == updated_email

@pytest.mark.asyncio
async def test_update_user_profile_not_found(
    user_dal: UserDAL, # Update type hint
    mock_execute_query: AsyncMock,
    mock_db_connection: MagicMock # Inject mock_db_connection fixture
):
    """Test user profile update when user is not found."""
    user_id = TEST_USER_ID
    mock_execute_query.return_value = {"OperationResultCode": -1, "Message": "用户未找到。"} # Simulate user not found

    # Act & Assert
    with pytest.raises(NotFoundError, match=f"User with ID {user_id} not found for update."):
        await user_dal.update_user_profile(mock_db_connection, user_id, major="New Major")

    mock_execute_query.assert_called_once_with(
        mock_db_connection,
        "{CALL sp_UpdateUserProfile(?, ?, ?, ?, ?, ?)}",
        (user_id, "New Major", None, None, None, None), # Default values for optional params
        fetchone=True
    )

@pytest.mark.asyncio
async def test_update_user_profile_duplicate_phone(
    user_dal: UserDAL, # Update type hint
    mock_execute_query: AsyncMock,
    mock_db_connection: MagicMock # Inject mock_db_connection fixture
):
    """Test user profile update with a duplicate phone number."""
    user_id = TEST_USER_ID
    duplicate_phone = "1234567890"
    mock_execute_query.return_value = {"OperationResultCode": -1, "Message": "此手机号码已被其他用户使用。"} # Simulate duplicate phone

    # Act & Assert
    with pytest.raises(IntegrityError, match="Phone number already in use by another user."):
        await user_dal.update_user_profile(mock_db_connection, user_id, phone_number=duplicate_phone)
    
    mock_execute_query.assert_called_once_with(
        mock_db_connection,
        "{CALL sp_UpdateUserProfile(?, ?, ?, ?, ?, ?)}",
        (user_id, None, None, None, duplicate_phone, None), # Default values for optional params
        fetchone=True
    )

@pytest.mark.asyncio
async def test_update_user_password_success(
    user_dal: UserDAL, # Update type hint
    mock_execute_query: AsyncMock,
    mock_db_connection: MagicMock # Inject mock_db_connection fixture
):
    """Test successful user password update."""
    user_id = TEST_USER_ID
    new_hashed_password = "new_hashed_password"
    # Simulate SP returning a success message/code
    mock_execute_query.return_value = {"OperationResultCode": 0, "Message": "密码更新成功。"}

    # Act
    success = await user_dal.update_user_password(mock_db_connection, user_id, new_hashed_password)

    # Assert
    mock_execute_query.assert_called_once_with(
        mock_db_connection,
        "{CALL sp_UpdateUserPassword(?, ?)}",
        (user_id, new_hashed_password),
        fetchone=True
    )
    assert success is True

@pytest.mark.asyncio
async def test_update_user_password_not_found(
    user_dal: UserDAL, # Update type hint
    mock_execute_query: AsyncMock,
    mock_db_connection: MagicMock # Inject mock_db_connection fixture
):
    """Test user password update when user is not found."""
    user_id = TEST_USER_ID
    new_hashed_password = "new_hashed_password"
    # Simulate SP returning user not found message/code
    mock_execute_query.return_value = {"OperationResultCode": -1, "Message": "用户未找到。"}

    # Act & Assert
    with pytest.raises(NotFoundError, match=f"User with ID {user_id} not found for password update."):
        await user_dal.update_user_password(mock_db_connection, user_id, new_hashed_password)

    mock_execute_query.assert_called_once_with(
        mock_db_connection,
        "{CALL sp_UpdateUserPassword(?, ?)}",
        (user_id, new_hashed_password),
        fetchone=True
    )

@pytest.mark.asyncio
async def test_delete_user_success(
    user_dal: UserDAL, # Update type hint
    mock_execute_query: AsyncMock,
    mock_db_connection: MagicMock # Inject mock_db_connection fixture
):
    """Test successful user deletion."""
    user_id = TEST_USER_ID
    # Simulate SP returning success message/code
    mock_execute_query.return_value = {"OperationResultCode": 0, "Debug_Message": "User deleted successfully.", "Message": "User deleted successfully."} 

    # Act
    success = await user_dal.delete_user(mock_db_connection, user_id)

    # Assert
    mock_execute_query.assert_called_once_with(
        mock_db_connection,
        "{CALL sp_DeleteUser(?)}",
        (user_id,),
        fetchone=True
    )
    assert success is True

@pytest.mark.asyncio
async def test_delete_user_not_found(
    user_dal: UserDAL, # Update type hint
    mock_execute_query: AsyncMock,
    mock_db_connection: MagicMock # Inject mock_db_connection fixture
):
    """Test user deletion when user is not found."""
    user_id = TEST_USER_ID
    # Simulate SP returning user not found message/code
    mock_execute_query.return_value = {"OperationResultCode": -1, "Debug_Message": "User not found.", "Message": "用户不存在。"} # Updated message

    # Act & Assert
    with pytest.raises(NotFoundError, match=f"User with ID {user_id} not found for deletion."):
        await user_dal.delete_user(mock_db_connection, user_id)

    mock_execute_query.assert_called_once_with(
        mock_db_connection,
        "{CALL sp_DeleteUser(?)}",
        (user_id,),
        fetchone=True
    )

@pytest.mark.asyncio
async def test_request_verification_link_success(
    user_dal: UserDAL, # Update type hint
    mock_execute_query: AsyncMock,
    mock_db_connection: MagicMock # Inject mock_db_connection fixture
):
    """Test successful request for a verification link."""
    user_id = TEST_USER_ID
    email = "test@example.com"
    magic_link_token = uuid4()
    # Simulate SP returning the token and expiry
    mock_execute_query.return_value = {
        "VerificationToken": str(magic_link_token),
        "ExpiresAt": (datetime.now(timezone.utc) + timedelta(minutes=15)).isoformat(),
        "OperationResultCode": 0,
        "Message": "Verification link sent."
    }

    # Act
    result = await user_dal.request_verification_link(mock_db_connection, user_id, email)

    # Assert
    mock_execute_query.assert_called_once_with(
        mock_db_connection,
        "{CALL sp_RequestMagicLink(?, ?)}",
        (email, user_id),
        fetchone=True
    )
    assert result is not None
    assert result["VerificationToken"] == str(magic_link_token)
    assert "ExpiresAt" in result

@pytest.mark.asyncio
async def test_adjust_user_credit_success(
    user_dal: UserDAL, # Update type hint
    mock_execute_query: AsyncMock,
    mock_db_connection: MagicMock # Inject mock_db_connection fixture
):
    """Test successful user credit adjustment."""
    user_id = TEST_USER_ID
    credit_adjustment = 50
    admin_id = TEST_ADMIN_USER_ID
    reason = "Good behavior"
    # Simulate SP returning success message/code
    mock_execute_query.return_value = {"OperationResultCode": 0, "Message": "Credit adjusted successfully."}

    # Act
    success = await user_dal.adjust_user_credit(mock_db_connection, user_id, credit_adjustment, admin_id, reason)

    # Assert
    mock_execute_query.assert_called_once_with(
        mock_db_connection,
        "{CALL sp_AdjustUserCredit(?, ?, ?, ?)}",
        (user_id, credit_adjustment, admin_id, reason),
        fetchone=True
    )
    assert success is True

@pytest.mark.asyncio
async def test_adjust_user_credit_not_found(
    user_dal: UserDAL, # Update type hint
    mock_execute_query: AsyncMock,
    mock_db_connection: MagicMock # Inject mock_db_connection fixture
):
    """Test user credit adjustment when user is not found."""
    user_id = TEST_USER_ID
    credit_adjustment = 50
    admin_id = TEST_ADMIN_USER_ID
    reason = "Good behavior"
    # Simulate SP returning user not found message/code
    mock_execute_query.return_value = {"OperationResultCode": -1, "Message": "用户未找到。"}

    # Act & Assert
    with pytest.raises(NotFoundError, match=f"User with ID {user_id} not found for credit adjustment."):
        await user_dal.adjust_user_credit(mock_db_connection, user_id, credit_adjustment, admin_id, reason)

    mock_execute_query.assert_called_once_with(
        mock_db_connection,
        "{CALL sp_AdjustUserCredit(?, ?, ?, ?)}",
        (user_id, credit_adjustment, admin_id, reason),
        fetchone=True
    )

@pytest.mark.asyncio
async def test_get_all_users_success(
    user_dal: UserDAL, # Update type hint
    mock_execute_query: AsyncMock,
    mock_db_connection: MagicMock # Inject mock_db_connection fixture
):
    """Test fetching all users successfully."""
    admin_id = TEST_ADMIN_USER_ID
    expected_users_data = [
        {
            "user_id": UUID("a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11"),
            "username": "user1",
            "email": "user1@example.com",
            "status": "Active",
            "credit": 100,
            "is_staff": False,
            "is_super_admin": False,
            "is_verified": True,
            "major": None,
            "avatar_url": None,
            "bio": None,
            "phone_number": "111222333",
            "join_time": datetime.now(timezone.utc)
        },
        {
            "user_id": UUID("b0eebc99-9c0b-4ef8-bb6d-6bb9bd380a12"),
            "username": "user2",
            "email": "user2@example.com",
            "status": "Disabled",
            "credit": 50,
            "is_staff": True,
            "is_super_admin": False,
            "is_verified": True,
            "major": None,
            "avatar_url": None,
            "bio": None,
            "phone_number": "444555666",
            "join_time": datetime.now(timezone.utc)
        }
    ]
    mock_execute_query.return_value = expected_users_data # Mock the return value of execute_query with list of dicts

    # Act
    users = await user_dal.get_all_users(mock_db_connection, admin_id)

    # Assert
    mock_execute_query.assert_called_once_with(
        mock_db_connection,
        "{CALL sp_GetAllUsers(?)}",
        (admin_id,),
        fetchall=True
    )
    assert len(users) == 2
    assert users[0]["username"] == "user1"
    assert users[1]["username"] == "user2"

@pytest.mark.asyncio
async def test_admin_get_all_users_forbidden(
    user_dal: UserDAL, # Update type hint
    mock_execute_query: AsyncMock,
    mock_db_connection: MagicMock # Inject mock_db_connection fixture
):
    """Test fetching all users when admin is forbidden."""
    admin_id = TEST_ADMIN_USER_ID
    mock_execute_query.return_value = {"OperationResultCode": -2, "Message": "只有超级管理员可以查看所有用户。"} # Simulate forbidden

    # Act & Assert
    with pytest.raises(ForbiddenError, match="只有超级管理员可以查看所有用户。"):
        await user_dal.get_all_users(mock_db_connection, admin_id)

    mock_execute_query.assert_called_once_with(
        mock_db_connection,
        "{CALL sp_GetAllUsers(?)}",
        (admin_id,),
        fetchall=True
    )

@pytest.mark.asyncio
async def test_admin_get_all_users_not_found(
    user_dal: UserDAL, # Update type hint
    mock_execute_query: AsyncMock,
    mock_db_connection: MagicMock # Inject mock_db_connection fixture
):
    """Test fetching all users when admin is not found (or no users)."""
    admin_id = TEST_ADMIN_USER_ID
    mock_execute_query.return_value = [] # Simulate no users found or admin not found

    # Act
    users = await user_dal.get_all_users(mock_db_connection, admin_id)

    # Assert
    mock_execute_query.assert_called_once_with(
        mock_db_connection,
        "{CALL sp_GetAllUsers(?)}",
        (admin_id,),
        fetchall=True
    )
    assert users == []

@pytest.mark.asyncio
async def test_change_user_status_success(
    user_dal: UserDAL,
    mock_execute_query: AsyncMock,
    mock_db_connection: MagicMock
):
    """Test changing user status successfully."""
    user_id = TEST_USER_ID
    new_status = "Disabled"
    admin_id = TEST_ADMIN_USER_ID
    mock_execute_query.return_value = {"OperationResultCode": 0, "Message": "User status updated successfully."} # Mock with success message

    # Act
    success = await user_dal.change_user_status(mock_db_connection, user_id, new_status, admin_id)

    # Assert
    mock_execute_query.assert_called_once_with(
        mock_db_connection,
        "{CALL sp_ChangeUserStatus(?, ?, ?)}",
        (user_id, new_status, admin_id),
        fetchone=True
    )
    assert success is True

@pytest.mark.asyncio
async def test_change_user_status_user_not_found(
    user_dal: UserDAL,
    mock_execute_query: AsyncMock,
    mock_db_connection: MagicMock
):
    """Test changing user status when user is not found."""
    user_id = TEST_USER_ID
    new_status = "Disabled"
    admin_id = TEST_ADMIN_USER_ID
    mock_execute_query.return_value = {"OperationResultCode": -1, "Message": "用户不存在。"}

    # Act & Assert
    with pytest.raises(NotFoundError, match=f"User with ID {user_id} not found."):
        await user_dal.change_user_status(mock_db_connection, user_id, new_status, admin_id)

    mock_execute_query.assert_called_once_with(
        mock_db_connection,
        "{CALL sp_ChangeUserStatus(?, ?, ?)}",
        (user_id, new_status, admin_id),
        fetchone=True
    )

@pytest.mark.asyncio
async def test_change_user_status_admin_forbidden(
    user_dal: UserDAL,
    mock_execute_query: AsyncMock,
    mock_db_connection: MagicMock
):
    """Test changing user status when admin is forbidden."""
    user_id = TEST_USER_ID
    new_status = "Disabled"
    admin_id = TEST_ADMIN_USER_ID
    mock_execute_query.return_value = {"OperationResultCode": -2, "Message": "无权限执行此操作。"}

    # Act & Assert
    with pytest.raises(ForbiddenError, match="只有管理员可以更改用户状态。"):
        await user_dal.change_user_status(mock_db_connection, user_id, new_status, admin_id)

    mock_execute_query.assert_called_once_with(
        mock_db_connection,
        "{CALL sp_ChangeUserStatus(?, ?, ?)}",
        (user_id, new_status, admin_id),
        fetchone=True
    )

@pytest.mark.asyncio
async def test_change_user_status_dal_error(
    user_dal: UserDAL,
    mock_execute_query: AsyncMock,
    mock_db_connection: MagicMock
):
    """Test changing user status raises DALError for unexpected database errors."""
    user_id = TEST_USER_ID
    new_status = "Active"
    admin_id = TEST_ADMIN_USER_ID
    mock_execute_query.return_value = {"OperationResultCode": -99, "Message": "未知数据库错误。"} # Simulate a generic DAL error

    # Act & Assert
    with pytest.raises(DALError, match="Stored procedure failed with result code: -99"):
        await user_dal.change_user_status(mock_db_connection, user_id, new_status, admin_id)

    mock_execute_query.assert_called_once_with(
        mock_db_connection,
        "{CALL sp_ChangeUserStatus(?, ?, ?)}",
        (user_id, new_status, admin_id),
        fetchone=True
    )

@pytest.mark.asyncio
async def test_toggle_user_staff_status_success(
    user_dal: UserDAL,
    mock_execute_query: AsyncMock,
    mock_db_connection: MagicMock
):
    """Test successful toggling of user staff status."""
    target_user_id = TEST_USER_ID
    super_admin_id = TEST_ADMIN_USER_ID # Assuming admin user is super admin for testing
    
    # Mock the initial get_user_by_id to return a non-staff user
    mock_execute_query.side_effect = [
        {
            "user_id": target_user_id,
            "username": "testuser",
            "email": "test@example.com",
            "status": "Active",
            "credit": 100,
            "is_staff": False, # Initial status is False
            "is_super_admin": False,
            "is_verified": True,
            "major": None,
            "avatar_url": None,
            "bio": None,
            "phone_number": "111222333",
            "join_time": datetime.now(timezone.utc)
        },
        # Mock the update_user_staff_status call to return 1 row affected
        1 # Indicates 1 row affected by the UPDATE statement
    ]

    # Act
    success = await user_dal.update_user_staff_status(mock_db_connection, target_user_id, True, super_admin_id) # Toggle to True

    # Assert
    assert success is True
    # Assert two calls: one for get_user_by_id and one for update_user_staff_status
    mock_execute_query.assert_has_calls([
        call(
        mock_db_connection,
            "{CALL sp_GetUserProfileById(?)}", # This call is from Service layer
            (target_user_id,),
        fetchone=True
        ),
        call(
        mock_db_connection,
            """
                UPDATE [User]
                SET IsStaff = ?
                WHERE UserID = ?
            """,
            (True, target_user_id)
        )
    ])

@pytest.mark.asyncio
async def test_toggle_user_staff_status_user_not_found(
    user_dal: UserDAL,
    mock_execute_query: AsyncMock,
    mock_db_connection: MagicMock
):
    """Test toggling user staff status when user is not found."""
    target_user_id = TEST_USER_ID
    super_admin_id = TEST_ADMIN_USER_ID

    # Mock get_user_by_id to return None
    mock_execute_query.return_value = None

    # Act & Assert
    with pytest.raises(NotFoundError, match=f"User with ID {target_user_id} not found."):
        await user_dal.update_user_staff_status(mock_db_connection, target_user_id, True, super_admin_id)

    mock_execute_query.assert_called_once_with(
        mock_db_connection,
        "{CALL sp_GetUserProfileById(?)}", # This call is from Service layer
        (target_user_id,),
        fetchone=True
    )

@pytest.mark.asyncio
async def test_toggle_user_staff_status_dal_error_on_fetch(
    user_dal: UserDAL,
    mock_execute_query: AsyncMock,
    mock_db_connection: MagicMock
):
    """Test toggling user staff status when DAL error occurs during user fetch."""
    target_user_id = TEST_USER_ID
    super_admin_id = TEST_ADMIN_USER_ID

    # Mock get_user_by_id to raise DALError
    mock_execute_query.side_effect = DALError("Database fetch error")

    # Act & Assert
    with pytest.raises(DALError, match="Database fetch error"):
        await user_dal.update_user_staff_status(mock_db_connection, target_user_id, True, super_admin_id)

    mock_execute_query.assert_called_once_with(
        mock_db_connection,
        "{CALL sp_GetUserProfileById(?)}",
        (target_user_id,),
        fetchone=True
    )

@pytest.mark.asyncio
async def test_toggle_user_staff_status_dal_error_on_update(
    user_dal: UserDAL,
    mock_execute_query: AsyncMock,
    mock_db_connection: MagicMock
):
    """Test toggling user staff status when DAL error occurs during update."""
    target_user_id = TEST_USER_ID
    super_admin_id = TEST_ADMIN_USER_ID

    # Mock get_user_by_id to return a non-staff user, then mock update to raise DALError
    mock_execute_query.side_effect = [
        {
            "user_id": target_user_id,
            "username": "testuser",
            "email": "test@example.com",
            "status": "Active",
            "credit": 100,
            "is_staff": False, # Initial status is False
            "is_super_admin": False,
            "is_verified": True,
            "major": None,
            "avatar_url": None,
            "bio": None,
            "phone_number": "111222333",
            "join_time": datetime.now(timezone.utc)
        },
        DALError("Database update error") # Simulate DAL error on update
    ]

    # Act & Assert
    with pytest.raises(DALError, match="Database update error"):
        await user_dal.update_user_staff_status(mock_db_connection, target_user_id, True, super_admin_id)
    
    # Assert two calls
    mock_execute_query.assert_has_calls([
        call(
        mock_db_connection,
            "{CALL sp_GetUserProfileById(?)}",
            (target_user_id,),
        fetchone=True
        ),
        call(
        mock_db_connection,
            """
                UPDATE [User]
                SET IsStaff = ?
                WHERE UserID = ?
            """,
            (True, target_user_id)
        )
    ])

