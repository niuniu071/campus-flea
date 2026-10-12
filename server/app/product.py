"""商品模块：发布 / 列表筛选 / 详情 / 状态流转 / 「想要」。"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from .database import get_db
from .deps import get_current_user_id, get_optional_user_id, require_verified
from .models import Product, Want

router = APIRouter(prefix="/products", tags=["product"])

# 商品状态白名单
PRODUCT_STATUSES = ("on_sale", "reserved", "sold", "off_shelf")


class ProductCreateIn(BaseModel):
    title: str
    price: float
    description: str | None = None
    dorm_building: str | None = None
    category: str | None = None
    campus: str | None = None
    meetup_place: str | None = None
    available_time: str | None = None
    negotiable: bool = True
    item_condition: str | None = None
    cover_image_path: str | None = None
    image_paths: str | None = None


class ProductStatusIn(BaseModel):
    status: str


def product_to_dict(product: Product, *, want_count: int = 0, wanted: bool = False) -> dict:
    return {
        "id": product.id,
        "seller_id": product.seller_id,
        "title": product.title,
        "description": product.description,
        "category": product.category,
        "price": product.price,
        "negotiable": product.negotiable,
        "item_condition": product.item_condition,
        "campus": product.campus,
        "dorm_building": product.dorm_building,
        "meetup_place": product.meetup_place,
        "available_time": product.available_time,
        "cover_image_path": product.cover_image_path,
        "image_paths": product.image_paths,
        "status": product.status,
        "want_count": want_count,
        "wanted": wanted,
        "created_at": product.created_at,
        "updated_at": product.updated_at,
    }


def product_with_wants(
    db: Session, product: Product, user_id: int | None
) -> dict:
    """单条商品的序列化：额外填充「想要」计数与当前用户是否已想要。"""
    want_count = db.query(func.count(Want.id)).filter(Want.product_id == product.id).scalar() or 0
    wanted = False
    if user_id is not None:
        wanted = (
            db.query(Want.id)
            .filter(Want.product_id == product.id, Want.user_id == user_id)
            .first()
            is not None
        )
    return product_to_dict(product, want_count=want_count, wanted=wanted)


def _want_meta(
    db: Session, product_ids: list[int], user_id: int | None
) -> tuple[dict[int, int], set[int]]:
    """批量查询「想要」计数与当前用户已想要的商品 id，避免逐条查询（N+1）。"""
    if not product_ids:
        return {}, set()

    count_rows = (
        db.query(Want.product_id, func.count(Want.id))
        .filter(Want.product_id.in_(product_ids))
        .group_by(Want.product_id)
        .all()
    )
    counts = {pid: cnt for pid, cnt in count_rows}

    wanted_ids: set[int] = set()
    if user_id is not None:
        wanted_rows = (
            db.query(Want.product_id)
            .filter(Want.product_id.in_(product_ids), Want.user_id == user_id)
            .all()
        )
        wanted_ids = {pid for (pid,) in wanted_rows}

    return counts, wanted_ids


def _parse_status_filter(status: str | None):
    """返回 None 表示不过滤；否则返回需要命中的状态列表。"""
    if not status:
        return ["on_sale", "reserved"]
    if status.strip() == "all":
        return None
    codes = [s.strip() for s in status.split(",") if s.strip()]
    return codes or ["on_sale", "reserved"]


@router.post("", summary="发布商品（需已实名认证）")
def create_product(
    payload: ProductCreateIn,
    user_id: int = Depends(require_verified),
    db: Session = Depends(get_db),
):
    product = Product(
        seller_id=user_id,
        title=payload.title,
        price=payload.price,
        description=payload.description,
        dorm_building=payload.dorm_building,
        category=payload.category,
        campus=payload.campus,
        meetup_place=payload.meetup_place,
        available_time=payload.available_time,
        negotiable=payload.negotiable,
        item_condition=payload.item_condition,
        cover_image_path=payload.cover_image_path,
        image_paths=payload.image_paths,
        status="on_sale",
    )
    db.add(product)
    db.commit()
    db.refresh(product)
    return product_to_dict(product)


@router.get("", summary="商品列表（关键词/分类/校区/宿舍楼/卖家/状态 + 排序）")
def list_products(
    keyword: str | None = None,
    category: str | None = None,
    campus: str | None = None,
    dorm_building: str | None = None,
    seller_id: int | None = None,
    status: str | None = None,
    sort: str = "latest",
    limit: int = 20,
    offset: int = 0,
    user_id: int | None = Depends(get_optional_user_id),
    db: Session = Depends(get_db),
):
    query = db.query(Product)

    status_filter = _parse_status_filter(status)
    if status_filter is not None:
        query = query.filter(Product.status.in_(status_filter))

    if keyword:
        query = query.filter(
            or_(Product.title.contains(keyword), Product.description.contains(keyword))
        )
    if category:
        query = query.filter(Product.category == category)
    if campus:
        query = query.filter(Product.campus == campus)
    if dorm_building:
        query = query.filter(Product.dorm_building == dorm_building)
    if seller_id is not None:
        query = query.filter(Product.seller_id == seller_id)

    total = query.count()

    if sort == "price":
        query = query.order_by(Product.price.asc(), Product.created_at.desc())
    else:
        query = query.order_by(Product.created_at.desc())

    items = query.offset(offset).limit(limit).all()
    counts, wanted_ids = _want_meta(db, [p.id for p in items], user_id)

    return {
        "total": total,
        "items": [
            product_to_dict(
                p, want_count=counts.get(p.id, 0), wanted=p.id in wanted_ids
            )
            for p in items
        ],
    }


@router.get("/{product_id}", summary="商品详情")
def get_product(
    product_id: int,
    user_id: int | None = Depends(get_optional_user_id),
    db: Session = Depends(get_db),
):
    product = db.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="商品不存在")
    return product_with_wants(db, product, user_id)


@router.post("/{product_id}/status", summary="卖家变更商品状态")
def set_product_status(
    product_id: int,
    payload: ProductStatusIn,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    if payload.status not in PRODUCT_STATUSES:
        raise HTTPException(status_code=400, detail="不支持的商品状态")

    product = db.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="商品不存在")
    if product.seller_id != user_id:
        raise HTTPException(status_code=403, detail="只有卖家本人可以修改商品状态")

    product.status = payload.status
    db.commit()
    db.refresh(product)
    return product_with_wants(db, product, user_id)


@router.post("/{product_id}/sold", summary="卖家标记已出")
def mark_product_sold(
    product_id: int,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    product = db.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="商品不存在")
    if product.seller_id != user_id:
        raise HTTPException(status_code=403, detail="只有卖家本人可以标记已出")

    product.status = "sold"
    db.commit()
    db.refresh(product)
    return product_to_dict(product)


@router.post("/{product_id}/want", summary="标记「想要」（幂等）")
def want_product(
    product_id: int,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    product = db.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="商品不存在")

    exists = (
        db.query(Want)
        .filter(Want.product_id == product_id, Want.user_id == user_id)
        .first()
    )
    if not exists:
        db.add(Want(product_id=product_id, user_id=user_id))
        db.commit()

    want_count = db.query(func.count(Want.id)).filter(Want.product_id == product_id).scalar() or 0
    return {"wanted": True, "want_count": want_count}


@router.delete("/{product_id}/want", summary="取消「想要」（幂等）")
def unwant_product(
    product_id: int,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    product = db.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="商品不存在")

    db.query(Want).filter(Want.product_id == product_id, Want.user_id == user_id).delete()
    db.commit()

    want_count = db.query(func.count(Want.id)).filter(Want.product_id == product_id).scalar() or 0
    return {"wanted": False, "want_count": want_count}
