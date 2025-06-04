import os
import hashlib
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from datetime import datetime, timedelta
from typing import Optional
from uuid import UUID

from app.config import settings
from app.schemas.user_schemas import TokenData

# 从配置文件获取 JWT 密钥和算法
SECRET_KEY = settings.SECRET_KEY
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30 # 访问令牌过期时间（分钟）

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login") # 指向登录API端点

# 密码哈希
def get_password_hash(password: str) -> str:
    """Hashes a password using PBKDF2 with SHA256."""
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 100000)
    # Store salt and hashed password together, separated by a colon, in hex format
    return f"{salt.hex()}:{dk.hex()}"

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifies a plain password against a hashed password."""
    try:
        salt_hex, dk_hex = hashed_password.split(':')
        salt = bytes.fromhex(salt_hex)
        dk = bytes.fromhex(dk_hex)

        # Hash the plain password with the retrieved salt
        new_dk = hashlib.pbkdf2_hmac('sha256', plain_password.encode('utf-8'), salt, 100000)

        # Compare the new hash with the stored hash
        return new_dk == dk
    except ValueError:
        # Handle cases where the hashed_password format is incorrect (e.g., not a valid hash format)
        return False

# 创建访问令牌
def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

# get_current_user, get_current_active_admin_user, get_current_authenticated_user 等依赖项
# 已移动到 dependencies.py，这里不需要重复定义