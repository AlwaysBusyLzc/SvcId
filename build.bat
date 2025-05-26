@echo off

rd /s /q "./logs" 2>nul
rd /s /q "./build" 2>nul
rd /s /q "./dist" 2>nul

rem 安装依赖
rem pip install --progress-bar off --no-cache-dir -r requirements.txt -i https://pypi.douban.com/simple
pip install --progress-bar off --no-cache-dir -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple
rem  pip install --progress-bar off --no-cache-dir -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple


rem 安装PyInstaller
pip install pyinstaller

rem pyinstaller --onefile --add-data ".env:." main.py
pyinstaller --name svc_ids --onefile main.py
rem  拷贝 .env
copy .env dist\