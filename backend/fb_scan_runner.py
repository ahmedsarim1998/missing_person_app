"""
Standalone periodic Facebook scan runner.

Run this in its OWN terminal (not inside app.py) -- the dev server runs with
debug=True, whose auto-reloader spawns two processes and would double-run any
in-process scheduler. Keeping the periodic scan here avoids that entirely.

Usage:
    python fb_scan_runner.py                # scrape live source every 10 min
    python fb_scan_runner.py --interval 300 # every 5 min
    python fb_scan_runner.py --once         # run a single scan and exit
    python fb_scan_runner.py --demo         # synthesize posts from active cases

Configure the live source via env vars before running:
    set FB_GROUP=<group id or url>
    set FB_COOKIES=<path to cookies.txt>
"""

import argparse
import time
from datetime import datetime

from app import create_app
import fb_service


def run_once(app, demo=False):
    with app.app_context():
        summary = fb_service.run_scan(app.config, demo=demo)
    ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"[{ts}] scan -> scanned={summary['scanned']} "
          f"matched={summary['matched']} updated={summary['updated']} "
          f"skipped={summary['skipped']}")
    return summary


def main():
    parser = argparse.ArgumentParser(description="Periodic Facebook scan runner")
    parser.add_argument('--interval', type=int, default=600,
                        help='seconds between scans (default 600)')
    parser.add_argument('--once', action='store_true', help='run a single scan and exit')
    parser.add_argument('--demo', action='store_true',
                        help='synthesize posts from active cases instead of scraping')
    args = parser.parse_args()

    app = create_app()

    if args.once:
        run_once(app, demo=args.demo)
        return

    print(f"Starting Facebook scan loop (every {args.interval}s). Ctrl+C to stop.")
    try:
        while True:
            run_once(app, demo=args.demo)
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == '__main__':
    main()
