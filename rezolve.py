"""Optional Rezolve Labs semantic product search, used only as a fallback.

Off by default.  It switches on when both environment variables are set (from your Labs account):

    REZOLVE_SEARCH_URL   the semantic-search endpoint of your Labs workspace
    REZOLVE_API_KEY      your key (never commit it)

The agent calls it in exactly one situation: the local reader found no *category* in the whole
request, so there is nothing to filter on.  The Labs result only supplies a category guess; the
product itself is still chosen by the counted local search.  Every call is reported with
`tools.record_search()`, has a 1.5 s timeout, and any failure just means "no help".

NOTE: the request/response shape below is an assumption (`POST {"query": ..., "top_k": n}` ->
`{"results": [{"category": ...}]}`).  Check it against the Labs docs for your workspace before
relying on it, and adjust `_parse`.  Not verified against the live service.
"""
import json
import os
import urllib.request

TIMEOUT_S = 1.5


class RezolveSearch:
    def __init__(self, tools, url=None, key=None):
        self.tools = tools
        self.url = url or os.environ.get("REZOLVE_SEARCH_URL")
        self.key = key or os.environ.get("REZOLVE_API_KEY")

    @property
    def enabled(self):
        return bool(self.url and self.key)

    def category_guess(self, text):
        """Most common category among the top results for `text`, or None."""
        if not self.enabled:
            return None
        self.tools.record_search(1)                       # one external call = one counted search
        try:
            req = urllib.request.Request(
                self.url, data=json.dumps({"query": text, "top_k": 5}).encode(),
                headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.key}"})
            with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
                return self._parse(json.load(resp))
        except Exception:                                  # network, timeout, bad JSON: just no help
            return None

    @staticmethod
    def _parse(payload):
        cats = [r.get("category", "").lower() for r in payload.get("results", []) if r.get("category")]
        return max(set(cats), key=cats.count) if cats else None
