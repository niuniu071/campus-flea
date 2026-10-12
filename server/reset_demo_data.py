"""重置演示数据。

用途：把数据库恢复到"干净可演示"的状态，供提交 / 答辩时使用。

它会做这几件事：
1. 清空全部业务数据（用户、商品、会话、消息、想要、评价、验证码）；
2. 写入 3 个已认证的演示用户（学号认证已通过，无需密码，走邮箱验证码流程即可登录）；
3. 写入 5 条干净的演示商品，归属到上述演示用户，校区统一为
   沙河校区 / 小营校区 / 天枢校区（与前端 campus.ts 的枚举一致）。

用法（在 server 目录下）：
    python reset_demo_data.py

注意：本脚本只增删数据，不修改任何表结构。
"""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# 允许直接以脚本方式运行（python reset_demo_data.py）
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.database import Base, SessionLocal, engine  # noqa: E402
from app.models import (  # noqa: E402
    Conversation,
    Message,
    Product,
    Review,
    User,
    VerificationCode,
    Want,
)

SCHOOL = "北京信息科技大学"

# 3 个演示用户：is_verified=True，直接可用
DEMO_USERS = [
    {
        "nickname": "张同学",
        "email": "student1@stu.edu",
        "student_no": "2023010101",
        "campus": "沙河校区",
        "dorm_building": "学一A",
        "credit_score": 102,
    },
    {
        "nickname": "李同学",
        "email": "student2@stu.edu",
        "student_no": "2023010102",
        "campus": "小营校区",
        "dorm_building": "学三A",
        "credit_score": 100,
    },
    {
        "nickname": "王同学",
        "email": "student3@stu.edu",
        "student_no": "2023010103",
        "campus": "天枢校区",
        "dorm_building": "学五A",
        "credit_score": 98,
    },
]

# 5 条演示商品：分类 / 成色 / 面交地点 / 时间段均取自前端常量，保证与界面选项一致
DEMO_PRODUCTS = [
    {
        "owner": "student1@stu.edu",
        "title": "二手机械键盘 87 键 青轴",
        "description": "大一买的机械键盘，青轴手感很好，因为换了静音轴所以出掉。按键全部正常，附赠原装数据线。",
        "category": "数码",
        "price": 99.0,
        "negotiable": True,
        "item_condition": "轻微使用痕迹",
        "meetup_place": "一食堂门口",
        "available_time": "周末上午,周末全天",
    },
    {
        "owner": "student1@stu.edu",
        "title": "高等数学教材（同济第七版 上册）",
        "description": "上学期用的高数教材，书角有一点点折痕，内页没有笔记，干干净净。",
        "category": "教材",
        "price": 15.0,
        "negotiable": True,
        "item_condition": "几乎全新",
        "meetup_place": "图书馆东门",
        "available_time": "工作日中午,工作日晚间",
    },
    {
        "owner": "student2@stu.edu",
        "title": "九成新通勤自行车 24 寸",
        "description": "骑了一年的通勤车，刹车和变速都正常，毕业离校出掉，可小刀。",
        "category": "生活",
        "price": 180.0,
        "negotiable": True,
        "item_condition": "轻微使用痕迹",
        "meetup_place": "菜鸟驿站",
        "available_time": "周末全天",
    },
    {
        "owner": "student3@stu.edu",
        "title": "加厚卫衣 男款 L 码（只穿过两次）",
        "description": "买大了一码，只穿过两次，无污渍无起球，实拍图可以私聊发。",
        "category": "服饰",
        "price": 45.0,
        "negotiable": False,
        "item_condition": "几乎全新",
        "meetup_place": "教学楼A座",
        "available_time": "工作日下午,工作日晚间",
    },
    {
        "owner": "student2@stu.edu",
        "title": "考研英语真题集（2010-2023）",
        "description": "备考时用的真题册，做过一遍，答案部分有少量铅笔笔记，可擦除。",
        "category": "教材",
        "price": 20.0,
        "negotiable": True,
        "item_condition": "明显使用痕迹",
        "meetup_place": "体育馆南门",
        "available_time": "工作日中午",
    },
]


def main() -> None:
    # 表不存在时先建表（不会改动已有表结构）
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        # 1) 清空业务数据（先删有外键指向的从表）
        for model in (Message, Conversation, Want, Review, Product, VerificationCode, User):
            deleted = db.query(model).delete()
            print(f"  清空 {model.__tablename__:<20} {deleted} 行")
        db.commit()

        # 2) 写入演示用户
        users: dict[str, User] = {}
        for item in DEMO_USERS:
            user = User(
                nickname=item["nickname"],
                email=item["email"],
                student_no=item["student_no"],
                school=SCHOOL,
                campus=item["campus"],
                dorm_building=item["dorm_building"],
                is_verified=True,
                credit_score=item["credit_score"],
            )
            db.add(user)
            users[item["email"]] = user
        db.commit()

        # 3) 写入演示商品（校区 / 宿舍楼跟随卖家，保证筛选结果合理）
        now = datetime.now(timezone.utc)
        for index, item in enumerate(DEMO_PRODUCTS):
            seller = users[item["owner"]]
            db.add(
                Product(
                    seller_id=seller.id,
                    title=item["title"],
                    description=item["description"],
                    category=item["category"],
                    price=item["price"],
                    negotiable=item["negotiable"],
                    item_condition=item["item_condition"],
                    campus=seller.campus,
                    dorm_building=seller.dorm_building,
                    meetup_place=item["meetup_place"],
                    available_time=item["available_time"],
                    status="on_sale",
                    created_at=now - timedelta(days=index, hours=index),
                )
            )
        db.commit()

        # 4) 结果回显
        print("\n重置完成：")
        print(f"  用户 {db.query(User).count()} 个：")
        for user in db.query(User).order_by(User.id).all():
            print(
                f"    id={user.id} {user.nickname} {user.email} "
                f"{user.campus} {user.dorm_building} 信用分{user.credit_score}"
            )
        print(f"  商品 {db.query(Product).count()} 件：")
        for product in db.query(Product).order_by(Product.id).all():
            print(
                f"    id={product.id} [{product.category}] {product.title} "
                f"￥{product.price:g} {product.campus}/{product.dorm_building}"
            )
    finally:
        db.close()


if __name__ == "__main__":
    main()
