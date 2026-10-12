"""聊天模块：会话创建 / 发送消息 / 获取聊天记录（简单 HTTP，无 WebSocket）。"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from .database import get_db
from .deps import get_current_user_id
from .models import Conversation, Message, Product, User
from .product import product_to_dict
from .user import user_to_dict

router = APIRouter(prefix="/chat", tags=["chat"])


class ConversationIn(BaseModel):
    product_id: int


class MessageIn(BaseModel):
    conversation_id: int
    content: str | None = None
    msg_type: str = "text"  # text / image
    image_path: str | None = None


def conversation_to_dict(conv: Conversation) -> dict:
    return {
        "id": conv.id,
        "product_id": conv.product_id,
        "buyer_id": conv.buyer_id,
        "seller_id": conv.seller_id,
        "created_at": conv.created_at,
        "updated_at": conv.updated_at,
    }


def message_to_dict(msg: Message) -> dict:
    return {
        "id": msg.id,
        "conversation_id": msg.conversation_id,
        "sender_id": msg.sender_id,
        "content": msg.content,
        "msg_type": msg.msg_type,
        "image_path": msg.image_path,
        "is_read": msg.is_read,
        "created_at": msg.created_at,
    }


@router.post("/conversations", summary="创建或获取会话（买家对商品发起）")
def get_or_create_conversation(
    payload: ConversationIn,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    product = db.get(Product, payload.product_id)
    if not product:
        raise HTTPException(status_code=404, detail="商品不存在")
    if product.seller_id == user_id:
        raise HTTPException(status_code=400, detail="不能对自已发布的商品发起会话")

    conv = (
        db.query(Conversation)
        .filter(
            Conversation.product_id == payload.product_id,
            Conversation.buyer_id == user_id,
            Conversation.seller_id == product.seller_id,
        )
        .first()
    )
    if not conv:
        conv = Conversation(
            product_id=payload.product_id,
            buyer_id=user_id,
            seller_id=product.seller_id,
        )
        db.add(conv)
        db.commit()
        db.refresh(conv)
    return conversation_to_dict(conv)


@router.post("/messages", summary="发送消息")
def send_message(
    payload: MessageIn,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    conv = db.get(Conversation, payload.conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="会话不存在")
    if user_id not in (conv.buyer_id, conv.seller_id):
        raise HTTPException(status_code=403, detail="你不在该会话中")
    if payload.msg_type == "text" and not payload.content:
        raise HTTPException(status_code=400, detail="文本消息内容不能为空")

    msg = Message(
        conversation_id=conv.id,
        sender_id=user_id,
        content=payload.content,
        msg_type=payload.msg_type,
        image_path=payload.image_path,
    )
    conv.updated_at = datetime.now(timezone.utc)
    db.add(msg)
    db.commit()
    db.refresh(msg)
    return message_to_dict(msg)


@router.get("/messages", summary="获取聊天记录")
def list_messages(
    conversation_id: int,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    conv = db.get(Conversation, conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="会话不存在")

    msgs = (
        db.query(Message)
        .filter(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.asc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return {"conversation_id": conversation_id, "items": [message_to_dict(m) for m in msgs]}


@router.get("/conversations", summary="当前用户的会话列表（含对方、最后一条消息、未读数）")
def list_conversations(
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    convs = (
        db.query(Conversation)
        .filter(or_(Conversation.buyer_id == user_id, Conversation.seller_id == user_id))
        .order_by(Conversation.updated_at.desc())
        .all()
    )
    conv_ids = [c.id for c in convs]

    unread_map: dict[int, int] = {}
    last_map: dict[int, Message] = {}
    if conv_ids:
        unread_rows = (
            db.query(Message.conversation_id, func.count(Message.id))
            .filter(
                Message.conversation_id.in_(conv_ids),
                Message.is_read.is_(False),
                Message.sender_id != user_id,
            )
            .group_by(Message.conversation_id)
            .all()
        )
        unread_map = {cid: cnt for cid, cnt in unread_rows}

        last_id_rows = (
            db.query(Message.conversation_id, func.max(Message.id))
            .filter(Message.conversation_id.in_(conv_ids))
            .group_by(Message.conversation_id)
            .all()
        )
        last_ids = [mid for _, mid in last_id_rows]
        if last_ids:
            last_msgs = db.query(Message).filter(Message.id.in_(last_ids)).all()
            last_map = {m.conversation_id: m for m in last_msgs}

    product_ids = {c.product_id for c in convs}
    pmap: dict[int, Product] = {}
    if product_ids:
        products = db.query(Product).filter(Product.id.in_(product_ids)).all()
        pmap = {p.id: p for p in products}

    other_ids = {
        (c.seller_id if c.buyer_id == user_id else c.buyer_id) for c in convs
    }
    umap: dict[int, User] = {}
    if other_ids:
        users = db.query(User).filter(User.id.in_(other_ids)).all()
        umap = {u.id: u for u in users}

    items = []
    for conv in convs:
        other_id = conv.seller_id if conv.buyer_id == user_id else conv.buyer_id
        product = pmap.get(conv.product_id)
        other = umap.get(other_id)
        last = last_map.get(conv.id)
        items.append(
            {
                **conversation_to_dict(conv),
                "unread": unread_map.get(conv.id, 0),
                "product": product_to_dict(product) if product else None,
                "other_user": user_to_dict(other) if other else None,
                "last_message": message_to_dict(last) if last else None,
            }
        )

    return {"total": len(items), "items": items}


@router.post("/conversations/{conversation_id}/read", summary="标记会话已读")
def read_conversation(
    conversation_id: int,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    conv = db.get(Conversation, conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="会话不存在")
    if user_id not in (conv.buyer_id, conv.seller_id):
        raise HTTPException(status_code=403, detail="你不在该会话中")

    updated = (
        db.query(Message)
        .filter(
            Message.conversation_id == conversation_id,
            Message.sender_id != user_id,
            Message.is_read.is_(False),
        )
        .update({Message.is_read: True}, synchronize_session=False)
    )
    db.commit()
    return {"conversation_id": conversation_id, "updated": updated}
