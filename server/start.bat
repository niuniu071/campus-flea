@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv" (
    echo [1/3] 创建虚拟环境 .venv ...
    python -m venv .venv
)

echo [2/3] 安装依赖 ...
call ".venv\Scripts\activate.bat"
python -m pip install --upgrade pip >nul
pip install -r requirements.txt

echo [3/3] 启动服务: http://127.0.0.1:8000/docs
python run.py

endlocal
