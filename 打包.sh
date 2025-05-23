#!/bin/bash

#apt update -y
#apt install python3.10-venv
#
## 创建虚拟环境
#python3 -m venv .venv
#source .venv/bin/activate
#
## 设置阿里云镜像源
#cat << EOF > .venv/pip/pip.conf
#[global]
#index-url = https://mirrors.aliyun.com/pypi/simple
#trusted-host = mirrors.aliyun.com
#EOF



# 安装依赖
#pip install --progress-bar off --no-cache-dir -r requirements.txt -i https://pypi.douban.com/simple
pip install --progress-bar off --no-cache-dir -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple
#pip install --progress-bar off --no-cache-dir -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple


# 安装PyInstaller
pip install pyinstaller

#pyinstaller --onefile --add-data ".env:." main.py
pyinstaller --name svc_ids --onefile main.py
# 拷贝 .env
cp .env dist/
