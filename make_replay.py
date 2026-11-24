"""Record a word-by-word replay of the agent for the demo dashboard (demo/index.html).

    python make_replay.py                 # writes demo/replay.js from dev.jsonl

This is a presentation tool, not part of the agent: it runs the real agent through the real
evaluator, then (for display only) counts how many catalogue rows match the agent's filters
after each word.  Those display lookups are not agent searches and never affect a score.
"""
import argparse
import json
from pathlib import Path

import evaluate
from my_agent import Agent
from search import load_catalogue, search

HERE = Path(__file__).resolve().parent
FIELDS = ("title", "brand", "colour", "size", "price")
SHELF = 6                                   # product cards the dashboard shows at once


class Recorder(Agent):
    """The real agent, plus a log of what it reported after every word."""

    def start(self, request_id):
        super().start(request_id)
        self.steps = []

    def observe(self, word):
        out = super().observe(word)
        self.steps.append({"word": word, "filters": out["filters"], "commit": out.get("commit")})
        return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=str(HERE / "dev.jsonl"))
    ap.add_argument("--out", default=str(HERE / "demo" / "replay.js"))
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    requests = [json.loads(line) for line in open(args.data, encoding="utf-8") if line.strip()]
    requests = requests[:args.limit] if args.limit else requests

    tools = evaluate.Tools()
    agent = Recorder(tools)
    by_id = {p["product_id"]: p for p in load_catalogue()}
    products, replay = {}, []
    for req in requests:
        tools.searches = 0
        agent.start(req["id"])
        commits, current = [], None
        for t, word in enumerate(req["words"], 1):
            out = agent.observe(word)
            if out.get("commit") and out["commit"] != current:
                current = out["commit"]
                commits.append((t, current))
        final = agent.finish() or current
        result = evaluate.score_one(req, commits, final, tools.searches, agent.reading.filters)

        for step in agent.steps:                       # display-only: how many items still match
            active = {k: v for k, v in step["filters"].items() if v is not None}
            hits = search("", active, k=100000) if active else []
            step["matches"] = len(hits)
            step["shelf"] = [h["product_id"] for h in hits[:SHELF]]
        for pid in {h for step in agent.steps for h in step["shelf"]} | {final, req["target"]}:
            if pid in by_id:
                products[pid] = {k: by_id[pid][k] for k in FIELDS}
        replay.append({"id": req["id"], "text": req["text"], "tags": req["tags"], "target": req["target"],
                       "final": final, "correct": result["correct"], "commit_at": commits[0][0] if commits else None,
                       "score": round(result["score"] * 100, 1), "searches": result["searches"],
                       "steps": agent.steps})

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write("window.REPLAY = " + json.dumps({"requests": replay, "products": products},
                                                 ensure_ascii=False, separators=(",", ":")) + ";\n")
    print(f"wrote {args.out}: {len(replay)} requests, {len(products)} products")


if __name__ == "__main__":
    main()
