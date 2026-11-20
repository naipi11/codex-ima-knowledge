"""在本机私下输入、验证并保存腾讯凭据。"""

import queue
import threading
import tkinter as tk
from tkinter import ttk
import webbrowser

from ima_client import ImaError, WIKI, request_data, save_credentials


def run():
    window = tk.Tk()
    window.title("腾讯 ima 知识库 · 账号连接")
    frame = ttk.Frame(window, padding=22)
    frame.grid(sticky="nsew")
    window.columnconfigure(0, weight=1)
    frame.columnconfigure(0, weight=1)
    ttk.Label(frame, text="连接你的 ima 账号", font=("Microsoft YaHei UI", 15)).grid(sticky="w")
    ttk.Label(frame, text="登录腾讯官方页面，将同一账号的两项凭据填入下方。").grid(sticky="w", pady=(8, 4))
    ttk.Button(frame, text="打开腾讯官方凭据页面",
               command=lambda: webbrowser.open("https://ima.qq.com/agent-interface")).grid(sticky="w")
    ttk.Label(frame, text="客户端标识（Client ID）").grid(sticky="w", pady=(14, 3))
    client = ttk.Entry(frame, width=54)
    client.grid(sticky="ew")
    ttk.Label(frame, text="接口密钥（API Key）").grid(sticky="w", pady=(10, 3))
    key = ttk.Entry(frame, show="●")
    key.grid(sticky="ew")
    state = tk.StringVar(value="验证成功后保存到当前用户的 Windows 凭据管理器。")
    results = queue.Queue()

    def verify(pair):
        try:
            request_data(WIKI + "search_knowledge_base", {"query": "", "cursor": "", "limit": 1}, pair)
            save_credentials(*pair)
        except ImaError as exc:
            results.put((False, str(exc)))
        except Exception:
            results.put((False, "连接未完成，请检查凭据并重试。"))
        else:
            results.put((True, "已验证并保存。现在可以回到 Codex，列出你的 ima 知识库。"))

    def finish():
        try:
            ok, message = results.get_nowait()
        except queue.Empty:
            window.after(100, finish)
            return
        if ok:
            key.delete(0, "end")
        state.set(message)
        button.state(["!disabled"])

    def connect():
        pair = client.get().strip(), key.get().strip()
        if not all(pair):
            state.set("请填写 Client ID 和 API Key。")
            return
        button.state(["disabled"])
        state.set("正在向腾讯验证知识库访问权限…")
        threading.Thread(target=verify, args=(pair,), daemon=True).start()
        window.after(100, finish)

    button = ttk.Button(frame, text="验证并保存", command=connect)
    button.grid(sticky="w", pady=(16, 5))
    ttk.Label(frame, textvariable=state, wraplength=420).grid(sticky="w")
    client.focus()
    window.mainloop()
