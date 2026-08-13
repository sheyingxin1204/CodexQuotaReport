# Codex 额度报告（跨平台版）

这个项目会把电脑里所有 Codex 账号找出来，读取每个账号的额度事件，生成可视化仪表盘，并支持导出 CSV / XLSX / JSON。新版基于 Python 标准库实现，不再依赖 Excel COM，Windows / macOS / Linux 都可以运行。

## 快速开始

需要 Python 3.10 或更高版本。

```powershell
python run.py
```

默认直接打开原生桌面客户端窗口。也可以显式指定：

```powershell
python run.py --desktop
```

使用纯命令行模式：

```powershell
python run.py --cli --refresh
```

命令行模式会打印汇总表，并把报告导出到配置的输出目录（默认桌面）。

常用参数：

```text
--cli          控制台报告 + 文件导出
--desktop      打开原生桌面客户端窗口
--refresh      刷新额度后再读取
--no-refresh   只读取历史会话数据
--output-dir   修改报告输出目录
--format       导出格式，默认 csv,xlsx,json
```

没有 `--cli` 时始终进入桌面客户端。后端本地 HTTP 服务仅作为窗口内部实现，不再提供浏览器访问入口。

## 为什么是通用的

原来的 PowerShell 脚本依赖你的个人 Profile 快捷方式、Windows PowerShell 和本机 Excel。新版改为以下通用策略：

1. 自动发现 Codex 账号目录：环境变量 `CODEX_HOME`、默认 `~/.codex`、主目录下所有 `.codex*` 目录、常见 shell Profile 里的快捷方式，以及你在设置里手动添加的目录。
2. 直接读取 `auth.json` 的 JWT，提取邮箱和套餐；读取 `sessions/**/*.jsonl` 里最新的 `token_count` 事件，解析周/主额度和 5 小时额度。
3. 刷新额度时调用 `codex exec --skip-git-repo-check --ignore-user-config --json /status`，在干净的临时工作目录中运行，避免本机项目配置干扰；找不到 codex CLI 时会退化为读取历史数据。
4. XLSX 导出由 Python 标准库直接生成，不需要安装 Office 或 Excel COM。

## Web 仪表盘

页面包含：

- 汇总卡片：总数、正常、预警、危险、无数据/异常。
- 账号卡片：剩余额度圆环、重置时间、套餐、快捷方式、累计 token、事件来源文件。
- 卡片/表格两种视图、搜索、按套餐/状态筛选、多种排序。
- 设置面板：是否扫描主目录和 Profile、启动是否自动刷新、超时时间、额外 Codex 目录、导出目录。
- 导出 CSV / XLSX / JSON。

刷新按钮会向 Codex 发送一次 `/status` 请求。这一步会真实产生少量 token 消耗，可以关闭“启动时自动刷新”，只在需要时手动刷新。

## 配置

配置文件保存在 `~/.codex_quota/config.json`，也可以通过 Web 设置面板修改。主要字段：

```json
{
  "extra_code_homes": ["C:\\path\\to\\another-codex-home"],
  "scan_home": true,
  "scan_profiles": true,
  "refresh_on_start": true,
  "refresh_timeout_seconds": 60,
  "output_dir": ""
}
```

`extra_code_homes` 支持两种写法：直接指向一个 Codex 目录，或指向一个包含多个 `.codex*` 子目录的父目录。

## 打包成 exe

Windows 下运行：

```powershell
.\build_exe.ps1
```

构建产物在 `dist\CodexQuotaReport.exe`，目标机器只需要有网络和 codex CLI 即可，不需要安装 Python 或 Excel。

构建完成后会自动在桌面创建 `CodexQuotaReport.lnk` 快捷方式，双击即可启动原生客户端窗口。exe 会先启动本地额度服务，再打开内置窗口展示仪表盘；窗口组件随 exe 一起打包，不依赖本机 Python 或浏览器。

如果源码方式运行时报“原生窗口组件不可用”，先执行 `python -m pip install pywebview`。

## 测试

```powershell
python -m unittest discover -s tests -v
```

## 已知边界

- 额度数据来自 Codex 写入的 `token_count` 事件，字段结构由 Codex 决定；解析器对 `primary` / `secondary` / `individual_limit` 和多种字段名做了兼容。
- 如果没有 codex CLI 或账号从未产生过额度事件，会显示“无数据”并给出错误信息，不会静默生成错误报告。
- 只监听 `127.0.0.1`，不会暴露到局域网。
