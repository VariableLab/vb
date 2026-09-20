import os
import sys
import streamlit.web.cli as stcli
import requests
import openai

def resolve_path(path):
    """处理 PyInstaller 打包后的临时路径问题"""
    if hasattr(sys, '_MEIPASS'):
        # PyInstaller 打包后的运行路径
        return os.path.join(sys._MEIPASS, path)
    return os.path.join(os.path.abspath(os.path.dirname(__file__)), path)

if __name__ == "__main__":
    script_path = resolve_path("web_app.py")
    
    sys.argv = [
        "streamlit",
        "run",
        script_path,
        "--global.developmentMode=false",
        "--server.headless=false",
        "--server.address=127.0.0.1",
        "--server.port=8501",
        "--browser.gatherUsageStats=false",
        "--theme.base=light"
    ]
    sys.exit(stcli.main())
