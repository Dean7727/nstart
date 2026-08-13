"""nstart 指令進入點:方向鍵選單管理 ngrok 網域、TCP 位址。"""

import os
import subprocess
import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

import questionary
from prompt_toolkit.completion import Completer, Completion
from questionary import Style
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from . import vault as vaultmod
from .ngrok_api import (
    create_reserved_addr,
    create_reserved_domain,
    list_reserved_addrs,
    list_reserved_domains,
)

console = Console()

STYLE = Style(
    [
        ("qmark", "fg:#00d7ff bold"),
        ("question", "bold"),
        ("pointer", "fg:#00d7ff bold"),
        ("highlighted", "fg:#00d7ff bold"),
        ("selected", "fg:#00d7ff"),
        ("answer", "fg:#00d7ff bold"),
        ("instruction", "fg:#5f5f5f"),
    ]
)

CREATE = "__create__"
CANCEL = "__cancel__"
INSTRUCTION = "(↑↓ 移動 · 數字鍵快速跳選 · Enter 確認)"

ENV_PATH = Path(__file__).resolve().parent.parent / ".env"

# ngrok 官方提供的網域後綴(對照 ngrok dashboard 建立網域時的實際選項)。
DOMAIN_SUFFIXES = [
    ".ngrok.app",
    ".ngrok.dev",
    ".ngrok.pizza",
    ".ngrok.pro",
    ".ngrok-free.app",
    ".ngrok-free.dev",
    ".ngrok.io",
]


class DomainSuffixCompleter(Completer):
    """輸入前綴時即時提示 ngrok 各種官方後綴組合,行為跟 ngrok 官網建立網域時一樣。

    全部後綴都會列出來;已經是你這個帳號保留的整行反灰標「Owned」,
    其餘用黑色文字(配下拉選單淺灰底較清楚)、後面加一個綠色打勾,
    標「available」。這只代表你自己帳號的狀態 —— 其他人是否已註冊
    某個組合,ngrok 沒有提供事先查詢的 API,只能在實際建立時才知道。
    """

    def __init__(self, existing_domains):
        self.existing_domains = existing_domains

    def get_completions(self, document, complete_event):
        raw = document.text
        text = raw.rstrip(".")
        if not text or any(text.endswith(suf) for suf in DOMAIN_SUFFIXES):
            return
        for suf in DOMAIN_SUFFIXES:
            candidate = f"{text}{suf}"
            taken = candidate in self.existing_domains
            if taken:
                display = candidate
                style = "fg:#999999"
                meta = "Owned"
            else:
                display = [("fg:#000000", candidate), ("fg:#00a050", " ✓")]
                style = "fg:#000000"
                meta = "available"
            yield Completion(
                candidate,
                start_position=-len(raw),
                display=display,
                display_meta=meta,
                style=style,
            )


def pick_or_create(prompt_text, items, label_fn, create_label="+ 建立新的"):
    """通用選單:從既有項目挑一個,或建立新的,或取消。回傳 (action, item)。"""
    choices = [questionary.Choice(title=label_fn(i), value=i) for i in items]
    if choices:
        choices.append(questionary.Separator())
    choices.append(questionary.Choice(title=create_label, value=CREATE))
    choices.append(questionary.Choice(title="✕ 取消", value=CANCEL))

    answer = questionary.select(
        prompt_text,
        choices=choices,
        style=STYLE,
        use_shortcuts=True,
        instruction=INSTRUCTION,
    ).ask()

    if answer is None or answer == CANCEL:
        return "cancel", None
    if answer == CREATE:
        return "create", None
    return "use", answer


def ask_domain_name(existing_domains):
    console.print(
        "[dim]提示裡「Owned」是你自己帳號已保留的網域(反灰);"
        "「available」只代表你還沒用過,其他人是否已註冊要送出後才知道。[/dim]"
    )
    domain = questionary.text(
        "請輸入網域名稱(最多 30 個字元;邊打邊會提示 ngrok 官方後綴組合,如 xxx.ngrok.app;"
        "也可以直接輸入自己已綁定 ngrok 的完整網域):",
        completer=DomainSuffixCompleter(existing_domains),
        complete_while_typing=True,
        validate=_validate_domain_name,
        style=STYLE,
    ).ask()
    return domain.strip() if domain else None


def _validate_domain_name(v):
    if not v.strip():
        return "請輸入內容"
    if len(v.strip()) > 30:
        return "網域名稱不能超過 30 個字元"
    return True


def ask_port():
    return questionary.text(
        "要轉發到本機哪個 port?",
        validate=lambda v: v.isdigit() or "請輸入數字 port",
        style=STYLE,
    ).ask()


def run_ngrok_http(domain, port):
    console.print(
        Panel(
            f"[bold]https://{domain}[/bold] → [bold]localhost:{port}[/bold]\n"
            f"[dim]流量儀表板: http://127.0.0.1:4040[/dim]",
            title="啟動 ngrok (HTTP)",
            border_style="cyan",
        )
    )
    _run_ngrok(["ngrok", "http", f"--domain={domain}", str(port)])


def run_ngrok_tcp(addr, port):
    console.print(
        Panel(
            f"[bold]tcp://{addr}[/bold] → [bold]localhost:{port}[/bold]\n"
            f"[dim]流量儀表板: http://127.0.0.1:4040[/dim]",
            title="啟動 ngrok (TCP)",
            border_style="cyan",
        )
    )
    _run_ngrok(["ngrok", "tcp", f"--remote-addr={addr}", str(port)])


def _run_ngrok(cmd):
    try:
        subprocess.run(cmd, check=False)
    except FileNotFoundError:
        console.print("[bold red]錯誤:[/bold red] 找不到 ngrok,請確認已安裝並加入 PATH。")


# ---- 網域 Domain ----


def domain_flow():
    try:
        with console.status("[cyan]正在讀取保留網域...[/cyan]"):
            domains = list_reserved_domains()
    except Exception as e:
        console.print(f"[bold red]取得網域清單失敗:[/bold red] {e}")
        return

    action, selected = pick_or_create(
        "請選擇要啟用的網域:", domains, lambda d: d["domain"], "+ 建立新網域"
    )

    if action == "cancel":
        console.print("[dim]已取消。[/dim]")
        return

    if action == "create":
        existing_domains = {d["domain"] for d in domains}
        name = ask_domain_name(existing_domains)
        if not name:
            console.print("[yellow]未輸入網域名稱,已取消。[/yellow]")
            return
        try:
            with console.status("[cyan]正在建立網域...[/cyan]"):
                selected = create_reserved_domain(name)
        except Exception as e:
            console.print(f"[bold red]建立網域失敗:[/bold red] {e}")
            return
        console.print(f"[green]已建立網域:[/green] {selected['domain']}")

    port = ask_port()
    if port is None:
        console.print("[dim]已取消。[/dim]")
        return
    run_ngrok_http(selected["domain"], port)


# ---- TCP 位址 TCP Address ----


def tcp_flow():
    try:
        with console.status("[cyan]正在讀取保留 TCP 位址...[/cyan]"):
            addrs = list_reserved_addrs()
    except Exception as e:
        console.print(f"[bold red]取得 TCP 位址清單失敗:[/bold red] {e}")
        return

    def label(a):
        desc = f"  ({a['description']})" if a.get("description") else ""
        return f"{a['addr']}{desc}"

    action, selected = pick_or_create(
        "請選擇要啟用的 TCP 位址:", addrs, label, "+ 建立新 TCP 位址"
    )

    if action == "cancel":
        console.print("[dim]已取消。[/dim]")
        return

    if action == "create":
        console.print("[dim]TCP 位址(host:port)是 ngrok 自動配發的,不能自訂。[/dim]")
        description = questionary.text("描述(可留空,方便之後辨識用途):", style=STYLE).ask()
        try:
            with console.status("[cyan]正在建立 TCP 位址...[/cyan]"):
                selected = create_reserved_addr(
                    description=description.strip() if description else None
                )
        except Exception as e:
            console.print(f"[bold red]建立 TCP 位址失敗:[/bold red] {e}")
            return
        console.print(f"[green]已建立 TCP 位址:[/green] {selected['addr']}")

    port = ask_port()
    if port is None:
        console.print("[dim]已取消。[/dim]")
        return
    run_ngrok_tcp(selected["addr"], port)


# ---- 設定 Settings ----


def _read_env_lines():
    if not ENV_PATH.exists():
        return []
    return ENV_PATH.read_text(encoding="utf-8").splitlines()


def _set_env_value(key, value):
    lines = _read_env_lines()
    found = False
    for i, line in enumerate(lines):
        if line.strip().startswith(f"{key}="):
            lines[i] = f"{key}={value}"
            found = True
            break
    if not found:
        lines.append(f"{key}={value}")
    ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def settings_flow():
    current = os.environ.get("NGROK_API_KEY", "")
    masked = f"{current[:6]}...{current[-4:]}" if len(current) > 12 else "(未設定)"
    console.print(f"目前 NGROK_API_KEY: [cyan]{masked}[/cyan]")
    console.print(f"[dim].env 位置: {ENV_PATH}[/dim]")

    answer = questionary.select(
        "設定 Settings:",
        choices=[
            questionary.Choice(title="更新 NGROK_API_KEY(管理 API 用)", value="update_api_key"),
            questionary.Choice(
                title="設定 ngrok Authtoken(ngrok config add-authtoken,agent 連線用)",
                value="update_authtoken",
            ),
            questionary.Choice(title="✕ 返回", value=CANCEL),
        ],
        style=STYLE,
        use_shortcuts=True,
        instruction=INSTRUCTION,
    ).ask()

    if answer is None or answer == CANCEL:
        return

    if answer == "update_api_key":
        new_key = questionary.text("請輸入新的 NGROK_API_KEY:", style=STYLE).ask()
        if not new_key:
            console.print("[yellow]未輸入,已取消。[/yellow]")
            return
        _set_env_value("NGROK_API_KEY", new_key.strip())
        os.environ["NGROK_API_KEY"] = new_key.strip()
        console.print("[green]已更新 .env,並套用到本次執行。[/green]")
        return

    token = questionary.text(
        "請輸入 ngrok Authtoken(到 https://dashboard.ngrok.com/get-started/your-authtoken 複製):",
        style=STYLE,
    ).ask()
    if not token:
        console.print("[yellow]未輸入,已取消。[/yellow]")
        return
    cmd = ["ngrok", "config", "add-authtoken", token.strip()]
    try:
        result = subprocess.run(cmd, check=False, capture_output=True, text=True)
    except FileNotFoundError:
        console.print("[bold red]錯誤:[/bold red] 找不到 ngrok,請確認已安裝並加入 PATH。")
        return
    if result.returncode == 0:
        console.print("[green]已設定 ngrok authtoken。[/green]")
    else:
        console.print(
            f"[bold red]設定 authtoken 失敗:[/bold red] {result.stderr.strip() or result.stdout.strip()}"
        )


# ---- 金鑰庫 Vault(AES-256,跟 ngrok 無關的本機加密儲存)----


def _vault_setup():
    console.print("[yellow]還沒有金鑰庫,先設定一組主密碼。[/yellow]")
    pw1 = questionary.password("設定主密碼:", style=STYLE).ask()
    if not pw1:
        console.print("[dim]已取消。[/dim]")
        return False
    pw2 = questionary.password("再輸入一次確認:", style=STYLE).ask()
    if pw1 != pw2:
        console.print("[bold red]兩次輸入不一致,已取消。[/bold red]")
        return False

    recovery_code = vaultmod.init_vault(pw1)
    console.print(
        Panel(
            f"[bold yellow]{recovery_code}[/bold yellow]\n\n"
            "這組救援碼只會顯示這一次,忘記主密碼時可以靠它重設。\n"
            "請現在就抄下來存到別的地方(不要存在這台電腦上)。",
            title="救援碼(僅顯示一次)",
            border_style="yellow",
        )
    )
    questionary.text("抄好了嗎?按 Enter 繼續。", style=STYLE).ask()
    return True


def _vault_unlock(prompt_text="輸入主密碼解鎖:"):
    pw = questionary.password(prompt_text, style=STYLE).ask()
    if not pw:
        console.print("[dim]已取消。[/dim]")
        return None
    try:
        with console.status("[cyan]正在解密...[/cyan]"):
            return vaultmod.unlock_with_master(pw)
    except vaultmod.WrongPassword:
        console.print("[bold red]主密碼錯誤。[/bold red]")
        return None


def _vault_add_entry():
    dek = _vault_unlock()
    if dek is None:
        return

    name = questionary.text(
        "項目名稱(例如 github、gitlab、openai):",
        validate=lambda v: bool(v.strip()) or "請輸入內容",
        style=STYLE,
    ).ask()
    if not name:
        console.print("[dim]已取消。[/dim]")
        return
    account = questionary.text("帳號(可留空):", style=STYLE).ask()
    secret_value = questionary.text(
        "密碼 / Token:", validate=lambda v: bool(v.strip()) or "請輸入內容", style=STYLE
    ).ask()
    if not secret_value:
        console.print("[dim]已取消。[/dim]")
        return

    vaultmod.add_entry(dek, name.strip(), (account or "").strip(), secret_value.strip())
    console.print(f"[green]已新增:[/green] {name.strip()}")


def _copy_to_clipboard(text):
    subprocess.run(["clip"], input=text.encode("utf-16-le"), check=True)


def _vault_view_entry(entry_id, entry_name):
    dek = _vault_unlock(f"輸入主密碼查看「{entry_name}」:")
    if dek is None:
        return
    try:
        with console.status("[cyan]正在解密...[/cyan]"):
            data = vaultmod.decrypt_entry(dek, entry_id)
    except vaultmod.WrongPassword as e:
        console.print(f"[bold red]{e}[/bold red]")
        return

    try:
        _copy_to_clipboard(data["secret"])
    except Exception as e:
        console.print(f"[bold red]複製到剪貼簿失敗:[/bold red] {e}")
        return

    account = data.get("account") or "(無)"
    console.print(
        Panel(
            f"帳號: [bold]{account}[/bold]\n"
            "密碼 / Token 已複製到剪貼簿,直接在需要的地方貼上即可。",
            title=entry_name,
            border_style="green",
        )
    )


def _vault_delete_entry(entries):
    if not entries:
        console.print("[yellow]目前沒有項目。[/yellow]")
        return
    choices = [questionary.Choice(title=e["name"], value=e["id"]) for e in entries]
    choices.append(questionary.Choice(title="✕ 取消", value=CANCEL))
    answer = questionary.select(
        "要刪除哪一個?",
        choices=choices,
        style=STYLE,
        use_shortcuts=True,
        instruction=INSTRUCTION,
    ).ask()
    if answer is None or answer == CANCEL:
        return
    confirm = questionary.confirm(
        "確定要刪除嗎?這個動作無法復原。", default=False, style=STYLE
    ).ask()
    if not confirm:
        console.print("[dim]已取消。[/dim]")
        return
    vaultmod.delete_entry(answer)
    console.print("[green]已刪除。[/green]")


def _vault_reset_master():
    code = questionary.text("輸入救援碼:", style=STYLE).ask()
    if not code:
        console.print("[dim]已取消。[/dim]")
        return
    try:
        with console.status("[cyan]正在驗證救援碼...[/cyan]"):
            dek = vaultmod.unlock_with_recovery(code.strip())
    except vaultmod.WrongPassword as e:
        console.print(f"[bold red]{e}[/bold red]")
        return
    new_pw = questionary.password("設定新的主密碼:", style=STYLE).ask()
    if not new_pw:
        console.print("[dim]已取消。[/dim]")
        return
    vaultmod.rewrap_master(dek, new_pw)
    console.print("[green]已重設主密碼。[/green]")


DELETE = "__delete__"
RESET_MASTER = "__reset_master__"


def vault_flow():
    if not vaultmod.vault_exists():
        if not _vault_setup():
            return

    while True:
        entries = vaultmod.list_entries()
        choices = [questionary.Choice(title=e["name"], value=e["id"]) for e in entries]
        if choices:
            choices.append(questionary.Separator())
        choices.append(questionary.Choice(title="+ 新增項目", value=CREATE))
        if entries:
            choices.append(questionary.Choice(title="刪除項目", value=DELETE))
        choices.append(questionary.Choice(title="忘記主密碼(用救援碼重設)", value=RESET_MASTER))
        choices.append(questionary.Choice(title="✕ 返回", value=CANCEL))

        answer = questionary.select(
            "金鑰庫(AES-256,跟 ngrok 無關):",
            choices=choices,
            style=STYLE,
            use_shortcuts=True,
            instruction=INSTRUCTION,
        ).ask()

        if answer is None or answer == CANCEL:
            return
        if answer == CREATE:
            _vault_add_entry()
            continue
        if answer == DELETE:
            _vault_delete_entry(entries)
            continue
        if answer == RESET_MASTER:
            _vault_reset_master()
            continue

        entry_name = next((e["name"] for e in entries if e["id"] == answer), answer)
        _vault_view_entry(answer, entry_name)


# ---- 主選單 ----


def _package_version():
    try:
        return version("nstart")
    except PackageNotFoundError:
        return "0.0.0"


def _cwd_display():
    home = Path.home()
    cwd = Path.cwd()
    try:
        rel = cwd.relative_to(home)
        return "~" if str(rel) == "." else f"~\\{rel}"
    except ValueError:
        return str(cwd)


def print_banner():
    body = Text()
    body.append("NGROK", style="bold #3fd0e0")
    body.append(f"  nstart v{_package_version()}\n", style="dim")
    body.append(_cwd_display(), style="dim")

    console.print()
    console.print(Panel(body, border_style="#3fd0e0", expand=False))
    console.print()


MENU_DOMAIN = "domain"
MENU_TCP = "tcp"
MENU_VAULT = "vault"
MENU_SETTINGS = "settings"
MENU_EXIT = "exit"


def main_menu():
    return questionary.select(
        "請選擇功能:",
        choices=[
            questionary.Choice(title="網域 Domain", value=MENU_DOMAIN),
            questionary.Choice(title="TCP 位址 TCP Address", value=MENU_TCP),
            questionary.Choice(title="金鑰庫 Vault", value=MENU_VAULT),
            questionary.Choice(title="設定 Settings", value=MENU_SETTINGS),
            questionary.Separator(),
            questionary.Choice(title="✕ 離開 Exit", value=MENU_EXIT),
        ],
        style=STYLE,
        use_shortcuts=True,
        instruction=INSTRUCTION,
    ).ask()


def _run():
    print_banner()

    while True:
        choice = main_menu()

        if choice is None or choice == MENU_EXIT:
            console.print("[dim]再見。[/dim]")
            return

        if choice == MENU_DOMAIN:
            domain_flow()
        elif choice == MENU_TCP:
            tcp_flow()
        elif choice == MENU_VAULT:
            vault_flow()
        elif choice == MENU_SETTINGS:
            settings_flow()

        console.print()


def main():
    try:
        _run()
    except KeyboardInterrupt:
        console.print("\n[dim]已取消。[/dim]")
        sys.exit(130)


if __name__ == "__main__":
    main()
