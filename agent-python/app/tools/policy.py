"""Small reproducible TF-IDF vector index. Sources are data, never instructions."""

import math
import os
import re
from collections import Counter
from pathlib import Path

STOP = {
    "the",
    "a",
    "an",
    "and",
    "or",
    "for",
    "to",
    "in",
    "of",
    "i",
    "me",
    "my",
    "what",
    "is",
    "are",
    "please",
    "policy",
    "policies",
    "about",
    "how",
    "do",
}


def terms(text):
    aliases = {
        "onboard": "onboarding",
        "requirements": "onboarding",
        "start": "onboarding",
        "monday": "onboarding",
        "equipment": "monitor",
        "booking": "desks",
        "desk": "desks",
        "room": "rooms",
        "hours": "hybrid",
    }
    return [
        aliases.get(t, t) for t in re.findall(r"[a-z]+", text.lower()) if t not in STOP
    ]


class PolicyIndex:
    def __init__(self, path=None):
        path = Path(
            path
            or os.getenv(
                "POLICY_DIR", Path(__file__).resolve().parents[3] / "policy-data"
            )
        )
        self.docs = [
            {
                "source": p.name,
                "title": p.read_text().splitlines()[0].lstrip("# "),
                "text": p.read_text(),
            }
            for p in sorted(path.glob("*.md"))
        ]
        self.counts = [Counter(terms(d["text"])) for d in self.docs]
        self.idf = {
            t: math.log((1 + len(self.docs)) / (1 + sum(t in c for c in self.counts)))
            + 1
            for c in self.counts
            for t in c
        }

    def search(self, query):
        q = Counter(terms(query))
        qv = {t: n * self.idf.get(t, 0) for t, n in q.items()}
        qnorm = math.sqrt(sum(v * v for v in qv.values())) or 1
        matches = []
        for d, c in zip(self.docs, self.counts):
            v = {t: n * self.idf[t] for t, n in c.items()}
            norm = math.sqrt(sum(x * x for x in v.values())) or 1
            score = sum(qv.get(t, 0) * x for t, x in v.items()) / qnorm / norm
            if score > 0.035:
                matches.append({**d, "score": round(score, 4)})
        return sorted(matches, key=lambda d: d["score"], reverse=True)[:3]
