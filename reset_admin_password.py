"""Reset a DataCapture user's password from the local machine."""
import argparse
import getpass
import sys

from datacapture import create_app
from datacapture.auth import hash_pw
from datacapture.db import audit, q, x


def list_users(data_dir=None):
    app = create_app(data_dir=data_dir)
    with app.app_context():
        return [dict(r) for r in q(
            "SELECT id, username, display_name, is_admin, active"
            " FROM users ORDER BY is_admin DESC, username"
        )]


def reset_password(username, password, data_dir=None):
    if len(password) < 8:
        return False, "Password must be at least 8 characters."
    app = create_app(data_dir=data_dir)
    with app.app_context():
        user = q("SELECT * FROM users WHERE username=?", (username,), one=True)
        if not user:
            return False, f"No user named '{username}' was found."
        x("UPDATE users SET password_hash=?, active=1 WHERE id=?",
          (hash_pw(password), user["id"]))
        audit("user.password_reset.local", details=username, username="local-cli")
    return True, f"Password reset for '{username}'."


def main():
    parser = argparse.ArgumentParser(
        description="Reset a DataCapture password in the local SQLite database."
    )
    parser.add_argument("username", nargs="?", help="Username to reset")
    parser.add_argument("--password", help="New password; omit for hidden prompt")
    parser.add_argument("--data-dir", help="Alternate data directory for tests")
    args = parser.parse_args()

    users = list_users(args.data_dir)
    if not users:
        print("No DataCapture users exist yet. Start the app and complete setup first.")
        return 1

    default = next((u["username"] for u in users if u["is_admin"]), users[0]["username"])
    username = args.username or input(f"Username to reset [{default}]: ").strip() or default

    if args.password is None:
        password = getpass.getpass("New password: ")
        confirm = getpass.getpass("Confirm password: ")
        if password != confirm:
            print("Passwords did not match.")
            return 1
    else:
        password = args.password

    ok, message = reset_password(username, password, args.data_dir)
    print(message)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
