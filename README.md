# cellpose web

<p align="center">
  🛰️一个cellpose的简单web前后端🛰️<br><br>
  <img alt="Static Badge" src="https://img.shields.io/badge/Python-3.12-blue">
  <img alt="Static Badge" src="https://img.shields.io/badge/Redis-6.4.0-red">
  <img alt="Static Badge" src="https://img.shields.io/badge/JSDelivr-in_use-brown">
  <img alt="Static Badge" src="https://img.shields.io/badge/Flask-3.1.2-8ecae6">
</p>

<br>

🌈 实现功能：

- 🚀 一键上传，在线调参
- ⛵️ 训练、分割结果随时下载
- 📚 权重可直接作为后续分割模型
- 🛠️ 一键安装部署脚本
- 🎨 前端样式美化

<br>

## 🛠️手动部署

#### 0. 克隆本仓库至本地

```shell
git clone https://github.com/ClovertaTheTrilobita/cellpose-web.git
```

#### 1.修改配置文件

##### 后端配置文件位于[`backend/config.yaml`](backend/config.yaml)

默认配置如下：

```yaml
backend:
  ip: 192.168.193.141
  port: 5000

model:
  save_dir: models

data:
  root_dir: .

  run:
    test_output_dir: ${data.root_dir}/run/test_output
    output_dir: ${data.root_dir}/run/output

  train:
    test_test_dir: ${data.root_dir}/train/test_test
    test_train_dir: ${data.root_dir}/train/test_train
    test_dir: ${data.root_dir}/train/test
    train_dir: ${data.root_dir}/train/train

  upload_dir: ${data.root_dir}/uploads
```

请修改`ip`字段为你PC/服务器的ip。

##### 前端配置文件位于[`fronted/api.js`](frontend/api.js)

默认配置如下：

```javascript
const config = {
  server: {
    protocol: 'http',
    host: '192.168.193.141',
    port: 5000
  }
};

const API_BASE = `${config.server.protocol}://${config.server.host}:${config.server.port}/`;
```

请将`host`、`port`设置为和后端一致。

#### 2.Conda

推荐你使用`conda`作为Python环境管理器。

`Anaconda官网`：https://www.anaconda.com/

```shell
conda create -n cpweb python=3.12
```

#### 3.安装redis

项目使用`redis`作为临时存储数据库。在启动前你需要先安装它：

- **Windows**

  详见官方手册：<b>[Install Redis on Windows | Docs](https://redis.io/docs/latest/operate/oss_and_stack/install/archive/install-redis/install-redis-on-windows/)</b>

  Windows上推荐使用`PhpStudy`管理redis：<b>[phpstudy - Windows | 小皮面板](https://www.xp.cn/phpstudy)</b>

- **Debian/Ubuntu**

  ```shell
  sudo apt install redis-server
  ```

  安装完成后，Redis服务会自动启动。您可以使用以下命令检查Redis服务的状态：

  ```shell
  sudo systemctl status redis-server
  ```

- **Arch Linux**

  由于redis政策，其已从Arch官方仓库中移除，你可以安装redis的开源分支`valkey`，功能与redis完全相同：

  ```shell
  sudo pacman -S valkey
  sudo systemctl enable --now valkey
  ```

#### 4.安装依赖

启用你的Conda环境，并安装依赖：

```shell
conda activate cpweb
pip install -r requirements.txt
```

#### 5. 启动后端

```shell
cd backend/
python main.py
```

这会在你的机器上启动flask后端。默认监听`5000`端口。

#### 6.关于默认前端

项目有一个简单的默认前端。你可以配置`Nginx`实现从浏览器访问这几个HTML文件。

请将Nginx指向<b>[`frontend/index.html`](frontend/index.html)</b>。

如果你在本地部署，你可以在启动后端后直接打开<b>[`index.html`](frontend/index.html)</b>，开始使用。
