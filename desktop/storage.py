"""Small Windows DPAPI store for the random installation identity.

Session bearer tokens intentionally live in memory only. No hardware identifiers
or keyboard history are stored. Losing this identity requires owner transfer.
"""
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import secrets
import tempfile


def atomic_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def _protect(data: bytes, decrypt=False) -> bytes:
    return _dpapi(data, decrypt, local_machine=True)


def _dpapi(data: bytes, decrypt=False, *, local_machine=False) -> bytes:
    if os.name != "nt":
        raise RuntimeError("Device registration requires Windows DPAPI.")
    class BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_ubyte))]
    buffer = ctypes.create_string_buffer(data)
    source = BLOB(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    output = BLOB()
    crypt = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    if decrypt:
        fn = crypt.CryptUnprotectData
        fn.argtypes = [ctypes.POINTER(BLOB), ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(BLOB)]
        ok = fn(ctypes.byref(source), None, None, None, None, 1 if local_machine else 0, ctypes.byref(output))
    else:
        fn = crypt.CryptProtectData
        fn.argtypes = [ctypes.POINTER(BLOB), wintypes.LPCWSTR, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(BLOB)]
        ok = fn(ctypes.byref(source), "Sacred Tweaks protected session", None, None, None, 1 if local_machine else 0, ctypes.byref(output))
    if not ok:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        return ctypes.string_at(output.pbData, output.cbData)
    finally:
        kernel.LocalFree(output.pbData)


class SessionVault:
    """Opt-in refresh token storage, encrypted to the current Windows user."""
    def __init__(self, path: Path, protector=None):
        self.path = Path(path)
        self.protector = protector or (lambda data, decrypt=False: _dpapi(data, decrypt, local_machine=False))

    def save(self, token: str):
        if not isinstance(token, str) or not 32 <= len(token) <= 256:
            raise ValueError("Invalid saved session token.")
        encrypted = self.protector(token.encode("utf-8"))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(prefix=self.path.name + ".", dir=self.path.parent)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(encrypted)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(name, self.path)
            try:
                os.chmod(self.path, 0o600)
            except OSError:
                pass
        finally:
            if os.path.exists(name):
                os.unlink(name)

    def load(self):
        try:
            raw = self.path.read_bytes()
            if not raw:
                return None
            token = self.protector(raw, decrypt=True).decode("utf-8")
            if not 32 <= len(token) <= 256:
                raise ValueError("Invalid saved session token.")
            return token
        except FileNotFoundError:
            return None
        except Exception:
            self.clear()
            return None

    def clear(self):
        try:
            self.path.unlink()
        except FileNotFoundError:
            pass


def load_device_id(data_dir: Path) -> str:
    path = Path(data_dir) / "device.dpapi"
    if path.exists():
        try:
            identity = _protect(path.read_bytes(), decrypt=True).decode("ascii")
        except Exception as exc:
            raise RuntimeError("This Windows profile cannot unlock the device registration. Ask the owner for a device transfer.") from exc
        if len(identity) != 64:
            raise RuntimeError("Device registration is damaged. Ask the owner for a device reset.")
        return identity
    path.parent.mkdir(parents=True, exist_ok=True)
    identity = secrets.token_hex(32)
    encrypted = _protect(identity.encode("ascii"))
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(encrypted)
        stream.flush()
        os.fsync(stream.fileno())
    return identity
