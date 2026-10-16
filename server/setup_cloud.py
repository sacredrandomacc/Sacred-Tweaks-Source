"""Private, interactive first-owner setup. No secrets in shell history."""
import getpass
import os
from .__main__ import main


def setup():
    print('Create a NEW hosted Sacred Tweaks database and owner account.')
    print('Existing local accounts are not copied. Use a dedicated empty database.')
    url = getpass.getpass('Paste PostgreSQL connection URL (hidden): ').strip()
    if not url.startswith(('postgres://', 'postgresql://')):
        raise ValueError('Expected a PostgreSQL connection URL')
    username = input('Owner username [owner]: ').strip() or 'owner'
    previous = os.environ.get('DATABASE_URL')
    os.environ['DATABASE_URL'] = url
    try:
        main(['--init-db'])
        main(['--bootstrap-owner', username])
    finally:
        if previous is None:
            os.environ.pop('DATABASE_URL', None)
        else:
            os.environ['DATABASE_URL'] = previous


if __name__ == '__main__':
    try:
        setup()
    except (KeyboardInterrupt, EOFError):
        print('\nSetup cancelled.')
        raise SystemExit(1)
    except Exception:
        print('Setup failed. Check the database URL, TLS setting, and connectivity. No connection credentials were printed.')
        raise SystemExit(1)
