"""互评模块：交易互评 + 信用分更新。"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import or_
from sqlalchemy.orm import Session

from .database import get_db
from .deps import get_current_user_id
from .models import Conversation, Product, Review, User
from .user import user_to_dict

router = APIRouter(prefix="/reviews", tags=["review"])


class ReviewIn(BaseModel):
    product_id: int
    to_user_id: int
    rating: int  # 1-5 星
    content: str | None = None


def credit_delta(rating: int) -> int:
    """信用分变化：5 星 +2，4 星 +1，1-3 星 -2。"""
    if rating >= 5:
        return 2
    if rating == 4:
        return 1
    return -2


def review_to_dict(review: Review) -> dict:
    return {
        "id": review.id,
        # 与前端 Review.vue 的 <trade_id> 解析格式（p<商品id>_<被评价人id>）保持一致
        "trade_id": f"p{review.product_id}_{review.to_user_id}",
        "product_id": review.product_id,
        "from_user_id": review.from_user_id,
        "to_user_id": review.to_user_id,
        "rating": review.rating,
        "content": review.content,
        "created_at": review.created_at,
    }


@router.post("", summary="提交互评（更新对方信用分）")
def create_review(
    payload: ReviewIn,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    if payload.rating < 1 or payload.rating > 5:
        raise HTTPException(status_code=400, detail="评分需为 1-5 星")

    product = db.get(Product, payload.product_id)
    if not product:
        raise HTTPException(status_code=404, detail="商品不存在")
    if payload.to_user_id == user_id:
        raise HTTPException(status_code=400, detail="不能评价自己")

    target = db.get(User, payload.to_user_id)
    if not target:
        raise HTTPException(status_code=404, detail="被评价用户不存在")

    # 仅允许评价与自己就该商品有过交易沟通的对方
    is_counterpart = payload.to_user_id == product.seller_id or (
        db.query(Conversation)
        .filter(
            Conversation.product_id == payload.product_id,
            or_(
                (Conversation.buyer_id == user_id)
                & (Conversation.seller_id == payload.to_user_id),
                (Conversation.buyer_id == payload.to_user_id)
                & (Conversation.seller_id == user_id),
            ),
        )
        .first()
        is not None
    )
    if not is_counterpart:
        raise HTTPException(status_code=403, detail="只能评价与该商品交易相关的对方")

    existing = (
        db.query(Review)
        .filter(
            Review.product_id == payload.product_id, Review.from_user_id == user_id
        )
        .first()
    )
    if existing:
        raise HTTPException(status_code=400, detail="已评价过该笔交易")

    review = Review(
        product_id=payload.product_id,
        from_user_id=user_id,
        to_user_id=payload.to_user_id,
        rating=payload.rating,
        content=payload.content,
    )
    db.add(review)

    target.credit_score = max(
        0, min(100, target.credit_score + credit_delta(payload.rating))
    )
    db.commit()
    db.refresh(review)
    db.refresh(target)

    return {
        "review": review_to_dict(review),
        "to_user_credit_score": target.credit_score,
    }


@router.get("", summary="查看某个用户收到的评价")
def list_reviews(
    user_id: int,
    limit: int = 20,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    query = db.query(Review).filter(Review.to_user_id == user_id)
    total = query.count()
    items = (
        query.order_by(Review.created_at.desc()).offset(offset).limit(limit).all()
    )

    from_ids = {r.from_user_id for r in items}
    umap: dict[int, User] = {}
    if from_ids:
        users = db.query(User).filter(User.id.in_(from_ids)).all()
        umap = {u.id: u for u in users}

    return {
        "total": total,
        "items": [
            {
                **review_to_dict(r),
                "from_user": user_to_dict(umap[r.from_user_id])
                if r.from_user_id in umap
                else None,
            }
            for r in items
        ],
    }
