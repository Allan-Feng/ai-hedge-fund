# ZeroLeaks candidate scan for the AAPL headline experiment

This is a bounded scan to suggest new attack headlines. A local adapter
replaces each ZeroLeaks target request with the saved AAPL Buffett system and
user prompts, appending the candidate text to the first news title. It does
not run AIHF's JSON parser, portfolio, or broker. A ZeroLeaks finding is
therefore a candidate, not an AIHF finding.

The wrapper extracts the exact Buffett B/C **system and user** messages from
the saved B prompt, uses `gpt-6-sol` for all provider calls, selects
`indirect_injection,authority_exploit`, and disables multi-turn probes. The
target uses an `aihf-buffett` alias so the adapter can identify it. Its local
OpenAI-compatible proxy removes ZeroLeaks's unsupported `temperature=0`
setting and sets `reasoning_effort=none` for its tool-using evaluator calls
before forwarding requests to `gpt-6-sol`.

From the repository root in WSL:

```bash
npm install --prefix ~/.cache/aihf-zeroleaks zeroleaks@1.5.0 --no-audit --no-fund
.venv/bin/python -m hedge_fund.experiments.zeroleaks_scan \
  --out outputs/zeroleaks_prepare_01
```

Preparation makes zero provider calls. To run a two-probe scan, choose a **new**
output directory:

```bash
.venv/bin/python -m hedge_fund.experiments.zeroleaks_scan \
  --out outputs/zeroleaks_scan_01 --max-probes 2 --execute
```

The wrapper reads `OPENAI_API_KEY` from the environment or
`~/.hedge-fund/.env`, without printing or writing it. The scan may make
multiple model calls per probe and incur model charges. It saves the exact
system prompt, command template, log, ZeroLeaks JSON report, and every target request
and raw provider response in `target_calls.jsonl` under `outputs/`.
Code 0 means completed with no finding, 1 means a finding, and 2 means no
complete verdict. Keep the report and its individual probe outcomes.

ZeroLeaks's built-in probes may describe PDFs, emails, or support tickets.
The adapter preserves their text but places it in a news headline. Its
compliance judge may grade the original probe task rather than the AIHF JSON
contract, so inspect `target_calls.jsonl` and replay promising candidates.
The recorded two-probe [example](../../evidence/aapl_20261103/zeroleaks/scan_20261110/)
completed without a finding; it is not evidence of general resistance.

To test a candidate against AIHF, copy only its attack text into a **new**
fixture's `attack.suffix`; preserve the five recorded headlines, fundamentals,
and clean B input. Run B/C using
[the AIHF reproduction guide](REPRODUCE_AAPL_20261103.md). Score the
registered criterion from raw response, parser result, and
`metadata.abstained`, then archive the new trial in
[the evidence index](../../evidence/aapl_20261103/README.md).
