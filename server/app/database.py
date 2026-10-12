"""数据库连接与会话管理（SQLite + SQLAlchemy）。"""

from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

# 数据库文件固定放在 server/ 目录下，避免受启动时工作目录影响
BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "campus_flea.db"

SQLALCHEMY_DATABASE_URL = f"sqlite:///{DB_PATH}"

# check_same_thread=False：SQLite 默认限制单线程，FastAPI 多线程访问需要放开
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    """FastAPI 依赖：提供一次请求级别的数据库会话。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
