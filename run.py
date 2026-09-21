import os
import socket
import stitcher
import sys
import threading
import time
import urllib.request
import webbrowser
import streamlit.web.cli as stcli


APP_HOST = "127.0.0.1"
APP_PORT = 8501
APP_URL = f"http://{APP_HOST}:{APP_PORT}"
# 冷启动窗口（秒）：Windows onedir 首次解压 + 杀软扫描会比较慢，放宽到 120s。
READY_TIMEOUT = 120
MAX_OPEN_ATTEMPTS = 3


def resolve_path(path):
    """处理 PyInstaller 打包后的临时路径问题"""
    if hasattr(sys, "_MEIPASS"):
        # PyInstaller 打包后的运行路径
        return os.path.join(sys._MEIPASS, path)
    return os.path.join(os.path.abspath(os.path.dirname(__file__)), path)


def log_dir():
    """启动日志目录。_MEIPASS 是临时目录会被清理，优先写到 EXE 同级目录。"""
    base = None
    if hasattr(sys, "_MEIPASS"):
        base = os.path.dirname(sys.executable)
    if not base:
        base = os.path.abspath(os.path.dirname(__file__))
    try:
        os.makedirs(base, exist_ok=True)
        return base
    except Exception:
        return os.getcwd()


def write_log(text):
    try:
        with open(os.path.join(log_dir(), "startup.log"), "a", encoding="utf-8") as f:
            f.write(text.rstrip("\n") + "\n")
    except Exception:
        pass


def port_in_use(host, port):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind((host, port))
        return False
    except OSError:
        return True
    finally:
        s.close()


def health_ok():
    """只有 HTTP 健康端点真正返回 200 才算就绪，避免『端口起来了但还没准备好』。"""
    try:
        with urllib.request.urlopen(f"{APP_URL}/_stcore/health", timeout=2) as r:
            return r.status == 200
    except Exception:
        return False


def try_open_browser():
    """用多种方式打开默认浏览器，返回是否成功。"""
    write_log("opening browser: " + APP_URL)
    try:
        if sys.platform == "win32":
            os.startfile(APP_URL)  # type: ignore[attr-defined]
            return True
        webbrowser.open_new(APP_URL)
        return True
    except Exception as e:
        write_log("primary open failed: %r" % (e,))
        try:
            if sys.platform == "win32":
                import subprocess
                subprocess.Popen(
                    f"rundll32 url.dll,FileProtocolHandler {APP_URL}", shell=True
                )
                return True
            return bool(webbrowser.open(APP_URL))
        except Exception as e2:
            write_log("fallback open failed: %r" % (e2,))
            return False


def show_message(title, text):
    """无控制台（--windowed）下的可视化反馈：Windows 弹原生 MessageBox。"""
    write_log("[MSG] " + title + " | " + text.replace("\n", " "))
    try:
        if sys.platform == "win32":
            import ctypes
            ctypes.windll.user32.MessageBoxW(0, text, title, 0)
            return
    except Exception:
        pass
    print(title)
    print(text)


def open_browser_when_ready():
    """等服务真正就绪后打开浏览器；打不开就给出可手动访问的 URL。"""
    deadline = time.time() + READY_TIMEOUT
    ready = False
    while time.time() < deadline:
        if health_ok():
            ready = True
            break
        time.sleep(0.5)
    write_log(f"server ready={ready}")

    if not ready:
        show_message(
            "AI视频生成神器 启动提示",
            "本地服务在 %.0f 秒内尚未就绪。\n请手动在浏览器打开：\n%s\n\n"
            "若长时间打不开，请查看 %s 目录下的 startup.log。"
            % (READY_TIMEOUT, APP_URL, log_dir()),
        )
        return

    time.sleep(1)  # 给首帧一点渲染时间
    for _ in range(MAX_OPEN_ATTEMPTS):
        if try_open_browser():
            return
        time.sleep(2)
    show_message(
        "AI视频生成神器",
        "本地服务已启动，但浏览器没有自动弹出。\n请手动打开：\n" + APP_URL,
    )


if __name__ == "__main__":
    script_path = resolve_path("web_app.py")
    write_log(f"=== launch ===\npython={sys.executable}\nscript={script_path}")

    # 端口被占用（通常上次没彻底关闭）：不再强行启动第二份会崩溃的服务，
    # 直接提示并尝试打开已在运行的实例。
    if port_in_use(APP_HOST, APP_PORT):
        write_log("port %d already in use" % APP_PORT)
        show_message(
            "AI视频生成神器",
            "端口 %d 已被占用（可能上次未完全关闭）。\n"
            "请先结束之前的 “AI视频生成神器” 进程再重试；\n"
            "或直接打开已在运行的实例：" + APP_URL,
        )

    sys.argv = [
        "streamlit",
        "run",
        script_path,
        "--global.developmentMode=false",
        "--server.headless=true",
        f"--server.address={APP_HOST}",
        f"--server.port={APP_PORT}",
        "--browser.gatherUsageStats=false",
        "--theme.base=light",
    ]
    threading.Thread(target=open_browser_when_ready, daemon=True).start()
    sys.exit(stcli.main())
