"""Upgrade an existing hosted database to the current schema. Accounts are untouched.

Run after deploying a new server version:  python -m server.migrate_cloud
The URL is read from a hidden prompt so it never lands in shell history.
"""
import getpass
import os

from .__main__ import main


def migrate():
    url = getpass.getpass('Paste PostgreSQL connection URL (hidden): ').strip()
    if not url.startswith(('postgres://', 'postgresql://')):
        raise ValueError('Expected a PostgreSQL connection URL')
    previous = os.environ.get('DATABASE_URL')
    os.environ['DATABASE_URL'] = url
    try:
        main(['--init-db'])  # Idempotent: adds missing tables/columns, never deletes data.
    finally:
        if previous is None:
            os.environ.pop('DATABASE_URL', None)
        else:
            os.environ['DATABASE_URL'] = previous
    print('Database is up to date. Existing accounts, licenses and content were kept.')


if __name__ == '__main__':
    try:
        migrate()
    except (KeyboardInterrupt, EOFError):
        print('\nCancelled.')
        raise SystemExit(1)
    except Exception:
        print('Upgrade failed. Check the database URL, TLS setting and connectivity. No credentials were printed.')
        raise SystemExit(1)
