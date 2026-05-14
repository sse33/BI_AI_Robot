FROM python:3.11-slim

# 安装 Node.js（guancli 依赖）
RUN apt-get update && apt-get install -y --no-install-recommends \
    nodejs npm \
    && npm install -g @guandata/guancli \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 先装 Python 依赖（利用 Docker 层缓存）
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制应用代码
COPY . .

RUN chmod +x entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["./entrypoint.sh"]
