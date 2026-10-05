"""Golden-set evaluation runner (PRD Sections 3 and 10). STUB until M2.

M1: validates eval/golden.jsonl and prints the metric names with "n/a".
M2: runs every question through the agent (FakeLLM or the real provider behind a flag)
and fills in the numbers. Standard library only, so `make eval` runs anywhere.

Usage: python eval/run.py [path/to/golden.jsonl]
"""

import json
import sys
from pathlib import Path

GOLDEN = Path(__file__).with_name("golden.jsonl")
REQUIRED_FIELDS = ("question", "expected_facts", "expected_tool", "should_fallback")

# Metric name -> target, from PRD Section 3 (success metrics).
METRICS: list[tuple[str, str]] = [
    ("Correct answers on golden set", ">= 85%"),
    ("Correct fallback on questions with no data", ">= 90%"),
    ("Answers carrying a valid source (excl. small talk)", "100%"),
    ("Invented phone numbers, fees or dates", "0"),
    ("Exact-data answers matching tables", "100%"),
    ("First token latency p95 (text, server awake)", "< 4 s"),
    ("Voice message round trip p95 (server awake)", "< 8 s"),
]


def load_items(path: Path) -> list[dict[str, object]]:
    items: list[dict[str, object]] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        item = json.loads(line)
        missing = [field for field in REQUIRED_FIELDS if field not in item]
        if missing:
            raise ValueError(f"{path.name}:{number} missing fields: {', '.join(missing)}")
        items.append(item)
    return items


def main(argv: list[str]) -> int:
    path = Path(argv[1]) if len(argv) > 1 else GOLDEN
    items = load_items(path)
    fallback_items = sum(1 for item in items if item["should_fallback"])

    print(f"Golden set: {path} ({len(items)} items, {fallback_items} should fall back)")
    print("Agent not built yet (M2): metrics are placeholders.\n")
    width = max(len(name) for name, _ in METRICS)
    print(f"{'Metric':<{width}}  {'Target':<8}  Result")
    print(f"{'-' * width}  {'-' * 8}  ------")
    for name, target in METRICS:
        print(f"{name:<{width}}  {target:<8}  n/a")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
