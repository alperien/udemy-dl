#!/usr/bin/env python3
import curses
import sys

from .app import Application
from .utils import setup_logging

logger = None


def _main(stdscr):
    global logger
    logger = setup_logging()
    try:
        app = Application(stdscr)
        app.run()
    except KeyboardInterrupt:
        if logger:
            logger.info("User pressed Ctrl+C, exiting cleanly")
    except Exception as e:
        if logger:
            logger.exception(f"Unhandled exception: {e}")
        print(f"\nFatal error: {e}")
        print("Check downloader.log for details")
        sys.exit(1)


def run():
    curses.wrapper(_main)


if __name__ == "__main__":
    run()
