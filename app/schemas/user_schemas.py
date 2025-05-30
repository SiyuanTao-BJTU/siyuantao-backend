from pydantic import BaseModel, Field, EmailStr
from uuid import UUID
from typing import Optional, Literal
from datetime import datetime # Import datetime for UserResponseSchema

# Properties to receive via API on creation (e.g., for registration)
# Renamed from UserCreate to UserRegisterSchema as per plan
class UserRegisterSchema(BaseModel):
    username: str = Field(..., min_length=3, max_length=128, description="用户名")
    email: Optional[EmailStr] = Field(None, description="邮箱") # 邮箱设为可选
    password: str = Field(..., min_length=6, description="密码") # Password hashing handled in Service layer
    major: Optional[str] = Field(None, max_length=100, description="专业")
    phone_number: str = Field(..., max_length=20, description="手机号码") # 确保 phone_number 存在且为必填
    # is_staff field should not be provided by the user on registration

# Properties to receive via API on login
# Renamed from UserLogin to UserLoginSchema as per plan
class UserLoginSchema(BaseModel):
    username: str = Field(..., description="用户名或邮箱") # 实际登录可能支持用户名或邮箱
    password: str = Field(..., description="密码")

# Properties to receive via API on profile update
# Renamed from UserUpdate to UserProfileUpdateSchema as per plan
class UserProfileUpdateSchema(BaseModel):
    username: Optional[str] = Field(None, min_length=3, max_length=128, description="用户名") # Username update likely not allowed via profile update
    # email: Optional[EmailStr] = Field(None, description="邮箱") # Email update may require separate verification
    # password: Optional[str] = Field(None, min_length=6, description="新密码") # Password update handled via separate endpoint
    major: Optional[str] = Field(None, max_length=100, description="专业")
    avatar_url: Optional[str] = Field(None, description="头像URL")
    bio: Optional[str] = Field(None, max_length=500, description="个人简介")
    phone_number: Optional[str] = Field(None, max_length=20, description="手机号码")

# Schema for updating user password
# Name already matches plan: UserPasswordUpdate
class UserPasswordUpdate(BaseModel):
    old_password: str = Field(..., description="旧密码")
    new_password: str = Field(..., min_length=6, description="新密码")

# Properties to return via API
# Renamed from UserResponse to UserResponseSchema as per plan
class UserResponseSchema(BaseModel):
    user_id: UUID = Field(..., description="用户唯一ID")
    username: str = Field(..., description="用户名")
    email: Optional[str] = Field(None, description="邮箱") # 邮箱改为可选，并允许 None
    status: str = Field(..., description="账户状态")
    credit: int = Field(..., description="信用分")
    is_staff: bool = Field(..., description="是否管理员")
    is_super_admin: bool = Field(..., description="是否超级管理员")
    is_verified: bool = Field(..., description="是否已认证")
    major: Optional[str] = Field(None, description="专业")
    avatar_url: Optional[str] = Field(None, description="头像URL")
    bio: Optional[str] = Field(None, description="个人简介")
    phone_number: Optional[str] = Field(None, description="手机号码") # 手机号改为可选
    join_time: datetime = Field(..., description="注册时间 (ISO 8601格式)") # Use datetime object
    last_login_time: Optional[datetime] = Field(None, description="最后登录时间") # Added for admin view

    class Config:
        from_attributes = True # Pydantic v2: 允许通过 ORM 属性名访问
        # orm_mode = True # Pydantic v1 equivalent

# Schema for JWT Token response
# Name already matches plan: Token
class Token(BaseModel):
    access_token: str
    token_type: str

# Schema for Token data (used internally for JWT payload)
# Name already matches plan: TokenData
class TokenData(BaseModel):
    user_id: Optional[UUID] = None
    is_staff: Optional[bool] = None
    is_verified: Optional[bool] = None # Added is_verified to token data as it's often needed for auth checks

# Schema for email verification request
# Name already matches plan: RequestVerificationEmail
class RequestVerificationEmail(BaseModel):
    email: EmailStr = Field(..., description="请求发送验证邮件的邮箱")

# Schema for email verification token
# Name already matches plan: VerifyEmail
class VerifyEmail(BaseModel):
     token: UUID = Field(..., description="邮箱验证令牌") 

# New Schemas for Admin User Management

class UserStatusUpdateSchema(BaseModel):
    status: Literal['Active', 'Disabled'] = Field(..., description="新的用户状态 ('Active' 或 'Disabled')")

class UserCreditAdjustmentSchema(BaseModel):
    credit_adjustment: int = Field(..., ge=-1000, le=1000, description="信用分调整值 (正数增加，负数减少)")
    reason: str = Field(..., description="调整信用分的原因")

# New Schema for requesting OTP for password reset
class RequestOtpSchema(BaseModel):
    email: EmailStr = Field(..., description="请求发送OTP的邮箱")

# New Schema for verifying OTP and resetting password
class VerifyOtpAndResetPasswordSchema(BaseModel):
    email: EmailStr = Field(..., description="用户邮箱")
    otp: str = Field(..., min_length=6, max_length=6, description="收到的OTP") # Assuming 6-digit OTP
    new_password: str = Field(..., min_length=6, description="新密码")

# New Schema for verifying OTP (general purpose)
class VerifyOtpSchema(BaseModel):
    email: EmailStr = Field(..., description="用户邮箱")
    otp: str = Field(..., min_length=6, max_length=6, description="收到的OTP") # Assuming 6-digit OTP

# New Schema for requesting OTP for passwordless login
class RequestLoginOtpSchema(BaseModel):
    identifier: str = Field(..., description="用户名或邮箱，用于请求登录OTP")

# New Schema for verifying OTP and performing passwordless login
class VerifyLoginOtpSchema(BaseModel):
    identifier: str = Field(..., description="用户名或邮箱")
    otp: str = Field(..., min_length=6, max_length=6, description="收到的登录OTP") # Assuming 6-digit OTP 