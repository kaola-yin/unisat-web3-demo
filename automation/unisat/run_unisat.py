"""UniSat Demo 浏览器交互入口，推荐独立 Python 3.13 环境。"""

import argparse
import json
import math
import os
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path


PROJECT_DIR = Path(os.path.abspath(__file__)).parent
DEMO_URL = "https://demo.unisat.io/"
DOWNLOAD_URL = "https://unisat.io/download"
RUN_COMMAND = ".\\.venv-unisat313\\Scripts\\python.exe run_unisat.py"
UNISAT_EXTENSION_ID = "ppbibelpcjmhbdihakflkdcoccbgbkpo"
BROWSER_CONFIG_FILE = PROJECT_DIR / "config/unisat_browser.json"


class InteractionError(RuntimeError):
    pass


def absolute_path(value):
    # 不依赖 Windows 对文件句柄的额外权限，便于在受限环境中运行。
    return Path(os.path.abspath(os.path.expanduser(str(value))))


def load_browser_config():
    if not BROWSER_CONFIG_FILE.is_file():
        return {}
    try:
        config = json.loads(BROWSER_CONFIG_FILE.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        raise InteractionError("无法读取浏览器配置 {}：{}".format(BROWSER_CONFIG_FILE, exc)) from exc
    if not isinstance(config, dict):
        raise InteractionError("浏览器配置必须为 JSON 对象：{}".format(BROWSER_CONFIG_FILE))
    for field in ("chrome_path", "profile"):
        if field in config and (not isinstance(config[field], str) or not config[field].strip()):
            raise InteractionError("浏览器配置中的 {} 必须为非空路径。".format(field))
    return config


def find_chrome(explicit_path=None):
    if explicit_path is None:
        explicit_path = load_browser_config().get("chrome_path")
    if explicit_path:
        path = absolute_path(explicit_path)
        if not path.is_file():
            raise InteractionError("Chrome 路径不存在：{}".format(path))
        return str(path)
    candidates = []
    for variable in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA"):
        root = os.environ.get(variable)
        if root:
            candidates.append(Path(root) / "Google/Chrome/Application/chrome.exe")
    candidates.extend([
        Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
    ])
    for command in ("google-chrome", "google-chrome-stable"):
        executable = shutil.which(command)
        if executable:
            candidates.append(Path(executable))
    for candidate in candidates:
        if candidate.is_file():
            return str(absolute_path(candidate))
    raise InteractionError("未找到 Chrome。请安装 Chrome，或用 --chrome 指定 chrome.exe。")


def create_browser(args):
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise InteractionError(
            "缺少 Playwright，请先执行 setup_unisat.ps1，并使用 .venv-unisat313 内的 Python。"
        ) from exc
    chrome_path = find_chrome(args.chrome)
    profile = absolute_path(args.profile)
    profile.mkdir(parents=True, exist_ok=True)
    runtime = sync_playwright().start()
    try:
        context = runtime.chromium.launch_persistent_context(
            user_data_dir=str(profile),
            executable_path=chrome_path,
            headless=False,
            no_viewport=True,
            ignore_default_args=["--disable-extensions"],
            args=["--start-maximized", "--no-first-run", "--no-default-browser-check"],
            timeout=60000,
        )
    except Exception as exc:
        runtime.stop()
        raise InteractionError(
            "浏览器启动失败。请检查 Chrome 路径，并关闭使用同一专用配置目录的浏览器。"
            "\n原始错误：{}".format(exc)
        ) from exc
    context.set_default_timeout(min(args.timeout, 15) * 1000)
    context.set_default_navigation_timeout(min(args.timeout, 60) * 1000)
    page = context.pages[0] if context.pages else context.new_page()
    return runtime, context, page


def wallet_setup_url(args):
    extension_dir = absolute_path(args.profile) / "Default/Extensions" / UNISAT_EXTENSION_ID
    if extension_dir.is_dir() and any(extension_dir.glob("*/manifest.json")):
        return "chrome-extension://{}/index.html".format(UNISAT_EXTENSION_ID)
    return DOWNLOAD_URL


def wallet_call(page, method, timeout=15):
    # 只允许读取接口，避免把输入字符串直接拼进 JavaScript。
    allowed = {"getAccounts", "getPublicKey", "getChain", "getBalance", "getBalanceV2"}
    if method not in allowed:
        raise InteractionError("不支持的钱包读取方法：{}".format(method))
    reply = page.evaluate("""async ({method, timeoutMs}) => {
        const wallet = window.unisat;
        if (!wallet || typeof wallet[method] !== 'function') {
            return {ok: false, error: '钱包不支持 ' + method};
        }
        let timer;
        try {
            const value = await Promise.race([
                Promise.resolve().then(() => wallet[method]()),
                new Promise((_, reject) => {
                    timer = setTimeout(() => reject(new Error(method + ' 调用超时')), timeoutMs);
                })
            ]);
            return {ok: true, value};
        } catch (error) {
            return {ok: false, error: String(error.message || error), code: error.code};
        } finally {
            clearTimeout(timer);
        }
    }""", {"method": method, "timeoutMs": timeout * 1000})
    if not isinstance(reply, dict) or not reply.get("ok"):
        error = reply.get("error", "未知返回值") if isinstance(reply, dict) else "未知返回值"
        raise InteractionError("{} 调用失败：{}".format(method, error))
    return reply.get("value")


def validate_wallet_info(info, expected_chain=None):
    accounts = info.get("accounts")
    if not isinstance(accounts, list) or not accounts or any(
        not isinstance(address, str) or not address.strip() for address in accounts
    ):
        raise InteractionError("钱包没有返回有效地址，请检查是否已解锁并授权该网站。")
    if not isinstance(info.get("public_key"), str) or not info["public_key"].strip():
        raise InteractionError("钱包没有返回公钥。")
    chain = info.get("chain")
    if not isinstance(chain, dict) or not isinstance(chain.get("enum"), str) or not chain["enum"]:
        raise InteractionError("钱包没有返回有效网络信息。")
    if expected_chain and chain["enum"] != expected_chain:
        raise InteractionError(
            "网络不一致：期望 {}，实际 {}。请在钱包切换网络后重新运行。".format(
                expected_chain, chain["enum"]
            )
        )
    balance = info.get("balance")
    fields = ("available", "unavailable", "total") if info.get("balance_method") == "getBalanceV2" else (
        "confirmed", "unconfirmed", "total"
    )
    if not isinstance(balance, dict):
        raise InteractionError("余额返回值格式错误。")
    for field in fields:
        value = balance.get(field)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0 or value != int(value):
            raise InteractionError("余额 {} 应为非负整数，实际为 {!r}。".format(field, value))
    if balance[fields[0]] + balance[fields[1]] != balance["total"]:
        raise InteractionError("余额分项之和与 total 不一致，请检查钱包返回值。")


def run_interaction(page, args, result):
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

    wait_ms = args.timeout * 1000
    result["stage"] = "page_load"
    print("打开 {}".format(DEMO_URL), flush=True)
    page.goto(DEMO_URL, wait_until="domcontentloaded")
    try:
        page.get_by_role("button", name=re.compile(r"^(Connect Wallet|Connect|Disconnect)$")).first.wait_for(
            state="visible", timeout=wait_ms
        )
    except PlaywrightTimeoutError as exc:
        raise InteractionError("演示站未显示连接按钮。请检查网络或页面是否已更新。") from exc

    result["stage"] = "wallet_detection"
    try:
        page.wait_for_function("typeof window.unisat !== 'undefined'", timeout=min(wait_ms, 5000))
    except PlaywrightTimeoutError as exc:
        raise InteractionError(
            "该浏览器没有检测到 UniSat。先执行 {} --setup，"
            "在打开的专用浏览器里安装插件并配置钱包，再重新运行。".format(RUN_COMMAND)
        ) from exc

    result["stage"] = "wallet_connect"
    connect_button = page.get_by_role("button", name=re.compile(r"^(Connect Wallet|Connect)$")).first
    if connect_button.count():
        connect_button.click()
    print(
        "请在网站的钱包选择框中选择 UniSat，并在插件弹窗解锁、确认连接。"
        "脚本最多等待 {} 秒。".format(args.timeout), flush=True
    )

    try:
        page.get_by_role("button", name="Disconnect", exact=True).wait_for(state="visible", timeout=wait_ms)
    except PlaywrightTimeoutError as exc:
        raise InteractionError("连接超时。请确认已选择 UniSat、解锁钱包并同意连接。") from exc
    accounts = wallet_call(page, "getAccounts")

    result["stage"] = "wallet_read"
    use_v2 = page.evaluate("typeof window.unisat.getBalanceV2 === 'function'")
    balance_method = "getBalanceV2" if use_v2 else "getBalance"
    info = {
        "accounts": accounts,
        "public_key": wallet_call(page, "getPublicKey"),
        "chain": wallet_call(page, "getChain"),
        "balance_method": balance_method,
        "balance": wallet_call(page, balance_method),
    }
    result["stage"] = "result_validation"
    validate_wallet_info(info, args.expected_chain)
    try:
        page.wait_for_function(
            "address => document.body.innerText.includes(address)", arg=accounts[0], timeout=wait_ms
        )
    except PlaywrightTimeoutError as exc:
        raise InteractionError("钱包已返回地址，但演示站没有显示对应地址。") from exc
    final_accounts = wallet_call(page, "getAccounts")
    final_chain = wallet_call(page, "getChain")
    if final_accounts != accounts or final_chain.get("enum") != info["chain"]["enum"]:
        raise InteractionError("检查过程中钱包账户或网络发生变化，请重新运行。")
    result.update(info)
    result["page_address_verified"] = True
    result["stage"] = "complete"
    result["status"] = "passed"


def write_result(result):
    output_dir = PROJECT_DIR / "reports/unisat"
    output_dir.mkdir(parents=True, exist_ok=True)
    file_path = output_dir / ("result-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + ".json")
    file_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return file_path


def positive_timeout(value):
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("等待秒数必须为正整数") from exc
    if parsed <= 0:
        raise argparse.ArgumentTypeError("等待秒数必须为正整数")
    return parsed


def main(argv=None):
    parser = argparse.ArgumentParser(description="连接 UniSat Demo，检查钱包地址、网络和余额")
    try:
        browser_config = load_browser_config()
    except InteractionError as exc:
        parser.error(str(exc))
    preparation = parser.add_mutually_exclusive_group()
    preparation.add_argument("--setup", action="store_true", help="打开专用浏览器，配置钱包")
    preparation.add_argument("--install", action="store_true", help="打开 UniSat 官网安装入口，重新安装并配置钱包")
    parser.add_argument("--chrome", help="Chrome 可执行文件的路径")
    parser.add_argument("--profile", help="专用浏览器配置目录，默认使用保存的浏览器配置")
    parser.add_argument("--timeout", type=positive_timeout, default=180, help="等待连接的秒数，默认 180")
    parser.add_argument("--expected-chain", help="校验网络，例如 BITCOIN_TESTNET4；不自动切换网络")
    args = parser.parse_args(argv)
    profile = args.profile or browser_config.get("profile") or str(PROJECT_DIR / ".browser/unisat")
    profile_path = Path(profile).expanduser()
    args.profile = str(absolute_path(profile_path if profile_path.is_absolute() else PROJECT_DIR / profile_path))
    result = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "url": DEMO_URL,
        "status": "failed",
        "stage": "browser_start",
    }
    runtime = None
    context = None
    exit_code = 1
    try:
        chrome_path = find_chrome(args.chrome)
        args.chrome = chrome_path
        result["chrome_path"] = chrome_path
        print("使用 Chrome：{}".format(chrome_path), flush=True)
        runtime, context, page = create_browser(args)
        if args.setup or args.install:
            result["stage"] = "wallet_setup"
            setup_url = DOWNLOAD_URL if args.install else wallet_setup_url(args)
            page.goto(setup_url, wait_until="domcontentloaded")
            if setup_url == DOWNLOAD_URL:
                print("请在此浏览器中从 UniSat 官网安装插件，并在插件内配置钱包。", flush=True)
            else:
                print("已在标签页中打开 UniSat 钱包，请在此页面完成钱包配置。", flush=True)
            input("完成后回到此终端，按 Enter 保存浏览器配置并关闭窗口：")
            page.goto(DEMO_URL, wait_until="domcontentloaded")
            try:
                page.wait_for_function("typeof window.unisat !== 'undefined'", timeout=10000)
            except Exception as exc:
                raise InteractionError("未检测到 UniSat，安装尚未完成。请重新运行 --setup。") from exc
            print("插件已检测到，配置保存在 {}。接下来运行 {}。".format(args.profile, RUN_COMMAND), flush=True)
            return 0
        run_interaction(page, args, result)
        print("交互检查通过：地址 {}，网络 {}，余额 {} 聪。".format(
            result["accounts"][0], result["chain"]["enum"], result["balance"]["total"]
        ), flush=True)
        exit_code = 0
    except KeyboardInterrupt:
        result["error"] = "用户中断了运行。"
        print(result["error"], file=sys.stderr)
        exit_code = 130
    except Exception as exc:
        result["error"] = str(exc)
        print("运行失败 [{}]：{}".format(result["stage"], exc), file=sys.stderr)
    finally:
        if context is not None:
            try:
                context.close()
            except Exception as exc:
                print("关闭浏览器时遇到问题：{}".format(exc), file=sys.stderr)
        if runtime is not None:
            try:
                runtime.stop()
            except Exception as exc:
                print("停止浏览器控制时遇到问题：{}".format(exc), file=sys.stderr)
        if not (args.setup or args.install):
            print("结果文件：{}".format(write_result(result)), flush=True)
    return exit_code


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="backslashreplace")
    sys.exit(main())
