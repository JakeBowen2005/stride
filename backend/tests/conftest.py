"""Point the app at a throwaway SQLite file *before* any app module is imported,
so API tests never touch the real stride.db and the Garmin poller stays off."""

import os
import tempfile

_tmp = tempfile.mkdtemp(prefix="stride-test-")
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}/test.db"
os.environ["GARMIN_POLL_MINUTES"] = "0"
os.environ["GARMIN_TOKENSTORE"] = os.path.join(_tmp, "garmin")
os.environ["ANTHROPIC_API_KEY"] = ""  # coach uses template responses
