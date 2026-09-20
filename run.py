import os
import sys
import socket
import threading
import time
import webbrowser
import streamlit.web.cli as stcli


APP_URL = "http://127.0.0.1:8501"

def resolve_path(path):
    """处理 PyInstaller 打包后的临时路径问题"""
    if hasattr(sys, '_MEIPASS'):
        # PyInstaller 打包后的运行路径
        return os.path.join(sys._MEIPASS, path)
    return os.path.join(os.path.abspath(os.path.dirname(__file__)), path)


def open_browser_when_ready():
    """Open the app in the default browser after Streamlit is listening."""
    for _ in range(60):
        try:
            with socket.create_connection(("127.0.0.1", 8501), timeout=1):
                if sys.platform == "win32":
                    os.startfile(APP_URL)  # type: ignore[attr-defined]
                else:
                    webbrowser.open_new_tab(APP_URL)
                return
        except OSError:
            time.sleep(0.5)

if __name__ == "__main__":
    script_path = resolve_path("web_app.py")
    
    sys.argv = [
        "streamlit",
        "run",
        script_path,
        "--global.developmentMode=false",
        "--server.headless=true",
        "--server.address=127.0.0.1",
        "--server.port=8501",
        "--browser.gatherUsageStats=false",
        "--theme.base=light"
    ]
    threading.Thread(target=open_browser_when_ready, daemon=True).start()
    sys.exit(stcli.main())
