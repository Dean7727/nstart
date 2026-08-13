#!/usr/bin/env bash
# nstart 一鍵安裝腳本
#   curl -fsSL https://raw.githubusercontent.com/Dean7727/nstart/main/install.sh | bash
set -euo pipefail

REPO_URL="https://github.com/Dean7727/nstart.git"
INSTALL_DIR="$HOME/.nstart"

echo "==> 安裝 nstart..."

command -v git >/dev/null 2>&1 || { echo "錯誤:需要先安裝 git"; exit 1; }

PYTHON=""
for candidate in python3 python py; do
  if command -v "$candidate" >/dev/null 2>&1; then
    PYTHON="$candidate"
    break
  fi
done
[ -n "$PYTHON" ] || { echo "錯誤:需要先安裝 Python 3.9+"; exit 1; }

if [ -d "$INSTALL_DIR/.git" ]; then
  echo "==> 偵測到已安裝,更新中..."
  git -C "$INSTALL_DIR" pull --ff-only
else
  git clone --depth 1 "$REPO_URL" "$INSTALL_DIR"
fi

echo "==> 建立虛擬環境並安裝套件..."
"$PYTHON" -m venv "$INSTALL_DIR/.venv"

if [ -f "$INSTALL_DIR/.venv/Scripts/python.exe" ]; then
  VENV_BIN="$INSTALL_DIR/.venv/Scripts"
else
  VENV_BIN="$INSTALL_DIR/.venv/bin"
fi

"$VENV_BIN/python" -m pip install --upgrade pip -q
"$VENV_BIN/pip" install -e "$INSTALL_DIR" -q

# ---- 加入 PATH(讓 nstart 指令在任何終端機都能直接打)----
add_path_line() {
  local rc="$1"
  [ -f "$rc" ] || touch "$rc"
  grep -qF "$VENV_BIN" "$rc" 2>/dev/null || {
    {
      echo ""
      echo "# nstart"
      echo "export PATH=\"$VENV_BIN:\$PATH\""
    } >>"$rc"
  }
}
for rc in "$HOME/.bashrc" "$HOME/.zshrc"; do
  [ -f "$rc" ] && add_path_line "$rc"
done
add_path_line "$HOME/.profile"
export PATH="$VENV_BIN:$PATH"

# Windows:額外把路徑寫進使用者層級的 PATH,PowerShell / cmd 重開後也認得 nstart
if command -v cygpath >/dev/null 2>&1 && command -v powershell.exe >/dev/null 2>&1; then
  WIN_VENV_BIN="$(cygpath -w "$VENV_BIN")"
  CURRENT_WIN_PATH="$(powershell.exe -NoProfile -Command "[Environment]::GetEnvironmentVariable('Path','User')" 2>/dev/null | tr -d '\r')"
  if [[ "$CURRENT_WIN_PATH" != *"$WIN_VENV_BIN"* ]]; then
    powershell.exe -NoProfile -Command \
      "[Environment]::SetEnvironmentVariable('Path', [Environment]::GetEnvironmentVariable('Path','User') + ';$WIN_VENV_BIN', 'User')" \
      >/dev/null 2>&1 &&
      echo "==> 已將 $WIN_VENV_BIN 加入 Windows PATH(重開終端機後,PowerShell / cmd 也能直接打 nstart)"
  fi
fi

# ---- 設定環境變數 NGROK_API_KEY ----
ENV_FILE="$INSTALL_DIR/.env"
if [ ! -s "$ENV_FILE" ] || ! grep -q "^NGROK_API_KEY=..*" "$ENV_FILE" 2>/dev/null; then
  echo ""
  echo "==> 設定 NGROK_API_KEY(到 https://dashboard.ngrok.com/api 建立一組)"
  if [ -r /dev/tty ]; then
    read -rp "貼上 NGROK_API_KEY(可留空,之後用 nstart 的 Settings 補設定): " API_KEY </dev/tty || API_KEY=""
  else
    API_KEY=""
  fi
  echo "NGROK_API_KEY=${API_KEY}" >"$ENV_FILE"
fi

echo ""
echo "==> 安裝完成!請重新開一個終端機,然後輸入: nstart"
