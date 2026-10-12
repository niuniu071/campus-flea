"""邮箱验证码模块（演示用）。

说明（当前阶段限定）：
- 不接真实邮件服务，验证码通过接口的 debug_code 字段返回，供演示使用；
- 不写加密、不写 JWT；
- 白名单后缀、60 秒重发冷却、连续错误 5 次锁定 10 分钟均由服务端强制。
"""

import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .database import get_db
from .models import VerificationCode

router = APIRouter(prefix="/verify", tags=["verify"])

# 与前端 prototype/src/constants.ts 的 CAMPUS_EMAIL_SUFFIXES 保持一致
CAMPUS_EMAIL_SUFFIXES = ("@school.edu", "@campus.edu", "@stu.edu")

CODE_TTL_SECONDS = 300       # 验证码 5 分钟有效
SEND_COOLDOWN_SECONDS = 60   # 60 秒内不可重复发送
MAX_WRONG = 5                # 连续错误次数上限
LOCK_SECONDS = 600           # 连续错误达到上限后锁定 10 分钟


class SendCodeIn(BaseModel):
    email: str


class ConfirmCodeIn(BaseModel):
    email: str
    code: str


def _naive_utcnow() -> datetime:
    """统一使用「无时区的 UTC 时间」，与 SQLite 读回的 datetime 可直接比较。"""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _latest(db: Session, email: str) -> VerificationCode | None:
    return (
        db.query(VerificationCode)
        .filter(VerificationCode.email == email)
        .order_by(VerificationCode.id.desc())
        .first()
    )


@router.post("/email/send", summary="发送校园邮箱验证码（演示：验证码随响应返回）")
def send_email_code(payload: SendCodeIn, db: Session = Depends(get_db)):
    email = payload.email.strip().lower()

    if not any(email.endswith(suffix) for suffix in CAMPUS_EMAIL_SUFFIXES):
        raise HTTPException(status_code=400, detail="仅支持本校校园邮箱")

    now = _naive_utcnow()
    latest = _latest(db, email)

    if latest and latest.locked_until and latest.locked_until > now:
        raise HTTPException(status_code=429, detail="错误次数过多，请 10 分钟后再试")

    if latest and (now - latest.created_at) < timedelta(seconds=SEND_COOLDOWN_SECONDS):
        raise HTTPException(status_code=429, detail="发送过于频繁，请 60 秒后再试")

    code = f"{secrets.randbelow(900000) + 100000}"
    record = VerificationCode(
        email=email,
        code=code,
        scene="email",
        expires_at=now + timedelta(seconds=CODE_TTL_SECONDS),
        used=False,
        wrong_count=0,
    )
    db.add(record)
    db.commit()

    return {"sent": True, "expires_in": CODE_TTL_SECONDS, "debug_code": code}


@router.post("/email/confirm", summary="校验校园邮箱验证码")
def confirm_email_code(payload: ConfirmCodeIn, db: Session = Depends(get_db)):
    email = payload.email.strip().lower()
    now = _naive_utcnow()

    latest = _latest(db, email)
    if not latest:
        raise HTTPException(status_code=400, detail="请先获取验证码")
    if latest.locked_until and latest.locked_until > now:
        raise HTTPException(status_code=429, detail="错误次数过多，请 10 分钟后再试")
    if latest.used:
        raise HTTPException(status_code=400, detail="验证码已失效，请重新获取")
    if latest.expires_at < now:
        raise HTTPException(status_code=400, detail="验证码已过期，请重新获取")

    if latest.code != payload.code.strip():
        latest.wrong_count += 1
        if latest.wrong_count >= MAX_WRONG:
            latest.locked_until = now + timedelta(seconds=LOCK_SECONDS)
            db.commit()
            raise HTTPException(status_code=429, detail="错误次数过多，请 10 分钟后再试")
        remain = MAX_WRONG - latest.wrong_count
        db.commit()
        raise HTTPException(status_code=400, detail=f"验证码不正确，还可尝试 {remain} 次")

    latest.used = True
    db.commit()
    return {"verified": True, "email": email}
