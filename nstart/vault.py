"""本機加密金鑰庫,跟 ngrok 無關:AES-256-GCM 加密儲存帳號/密碼/token。

主密碼只在解密當下由使用者輸入,不落地存放(不寫進 .env、不寫在程式碼裡)。
實際加密資料的是一把隨機產生的 DEK(data encryption key),DEK 本身分別用
「主密碼」與「救援碼」各包一份存起來,兩者都能解鎖 —— 救援碼是備援機制,
只在建立金鑰庫當下顯示一次。
"""

import base64
import json
import secrets
from pathlib import Path

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

VAULT_PATH = Path(__file__).resolve().parent.parent / "vault.enc.json"
KDF_ITERATIONS = 480_000
KEY_LEN = 32  # AES-256
RECOVERY_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"  # 去掉容易混淆的字元


class WrongPassword(Exception):
    """主密碼或救援碼不正確(或資料被竄改)。"""


def vault_exists():
    return VAULT_PATH.exists()


def _derive_key(secret_text, salt):
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(), length=KEY_LEN, salt=salt, iterations=KDF_ITERATIONS
    )
    return kdf.derive(secret_text.encode("utf-8"))


def _b64e(b):
    return base64.b64encode(b).decode("ascii")


def _b64d(s):
    return base64.b64decode(s.encode("ascii"))


def _load():
    return json.loads(VAULT_PATH.read_text(encoding="utf-8"))


def _save(data):
    VAULT_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def generate_recovery_code():
    groups = ["".join(secrets.choice(RECOVERY_ALPHABET) for _ in range(5)) for _ in range(6)]
    return "-".join(groups)


def _wrap_dek(dek, secret_text):
    salt = secrets.token_bytes(16)
    nonce = secrets.token_bytes(12)
    kek = _derive_key(secret_text, salt)
    wrapped = AESGCM(kek).encrypt(nonce, dek, None)
    return {"salt": _b64e(salt), "nonce": _b64e(nonce), "wrapped_dek": _b64e(wrapped)}


def _unwrap_dek(block, secret_text):
    salt = _b64d(block["salt"])
    nonce = _b64d(block["nonce"])
    kek = _derive_key(secret_text, salt)
    try:
        return AESGCM(kek).decrypt(nonce, _b64d(block["wrapped_dek"]), None)
    except Exception:
        raise WrongPassword("密碼或救援碼不正確")


def init_vault(master_password):
    """建立新的金鑰庫,回傳只會出現這一次的救援碼。"""
    dek = secrets.token_bytes(KEY_LEN)
    recovery_code = generate_recovery_code()
    data = {
        "version": 1,
        "master": _wrap_dek(dek, master_password),
        "recovery": _wrap_dek(dek, recovery_code),
        "entries": [],
    }
    _save(data)
    return recovery_code


def unlock_with_master(master_password):
    data = _load()
    return _unwrap_dek(data["master"], master_password)


def unlock_with_recovery(recovery_code):
    data = _load()
    return _unwrap_dek(data["recovery"], recovery_code)


def rewrap_master(dek, new_master_password):
    data = _load()
    data["master"] = _wrap_dek(dek, new_master_password)
    _save(data)


def list_entries():
    data = _load()
    return [{"id": e["id"], "name": e["name"]} for e in data["entries"]]


def add_entry(dek, name, account, secret_value):
    data = _load()
    nonce = secrets.token_bytes(12)
    plaintext = json.dumps(
        {"account": account, "secret": secret_value}, ensure_ascii=False
    ).encode("utf-8")
    ciphertext = AESGCM(dek).encrypt(nonce, plaintext, None)
    entry = {
        "id": secrets.token_hex(8),
        "name": name,
        "nonce": _b64e(nonce),
        "ciphertext": _b64e(ciphertext),
    }
    data["entries"].append(entry)
    _save(data)
    return entry


def decrypt_entry(dek, entry_id):
    data = _load()
    entry = next((e for e in data["entries"] if e["id"] == entry_id), None)
    if entry is None:
        raise KeyError("entry not found")
    nonce = _b64d(entry["nonce"])
    ciphertext = _b64d(entry["ciphertext"])
    try:
        plaintext = AESGCM(dek).decrypt(nonce, ciphertext, None)
    except Exception:
        raise WrongPassword("解密失敗,金鑰不正確")
    return json.loads(plaintext.decode("utf-8"))


def delete_entry(entry_id):
    data = _load()
    data["entries"] = [e for e in data["entries"] if e["id"] != entry_id]
    _save(data)
