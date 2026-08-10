"""Windowless DataCapture server entry point for the desktop shortcut."""
import os
import sys
import traceback

from datacapture import create_app

ROOT = os.path.dirname(os.path.abspath(__file__))
LOG_PATH = os.path.join(ROOT, "data", "launcher.log")


def log_error(exc):
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    with open(LOG_PATH, "a", encoding="utf-8") as fh:
        fh.write("\n--- DataCapture launch error ---\n")
        fh.write("".join(traceback.format_exception(exc)))


def main():
    try:
        app = create_app()
        try:
            from waitress import serve
            serve(app, host="127.0.0.1", port=8710, threads=8)
        except ImportError:
            app.run(host="127.0.0.1", port=8710, debug=False)
    except Exception as exc:  # keep windowless failures discoverable
        log_error(exc)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
