import json
import logging
from logging.handlers import RotatingFileHandler
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
    no_overlay = "--no-overlay" in sys.argv
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
        base.mkdir(parents=True, exist_ok=True)
        logger = logging.getLogger('sacred.startup')
        if not logger.handlers:
            handler = RotatingFileHandler(base / 'startup.log', maxBytes=64 * 1024, backupCount=1,
                                          encoding='utf-8')
            handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
            logger.addHandler(handler)
            logger.setLevel(logging.INFO)
        logger.info('Starting %s; overlay %s', mode, 'disabled' if no_overlay else 'enabled')
        native = NativeTools(base)
        logger.info('Native services ready')
        api = Api(mode, base, config["api_url"], native, allow_http=config.get("allow_local_http", False) is True)
        window = webview.create_window("Sacred Tweaks Manager" if mode == "manager" else "Sacred Tweaks", url=str(root / "web" / "index.html"), js_api=api, width=1280, height=850, min_size=(900, 650), background_color="#090811")
        window.events.loaded += lambda: apply_window_icon(window, root)
        window.events.loaded += lambda: api._attach(window)
        window.events.minimized += lambda: api._emit({"minimized": True})
        window.events.restored += lambda: api._emit({"minimized": False})
        if mode == "member" and not smoke and not no_overlay:
            from desktop.desktop_overlay import OverlayBridge, DesktopOverlayController, WindowsOverlayProbe
            overlay_stop = threading.Event()
            overlay = {'window': None, 'controller': None}

            def start_overlay_when_needed():
                try:
                    probe = WindowsOverlayProbe(native.platform)
                    while not overlay_stop.wait(.4):
                        if not probe.is_game():
                            continue
                        if overlay_stop.is_set():
                            return
                        logger.info('Fortnite active; creating companion')
                        bridge = OverlayBridge(api, base)
                        companion = webview.create_window(
                            'Sacred Tweaks • Companion', url=str(root / 'web' / 'overlay.html'),
                            js_api=bridge, width=1020, height=640, min_size=(880, 560),
                            hidden=True, frameless=True, easy_drag=False, on_top=True,
                            background_color='#111722')
                        controller = DesktopOverlayController(companion, window, bridge, probe)
                        overlay.update(window=companion, controller=controller)
                        companion.events.loaded += lambda: (logger.info('Companion ready'), controller.start())
                        if companion.events.loaded.is_set():
                            controller.start()

                        def close_companion():
                            if overlay_stop.is_set():
                                return True
                            threading.Thread(target=lambda: controller.hide(restore=True), daemon=True).start()
                            return False

                        companion.events.closing += close_companion
                        if overlay_stop.is_set():
                            controller.close()
                            companion.destroy()
                        return
                except Exception:
                    logger.exception('Companion failed to initialize')

            def stop_overlay():
                overlay_stop.set()
                if overlay['controller']:
                    overlay['controller'].close()
                if overlay['window']:
                    overlay['window'].destroy()

            window.events.loaded += lambda: threading.Thread(target=start_overlay_when_needed,
                                                               name='Sacred-companion-start', daemon=True).start()
            window.events.closed += stop_overlay
        window.events.closed += api._close
        if smoke:
            def verify_window():
                smoke_result["loaded"] = window.evaluate_js("document.readyState === 'complete' && !!document.body") is True
                threading.Timer(1, window.destroy).start()
            window.events.loaded += verify_window
            threading.Timer(25, window.destroy).start()
        logger.info('Starting main WebView2 window')
        webview.start(gui="edgechromium", debug=False)
        logger.info('Main window closed')
        if smoke and not smoke_result["loaded"]:
            raise RuntimeError("WebView2 did not load the local application document.")
    except Exception as exc:
        if 'logger' in locals():
            logger.exception('Startup failed')
        if smoke:
            print(str(exc), file=sys.stderr)
            raise SystemExit(1)
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, str(exc), "Sacred Tweaks — Startup error", 0x10)
        raise SystemExit(1)
