#!/bin/bash
# EasySpeak 后端部署脚本
# 适用于阿里云 Alinux / CentOS / Ubuntu
# 使用方法: bash deploy/setup.sh easyspeak.yourdomain.com
#
# 前提条件:
#   1. 阿里云域名已备案
#   2. 子域名 DNS 已解析到服务器 IP（A记录）
#   3. 服务器安全组开放了 80 和 443 端口

set -e

DOMAIN=${1:?"用法: bash setup.sh easyspeak.yourdomain.com"}
APP_DIR="/opt/easyspeak"
APP_USER="easyspeak"

echo "========================================="
echo "  EasySpeak 部署脚本"
echo "  域名: ${DOMAIN}"
echo "  安装目录: ${APP_DIR}"
echo "========================================="

# ========================
# 1. 安装系统依赖
# ========================
echo ""
echo "[1/6] 安装系统依赖..."

if command -v dnf &> /dev/null; then
    # Alinux / CentOS 8+
    dnf install -y python3 python3-pip git nginx certbot python3-certbot-nginx
elif command -v yum &> /dev/null; then
    # CentOS 7
    yum install -y python3 python3-pip git nginx certbot python3-certbot-nginx
elif command -v apt &> /dev/null; then
    # Ubuntu / Debian
    apt update && apt install -y python3 python3-pip python3-venv git nginx certbot python3-certbot-nginx
fi

echo "系统依赖安装完成。"

# ========================
# 2. 创建用户和目录
# ========================
echo ""
echo "[2/6] 创建应用目录..."

id -u ${APP_USER} &>/dev/null || useradd -r -s /sbin/nologin ${APP_USER}

mkdir -p ${APP_DIR}/backend
mkdir -p ${APP_DIR}/data
mkdir -p ${APP_DIR}/logs

echo "目录创建完成。"

# ========================
# 3. 部署后端代码
# ========================
echo ""
echo "[3/6] 部署后端代码..."

# 如果是从本地上传，用 scp:
#   scp -r backend/* root@服务器IP:${APP_DIR}/backend/
#
# 如果是从 git 拉取:
#   git clone <你的仓库地址> ${APP_DIR}/repo
#   cp -r ${APP_DIR}/repo/backend/* ${APP_DIR}/backend/

cd ${APP_DIR}/backend

# 创建虚拟环境
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
pip install uvicorn[standard]

echo "后端代码部署完成。"

# ========================
# 4. 创建 .env 配置
# ========================
echo ""
echo "[4/6] 创建配置文件..."

if [ ! -f .env ]; then
    cat > .env << 'ENVEOF'
# EasySpeak 生产环境配置
DEBUG=false
DATABASE_URL=sqlite:///./data/easyspeak.db

# 管理员 API Key（请修改）
ADMIN_API_KEY=请修改为随机字符串

# JWT 密钥（请修改，可用: python3 -c "import secrets; print(secrets.token_urlsafe(32))"）
JWT_SECRET_KEY=请修改为随机密钥

# 微信小程序配置
WECHAT_APP_ID=填写你的小程序 appid
WECHAT_APP_SECRET= 填写你的小程序 appsecret
ENVEOF
    echo "已创建 .env 模板，请编辑 ${APP_DIR}/backend/.env 修改密钥！"
else
    echo ".env 已存在，跳过。"
fi

echo "配置文件准备完成。"

# ========================
# 5. 初始化数据库
# ========================
echo ""
echo "[5/6] 初始化数据库..."

source venv/bin/activate
python3 scripts/seed_data.py

echo "数据库初始化完成。"

# ========================
# 6. 配置 systemd 服务
# ========================
echo ""
echo "[6/6] 配置系统服务..."

cat > /etc/systemd/system/easyspeak.service << SVCEOF
[Unit]
Description=EasySpeak Backend API
After=network.target

[Service]
Type=simple
User=${APP_USER}
Group=${APP_USER}
WorkingDirectory=${APP_DIR}/backend
ExecStart=${APP_DIR}/backend/venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 2
Restart=always
RestartSec=5
Environment=PATH=${APP_DIR}/backend/venv/bin:/usr/bin:/bin

[Install]
WantedBy=multi-user.target
SVCEOF

chown -R ${APP_USER}:${APP_USER} ${APP_DIR}

systemctl daemon-reload
systemctl enable easyspeak
systemctl start easyspeak

echo "后端服务已启动。"

# ========================
# 7. 配置 Nginx
# ========================
echo ""
echo "[额外] 配置 Nginx..."

cat > /etc/nginx/conf.d/easyspeak.conf << 'NGINXEOF'
server {
    listen 80;
    server_name _DOMAIN_;

    # 强制 HTTPS
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name _DOMAIN_;

    # SSL 证书路径（certbot 会自动配置）
    # ssl_certificate /etc/letsencrypt/live/_DOMAIN_/fullchain.pem;
    # ssl_certificate_key /etc/letsencrypt/live/_DOMAIN_/privkey.pem;

    # 临时先用 HTTP 测试，注释掉上面的 SSL 块，取消注释下面这段:
    # listen 80;
    # server_name _DOMAIN_;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_connect_timeout 60s;
        proxy_read_timeout 60s;
    }

    location /docs {
        proxy_pass http://127.0.0.1:8000;
    }
}
NGINXEOF

sed -i "s/_DOMAIN_/${DOMAIN}/g" /etc/nginx/conf.d/easyspeak.conf

nginx -t && systemctl enable nginx && systemctl restart nginx

echo ""
echo "========================================="
echo "  Nginx 配置完成"
echo ""
echo "  下一步操作:"
echo "  1. 确认 DNS 解析: dig ${DOMAIN}"
echo "  2. 测试 HTTP: curl http://${DOMAIN}/api/v1/health"
echo "  3. 申请 SSL 证书: certbot --nginx -d ${DOMAIN}"
echo "  4. 在微信公众平台配置服务器域名"
echo "  5. 修改小程序 baseUrl 为 https://${DOMAIN}/api/v1"
echo "========================================="
