# 在 Codex 中使用 ima 知识库

这是一个公开的第三方 Codex 插件市场，适用于 Windows。安装“腾讯 ima 知识库”并连接自己的 ima 账号后，可以在本地 Codex 聊天中列出知识库、浏览文件夹、搜索资料，以及按权限读取笔记、文本型 PDF、DOCX、TXT 和 Markdown。

## 在新电脑上安装

准备支持插件市场的 Codex 桌面客户端及命令行、Git 和 uv。首次运行时，uv 会联网准备 Python 环境和依赖。任何人都可以在 PowerShell 中运行以下命令添加公开市场，每台电脑只需添加一次。

```powershell
codex plugin marketplace add https://github.com/naipi11/codex-ima-knowledge.git
```

打开 Codex 的“自定义 → 插件”，刷新后选择 **我的知识库插件** 来源，点击 **腾讯 ima 知识库 → 安装**。也可以在 PowerShell 中安装：

```powershell
codex plugin add ima-knowledge@ima-local
```

## 连接自己的腾讯账号

运行 `codex mcp get ima`，在显示的 `cwd` 目录中双击 **连接我的知识库.cmd**。点击 **打开腾讯官方凭据页面**，填入该账号的 Client ID 和 API Key，然后点击 **验证并保存**。凭据保存在当前电脑的 Windows 凭据管理器。[腾讯 ima 官方凭据页](https://ima.qq.com/agent-interface)

新建一个本地 Codex 聊天，输入“列出我的 ima 知识库”。也可以问“在指定知识库中搜索裂缝宽度，按资料标题列出命中片段”。原文是否可读取取决于腾讯授权及文件格式。这个市场分发只读连接插件，安装时每台电脑各自连接 ima 账号。

## 更新

先刷新远程市场，再从插件页安装新版本。命令行操作如下。

```powershell
codex plugin marketplace upgrade ima-local
codex plugin add ima-knowledge@ima-local
```
