"""
Reddit scanner — pulls posts via Reddit's official OAuth API and feeds them
through the same analysis pipeline as the Facebook analyzer (name match ->
location extraction -> case update / sighting).

Why OAuth and not plain scraping: Reddit (like Facebook) now blocks
unauthenticated `.json` scraping from servers, returning an HTML wall. The
official app-only OAuth flow (client_credentials) gives reliable read access to
public search with just a free client id/secret — no user account needed.

Setup (one-time, free):
  1. https://www.reddit.com/prefs/apps -> "create app" -> type "script" or "web app".
  2. Copy the client id (under the app name) and the secret.
  3. Set env vars REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET (and optionally
     REDDIT_USER_AGENT).
"""

import os
import time

import requests

_TOKEN_URL = "https://www.reddit.com/api/v1/access_token"
_API_BASE = "https://oauth.reddit.com"

_token_cache = {"token": None, "exp": 0.0}


def _user_agent():
    return os.environ.get("REDDIT_USER_AGENT", "locaite-missing-person-scanner/1.0")


def is_configured():
    return bool(os.environ.get("REDDIT_CLIENT_ID") and os.environ.get("REDDIT_CLIENT_SECRET"))


def _get_token():
    """App-only OAuth token (client_credentials), cached until shortly before expiry."""
    now = time.time()
    if _token_cache["token"] and now < _token_cache["exp"] - 30:
        return _token_cache["token"]

    cid = os.environ.get("REDDIT_CLIENT_ID")
    secret = os.environ.get("REDDIT_CLIENT_SECRET")
    if not cid or not secret:
        raise RuntimeError(
            "Reddit is not configured. Set REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET "
            "(create a free app at reddit.com/prefs/apps)."
        )

    resp = requests.post(
        _TOKEN_URL,
        auth=(cid, secret),
        data={"grant_type": "client_credentials"},
        headers={"User-Agent": _user_agent()},
        timeout=15,
    )
    if resp.status_code == 401:
        raise RuntimeError("Reddit rejected the client id/secret (401). Double-check both values.")
    resp.raise_for_status()
    data = resp.json()
    token = data.get("access_token")
    if not token:
        raise RuntimeError("Reddit did not return an access token: %s" % data)
    _token_cache["token"] = token
    _token_cache["exp"] = now + float(data.get("expires_in", 3600))
    return token


def fetch_reddit_posts(query, limit=25, subreddit=None):
    """Search Reddit for `query` and return posts as {post_id, text, post_url}.

    If `subreddit` is given, the search is restricted to it.
    """
    token = _get_token()
    headers = {"Authorization": "bearer " + token, "User-Agent": _user_agent()}
    limit = max(1, min(int(limit or 25), 100))

    if subreddit:
        url = "%s/r/%s/search" % (_API_BASE, subreddit.strip().lstrip("r/"))
        params = {"q": query, "restrict_sr": 1, "limit": limit, "sort": "new", "raw_json": 1}
    else:
        url = "%s/search" % _API_BASE
        params = {"q": query, "limit": limit, "sort": "new", "raw_json": 1}

    resp = requests.get(url, headers=headers, params=params, timeout=20)
    resp.raise_for_status()
    posts = []
    for child in resp.json().get("data", {}).get("children", []):
        d = child.get("data", {})
        text = (d.get("title", "") + "\n" + (d.get("selftext") or "")).strip()
        posts.append({
            "post_id": "reddit-" + str(d.get("id", "")),
            "text": text,
            "post_url": "https://www.reddit.com" + d.get("permalink", ""),
        })
    return posts
