"""Replay every executed instruction attack in the AAPL evidence index on one model."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "hedge_fund/experiments/daily_news.py").exists())
INDEX = ROOT / "evidence/aapl_20261103/README.md"
FIXTURE_ROOT = INDEX.parent
RATES = {
    "gpt-4o-2024-08-06": (2.5, 10.0, 1.25),
    "gpt-4o-mini-2024-07-18": (0.15, 0.6, 0.075),
}


def indexed_attacks():
    section = INDEX.read_text(encoding="utf-8").split("## Executed instruction attacks", 1)[1].split("\n## ", 1)[0]
    attacks = []
    for line in section.splitlines():
        if not line.startswith("| ") or "[fixture](" not in line:
            continue
        label = line.split("| ")[1].strip()
        relative = re.search(r"\[fixture\]\(([^)]+)\)", line).group(1)
        path = FIXTURE_ROOT / relative
        fixture = json.loads(path.read_text(encoding="utf-8"))
        slug = re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")
        attacks.append({
            "label": label, "slug": slug, "fixture": str(path.relative_to(ROOT)),
            "fixture_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "expected_response": fixture["attack"]["expected_response"],
        })
    if len(attacks) != 11 or len({a["slug"] for a in attacks}) != 11:
        raise ValueError("Expected exactly 11 unique executed attacks in the index")
    return attacks


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", choices=RATES, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    attacks = indexed_attacks()
    (out / "batch_setup.json").write_text(
        json.dumps({"model": args.model, "execute": args.execute, "attacks": attacks,
                    "groups": ["B", "C"], "repeats": 1, "cache_policy": "independent",
                    "rates_usd_per_million": RATES[args.model]}, indent=2) + "\n",
        encoding="utf-8")
    summaries = []
    for i, attack in enumerate(attacks, 1):
        dest = out / attack["slug"]
        cmd = [
            sys.executable, "-m", "hedge_fund.experiments.daily_news", "run",
            "--fixtures", str((ROOT / attack["fixture"]).parent), "--out", str(dest),
            "--persona", "buffett", "--model", args.model, "--groups", "B", "C",
            "--repeats", "1", "--cache-policy", "independent",
        ]
        if args.execute:
            cmd += ["--execute", "--input-usd-per-million", str(RATES[args.model][0]),
                    "--output-usd-per-million", str(RATES[args.model][1]),
                    "--cached-usd-per-million", str(RATES[args.model][2])]
        print(f"{i}/{len(attacks)} {args.model}: {attack['label']}", flush=True)
        with (out / f"{attack['slug']}.log").open("w", encoding="utf-8") as log:
            result = subprocess.run(cmd, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, check=False)
        row = {"attack": attack["label"], "slug": attack["slug"], "exit_code": result.returncode}
        summary_path = dest / "summary.json"
        if summary_path.exists():
            row["summary"] = json.loads(summary_path.read_text(encoding="utf-8"))
        summaries.append(row)
        (out / "batch_summary.json").write_text(json.dumps(summaries, indent=2) + "\n", encoding="utf-8")
    if any(row["exit_code"] for row in summaries):
        raise SystemExit(1)


if __name__ == "__main__":
    main()

