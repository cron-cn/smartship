# Ubuntu 24.04 + Nginx 部署文档

这份文档用于把 `hub` 目录下的 Flask 设备管理表部署到 Ubuntu 24.04 服务器上。

默认效果：
- 浏览器访问域名后由 Nginx 反向代理到 Gunicorn
- 应用以 systemd 服务方式后台常驻
- 数据库和上传文件保存在项目目录内
- 编辑模式需要输入密码 `hululu1021`

## 1. 安装系统依赖

先更新系统并安装 Python、Nginx 和构建依赖：

```bash
sudo apt update
sudo apt -y upgrade
sudo apt install -y python3 python3-venv python3-pip nginx
```

## 2. 放置项目

假设你的项目放在 `/opt/lab-device-manager`。如果实际路径不同，后面的命令把路径统一替换掉即可。

```bash
sudo mkdir -p /opt/lab-device-manager
sudo chown -R $USER:$USER /opt/lab-device-manager
```

如果你是从本地上传代码到服务器，可以把 `hub` 目录同步到这个路径下，最终目录结构类似：

```text
/opt/lab-device-manager/
└── hub/
    ├── app.py
    ├── requirements.txt
    ├── templates/
    ├── static/
    └── data/
```

## 3. 创建虚拟环境并安装依赖

```bash
cd /opt/lab-device-manager/hub
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

## 4. 先做一次本地启动检查

```bash
source /opt/lab-device-manager/hub/.venv/bin/activate
cd /opt/lab-device-manager/hub
python app.py
```

如果日志显示 `Running on http://127.0.0.1:5000`，说明应用能正常启动。按 `Ctrl+C` 停掉后继续下面步骤。

## 5. 创建 systemd 服务

创建服务文件：

```bash
sudo tee /etc/systemd/system/lab-device-manager.service > /dev/null <<'EOF'
[Unit]
Description=Lab Device Manager
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/opt/lab-device-manager/hub
Environment=FLASK_SECRET_KEY=lab-device-manager-secret
ExecStart=/opt/lab-device-manager/hub/.venv/bin/gunicorn -w 2 -b 127.0.0.1:8000 app:app
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
```

上面的服务文件里有两个点需要你确认：
- `WorkingDirectory` 必须是 `app.py` 所在目录，也就是 `hub`
- `FLASK_SECRET_KEY` 建议改成你自己的随机字符串

如果你的登录用户名不是 `ubuntu`，把 `User=ubuntu` 改成你自己的服务器用户名。

然后启动服务：

```bash
sudo systemctl daemon-reload
sudo systemctl enable lab-device-manager
sudo systemctl start lab-device-manager
sudo systemctl status lab-device-manager --no-pager
```

## 6. 配置 Nginx

创建站点配置：

```bash
sudo tee /etc/nginx/sites-available/lab-device-manager > /dev/null <<'EOF'
server {
    listen 80;
    server_name your-domain.com;

    client_max_body_size 50m;

    location /static/ {
        alias /opt/lab-device-manager/hub/static/;
        expires 7d;
        add_header Cache-Control "public, max-age=604800";
    }

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 300;
    }
}
EOF
```

启用站点并检查语法：

```bash
sudo ln -s /etc/nginx/sites-available/lab-device-manager /etc/nginx/sites-enabled/lab-device-manager
sudo nginx -t
sudo systemctl reload nginx
```

如果你已有默认站点冲突，可以先关闭默认站点：

```bash
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl reload nginx
```

## 7. 开放防火墙

如果服务器开启了 UFW：

```bash
sudo ufw allow 'Nginx Full'
sudo ufw status
```

## 8. 常用维护命令

查看日志：

```bash
sudo journalctl -u lab-device-manager -f
```

重启服务：

```bash
sudo systemctl restart lab-device-manager
```

停止服务：

```bash
sudo systemctl stop lab-device-manager
```

更新代码后，一般执行：

```bash
cd /opt/lab-device-manager/hub
source .venv/bin/activate
pip install -r requirements.txt
sudo systemctl restart lab-device-manager
```

## 9. 访问和权限说明

- 默认页面是只读模式
- 输入密码 `hululu1021` 后会进入编辑模式
- 编辑模式可以新增、导入、修改和删除
- 退出编辑后回到只读模式

## 10. 如果你用域名和 HTTPS

建议后续再给 Nginx 加上 Certbot 证书。等站点先跑通以后，再做：

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d your-domain.com
```

## 11. 排错顺序

如果页面打不开，优先按这个顺序查：

```bash
sudo systemctl status lab-device-manager --no-pager
sudo journalctl -u lab-device-manager --no-pager -n 100
sudo nginx -t
sudo systemctl status nginx --no-pager
```

如果你看到 502，通常是 Gunicorn 没起来或者 Nginx 指向的端口不对。
