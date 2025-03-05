#!/bin/bash

# 创建虚拟环境
python3 -m venv .venv
source .venv/bin/activate

# 设置阿里云镜像源
cat << EOF > .venv/pip/pip.conf
[global]
index-url = https://mirrors.aliyun.com/pypi/simple
trusted-host = mirrors.aliyun.com
EOF

# 安装依赖
pip install -r requirements.txt

# 安装PyInstaller
pip install pyinstaller

#pyinstaller --onefile --add-data ".env:." main.py
pyinstaller --name svc_ids --onefile main.py
# 拷贝 .env
cp .env dist/
