"""用户模块：注册 / 登录（极简，不写复杂加密）。"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import or_
from sqlalchemy.orm import Session

from .database import get_db
from .deps import get_current_user_id, issue_token
from .models import User

router = APIRouter(prefix="/users", tags=["user"])


class RegisterIn(BaseModel):
    nickname: str
    email: str
    student_no: str | None = None
    school: str | None = None
    campus: str | None = None
    dorm_building: str | None = None


class LoginIn(BaseModel):
    account: str  # 邮箱或学号


class VerifyIn(BaseModel):
    nickname: str
    student_no: str
    school: str | None = None
    campus: str | None = None
    dorm_building: str | None = None


class UpdateMeIn(BaseModel):
    """修改个人资料：字段均可选，只更新传入的字段。"""

    nickname: str | None = None
    campus: str | None = None
    dorm_building: str | None = None


def user_to_dict(user: User) -> dict:
    return {
        "id": user.id,
        "nickname": user.nickname,
        "avatar_path": user.avatar_path,
        "school": user.school,
        "campus": user.campus,
        "dorm_building": user.dorm_building,
        "student_no": user.student_no,
        "email": user.email,
        "is_verified": user.is_verified,
        "credit_score": user.credit_score,
        "created_at": user.created_at,
    }


@router.post("/register", summary="注册")
def register(payload: RegisterIn, db: Session = Depends(get_db)):
    if db.query(User).filter(User.email == payload.email).first():
        raise HTTPException(status_code=400, detail="该邮箱已被注册")
    if payload.student_no and db.query(User).filter(
        User.student_no == payload.student_no
    ).first():
        raise HTTPException(status_code=400, detail="该学号已被绑定")

    user = User(
        nickname=payload.nickname,
        email=payload.email,
        student_no=payload.student_no,
        school=payload.school,
        campus=payload.campus,
        dorm_building=payload.dorm_building,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return {"token": issue_token(user.id), "user_id": user.id, "user": user_to_dict(user)}


@router.post("/login", summary="登录（邮箱或学号）")
def login(payload: LoginIn, db: Session = Depends(get_db)):
    user = (
        db.query(User)
        .filter(or_(User.email == payload.account, User.student_no == payload.account))
        .first()
    )
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在，请先注册")
    return {"token": issue_token(user.id), "user_id": user.id, "user": user_to_dict(user)}


@router.get("/me", summary="获取当前登录用户")
def get_me(user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    return user_to_dict(user)


@router.post("/me", summary="修改个人资料")
def update_me(
    payload: UpdateMeIn,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    if payload.nickname is not None:
        nickname = payload.nickname.strip()
        if not nickname:
            raise HTTPException(status_code=400, detail="昵称不能为空")
        user.nickname = nickname
    if payload.campus is not None:
        user.campus = payload.campus
    if payload.dorm_building is not None:
        user.dorm_building = payload.dorm_building

    db.commit()
    db.refresh(user)
    return user_to_dict(user)


@router.post("/me/verify", summary="提交学号认证（实名认证最后一步）")
def verify_me(
    payload: VerifyIn,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    occupied = (
        db.query(User)
        .filter(User.student_no == payload.student_no, User.id != user_id)
        .first()
    )
    if occupied:
        raise HTTPException(status_code=400, detail="该学号已被绑定")

    user.nickname = payload.nickname
    user.student_no = payload.student_no
    if payload.school is not None:
        user.school = payload.school
    if payload.campus is not None:
        user.campus = payload.campus
    if payload.dorm_building is not None:
        user.dorm_building = payload.dorm_building
    user.is_verified = True

    db.commit()
    db.refresh(user)
    return user_to_dict(user)
