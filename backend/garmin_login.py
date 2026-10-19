"""One-time Garmin Connect login for Stride.

Run from the backend folder:
    venv/bin/python garmin_login.py

You type your Garmin email + password (and MFA code if you have 2FA on) here in
your own terminal. Only the resulting session tokens are saved — to
backend/.garmin/garmin_tokens.json (git-ignored). Your password is not stored.
Re-run this if Stride ever says the Garmin session expired.
"""

import getpass
import os
import sys

from app.config import settings
from app.services.garmin import TOKEN_FILE, token_dir


def main():
    from garminconnect import Garmin

    path = token_dir()
    path.mkdir(parents=True, exist_ok=True)
    os.chmod(path, 0o700)

    print("Stride — connect Garmin Connect")
    email = input("Garmin email: ").strip()
    password = getpass.getpass("Garmin password (hidden): ")

    client = Garmin(email, password, prompt_mfa=lambda: input("Garmin MFA code (check email/app): ").strip())
    try:
        client.login(str(path))
    except Exception as e:
        print(f"\nLogin failed: {e}")
        print("Double-check your email/password. If Garmin rate-limited you (429), wait ~15 minutes and retry.")
        sys.exit(1)

    token_file = path / TOKEN_FILE
    if not token_file.exists():
        client.client.dump(str(path))
    os.chmod(token_file, 0o600)

    try:
        name = client.get_full_name()
    except Exception:
        name = email
    print(f"\nConnected as {name}. Tokens saved to {token_file}")
    print(f"Stride will now auto-sync every {settings.garmin_poll_minutes} min while the backend is running.")


if __name__ == "__main__":
    main()
