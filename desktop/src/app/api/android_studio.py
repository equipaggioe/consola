"""The page where Google publishes Android's command-line tools."""

from app.api import http

PAGE = "https://developer.android.com/studio#command-line-tools-only"
REPOSITORY = "https://dl.google.com/android/repository/"


def page() -> str:
    """Return the page's HTML, or raise `OSError`."""
    answer = http.request(PAGE, headers={"User-Agent": "Mozilla/5.0"}, timeout=60)
    return answer.decode("utf-8", errors="replace")
