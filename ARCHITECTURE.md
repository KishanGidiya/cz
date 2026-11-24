# Architecture note

Standard-library Python 3.9+, no installs. Run it:

```
python evaluate.py --agent my_agent.py --log dev_log.jsonl     # score + per-request log
python -m unittest tests.test_nlu                              # reader tests on unseen wording
python make_replay.py && python -m http.server -d demo 8765    # split-view replay dashboard
```

## Files

| File | Role |
|---|---|
| `my_agent.py` | The `Agent`: streaming loop, early-commit policy, counted searches |
| `nlu.py` | Reads words into filters: number words (English and Hindi), synonyms, sizes, brands |
| `rezolve.py` | Optional Rezolve Labs fallback (off unless keys are set; see below) |
| `tests/test_nlu.py` | Tests on phrasings that are not in `dev.jsonl` |
| `make_replay.py`, `demo/` | Word-by-word replay dashboard (React 18.3.1 from cdnjs, no build step) |
| `dev_log.jsonl` | Output of `evaluate.py --log` on `dev.jsonl` |

## How it decides

1. **Read.** After every word the whole request is re-read (`nlu.read`). Each mention of a slot
   (category, colour, size, brand, max price) is recorded in order and the **last mention wins**.
   One rule covers corrections ("black, no wait, white"), changed minds ("Horavo, matlab
   Tikkra") and late constraints ("oh, and in blue"). A number is a size only next to a size word
   (or right after a correction word), otherwise a price; number runs stop at commas and full stops.
2. **Search sparingly.** The catalogue is only read at start-up to build the vocabulary. Products are
   found only through `tools.search`. A search happens only when the commit rules below already
   pass, and identical filters are never searched twice. Result: 1.00 searches per request.
3. **Commit only when safe.** All of: at least 3 slots filled including category; reading
   unchanged for 2 words; no "wait / actually / or / oh / also" in the last 3 words; the shopper
   sounds finished ("please", "thanks", "for my dad", "as a gift", "need it this week"); and the
   search returns exactly one product. Anything else waits for `finish()`.
4. **Finish.** Final search with the full reading. If it matches nothing, drop slots one at a time
   (price, size, brand, colour, category) rather than return nothing.

## Why so cautious

A wrong commit costs 1.0 and wipes out the 0.4 for a right answer; an early commit earns at most
0.6 × the share of the request left. On dev, looser rules (commit after 1-2 stable words, no
wrap-up needed) scored up to 43 but made 2-7 wrong commits, which will not hold on a different
300 requests. The wrap-up rule gives 0 wrong commits on dev and fails closed on wording it has
never seen. Best possible earliness on dev is 16.3%; this agent reaches 2.5%.

## Results on `dev.jsonl` (baseline: 20.0, accuracy 0.527)

Score **41.5**, accuracy 1.000, wrong commits 0, searches 1.00 per request, 0.06 ms per word.

Caveat: the reader was developed while looking at `dev.jsonl`, so these numbers are optimistic for
the hidden set. `tests/test_nlu.py` covers phrasings outside dev (charcoal, "das number",
"pair of denims", ₹ amounts) but I have not measured a true held-out score.

## Rezolve Labs capabilities used

- **Semantic product search**: wired as an optional fallback in `rezolve.py`, used only when no
  category could be read from the request. Each call is reported with `tools.record_search()`.
  **Status: not used in the dev results above** (no Labs keys were available, so it is off) **and its
  request format is an unverified assumption** until checked against your Labs workspace.
- Managed knowledge retrieval, Conversational product finder, Live transcription: not used.

If the competition requires at least one Labs capability, set `REZOLVE_SEARCH_URL` and
`REZOLVE_API_KEY`, confirm the response shape in `rezolve._parse`, and re-run the evaluation so the
log reflects it. Do not state in a submission that Labs was used until that has actually run.
