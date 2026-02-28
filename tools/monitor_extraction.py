#!/usr/bin/env python3
"""
Simple monitor that tails extractor stdout/stderr and exits when the
`playwright_captures/import_complete.txt` marker appears or when the
stdout contains 'Import complete'. Useful for watching the detached
extractor progress from the host.

Usage: python3 tools/monitor_extraction.py
"""
import time
import os
from pathlib import Path

OUT = Path('playwright_captures')
STDOUT = OUT / 'extract_stdout.txt'
STDERR = OUT / 'extract_stderr.txt'
MARKER = OUT / 'import_complete.txt'


def follow(path):
    """Yield new lines appended to path, starting at current EOF."""
    try:
        f = open(path, 'r', encoding='utf-8', errors='replace')
    except FileNotFoundError:
        # return an empty generator-like iterator
        def _empty():
            while True:
                time.sleep(0.5)
                yield None
        return _empty()
    # seek to end
    f.seek(0, os.SEEK_END)
    while True:
        line = f.readline()
        if line:
            yield line.rstrip('\n')
        else:
            time.sleep(0.3)


def monitor():
    it_out = follow(STDOUT)
    it_err = follow(STDERR)
    print('Monitoring extractor logs. Waiting for import to complete...')
    try:
        while True:
            # check marker file
            if MARKER.exists():
                print('\nDetected import marker file:', MARKER)
                print(MARKER.read_text(encoding='utf-8'))
                return 0

            # read any new stdout lines
            try:
                line = next(it_out)
            except StopIteration:
                line = None
            if line:
                print('[STDOUT]', line)
                if 'Import complete' in line:
                    print('\nDetected Import complete message in stdout')
                    return 0

            # read any new stderr lines
            try:
                el = next(it_err)
            except StopIteration:
                el = None
            if el:
                print('[STDERR]', el)

            time.sleep(0.2)
    except KeyboardInterrupt:
        print('\nMonitor interrupted by user')
        return 2


if __name__ == '__main__':
    raise SystemExit(monitor())
