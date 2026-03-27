"""
notify.py — 通知推送模块

当前支持飞书 Webhook，后续可扩展钉钉、企微等。
"""

import json
import os
import re
import time
from datetime import datetime

import requests


def send_to_feishu(text: str, title: str | None = None):
    """
    将文本分段发送至飞书 Webhook。

    Args:
        text:  报告正文
        title: 消息标题，默认用"BI 日报 + 日期"
    """
    webhook_url = os.environ.get("FEISHU_WEBHOOK", "")
    if not webhook_url:
        print("[飞书] 未配置 FEISHU_WEBHOOK，跳过发送")
        return

    today  = datetime.now().strftime("%Y年%-m月%-d日")
    header = f"📊 {title or 'BI 日报'}（{today}）\n{'─' * 30}\n"

    MAX_LEN = 3800
    chunks  = []
    current = header

    for line in text.split("\n"):
        candidate = current + line + "\n"
        if len(candidate) > MAX_LEN:
            chunks.append(current)
            current = ""
        current += line + "\n"
    if current.strip():
        chunks.append(current)

    print(f"\n[飞书] 共 {len(chunks)} 段，开始发送...")

    for i, chunk in enumerate(chunks):
        suffix = f" ({i + 1}/{len(chunks)})" if len(chunks) > 1 else ""
        resp   = requests.post(
            webhook_url,
            headers={"Content-Type": "application/json"},
            json={"msg_type": "text", "content": {"text": chunk + suffix}},
            timeout=30,
        )
        result = resp.json()
        if result.get("code", -1) != 0 and result.get("StatusCode", -1) != 0:
            print(f"[飞书] 第{i + 1}段发送失败:", json.dumps(result, ensure_ascii=False))
        else:
            print(f"[飞书] 第{i + 1}段发送成功")
        if i < len(chunks) - 1:
            time.sleep(0.5)
