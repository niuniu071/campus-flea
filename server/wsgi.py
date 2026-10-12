"""WSGI 入口：供 PythonAnywhere 等只支持 WSGI 的宿主使用。

FastAPI 是 ASGI 应用，PythonAnywhere 免费档只提供 WSGI 宿主，
这里用 a2wsgi 把 ASGI 应用包成标准的 WSGI 可调用对象 `application`。

本地开发仍然用 run.py（uvicorn），不受影响。
"""

from a2wsgi import ASGIMiddleware

from app.main import app as asgi_app

application = ASGIMiddleware(asgi_app)