# nstart

互動式 CLI:輸入 `nstart` 進入主選單,管理 ngrok 帳號底下的資源:

- **網域 Domain** — 選/建立保留網域,啟動 `ngrok http --domain=<域名> <port>`
- **TCP 位址 TCP Address** — 選/建立保留 TCP 位址,啟動 `ngrok tcp --remote-addr=<位址> <port>`
- **設定 Settings** — 更新 `.env` 裡的 `NGROK_API_KEY`,或直接執行 `ngrok config add-authtoken`

## 安裝

### 一鍵安裝(推薦)

```
curl -fsSL https://raw.githubusercontent.com/Dean7727/nstart/main/install.sh | bash
```

會自動:clone 專案到 `~/.nstart`、建立虛擬環境並安裝套件、把 `nstart` 指令加進 PATH(Windows 會同時寫入使用者層級的 PATH,PowerShell / cmd / Git Bash 都能用),並互動式引導你貼上 `NGROK_API_KEY`。裝完重開一個終端機,直接打 `nstart` 就能用。

之後要更新版本,重新執行同一行指令即可(腳本會偵測已安裝並直接 `git pull`)。

### 手動安裝

```
cd nstart-cli
pip install -e .
```

## 設定

1. 到 https://dashboard.ngrok.com/api 建立一組 API Key。若用一鍵安裝,腳本會直接問你要不要貼上;若用手動安裝,複製 `.env.example` 為 `.env`,填入 `NGROK_API_KEY=你的金鑰`。`.env` 已加入 `.gitignore`,不會被提交。
2. 確認本機已執行過 `ngrok config add-authtoken <你的 authtoken>`(這是 agent 用來連線的 token,和上面的 API Key 是兩件事)。也可以直接在 `nstart` 的「設定 Settings」裡設定,不用自己開終端機打指令。

## 使用

```
nstart
```

依畫面選擇要用的功能分類,再照選單操作即可。啟動 ngrok 後會顯示連線狀態,並可到 http://127.0.0.1:4040 看流量儀表板。
