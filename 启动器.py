#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
动态选股系统 - Web界面启动器（支持多策略）
独立可执行文件启动脚本
"""

import sys
import os
import webbrowser
import time
import socket
import subprocess
from threading import Thread

# 检查端口是否可用
def is_port_available(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(('localhost', port))
            return True
        except OSError:
            return False

# 自动打开浏览器
def open_browser(port):
    time.sleep(3)  # 等待服务器启动
    url = f'http://localhost:{port}'
    print(f"正在打开浏览器: {url}")
    webbrowser.open(url)

def main():
    print("=" * 60)
    print("动态选股系统 - Web界面（多策略版本）")
    print("=" * 60)
    
    # 设置端口
    port = 5080
    
    # 检查端口是否可用
    if not is_port_available(port):
        print(f"错误: 端口 {port} 已被占用")
        print("请关闭占用该端口的程序，或修改代码中的端口号")
        input("按Enter键退出...")
        return
    
    # 获取当前目录
    if getattr(sys, 'frozen', False):
        # 如果是打包后的exe
        base_dir = os.path.dirname(sys.executable)
    else:
        # 如果是Python脚本
        base_dir = os.path.dirname(os.path.abspath(__file__))
    
    # 切换到项目目录
    os.chdir(base_dir)
    print(f"工作目录: {base_dir}")
    
    # 检查web_app.py是否存在
    web_app_path = os.path.join(base_dir, 'web_app.py')
    if not os.path.exists(web_app_path):
        print(f"错误: 找不到 web_app.py")
        print(f"查找路径: {web_app_path}")
        input("按Enter键退出...")
        return
    
    # 检查config.yaml是否存在
    config_path = os.path.join(base_dir, 'config.yaml')
    if not os.path.exists(config_path):
        print(f"警告: 找不到 config.yaml")
        print(f"查找路径: {config_path}")
    
    # 检查templates目录
    templates_dir = os.path.join(base_dir, 'templates')
    if not os.path.exists(templates_dir):
        print(f"警告: 找不到 templates 目录")
        print(f"查找路径: {templates_dir}")
    
    print(f"端口: {port}")
    print(f"访问地址: http://localhost:{port}")
    print("=" * 60)
    print("正在启动Web服务器...")
    print("按Ctrl+C停止服务")
    print("=" * 60)
    
    # 在后台打开浏览器
    Thread(target=open_browser, args=(port,), daemon=True).start()
    
    # 启动Flask应用
    try:
        # 导入并运行web_app
        sys.path.insert(0, base_dir)
        from web_app import app
        app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)
    except KeyboardInterrupt:
        print("\n服务已停止")
    except Exception as e:
        print(f"\n启动失败: {e}")
        input("按Enter键退出...")

if __name__ == '__main__':
    main()