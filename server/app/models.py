"""数据表模型：用户 / 商品 / 会话 / 消息。

说明（当前阶段限定）：
- 图片一律使用文本路径字段代替，暂不做上传功能；
- 暂不做加密、邮箱验证码、JWT 鉴权、WebSocket。
"""

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from .database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    """用户表。"""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    nickname = Column(String(50), nullable=False)
    avatar_path = Column(String(255))          # 头像：文本路径代替图片上传
    school = Column(String(100))               # 学校
    campus = Column(String(50))                # 校区：东区 / 西区 / 北区
    dorm_building = Column(String(50))         # 宿舍楼
    student_no = Column(String(50), unique=True, index=True)  # 学号
    email = Column(String(100), unique=True, index=True)      # 校园邮箱
    is_verified = Column(Boolean, default=False, nullable=False)  # 认证状态（暂不实现校验）
    credit_score = Column(Integer, default=100, nullable=False)   # 信用分
    created_at = Column(DateTime, default=_utcnow, nullable=False)

    products = relationship("Product", back_populates="seller")
    buyer_conversations = relationship(
        "Conversation", foreign_keys="Conversation.buyer_id", back_populates="buyer"
    )
    seller_conversations = relationship(
        "Conversation", foreign_keys="Conversation.seller_id", back_populates="seller"
    )
    messages = relationship("Message", back_populates="sender")


class Product(Base):
    """商品表。"""

    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    seller_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    title = Column(String(100), nullable=False)
    description = Column(Text)
    category = Column(String(30))              # 分类：数码 / 教材 / 生活 / 服饰 / 其他
    price = Column(Float, nullable=False, default=0.0)
    negotiable = Column(Boolean, default=True, nullable=False)  # 是否可议价
    item_condition = Column(String(20))        # 成色
    campus = Column(String(50))                # 校区
    dorm_building = Column(String(50))         # 宿舍楼
    meetup_place = Column(String(100))         # 预设面交地点
    available_time = Column(String(100))       # 可交易时间段
    cover_image_path = Column(String(255))     # 主图：文本路径代替图片上传
    image_paths = Column(Text)                 # 多图：文本路径，逗号分隔
    status = Column(String(20), default="on_sale", nullable=False)  # on_sale/reserved/sold/off_shelf
    created_at = Column(DateTime, default=_utcnow, nullable=False)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow, nullable=False)

    seller = relationship("User", back_populates="products")
    conversations = relationship("Conversation", back_populates="product")


class Conversation(Base):
    """会话表：买家与卖家围绕某件商品的一对一沟通（HTTP 轮询，暂不用 WebSocket）。"""

    __tablename__ = "conversations"

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False, index=True)
    buyer_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    seller_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    created_at = Column(DateTime, default=_utcnow, nullable=False)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow, nullable=False)

    product = relationship("Product", back_populates="conversations")
    buyer = relationship(
        "User", foreign_keys=[buyer_id], back_populates="buyer_conversations"
    )
    seller = relationship(
        "User", foreign_keys=[seller_id], back_populates="seller_conversations"
    )
    messages = relationship(
        "Message", back_populates="conversation", cascade="all, delete-orphan"
    )


class Message(Base):
    """消息表。"""

    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(
        Integer, ForeignKey("conversations.id"), nullable=False, index=True
    )
    sender_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    content = Column(Text)
    msg_type = Column(String(10), default="text", nullable=False)  # text / image
    image_path = Column(String(255))           # 图片消息路径：文本路径代替图片上传
    is_read = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=_utcnow, nullable=False)

    conversation = relationship("Conversation", back_populates="messages")
    sender = relationship("User", back_populates="messages")


class VerificationCode(Base):
    """邮箱验证码（演示用：不发送真实邮件，验证码随接口返回）。"""

    __tablename__ = "verification_codes"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(100), nullable=False, index=True)
    code = Column(String(6), nullable=False)
    scene = Column(String(20), default="email", nullable=False)  # 预留：email / register
    expires_at = Column(DateTime, nullable=False)
    used = Column(Boolean, default=False, nullable=False)
    wrong_count = Column(Integer, default=0, nullable=False)
    locked_until = Column(DateTime)  # 连续错误达到上限后的锁定截止时间
    created_at = Column(DateTime, default=_utcnow, nullable=False)


class Want(Base):
    """「想要」标记：同一用户对同一商品只保留一条记录，用于去重计数。"""

    __tablename__ = "wants"
    __table_args__ = (UniqueConstraint("product_id", "user_id", name="uq_want_product_user"),)

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    created_at = Column(DateTime, default=_utcnow, nullable=False)


class Review(Base):
    """交易互评：同一评价人对同一商品仅可评价一次。"""

    __tablename__ = "reviews"
    __table_args__ = (
        UniqueConstraint("product_id", "from_user_id", name="uq_review_product_from"),
    )

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False, index=True)
    from_user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    to_user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    rating = Column(Integer, nullable=False)  # 1-5 星
    content = Column(Text)
    created_at = Column(DateTime, default=_utcnow, nullable=False)
