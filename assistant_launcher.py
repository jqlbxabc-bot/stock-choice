#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
A股交易助手统一启动器。
Windows 打包后可直接作为 EXE 入口。
"""

from __future__ import annotations
import os
import subprocess
import sys
import threading
import webbrowser
from pathlib import Path
import tkinter as tk
from tkinter import messagebox

BASE = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
WORKDIR = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent

def resource(name: str) -> Path:
    p = BASE / name
    return p if p.exists() else WORKDIR / name

def run_py(script: str):
    if getattr(sys, "frozen", False):
        # EXE内置解释器不能直接执行源码模块，改为调用同目录 Python（如果有）
        py = WORKDIR / "python.exe"
        if py.exists():
            return subprocess.Popen([str(py), str(resource(script))], cwd=str(WORKDIR))
        raise RuntimeError("独立EXE模式请使用内置菜单功能；未发现外部 python.exe")
    return subprocess.Popen([sys.executable, str(resource(script))], cwd=str(WORKDIR))

class App:
    def __init__(self, root):
        self.root = root
        root.title("A股交易助手")
        root.geometry("520x390")
        root.resizable(False, False)
        self.rt_proc = None

        title = tk.Label(root, text="A股交易助手", font=("Microsoft YaHei UI", 22, "bold"))
        title.pack(pady=(24, 6))
        tk.Label(root, text="实时选股 · 风控 · 云端看板", font=("Microsoft YaHei UI", 11)).pack(pady=(0, 18))

        frame = tk.Frame(root)
        frame.pack(fill="x", padx=55)

        self.btn(frame, "启动实时选股", self.start_realtime).pack(fill="x", pady=6)
        self.btn(frame, "更新本地看板数据", self.update_dashboard).pack(fill="x", pady=6)
        self.btn(frame, "打开云端看板", self.open_cloud).pack(fill="x", pady=6)
        self.btn(frame, "打开项目目录", self.open_folder).pack(fill="x", pady=6)
        self.btn(frame, "停止实时选股", self.stop_realtime).pack(fill="x", pady=6)

        self.status = tk.StringVar(value="状态：待机")
        tk.Label(root, textvariable=self.status, font=("Microsoft YaHei UI", 10)).pack(pady=18)
        tk.Label(root, text="辅助决策，不自动下单。数据过期时不生成交易型动作。",
                 font=("Microsoft YaHei UI", 9)).pack(side="bottom", pady=12)

    def btn(self, parent, text, cmd):
        return tk.Button(parent, text=text, command=cmd, height=2, font=("Microsoft YaHei UI", 11))

    def start_realtime(self):
        if self.rt_proc and self.rt_proc.poll() is None:
            self.status.set("状态：实时选股已运行")
            return
        try:
            self.rt_proc = run_py("realtime_selector.py")
            self.status.set("状态：实时选股运行中")
        except Exception as e:
            messagebox.showerror("启动失败", str(e))

    def update_dashboard(self):
        def worker():
            try:
                p = run_py("sync_dashboard.py")
                p.wait()
                self.status.set("状态：看板数据已更新")
            except Exception as e:
                self.status.set("状态：更新失败")
                messagebox.showerror("更新失败", str(e))
        threading.Thread(target=worker, daemon=True).start()

    def open_cloud(self):
        webbrowser.open("https://jqlbxabc-bot.github.io/stock-choice/")
        self.status.set("状态：已打开云端看板")

    def open_folder(self):
        try:
            os.startfile(str(WORKDIR))
        except Exception:
            pass

    def stop_realtime(self):
        if self.rt_proc and self.rt_proc.poll() is None:
            self.rt_proc.terminate()
            self.status.set("状态：实时选股已停止")
        else:
            self.status.set("状态：实时选股未运行")

if __name__ == "__main__":
    root = tk.Tk()
    App(root)
    root.mainloop()
