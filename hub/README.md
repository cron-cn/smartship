# 实验室设备管理表

这是一个本地运行的 Flask + SQLite 设备管理小应用。

## 功能

- 上半部分支持上传 1 到 3 张设备图片。
- 下半部分是参数表，包含电压、电流、数量、其他/备注、资料附件、购买链接。
- 每新增一个设备，都会在 `data/devices/` 下创建独立文件夹。
- 数据会同时写入本地 SQLite 数据库 `data/lab_equipment.db`。
- 支持设备列表、图片预览、附件下载和设备删除。

## 运行

```bash
pip install -r requirements.txt
python app.py
```

打开浏览器访问 `http://127.0.0.1:5000/`。

## 服务器部署

如果要部署到 Ubuntu 24.04 + Nginx，请看 [DEPLOYMENT_UBUNTU24_NGINX.md](DEPLOYMENT_UBUNTU24_NGINX.md)。
