"""极简身份依赖：非 JWT，仅用于演示阶段从请求头解析 user_id。"""

import secrets

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from .database import get_db
from .models import User

TOKEN_PREFIX = "campus"


def issue_token(user_id: int) -> str:
    """生成形如 campus-<user_id>-<random> 的简单 token。"""
    return f"{TOKEN_PREFIX}-{user_id}-{secrets.token_hex(8)}"


def _parse_token(x_token: str) -> int | None:
    """解析 token，非法时返回 None（不抛异常）。"""
    parts = x_token.split("-")
    if len(parts) != 3 or parts[0] != TOKEN_PREFIX:
        return None
    try:
        return int(parts[1])
    except ValueError:
        return None


def get_current_user_id(x_token: str = Header(default="")) -> int:
    """从请求头 X-Token 中解析出 user_id。"""
    user_id = _parse_token(x_token)
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="缺少或无效的 token"
        )
    return user_id


def get_optional_user_id(x_token: str = Header(default="")) -> int | None:
    """用于可匿名访问的列表 / 详情接口：无 token 或 token 非法时返回 None。"""
    return _parse_token(x_token)


def require_verified(
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> int:
    """要求已实名认证，否则 403（用于发布商品等受限动作）。"""
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    if not user.is_verified:
        raise HTTPException(status_code=403, detail="请先完成校园实名认证")
    return user_id
