# MCP Server — 安装与使用说明

---

## 一、前置条件

1. **Python 3.11+**
2. **guancli 已安装并登录**
   ```bash
   guancli auth status   # 确认已登录
   guancli auth whoami   # 确认账号正确
   ```
   如未登录：
   ```bash
   guancli auth login --url https://your-bi-domain.com --save-password
   ```

---

## 二、安装

```bash
cd mcp_server

# 建议使用独立虚拟环境
python3 -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate

pip install -r requirements.txt
```

---

## 三、配置

在项目根目录的 `.env` 文件中添加（或确认已有）以下配置：

```env
# MCP Server
MCP_HOST=0.0.0.0    # 公网部署保持默认；仅本机访问改为 127.0.0.1
MCP_PORT=8000        # 端口，确保防火墙已放行
MCP_TRANSPORT=sse    # 飞书 Agent 使用 sse
```

`.env` 位于项目根目录（与 `python/` 版本共用），不提交到 git。

---

## 四、启动

```bash
cd mcp_server
source .venv/bin/activate

# 使用 .env 配置启动（推荐）
python server.py

# 或命令行临时覆盖
python server.py --port 9000
python server.py --host 127.0.0.1 --port 8000

# stdio 模式（本地调试，不启动 HTTP）
python server.py --transport stdio
```

启动成功后输出：
```
MCP Server 启动: http://0.0.0.0:8000/sse
INFO: Application startup complete.
```

---

## 五、本地验证

```bash
# 直接运行测试脚本（需在 mcp_server/ 目录下）
python test_client.py
```

预期输出：
- `list_cards`：返回 11 张卡片信息
- `get_card_data`：返回卡片实时数据（数值为原始 float/int）

---

## 六、接入飞书 Agent

### 6.1 确认 MCP Server 可访问

在飞书 Agent 能访问的网络中，确认服务器 IP 和端口可达：
```bash
# 在飞书 Agent 所在网络测试
curl http://<your-server-ip>:<port>/sse
```

### 6.2 在飞书智能伙伴创作平台添加 MCP 工具

1. 进入「工具」→「添加工具」→「MCP」
2. 填入 MCP Server 地址：`http://<your-server-ip>:8000/sse`
3. 保存后，平台会自动发现 `list_cards` 和 `get_card_data` 两个工具

### 6.3 配置 Agent System Prompt（建议）

在 Agent 的系统提示中补充以下说明，帮助 Agent 更准确地使用工具：

```
你可以通过 BI 工具查询仪表板数据。使用流程：
1. 调用 list_cards 了解当前仪表板有哪些卡片及其业务含义
2. 根据用户问题，选择最匹配的卡片
3. 调用 get_card_data 获取实时数据
4. 将数据整理后用自然语言回答用户

注意：
- 数值字段为原始值，百分比字段为小数（如 -0.21 = -21%）
- 金额单位为元（如 20489639 = 约 2049 万元）
- 不需要对数据进行二次计算，BI 已完成所有聚合
- 如用户指定了筛选条件（如"SS26 波段"），通过 filters 参数传入
```

---

## 七、后台运行（生产部署）

### 方式 A：nohup（简单）

```bash
cd mcp_server
source .venv/bin/activate
nohup python server.py > logs/server.log 2>&1 &
echo $! > server.pid
```

查看日志：
```bash
tail -f logs/server.log
```

停止：
```bash
kill $(cat server.pid)
```

### 方式 B：systemd（推荐，Linux 服务器）

创建 `/etc/systemd/system/bi-mcp.service`：

```ini
[Unit]
Description=BI Assistant MCP Server
After=network.target

[Service]
Type=simple
User=your-user
WorkingDirectory=/path/to/BI_AI_Robot/mcp_server
ExecStart=/path/to/BI_AI_Robot/mcp_server/.venv/bin/python server.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable bi-mcp
sudo systemctl start bi-mcp
sudo systemctl status bi-mcp
```

---

## 八、常见问题

**Q: 启动报 `address already in use`**
```bash
lsof -ti:8000 | xargs kill -9
```

**Q: guancli 调用失败 / Token 过期**
```bash
guancli auth status
guancli auth login --save-password   # 重新登录并保存密码
```

**Q: 飞书 Agent 无法连接**
- 确认防火墙已放行对应端口
- 确认 `MCP_HOST=0.0.0.0`（不是 127.0.0.1）
- 如在内网，确认飞书服务器与 MCP Server 在同一网络或有路由

**Q: get_card_data 返回 null 值**
- 筛选条件的字段值不存在于当前数据中（正常行为）
- 确认 filter 字段名与 `available_filters` 列表一致
