import json
import os
from pathlib import Path
import sys
import threading


def resource_root():
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))


def apply_window_icon(window, root):
    """Set the WinForms title-bar/taskbar icon after the native form exists."""
    from System import Action
    from System.Drawing import Icon
    def apply():
        window.native.Icon = Icon(str(root / 'assets' / 'sacred-app-icon.ico'))
        window.native.ShowIcon = True
    window.native.Invoke(Action(apply))


def launch(mode="member"):
    if os.name != "nt":
        raise SystemExit("Sacred Tweaks desktop requires Windows 10/11. The backend and tests are cross-platform.")
    smoke = "--smoke-test" in sys.argv
    smoke_result = {"loaded": False}
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "SacredLLC.SacredTweaks." + ("Manager" if mode == "manager" else "Member"))
        import webview
        from desktop.bridge import Api
        from desktop.native import NativeTools
        root = resource_root()
        config_path = Path(sys.executable).parent / "client-config.json" if getattr(sys, "frozen", False) else root / "client-config.json"
        if not config_path.exists():
            raise RuntimeError("Missing client-config.json. Copy client-config.example.json beside the application and set your HTTPS backend URL.")
        config = json.loads(config_path.read_text(encoding="utf-8"))
        base = Path(os.environ["LOCALAPPDATA"]) / "SacredTweaks"
        native = NativeTools(base)
        api = Api(mode, base, config["api_url"], native, allow_http=config.get("allow_local_http", False) is True)
        window = webview.create_window("Sacred Tweaks Manager" if mode == "manager" else "Sacred Tweaks", url=str(root / "web" / "index.html"), js_api=api, width=1280, height=850, min_size=(900, 650), background_color="#090811")
        window.events.loaded += lambda: apply_window_icon(window, root)
        window.events.loaded += lambda: api._attach(window)
        window.events.closed += api._close
        window.events.minimized += lambda: api._emit({"minimized": True})
        window.events.restored += lambda: api._emit({"minimized": False})
        if smoke:
            def verify_window():
                smoke_result["loaded"] = window.evaluate_js("document.readyState === 'complete' && !!document.body") is True
                threading.Timer(1, window.destroy).start()
            window.events.loaded += verify_window
            threading.Timer(25, window.destroy).start()
        webview.start(gui="edgechromium", debug=False)
        if smoke and not smoke_result["loaded"]:
            raise RuntimeError("WebView2 did not load the local application document.")
    except Exception as exc:
        if smoke:
            print(str(exc), file=sys.stderr)
            raise SystemExit(1)
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, str(exc), "Sacred Tweaks — Startup error", 0x10)
        raise SystemExit(1)
