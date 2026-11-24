"""Anticipatory-commerce agent: reads a shopping request word by word, commits only when safe.

    python evaluate.py --agent my_agent.py --log dev_log.jsonl

How it works (details in ARCHITECTURE.md):

1. Every word re-reads the whole request with `nlu.read` (cheap: a request is ~15 words).
   The reading is a set of filters; the last mention of a slot wins, which handles corrections
   and late constraints without special cases.
2. The catalogue is a remote store: products are only ever looked up through counted searches,
   and a search is only made when the reading is *worth* checking, and never twice for the
   same filters.
3. An early commit needs all of: a stable reading, no sign the shopper is about to change
   their mind, and a search that returns exactly one product.  A wrong commit costs more than
   two correct early ones earn, so every rule fails closed: when unsure, wait for `finish()`.
"""
from nlu import CORRECTION_WORDS, Lexicon, SLOTS, normalise, read
from rezolve import RezolveSearch
from search import load_catalogue

# ---- early-commit policy (tuned on dev with zero wrong commits; see ARCHITECTURE.md) --------
MIN_SLOTS = 3          # do not even search before this many slots are filled
STABLE_WORDS = 2       # the reading must have been unchanged for this many words
WRAP_UP = {"please", "thanks", "thank", "chahiye", "dikhao", "milega", "hai"}   # the request sounds finished
# "...for my dad", "as a gift", "need it this week": the shopper has moved on from describing the product.
TAIL_LEAD = {"for", "as", "need"}
TAIL_NEXT = {"my", "a", "an", "the", "it", "this", "office", "gym", "wedding", "gift", "dad", "brother",
             "mom", "sister", "friend", "party", "work"}
HEDGES = CORRECTION_WORDS | {"also", "aur", "and", "oh", "one", "more", "ek"}
RELAX_ORDER = ("max_price", "size", "brand", "colour", "category")   # what to drop if nothing matches


class Agent:
    def __init__(self, tools):
        self.tools = tools
        self.lexicon = Lexicon(load_catalogue())     # vocabulary only: never used to find products
        self.rezolve = RezolveSearch(tools)          # optional Rezolve Labs fallback (off without keys)

    def start(self, request_id):
        self.words = []
        self.reading = None
        self.cache = {}           # filters -> search hits, so equal filters are never searched twice
        self.committed = None

    # ------------------------------------------------------------------ streaming
    def observe(self, word):
        self.words.append(word)
        self.reading = read(self.words, self.lexicon)
        out = {"filters": dict(self.reading.filters), "confidence": self._confidence()}
        if self.committed is None and self._safe_to_commit():
            hits = self._lookup(self.reading.filters)
            if len(hits) == 1:
                self.committed = hits[0]["product_id"]
                out["commit"] = self.committed
        return out

    def _confidence(self):
        return round(self.reading.filled() / len(SLOTS), 2)

    def _safe_to_commit(self):
        r = self.reading
        n = len(self.words)
        if r.filled() < MIN_SLOTS or r.filters["category"] is None:
            return False
        if n - 1 - r.last_change() < STABLE_WORDS:           # something changed a moment ago
            return False
        tail = [normalise(w) for w in self.words[r.last_change() + 1:]]
        if any(t in HEDGES for t in tail[-3:]):               # "...no wait", "oh, and", "or rather"
            return False
        return self._sounds_finished(tail)

    @staticmethod
    def _sounds_finished(tail):
        """A polite wrap-up word, or a purpose phrase ("for the gym") after the last filter."""
        return (any(t in WRAP_UP for t in tail)
                or any(a in TAIL_LEAD and b in TAIL_NEXT for a, b in zip(tail, tail[1:])))

    # ------------------------------------------------------------------ searching
    def _lookup(self, filters):
        """Counted search for `filters`; identical filters are answered from the cache."""
        key = tuple(sorted((k, v) for k, v in filters.items() if v is not None))
        if key not in self.cache:
            self.cache[key] = self.tools.search(" ".join(self.words), dict(key), k=2)
        return self.cache[key]

    def finish(self):
        filters = dict(self.reading.filters) if self.reading else {}
        if filters.get("category") is None and self.words:       # nothing to filter on: ask Labs
            filters["category"] = self.rezolve.category_guess(" ".join(self.words))
        for drop in (None,) + RELAX_ORDER:                    # relax only if nothing matches
            filters.pop(drop, None)
            hits = self._lookup(filters)
            if hits:
                return hits[0]["product_id"]
        return None
