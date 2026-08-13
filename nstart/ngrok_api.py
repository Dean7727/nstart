"""呼叫 ngrok 官方管理 API (api.ngrok.com):網域、TCP 位址、SSH 公鑰、Vaults & Secrets。"""

import os
import sys

import requests
from dotenv import load_dotenv

load_dotenv()

API_BASE = "https://api.ngrok.com"


def _headers():
    api_key = os.environ.get("NGROK_API_KEY")
    if not api_key:
        print("錯誤: 找不到環境變數 NGROK_API_KEY。")
        print("請先到 https://dashboard.ngrok.com/api 建立 API Key,")
        print("再用系統環境變數設定 NGROK_API_KEY 後重新開啟終端機。")
        sys.exit(1)
    return {
        "Authorization": f"Bearer {api_key}",
        "Ngrok-Version": "2",
    }


def _get_json(url):
    resp = requests.get(url, headers=_headers(), timeout=10)
    resp.raise_for_status()
    return resp.json()


def _list_paginated(path, list_key):
    items = []
    url = f"{API_BASE}{path}"
    while url:
        data = _get_json(url)
        items.extend(data.get(list_key, []))
        next_uri = data.get("next_page_uri")
        url = f"{API_BASE}{next_uri}" if next_uri else None
    return items


def _post(path, payload, conflict_hint=None):
    resp = requests.post(f"{API_BASE}{path}", headers=_headers(), json=payload, timeout=10)
    if not resp.ok:
        try:
            msg = resp.json().get("msg", resp.text)
        except ValueError:
            msg = resp.text
        if conflict_hint and any(
            k in msg.lower() for k in ("already", "exist", "reserved", "taken")
        ):
            raise RuntimeError(f"{conflict_hint} 原始訊息: {msg}")
        raise RuntimeError(f"建立失敗 ({resp.status_code}): {msg}")
    return resp.json()


# ---- 保留網域 (Reserved Domains) ----


def list_reserved_domains():
    return _list_paginated("/reserved_domains", "reserved_domains")


def create_reserved_domain(domain, region=None):
    payload = {"domain": domain}
    if region:
        payload["region"] = region
    return _post(
        "/reserved_domains",
        payload,
        conflict_hint=f"「{domain}」已經被使用(可能是你自己或別人已註冊),請換一個名字。",
    )


# ---- 保留 TCP 位址 (Reserved Addresses) ----


def list_reserved_addrs():
    return _list_paginated("/reserved_addrs", "reserved_addrs")


def create_reserved_addr(description=None, region=None):
    payload = {}
    if description:
        payload["description"] = description
    if region:
        payload["region"] = region
    return _post("/reserved_addrs", payload)


# ---- SSH 公鑰 (SSH Credentials) ----


def list_ssh_credentials():
    return _list_paginated("/ssh_credentials", "ssh_credentials")


def create_ssh_credential(public_key, description=None):
    payload = {"public_key": public_key}
    if description:
        payload["description"] = description
    return _post(
        "/ssh_credentials",
        payload,
        conflict_hint="這組公鑰可能已經被加入過。",
    )


# ---- 金庫與密鑰 (Vaults & Secrets) ----


def list_vaults():
    return _list_paginated("/vaults", "vaults")


def create_vault(name, description=None):
    payload = {"name": name}
    if description:
        payload["description"] = description
    return _post(
        "/vaults", payload, conflict_hint=f"金庫名稱「{name}」可能已經被使用。"
    )


def list_secrets(vault_id=None):
    items = _list_paginated("/vault_secrets", "secrets")
    if vault_id:
        items = [s for s in items if s.get("vault_id") == vault_id]
    return items


def create_secret(name, value, vault_id):
    payload = {"name": name, "value": value, "vault_id": vault_id}
    return _post(
        "/vault_secrets",
        payload,
        conflict_hint=f"密鑰名稱「{name}」在這個金庫裡可能已經被使用。",
    )
