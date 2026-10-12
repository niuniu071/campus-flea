"""FastAPI 应用入口（后端骨架）。

当前阶段仅提供：
- 应用初始化与 CORS
- 启动时自动建表
- 健康检查接口

业务接口（发布 / 检索 / 聊天 / 交易）留待后续任务实现。
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import inspect, text

from . import models  # noqa: F401  导入以注册所有模型
from .chat import router as chat_router
from .database import Base, engine
from .product import router as product_router
from .review import router as review_router
from .user import router as user_router
from .verify import router as verify_router

# 启动时自动创建数据表（SQLite 文件不存在会自动生成）
Base.metadata.create_all(bind=engine)

app = FastAPI(title="校园版闲鱼 API", version="0.3.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 业务路由，统一前缀 /api
app.include_router(user_router, prefix="/api")
app.include_router(verify_router, prefix="/api")
app.include_router(product_router, prefix="/api")
app.include_router(chat_router, prefix="/api")
app.include_router(review_router, prefix="/api")


@app.get("/")
def root():
    """服务基础信息。"""
    return {
        "service": "campus-flea-api",
        "version": "0.1.0",
        "status": "ok",
        "docs": "/docs",
    }


@app.get("/health")
def health():
    """健康检查：验证数据库连通性并返回已建数据表。"""
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    return {
        "status": "ok",
        "database": "sqlite",
        "tables": inspect(engine).get_table_names(),
    }
