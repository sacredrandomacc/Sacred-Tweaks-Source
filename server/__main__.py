"""Run with python -m server --help. No low-cost password option is exposed."""
import argparse
import getpass
import os
from pathlib import Path
import sys
from urllib.parse import quote

from .http import make_server
from .service import Service


def main(argv=None):
    parser = argparse.ArgumentParser(description='Sacred Tweaks licensing backend; use Caddy for public HTTPS.')
    parser.add_argument('--db', default='data/sacred.db', help='Persistent SQLite database path')
    parser.add_argument('--host', default='127.0.0.1', help='Bind address; default localhost')
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--trusted-proxy', action='append', default=[], metavar='CIDR', help='Trusted reverse proxy IP/CIDR; repeatable. Never trust an unrestricted range.')
    operation = parser.add_mutually_exclusive_group()
    operation.add_argument('--bootstrap-owner', metavar='USERNAME', help='Create the initial owner interactively, then exit')
    operation.add_argument('--reset-owner-device', action='store_true', help='Server-operator recovery: clear owner device registration and sessions, then exit')
    args = parser.parse_args(argv)
    os.umask(0o077)
    service = Service(Path(args.db))
    if args.bootstrap_owner:
        password = getpass.getpass('Owner password (12–128 characters): ')
        if password != getpass.getpass('Repeat owner password: '):
            parser.error('Passwords did not match')
        try:
            setup = service.bootstrap_owner(args.bootstrap_owner, password)
        except Exception as error:
            parser.error(str(error))
        print('Owner created. Store these secrets safely; they are shown only now.')
        print('Authenticator setup secret:', setup['totp_secret'])
        label = quote('Sacred Tweaks:' + args.bootstrap_owner, safe='')
        print('Authenticator URI: otpauth://totp/' + label + '?secret=' + setup['totp_secret'] + '&issuer=Sacred%20Tweaks&algorithm=SHA1&digits=6&period=30')
        print('Single-use recovery codes (each also serves as owner login MFA):')
        for code in setup['recovery_codes']:
            print(code)
        return 0
    if args.reset_owner_device:
        if input('Type RESET OWNER DEVICE to clear its registration and sessions: ') != 'RESET OWNER DEVICE':
            parser.error('Confirmation did not match')
        with service.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            owner = db.execute("SELECT id FROM users WHERE role='owner'").fetchone()
            if not owner:
                parser.error('No owner exists')
            service._set_device(db, owner['id'], None)
            db.execute('UPDATE sessions SET revoked=1 WHERE user_id=?', (owner['id'],))
            service._audit(db, owner['id'], 'operator_owner_device_reset', 'user', owner['id'])
        print('Owner device registration cleared. Password and MFA are still required at next login.')
        return 0
    try:
        server = make_server(service, args.host, args.port, args.trusted_proxy)
    except ValueError as error:
        parser.error(str(error))
    print(f'Sacred Tweaks service listening on {args.host}:{args.port}; HTTPS must be provided by the reverse proxy.', file=sys.stderr)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
