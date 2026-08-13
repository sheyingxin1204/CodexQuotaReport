# codex自检额度

一个 Windows 桌面客户端，自动扫描电脑里的所有 Codex 账号，展示每个账号的套餐、剩余额度和重置时间，并支持一键刷新、查看 `auth.json`、导出 CSV / XLSX / JSON。

## 下载使用

到 [Releases](https://github.com/sheyingxin1204/CodexQuotaReport/releases) 下载最新版的 `CodexQuota.exe`，放到桌面或其他位置，双击即可运行。

不需要安装 Python，也不需要安装 Excel，窗口、图标和运行组件都已经打包在 exe 里。

## 功能

- 自动发现本机所有 Codex 账号目录，包括默认目录、`.codex*` 系列目录和 shell 快捷方式。
- 展示账号邮箱、套餐、主额度剩余、额度重置时间、累计 token。
- 卡片和表格两种视图，支持搜索、筛选、排序。
- 手动刷新额度，刷新会调用 Codex 的 `/status` 请求，有少量 token 消耗。
- 每个账号可以一键打开它的 `auth.json`。
- 导出 CSV / XLSX / JSON 报告到指定目录。
- 设置面板可以添加额外 Codex 目录、关闭启动自动刷新、修改导出目录。

## 常见问题

### 第一次启动有点慢

单文件 exe 启动时需要先解压到临时目录，第一次会比之后慢几秒，这是正常的。

### 提示没有额度数据

程序需要电脑上已经登录过 Codex 账号并产生过会话记录。如果账号从未运行过，或没有安装 codex CLI，会显示“无数据”。

### 刷新额度消耗 token 吗

会。每次点“刷新”都会向 Codex 发送一次 `/status` 请求，消耗少量 token。可以关闭“启动时自动刷新”，只在需要时手动刷新。

### 需要 Windows 吗

当前发布版是 Windows 客户端，需要 Win10 / Win11。系统一般自带 WebView2 运行时，极少数精简系统可能需要在微软官网安装 WebView2。

## 开源协作

仓库是公开只读的：任何人都可以查看代码，但不会被授予直接推送权限。外部贡献请通过 fork 后提交 Pull Request，所有合并由仓库维护者审阅后完成。

## 开发者构建

源码目录 `codex_quota/` 是客户端核心模块。需要从源码构建时：

```powershell
.\build_exe.ps1
```

构建产物在 `dist\CodexQuota.exe`，并会自动在桌面创建 `codex自检额度.lnk` 快捷方式。

## 已知边界

- 额度数据来自 Codex 写入的 `token_count` 事件，字段结构由 Codex 决定，解析器对多种字段形态做了兼容。
- 本地服务只监听 `127.0.0.1`，不会暴露到局域网。
