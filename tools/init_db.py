#!/usr/bin/env python3
"""Small launcher to initialize the DB and migrate any config files.

This replaces the multi-line ``python -c"..."`` usage in ``entrypoint.sh`` so
that imports inside ``app`` see a proper module ``__file__`` instead of being
executed from a Python string (which can lead to NameError for ``__file__``).
"""
import sys
import pathlib

# Ensure repository root is on sys.path (matches previous behaviour)
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app import init_db, migrate_from_files


def main():
    init_db()
    migrate_from_files()
    print('DB initialized')


if __name__ == '__main__':
    main()
