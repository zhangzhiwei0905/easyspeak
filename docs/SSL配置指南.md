# EasySpeak SSL 配置指南

> 备案通过后，按本文档为域名配置 HTTPS 证书。微信小程序强制要求 HTTPS。

## 前提条件

- [x] 域名 ICP 备案已通过
- [x] DNS A 记录已配置（easyspeak.amazingzz.xyz → 服务器IP）
- [x] Nginx 已安装并运行
- [x] 服务器安全组已开放 443 端口

---

## 第1步：安装 Certbot

```bash
# 方式A：pip 安装（推荐，Alinux 兼容）
pip3 install certbot certbot-nginx

# 方式B：snap 安装（如果方式A不可用）
dnf install -y snapd
systemctl enable --now snapd.socket
snap install --classic certbot
ln -s /snap/bin/certbot /usr/bin/certbot

# 验证安装
certbot --version
```

## 第2步：申请 SSL 证书

### 为 EasySpeak 申请

```bash
certbot --nginx -d easyspeak.amazingzz.xyz
```

执行过程中会问两个问题：
1. **邮箱**：填你的邮箱（用于证书过期提醒）
2. **是否重定向 HTTP → HTTPS**：选 `2`（自动把 HTTP 跳转到 HTTPS）

### 为 EasyBill 申请

```bash
certbot --nginx -d easybill.amazingzz.xyz
```

### 一次性为所有域名申请

```bash
certbot --nginx -d easyspeak.amazingzz.xyz -d easybill.amazingzz.xyz
```

## 第3步：验证 HTTPS

```bash
# 测试 EasySpeak
curl https://easyspeak.amazingzz.xyz/api/v1/health

# 测试 EasyBill
curl -I https://easybill.amazingzz.xyz
```

浏览器访问也应该能看到安全锁图标。

## 第4步：自动续期

Let's Encrypt 证书有效期 90 天，Certbot 会自动设置定时续期：

```bash
# 检查自动续期是否已配置
systemctl list-timers | grep certbot

# 手动测试续期（不会真的续，只是模拟）
certbot renew --dry-run
```

如果没有自动续期定时器，手动添加 crontab：

```bash
echo "0 3 * * * certbot renew --quiet --post-hook 'systemctl reload nginx'" | crontab -
```

含义：每天凌晨 3 点检查证书，快过期时自动续期并重载 Nginx。

## 第5步：修改小程序 baseUrl

SSL 配置完成后，修改小程序的 API 地址。

编辑 `miniprogram/utils/api.js`，将：

```javascript
baseUrl: 'http://localhost:8000/api/v1'
```

改为：

```javascript
baseUrl: 'https://easyspeak.amazingzz.xyz/api/v1'
```

同样编辑 `miniprogram/app.js` 中 globalData 里的 baseUrl。

## 第6步：微信公众平台配置

登录 [mp.weixin.qq.com](https://mp.weixin.qq.com)：

1. **开发管理 → 开发设置 → 服务器域名**
2. **request 合法域名**：`https://easyspeak.amazingzz.xyz`
3. 点击保存

注意：
- 域名必须以 `https://` 开头
- 不能有端口号
- 不能有尾部斜杠 `/`

## 第7步：上传发布

1. 微信开发者工具中打开项目
2. 确认 baseUrl 已改为线上地址
3. 点击右上角 **上传**，填写版本号和备注
4. 登录微信公众平台 → **版本管理**
5. 将开发版提交审核
6. 审核通过后点击 **发布**

---

## 证书文件位置

```
证书: /etc/letsencrypt/live/easyspeak.amazingzz.xyz/fullchain.pem
私钥: /etc/letsencrypt/live/easyspeak.amazingzz.xyz/privkey.pem
```

Certbot 会自动修改 Nginx 配置，添加 SSL 相关指令。

## 常见问题

### Q: certbot 报错 "Connection refused"
确保 Nginx 正在运行且 80 端口可访问：`systemctl status nginx`

### Q: certbot 报错 "Domain not found"
DNS 还没生效，等几分钟再试。用 `nslookup easyspeak.amazingzz.xyz` 确认。

### Q: 小程序提示 "不在以下 request 合法域名列表中"
检查微信公众平台的服务器域名配置是否正确，以及 baseUrl 是否用了 `https://`。

### Q: 需要给更多子域名加证书
```bash
certbot --nginx -d 新子域名.amazingzz.xyz
```
Certbot 会自动为新的子域名申请证书并更新 Nginx 配置。
