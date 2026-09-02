"""Fact-Checking Engine — independent second pass over a script's claims.

*** ADVISORY ONLY — THIS ENGINE DOES NOT, AND MUST NEVER, REPLACE THE HUMAN ***
*** APPROVAL GATE.                                                          ***

This project's pipeline is:

    Topic -> Research -> Script -> Fact Check -> Final Human Approval -> Publish

This module implements the "Fact Check" stage. Its entire job is to FEED the
Final Human Approval stage with an independent, machine-generated opinion on
each claim so a human reviewer has something concrete to check. It has no
authority to approve, clear, or wave a script through to publish, and nothing
in this codebase should ever be wired to skip Final Human Approval based on
this engine's output alone — no matter how confident every verdict looks.

Concretely, that shows up in the code as three defaults that always err
toward "make a human look at this":

  1. Every claim whose verdict is not the highest-confidence
     "likely_accurate" defaults `requires_human_review=True`. This flag is
     never taken from the model's own output — it is always computed here,
     from the validated verdict, so a model cannot talk its way past review.
  2. Any verdict string the model returns that isn't one of the three known
     values is clamped down to "unverifiable" (never silently treated as
     "likely_accurate").
  3. Any parsing failure, malformed JSON, or a batch that can't be resolved
     even after a retry produces the safe-default sentinel:
     verdict="unverifiable", requires_human_review=True. It never defaults to
     "accurate" just because the model's response couldn't be understood.

Input contract
--------------
`fact_check_claims` takes a plain `list[str]` of claim strings. This is a
deliberate, loose-coupling choice: this module does not import any claim
dataclass or extraction logic from another module (e.g. a future
`research_engine` or `script_engine` claim-extraction helper), since those may
live on sibling branches that don't exist in this checkout. Wiring this engine
into the rest of the pipeline — extracting claims out of a generated script,
and gating the Final Human Approval UI on these results — is a follow-up, not
part of this module.
"""

import json
import logging
import re
from dataclasses import dataclass

from config import GEMINI_MODEL
from modules.gemini_client import generate_with_retry, make_client

logger = logging.getLogger(__name__)

# Gemini is called once per batch of claims. A bigger batch means fewer
# requests (cheaper, faster, fewer chances to hit a rate limit) but a bigger
# risk that a very long claim list gets truncated by the model's output
# limit or that the model loses track of an item in the middle of a huge
# list. 30 mirrors the batch sizes used elsewhere in this codebase for
# similar bulk-JSON Gemini calls (see script_engine's per-section keyword
# batching) as a reasonable middle ground; tune via this constant if claims
# turn out to run much longer or shorter than expected.
MAX_BATCH_SIZE = 30

# The only verdicts this engine will ever record. Anything else the model
# returns is clamped to "unverifiable" — see module docstring point 2.
VALID_VERDICTS = {"likely_accurate", "likely_inaccurate", "unverifiable"}

SAFE_DEFAULT_VERDICT = "unverifiable"
SAFE_DEFAULT_REASONING = (
    "Automated fact-check could not produce a resolvable verdict for this "
    "claim (parsing failure or unresolved batch after retry) — defaulting "
    "to the safe sentinel. Requires human review."
)

FACT_CHECK_SYSTEM_PROMPT = """
You are an independent fact-checking assistant reviewing claims that will be
shown to a human reviewer before anything is published. You are NOT the final
decision-maker — a human always reviews your output afterward. Your job is to
give your best independent assessment of each claim's likely factual accuracy,
plus a brief, concrete reason.

For EACH claim, decide one of exactly three verdicts:
  "likely_accurate"   — you are confident the claim is factually correct.
  "likely_inaccurate" — you believe the claim is false, misleading, or
                         exaggerated.
  "unverifiable"       — you cannot confidently assess the claim (too vague,
                         no reliable way to check, contradictory evidence,
                         outside your knowledge, etc.). Use this whenever you
                         are not confident — do not guess "likely_accurate".

Input is a JSON object: {"claims": ["claim text 0", "claim text 1", ...]}
where the array index of each claim is its identity.

Return ONLY a JSON object with this EXACT schema, with one entry per input
claim, using the SAME index as the input array (0-based) — every index from 0
to N-1 must appear exactly once, where N is the number of input claims:

{
  "results": [
    {"index": 0, "verdict": "likely_accurate", "reasoning": "Brief reason."},
    {"index": 1, "verdict": "unverifiable", "reasoning": "Brief reason."}
  ]
}

Do not omit any index. Do not add extra indices. Do not merge claims. Do not
wrap the JSON in markdown code fences.
"""


@dataclass
class FactCheckResult:
    """A single claim's independent fact-check verdict.

    `requires_human_review` is ALWAYS computed from `verdict` by this module
    (True for anything other than "likely_accurate") — it is never taken
    directly from the model's response. See the module docstring. Build
    instances through `_make_result`/`_safe_default` below rather than
    constructing this directly, so that invariant can't be bypassed.
    """

    claim: str
    verdict: str
    reasoning: str
    requires_human_review: bool


def _make_result(claim: str, verdict: str, reasoning: str) -> FactCheckResult:
    """Build a FactCheckResult, always computing requires_human_review here."""
    if verdict not in VALID_VERDICTS:
        verdict = "unverifiable"
    return FactCheckResult(
        claim=claim,
        verdict=verdict,
        reasoning=reasoning,
        requires_human_review=(verdict != "likely_accurate"),
    )


def _safe_default(claim: str) -> FactCheckResult:
    """The sentinel used whenever a claim's verdict can't be resolved."""
    return _make_result(claim, SAFE_DEFAULT_VERDICT, SAFE_DEFAULT_REASONING)


def _build_prompt(batch: list[str]) -> str:
    """Build the user prompt, JSON-encoding claims into the data section.

    Claims may ultimately come from a generated script or scraped text this
    module doesn't fully control, so they are never string-interpolated
    loose into the prompt — they go through json.dumps, same defensive
    pattern used by other batched-Gemini modules in this codebase.
    """
    payload = json.dumps({"claims": list(batch)}, ensure_ascii=False)
    return (
        "Fact-check the following claims. Respond with the JSON schema "
        "described in your instructions, one result per claim, indexed "
        "exactly as given below.\n\n"
        f"{payload}"
    )


def _extract_json(text: str) -> dict | None:
    """Parse Gemini's response text as JSON, tolerating code fences.

    Returns None (never raises) on any parsing failure — callers treat that
    as "malformed response" and fall into the split-and-retry / safe-default
    path rather than propagating an exception.
    """
    if not text:
        return None
    cleaned = re.sub(r"^```(?:json)?\s*", "", text.strip(), flags=re.MULTILINE)
    cleaned = re.sub(r"\s*```$", "", cleaned.strip(), flags=re.MULTILINE)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]+\}", cleaned)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                return None
        return None


def _parse_batch_response(text: str, batch_len: int) -> dict[int, dict] | None:
    """Validate the model's JSON against the expected index set.

    Returns a dict of index -> {"verdict", "reasoning"} only when every
    index 0..batch_len-1 is present exactly once. Otherwise returns None,
    which the caller treats as "mismatched/missing indices" and routes into
    the split-and-retry path.
    """
    data = _extract_json(text)
    if not isinstance(data, dict):
        return None
    results = data.get("results")
    if not isinstance(results, list):
        return None

    by_index: dict[int, dict] = {}
    for item in results:
        if not isinstance(item, dict):
            continue
        idx = item.get("index")
        if not isinstance(idx, int):
            continue
        if idx in by_index:
            continue  # duplicate index — leaves a gap, caught below
        by_index[idx] = item

    expected = set(range(batch_len))
    if set(by_index.keys()) != expected:
        return None
    return by_index


def _check_batch(client, batch: list[str], allow_split_retry: bool = True
                  ) -> list[FactCheckResult]:
    """Fact-check one batch of claims, with the split-and-retry fallback.

    On a clean, fully-indexed response, builds results directly. On a
    malformed response or one with mismatched/missing indices, splits the
    batch in half and retries each half once (`allow_split_retry=False` on
    the recursive calls, so this happens at most one level deep). Any claim
    still unresolved after that gets the safe-default sentinel rather than
    raising.
    """
    prompt = _build_prompt(batch)
    response = generate_with_retry(client, GEMINI_MODEL, prompt)
    text = getattr(response, "text", "") or ""

    by_index = _parse_batch_response(text, len(batch))

    if by_index is not None:
        results = []
        for i, claim in enumerate(batch):
            item = by_index[i]
            verdict = item.get("verdict")
            reasoning = str(item.get("reasoning", ""))
            results.append(_make_result(claim, verdict, reasoning))
        return results

    logger.warning(
        "Fact-checker got a malformed/mismatched response for a batch of "
        "%d claim(s)%s.",
        len(batch),
        " — splitting and retrying" if allow_split_retry and len(batch) > 1
        else " — no more retries left, using safe defaults",
    )

    if allow_split_retry and len(batch) > 1:
        mid = len(batch) // 2
        left = _check_batch(client, batch[:mid], allow_split_retry=False)
        right = _check_batch(client, batch[mid:], allow_split_retry=False)
        return left + right

    return [_safe_default(claim) for claim in batch]


def fact_check_claims(claims: list[str]) -> list[FactCheckResult]:
    """Independently assess each claim's likely factual accuracy.

    Batches `claims` into chunks of at most MAX_BATCH_SIZE, calls Gemini once
    per batch via `generate_with_retry`, and parses the structured JSON
    response into `FactCheckResult`s. See the module docstring: this is an
    advisory pass that feeds the human-approval gate — it never decides
    anything on its own.

    Returns results in the same order as `claims`. An empty input returns an
    empty list without making any API call.
    """
    if not claims:
        return []

    client = make_client()
    results: list[FactCheckResult] = []
    for start in range(0, len(claims), MAX_BATCH_SIZE):
        batch = claims[start:start + MAX_BATCH_SIZE]
        results.extend(_check_batch(client, batch))
    return results
