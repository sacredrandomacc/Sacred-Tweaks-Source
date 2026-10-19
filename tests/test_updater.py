import hashlib
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from desktop import updater


def make_package(files):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as archive:
        for name, data in files.items():
            archive.writestr(name, data)
    return buffer.getvalue()


class Response(io.BytesIO):
    def __init__(self, data):
        super().__init__(data)
        self.headers = {'Content-Length': str(len(data))}

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class UpdaterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.target = Path(self.tmp.name) / 'Programs' / 'Sacred Tweaks'
        self.package = make_package({'Sacred Tweaks/Sacred Tweaks.exe': b'new-exe', 'Sacred Tweaks/_internal/lib.dll': b'x',
                                     'Sacred Tweaks/client-config.json': b'{"api_url":"https://example.invalid"}'})
        self.manifest = {'version': '0.6.0', 'url': 'https://downloads.example.com/member.zip',
                         'sha256': hashlib.sha256(self.package).hexdigest()}

    def opener(self, manifest=None, package=None):
        def open_(request, timeout=0):
            if request.full_url.endswith('/v1/updates/latest'):
                return Response(json.dumps(manifest or self.manifest).encode())
            return Response(package if package is not None else self.package)
        return open_

    def test_fresh_install_then_update_keeps_user_config(self):
        self.assertEqual(updater.update('https://api.example.com', self.target, opener=self.opener()), '0.6.0')
        self.assertEqual((self.target / 'Sacred Tweaks.exe').read_bytes(), b'new-exe')
        (self.target / 'client-config.json').write_text('{"api_url":"https://mine.example.com"}')
        newer = make_package({'Sacred Tweaks/Sacred Tweaks.exe': b'v7', 'Sacred Tweaks/_internal/a': b'', 'Sacred Tweaks/client-config.json': b'{}'})
        manifest = {**self.manifest, 'version': '0.7.0', 'sha256': hashlib.sha256(newer).hexdigest()}
        self.assertEqual(updater.update('https://api.example.com', self.target, opener=self.opener(manifest, newer)), '0.7.0')
        self.assertEqual((self.target / 'Sacred Tweaks.exe').read_bytes(), b'v7')
        self.assertIn('mine.example.com', (self.target / 'client-config.json').read_text())
        self.assertFalse(self.target.with_name('Sacred Tweaks.old').exists())

    def test_same_or_older_version_does_not_download(self):
        updater.update('https://api.example.com', self.target, opener=self.opener())
        calls = []
        def opener(request, timeout=0):
            calls.append(request.full_url)
            return self.opener()(request, timeout)
        self.assertEqual(updater.update('https://api.example.com', self.target, opener=opener), '0.6.0')
        self.assertEqual(calls, ['https://api.example.com/v1/updates/latest'])

    def test_hash_mismatch_installs_nothing(self):
        bad = {**self.manifest, 'sha256': 'b' * 64}
        with self.assertRaises(updater.UpdateError):
            updater.update('https://api.example.com', self.target, opener=self.opener(bad))
        self.assertFalse(self.target.exists())

    def test_rejects_http_unsafe_zip_paths_and_manager_only_packages(self):
        with self.assertRaises(updater.UpdateError):
            updater.check_url('http://downloads.example.com/x.zip')
        for files in ({'../evil.exe': b'x'}, {'Sacred Tweaks Manager/Sacred Tweaks Manager.exe': b'x'}):
            package = Path(self.tmp.name) / 'p.zip'
            package.write_bytes(make_package(files))
            with self.assertRaises(updater.UpdateError):
                updater.safe_extract(package, Path(self.tmp.name) / 'out')
        self.assertLess(updater.parse_version('0.10.0'), updater.parse_version('0.10.1'))
        with self.assertRaises(updater.UpdateError):
            updater.parse_version('1.0-beta')


class ConfigLookupTests(unittest.TestCase):
    def test_finds_example_named_config_in_bundle(self):
        import sys
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / 'client-config.example.json').write_text('{"api_url": "https://api.example.com"}')
            old = getattr(sys, '_MEIPASS', None)
            sys._MEIPASS = tmp
            try:
                self.assertEqual(updater._config()['api_url'], 'https://api.example.com')
            finally:
                if old is None:
                    del sys._MEIPASS
                else:
                    sys._MEIPASS = old


if __name__ == '__main__':
    unittest.main()
