"""DataCapture launcher.

Usage:
    python run.py                 # localhost only, opens your browser
    python run.py --host 0.0.0.0  # share on your clinic LAN
    python run.py --port 8710
"""
import argparse
import threading
import webbrowser

from datacapture import create_app


def main():
    ap = argparse.ArgumentParser(description="DataCapture standalone server")
    ap.add_argument("--host", default="127.0.0.1",
                    help="127.0.0.1 (private) or 0.0.0.0 (share on LAN)")
    ap.add_argument("--port", type=int, default=8710)
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args()

    app = create_app()
    url = f"http://{'localhost' if args.host == '127.0.0.1' else args.host}:{args.port}"
    print(f"\n  DataCapture is running at {url}")
    print("  Press Ctrl+C to stop. Your data lives in the data/ folder.\n")

    if not args.no_browser:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()

    try:
        from waitress import serve
        serve(app, host=args.host, port=args.port, threads=8)
    except ImportError:
        app.run(host=args.host, port=args.port, debug=False)


if __name__ == "__main__":
    main()
