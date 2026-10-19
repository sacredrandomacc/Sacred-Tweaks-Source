# Copyright (c) 2026 Sacred LLC. All rights reserved. See LICENSE.
"""Single-file updater for the member app (never the Manager).

Flow: read the bundled client-config.json -> ask the backend for the latest stable
member release -> if newer than the installed copy, download over HTTPS, verify the
SHA-256 published by the owner, extract safely, swap folders atomically-ish, keep the
user's client-config.json -> launch Sacred Tweaks. Offline or no update: just launch.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import urllib.error
import urllib.parse
import urllib.request
import zipfile

APP_DIR_NAME = 'Sacred Tweaks'
APP_EXE = 'Sacred Tweaks.exe'
VERSION_FILE = 'sacred-version.txt'
MAX_PACKAGE_BYTES = 600 * 1024 * 1024


class UpdateError(Exception):
    pass


def parse_version(text):
    if not isinstance(text, str) or not re.fullmatch(r'\d+(\.\d+){0,3}', text.strip()):
        raise UpdateError(f'Invalid version: {text!r}')
    parts = [int(p) for p in text.strip().split('.')]
    return tuple(parts + [0] * (4 - len(parts)))


def install_dir():
    base = Path(os.environ.get('LOCALAPPDATA') or Path.home()) / 'Programs'
    return base / APP_DIR_NAME


def installed_version(target):
    try:
        return (target / VERSION_FILE).read_text('utf-8').strip()
    except OSError:
        return None


def check_url(url, allow_http=False):
    parts = urllib.parse.urlsplit(url)
    local = parts.hostname in ('localhost', '127.0.0.1', '::1')
    if parts.username or parts.password or not parts.hostname:
        raise UpdateError('Refusing a URL with credentials or no host.')
    if parts.scheme != 'https' and not (allow_http and local and parts.scheme == 'http'):
        raise UpdateError('Updates are only downloaded over HTTPS.')
    return url


def channel():
    """'beta' when the member opted in from the app (written to updater.json)."""
    try:
        value = json.loads((Path(os.environ.get('LOCALAPPDATA') or Path.home()) / 'SacredTweaks' / 'updater.json').read_text('utf-8')).get('channel')
    except (OSError, ValueError, AttributeError):
        return 'stable'
    return 'beta' if value == 'beta' else 'stable'


def fetch_manifest(api_url, allow_http=False, opener=urllib.request.urlopen, feed='stable'):
    url = check_url(api_url.rstrip('/') + ('/v1/updates/beta' if feed == 'beta' else '/v1/updates/latest'), allow_http)
    try:
        with opener(urllib.request.Request(url, headers={'User-Agent': 'SacredTweaksUpdater'}), timeout=10) as response:
            data = json.loads(response.read(64 * 1024).decode('utf-8'))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        if exc.code in (401, 403, 405):
            raise UpdateError('Your Sacred Tweaks server does not support auto-updates yet. The owner needs to deploy the '
                              'latest server version and publish a release in the Manager.') from exc
        raise UpdateError(f'Update server returned {exc.code}.') from exc
    except (OSError, ValueError) as exc:
        raise UpdateError(f'Could not reach the update server: {exc}') from exc
    if not isinstance(data, dict) or not re.fullmatch(r'[0-9a-f]{64}', str(data.get('sha256', ''))):
        raise UpdateError('Update manifest is malformed.')
    parse_version(data.get('version'))
    check_url(str(data.get('url')), allow_http)
    return data


def download(url, destination, expected_sha256, progress=None, allow_http=False, opener=urllib.request.urlopen):
    check_url(url, allow_http)
    digest, received = hashlib.sha256(), 0
    try:
        with opener(urllib.request.Request(url, headers={'User-Agent': 'SacredTweaksUpdater'}), timeout=30) as response, \
                open(destination, 'wb') as out:
            if 'text/html' in str(response.headers.get('Content-Type', '')).lower():
                raise UpdateError('The release link opens a web page, not the zip file. Use a direct download link '
                                  '(for example a GitHub Releases asset) in the Manager release.')
            total = int(response.headers.get('Content-Length') or 0)
            if total > MAX_PACKAGE_BYTES:
                raise UpdateError('Update package is too large.')
            while chunk := response.read(256 * 1024):
                received += len(chunk)
                if received > MAX_PACKAGE_BYTES:
                    raise UpdateError('Update package is too large.')
                digest.update(chunk)
                out.write(chunk)
                if progress and total:
                    progress(received / total)
    except OSError as exc:
        raise UpdateError(f'Download failed: {exc}') from exc
    if digest.hexdigest() != expected_sha256.lower():
        Path(destination).unlink(missing_ok=True)
        raise UpdateError('Downloaded package does not match the published SHA-256. Nothing was installed.')


def safe_extract(package, destination):
    """Extract without path traversal; return the folder that contains Sacred Tweaks.exe."""
    destination = Path(destination).resolve()
    with zipfile.ZipFile(package) as archive:
        for member in archive.infolist():
            target = (destination / member.filename).resolve()
            if destination not in target.parents and target != destination:
                raise UpdateError('Update package contains an unsafe path.')
        archive.extractall(destination)
    for exe in destination.rglob(APP_EXE):
        if 'Manager' not in exe.name and (exe.parent / '_internal').is_dir():
            return exe.parent
    raise UpdateError('Update package does not contain the Sacred Tweaks app.')


def unblock(folder):
    """Remove Windows' Mark-of-the-Web streams so no file needs Unblock-File."""
    if os.name != 'nt':
        return 0
    removed = 0
    for path in Path(folder).rglob('*'):
        if path.is_file():
            try:
                os.remove(str(path) + ':Zone.Identifier')
                removed += 1
            except OSError:
                pass
    return removed


def swap_in(new_app, target, version):
    """Replace target with new_app, keeping the user's client-config.json."""
    target = Path(target)
    config = target / 'client-config.json'
    if config.exists():
        shutil.copy2(config, Path(new_app) / 'client-config.json')
    (Path(new_app) / VERSION_FILE).write_text(version, 'utf-8')
    old = target.with_name(target.name + '.old')
    if old.exists():
        shutil.rmtree(old, ignore_errors=True)
    if target.exists():
        try:
            target.rename(old)
        except OSError as exc:
            raise UpdateError('Close Sacred Tweaks, then run the updater again.') from exc
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(new_app), str(target))
    except OSError:
        if old.exists() and not target.exists():
            old.rename(target)  # Roll back to the previous version.
        raise
    shutil.rmtree(old, ignore_errors=True)


def update(api_url, target=None, allow_http=False, progress=None, status=None, opener=urllib.request.urlopen, feed=None):
    """Returns the version now installed (or None if nothing could be installed)."""
    target = Path(target or install_dir())
    current = installed_version(target)
    say = status or (lambda text: None)
    say('Checking for updates…')
    manifest = fetch_manifest(api_url, allow_http, opener, feed or channel())
    if not manifest or (current and parse_version(manifest['version']) <= parse_version(current)):
        return current
    say(f"Downloading Sacred Tweaks {manifest['version']}…")
    with tempfile.TemporaryDirectory(prefix='sacred-update-') as work:
        package = Path(work) / 'package.zip'
        download(manifest['url'], package, manifest['sha256'], progress, allow_http, opener)
        say('Installing…')
        app = safe_extract(package, Path(work) / 'extract')
        unblock(app)
        swap_in(app, target, manifest['version'])
    return manifest['version']


def _config():
    # Bundled copy first, then one beside the updater, then the installed app's own config.
    roots = [Path(getattr(sys, '_MEIPASS', '')), Path(sys.executable).parent, install_dir(), Path(__file__).resolve().parents[1]]
    for root in roots:
        for name in ('client-config.json', 'client-config.example.json'):
            path = root / name
            if path.is_file():
                try:
                    config = json.loads(path.read_text('utf-8'))
                except ValueError:
                    continue
                if isinstance(config, dict) and isinstance(config.get('api_url'), str):
                    return config
    raise UpdateError('client-config.json is missing from the updater.')


def _message(text, title='Sacred Tweaks Updater', error=False):
    if os.name == 'nt':
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, text, title, 0x10 if error else 0x40)
    else:
        print(text)


def main():
    """Updater entry point with a small progress window."""
    result = {'version': None, 'error': None}
    target = install_dir()
    try:
        import tkinter as tk
        from tkinter import ttk
        root = tk.Tk()
        root.title('Sacred Tweaks')
        root.geometry('360x110')
        root.resizable(False, False)
        root.configure(bg='#0A1220')
        label = tk.Label(root, text='Starting…', fg='#EAF2FF', bg='#0A1220', font=('Segoe UI', 10))
        label.pack(pady=(22, 10))
        bar = ttk.Progressbar(root, length=300, mode='determinate', maximum=1.0)
        bar.pack()
    except Exception:
        root = label = bar = None

    def work():
        try:
            config = _config()
            ui = lambda fn: root.after(0, fn) if root else None
            result['version'] = update(config['api_url'], target, config.get('allow_local_http') is True,
                                       progress=lambda f: ui(lambda: bar.configure(value=f)),
                                       status=lambda t: ui(lambda: label.configure(text=t)))
        except UpdateError as exc:
            result['error'] = str(exc)
            result['version'] = installed_version(target)
        except Exception as exc:  # Never leave the user without their app.
            result['error'] = f'Unexpected update error: {exc}'
            result['version'] = installed_version(target)
        finally:
            if root:
                root.after(0, root.destroy)

    thread = threading.Thread(target=work, daemon=True)
    thread.start()
    if root:
        root.mainloop()
    thread.join()
    exe = target / APP_EXE
    unblock(target)  # Also fixes copies a user unzipped manually into the install folder.
    if not exe.exists():
        _message((result['error'] or 'No Sacred Tweaks release has been published yet.')
                 + '\n\nNothing was installed. Once a release is published in the Manager, run the updater again.', error=True)
        return 1
    if result['error'] and 'Close Sacred Tweaks' in result['error']:
        _message(result['error'], error=True)
        return 1
    subprocess.Popen([str(exe)], cwd=str(target), close_fds=True)
    return 0
