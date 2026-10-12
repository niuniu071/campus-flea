"""启动入口：python run.py

本地：默认监听 127.0.0.1:8000 并开启热重载，行为和以前一致。
云端：平台（如 Render）会注入 PORT 环境变量，此时自动监听 0.0.0.0 并关闭热重载。
"""

import os

import uvicorn

if __name__ == "__main__":
    is_cloud = "PORT" in os.environ
    uvicorn.run(
        "app.main:app",
        host=os.getenv("HOST", "0.0.0.0" if is_cloud else "127.0.0.1"),
        port=int(os.getenv("PORT", "8000")),
        reload=not is_cloud,
    )
