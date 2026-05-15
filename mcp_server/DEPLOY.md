# MCP Server 部署 SOP

本文档描述将 `mcp_server/` 部署到 K3s 集群的完整流程，人工操作和 Claude Code (`/k3s-deploy`) 均参照此文档。

## 基本信息

| 项目 | 值 |
|---|---|
| 服务名称 | `bi-assistant` |
| Namespace | `bi-assistant` |
| Git 仓库 | `https://github.com/sse33/BI_AI_Robot.git` |
| 分支 | `main` |
| Dockerfile 位置 | `mcp_server/Dockerfile`（build context 同目录） |
| 容器端口 | `8000` |
| NodePort | `30866` |
| 目标服务器 | `shqn8n01`（172.21.10.66） |
| 服务访问地址 | `http://172.21.10.66:30866/sse` |

---

## 前置条件检查

每次部署前确认以下三项：

```bash
# 1. SSH ControlMaster 是否存活（当日登录后有效）
ls ~/.ssh/control-shqn8n01 && echo "SSH OK" || echo "需要重新 auto-transfer 登录"

# 2. K3s 节点状态
~/.claude/scripts/remote_exec.sh shqn8n01 "kubectl get nodes --no-headers"
# 应输出 Ready

# 3. buildkit 服务状态
~/.claude/scripts/remote_exec.sh shqn8n01 "systemctl is-active buildkit"
# 应输出 active；若不是则执行 systemctl start buildkit
```

---

## 环境变量（K8s Secret）

容器运行时需要以下环境变量，通过 K8s Secret 注入，**不得明文写入 deployment.yaml**。

| 变量名 | 说明 |
|---|---|
| `GY_BASE_URL` | 观远 BI 地址，如 `https://bi.xxx.com` |
| `GY_DOMAIN` | 观远登录域（可为空） |
| `GY_ACCOUNT` | 登录工号 |
| `GY_PASSWORD` | 登录密码（注意反斜杠需双重转义） |
| `MCP_API_KEY` | API 认证密钥，飞书 Agent 调用时须在请求头携带 `Authorization: Bearer <值>` |

Secret 名称：`bi-assistant-secret`

> 生成强随机密钥：`openssl rand -hex 32`

---

## K8s Manifest

### Namespace

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: bi-assistant
```

### Secret

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: bi-assistant-secret
  namespace: bi-assistant
type: Opaque
stringData:
  GY_BASE_URL: "https://bi.xxx.com"
  GY_DOMAIN: ""
  GY_ACCOUNT: "xxxxxxxx"
  GY_PASSWORD: "xxxxxxxx"
  MCP_API_KEY: "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"  # openssl rand -hex 32
```

> 注意：密码中含反斜杠时，`\0` 需写为 `\\0`，否则报 `contains nul byte`。

### Deployment

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: bi-assistant
  namespace: bi-assistant
spec:
  replicas: 1
  selector:
    matchLabels:
      app: bi-assistant
  template:
    metadata:
      labels:
        app: bi-assistant
    spec:
      containers:
        - name: bi-assistant
          image: bi-assistant:latest
          imagePullPolicy: Never
          ports:
            - containerPort: 8000
          envFrom:
            - secretRef:
                name: bi-assistant-secret
```

### Service（NodePort）

```yaml
apiVersion: v1
kind: Service
metadata:
  name: bi-assistant
  namespace: bi-assistant
spec:
  type: NodePort
  selector:
    app: bi-assistant
  ports:
    - port: 8000
      targetPort: 8000
      nodePort: 30866
```

---

## 部署步骤

### 方式一：使用 Claude Code（推荐）

在 Claude Code 对话中输入：

```
/k3s-deploy
```

Claude 会自动读取本文档中的配置信息，完成以下步骤：
1. 前置检查（SSH / k3s / buildkit）
2. 服务器上 git pull 最新代码
3. nerdctl 后台构建镜像（以 git commit SHA 为 tag）
4. 展示生成的 YAML，**等待你输入"确认"后**才执行 apply
5. kubectl apply 所有 manifest
6. 验证 Pod 状态并输出访问地址

### 方式二：手动操作

```bash
REXEC=~/.claude/scripts/remote_exec.sh
SERVER=shqn8n01
SVC=bi-assistant

# Step 1：拉取代码
$REXEC $SERVER "cd /tmp/k3s-builds/$SVC && git pull origin main"

# Step 2：构建镜像（后台，需轮询 /tmp/build-bi-assistant.log）
GIT_SHA=$($REXEC $SERVER "cd /tmp/k3s-builds/$SVC && git rev-parse --short HEAD")
$REXEC $SERVER "nohup nerdctl build \
  -t $SVC:$GIT_SHA \
  -f /tmp/k3s-builds/$SVC/mcp_server/Dockerfile \
  /tmp/k3s-builds/$SVC/mcp_server \
  > /tmp/build-$SVC.log 2>&1 & echo started"

# 等构建完成后打 latest tag
$REXEC $SERVER "nerdctl tag $SVC:$GIT_SHA $SVC:latest"

# Step 3：apply manifest（按顺序）
$REXEC $SERVER "kubectl apply -f /tmp/$SVC-namespace.yaml"
$REXEC $SERVER "kubectl apply -f /tmp/$SVC-secret.yaml"
$REXEC $SERVER "kubectl apply -f /tmp/$SVC-deployment.yaml"
$REXEC $SERVER "kubectl apply -f /tmp/$SVC-service.yaml"

# Step 4：验证
$REXEC $SERVER "kubectl rollout status deployment/$SVC -n $SVC --timeout=120s"
$REXEC $SERVER "kubectl get pods -n $SVC -o wide"
```

---

## 验证部署成功

```bash
# Pod 状态应为 Running
~/.claude/scripts/remote_exec.sh shqn8n01 "kubectl get pods -n bi-assistant"

# 无认证时返回 SSE 响应头（内网调试）
curl -I http://172.21.10.66:30866/sse

# 有认证时验证（替换为实际 MCP_API_KEY）
curl -I http://61.140.131.180:30866/sse \
  -H "Authorization: Bearer <MCP_API_KEY>"
# 期望：200 OK；无 key 时返回 401 Unauthorized
```

---

## 飞书 Aily Agent 配置

在飞书「注册企业内部 MCP 服务」界面填写：

| 字段 | 值 |
|---|---|
| 请求地址 | `http://61.140.131.180:30866/sse` |
| Endpoint 类型 | SSE |
| 请求头 | `Authorization` = `Bearer <MCP_API_KEY>` |

---

## 常见问题

| 问题 | 解决方法 |
|---|---|
| SSH socket 不存在 | 执行 `zsh` → `auto-transfer` 重新登录 |
| GitHub 被防火墙屏蔽 | 服务器 remote URL 必须始终使用代理：`git remote set-url origin https://gh-proxy.com/https://github.com/sse33/BI_AI_Robot.git`，**不得改为直连** |
| buildkit 未启动 | `systemctl start buildkit` |
| Pod CrashLoopBackOff | `kubectl logs -n bi-assistant -l app=bi-assistant --tail=50` 查看启动日志，通常是 Secret 配置错误或 guancli 登录失败 |
| NodePort 30866 冲突 | `kubectl get svc --all-namespaces | grep 30866` 排查占用 |
| 密码含特殊字符报错 | Secret stringData 中反斜杠需双重转义（`\0` → `\\0`） |
