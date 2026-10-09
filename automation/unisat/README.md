# UniSat Demo 钱包连接检查（Python Playwright）

这个目录提供独立于 React 前端的半自动检查脚本，默认访问 <https://demo.unisat.io/>。

脚本负责打开 Chrome、检查 UniSat 插件、点击连接按钮、读取地址/公钥/网络/余额、校验页面地址并生成 JSON 报告。安装插件、配置测试钱包、解锁和批准连接需要操作者在浏览器中完成。这里验证连接和信息读取，签名、转账需要单独编写用例。

## 1. 准备 Python 环境

已验证的原始运行环境为 Python 3.13.16、Playwright 1.63.0、Chrome 138 和 UniSat 1.7.22。

在本目录打开 PowerShell。已安装 Python 3.13 时可执行：

```powershell
py -3.13 -m venv .venv-unisat313
.\.venv-unisat313\Scripts\python.exe -m pip install -r requirements-unisat.txt
```

也可使用提供的 Windows 准备脚本，它会从 CPython 官方 NuGet 包下载 Python 3.13.16、创建本目录的虚拟环境并安装依赖：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\setup_unisat.ps1
```

PyCharm 的项目解释器应选择准备好的 `.venv-unisat313\Scripts\python.exe`。虚拟环境在每台电脑上分别创建。

## 2. 配置 Chrome

脚本会查找常见的 Chrome 安装位置。Chrome 安装在其他位置时，复制示例配置后，把 `chrome_path` 改为本机的实际路径：

```powershell
Copy-Item .\config\unisat_browser.example.json .\config\unisat_browser.json
```

`profile` 是测试专用的 Chrome 配置目录。示例值 `.browser/unisat` 相对于本目录。脚本也支持通过 `--chrome` 和 `--profile` 临时指定路径。

每台电脑使用自己的测试浏览器目录。同一个配置目录不能同时启动两个 Chrome 进程。

## 3. 首次安装和配置钱包

```powershell
.\.venv-unisat313\Scripts\python.exe run_unisat.py --setup
```

在脚本打开的专用 Chrome 窗口安装 UniSat 并配置测试钱包，完成后回到终端按 Enter。脚本会在 Demo 检测 `window.unisat`，成功后结束准备。

如果需要重新安装插件，使用 `--install`。普通 Chrome 窗口中的插件和钱包不会自动出现在新的测试浏览器目录中。

## 4. 执行钱包连接检查

```powershell
.\.venv-unisat313\Scripts\python.exe run_unisat.py --timeout 300
```

在网站的钱包选择框中选择 UniSat，在插件中解锁并批准连接。再次运行时，已授权的连接可能直接恢复。

可以要求指定网络，例如：

```powershell
.\.venv-unisat313\Scripts\python.exe run_unisat.py --expected-chain BITCOIN_TESTNET4 --timeout 300
```

脚本校验网络，网络切换由操作者在钱包中完成。

成功条件包括：

- Demo 显示已连接状态。
- 钱包返回非空地址、公钥和有效网络。
- 余额各字段为非负整数，分项之和等于总额；余额为零可以通过。
- Demo 显示的地址与钱包返回的地址一致。
- 检查过程中账户和网络保持一致。

成功返回退出码 `0`，失败返回 `1`，操作者中断返回 `130`。普通运行会在 `reports/unisat/result-*.json` 保存本次结果；`status: passed`、`stage: complete` 和 `page_address_verified: true` 表示这些检查全部通过。报告时间包含时区，文件名中的 `Z` 表示 UTC。

## 5. 本地检查

```powershell
.\.venv-unisat313\Scripts\python.exe -m unittest discover -s unisat_tests -v
```

默认执行数据校验和异常处理检查，不需要钱包或浏览器。浏览器检查默认跳过，可显式启用：

```powershell
$env:UNISAT_BROWSER_TEST = '1'
.\.venv-unisat313\Scripts\python.exe -m unittest discover -s unisat_tests -v
```

这些浏览器用例使用模拟钱包的本地 HTML，检查浏览器操作和 JavaScript 调用。另设 `UNISAT_LIVE_PAGE_TEST=1` 可额外检查真实 Demo 的连接按钮，需要联网。真实钱包连接仍需执行第 4 步。

## Git 中保留哪些文件

提交脚本、依赖清单、准备脚本、测试、说明和示例配置。`.gitignore` 排除了浏览器钱包目录、虚拟环境、缓存、实际配置和运行报告。配置示例供每位操作者填写自己的路径；运行报告包含钱包地址等信息，保留在本机。

当前页面地址和按钮定位针对 UniSat Demo。用于其他项目时，需要调整该网站的地址、连接入口和校验规则。

参考：[UniSat 钱包接口](https://docs.unisat.io/developer-support/open-api-documentation/unisat-wallet)、[Playwright 持久化浏览器](https://playwright.dev/python/docs/api/class-browsertype#browser-type-launch-persistent-context)。
