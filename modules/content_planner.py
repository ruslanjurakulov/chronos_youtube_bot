"""Content Planner — a lightweight topic queue sitting *before* the real
approval pipeline even starts.

A prior audit of this project found that content planning / a content
calendar was entirely absent from the codebase: no file, no queue, no
calendar of any kind existed anywhere. This module fills that gap.

Where this sits relative to ``pipeline_stages.py``
----------------------------------------------------
``pipeline_stages.PipelineStateMachine`` enforces the *approval chain* for a
topic that has already been chosen and is being worked on: Topic -> Research
-> Script -> Fact Check -> Human Approval -> Publish. It answers "is this run
allowed to move to the next stage yet?".

This module answers a different, earlier question: "what topic should we
attempt next?" ``ContentPlanner`` is a simple FIFO queue of candidate topics
— things worth making a video about — collected from wherever they come
from (a manual add, a `ContentOpportunity` produced by
``content_opportunity.ContentOpportunityEngine``, a Gemini brainstorm pick,
etc.), each carrying a lightweight ``queued`` / ``published`` / ``skipped``
status. It is deliberately NOT a state machine — there is no enforced
sequence of stages here, just a durable list with dedup and a "give me the
next thing to work on" accessor. Once a topic is pulled off this queue, it
is expected to be handed to ``PipelineStateMachine.start_run()`` (or
equivalent) to go through the real approval chain; wiring that hand-off up
in ``topic_manager.py`` / ``main.py`` is a deliberate follow-up and is NOT
done here (see this module's PR description).

Decoupling from ``content_opportunity.ContentOpportunity``
------------------------------------------------------------
``enqueue_opportunity()`` accepts anything duck-typed with ``.topic``,
``.source``, and ``.rationale`` attributes. It deliberately does NOT import
the real ``ContentOpportunity`` dataclass, to avoid a hard dependency on a
sibling module the same way ``content_opportunity.py`` itself avoids
importing its own siblings' dataclasses (``VideoSnapshot``, ``DemandSignal``,
etc.) and instead works off plain dicts. This keeps the two modules
mergeable independently regardless of merge order.

Dedup scope — exact-string, queued-only (NOT semantic)
----------------------------------------------------------
``enqueue()`` refuses to create a second ``"queued"`` entry for a topic
string that already has a ``"queued"`` entry, using plain exact string
equality. This is intentionally NOT semantic/near-duplicate detection —
catching "The Fall of Rome" vs. "Rome's Collapse" as the same topic is a
job for ``modules/originality_engine.py``, which already does semantic
similarity checking via model2vec. That module needs a model load and
(depending on configuration) network access; making a topic *queue insert*
depend on that is a deliberate choice NOT made here. Wiring
``originality_engine`` in as a stronger pre-enqueue (or pre-publish) check
is an explicit follow-up, not part of this module.

Dedup only ever considers *currently-queued* entries, never
``"published"`` or ``"skipped"`` ones — a topic that was already published
(or skipped) must remain re-enqueue-able later (e.g. a yearly recurring
topic, or a topic worth retrying after being skipped for an unrelated
reason). Blocking re-enqueue forever after a single publish/skip is
explicitly NOT the intent.

PERSISTENCE NOTE: like ``pipeline_stages.py``, this module uses its own
minimal JSON-file store as a deliberate placeholder, not a new
``state_store`` table. Simple write-through (read on each call, write on
each mutation) is plenty at this project's scale. If/when the shared
``state_store`` module needs to take over storage duties project-wide, this
class's persistence can be swapped out behind its stable public API
(``enqueue``, ``enqueue_opportunity``, ``next_topic``, ``mark_published``,
``mark_skipped``, ``list_entries``) — mirroring the same swap already
flagged in ``pipeline_stages.py``.
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Union

from config import HISTORY_DIR

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class CalendarEntry:
    """One queued (or resolved) topic candidate in the content calendar."""

    entry_id: str
    topic: str
    added_at: str
    source: str
    rationale: str = ""
    status: str = "queued"  # "queued" | "published" | "skipped"

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "CalendarEntry":
        return CalendarEntry(
            entry_id=d["entry_id"],
            topic=d["topic"],
            added_at=d["added_at"],
            source=d.get("source", ""),
            rationale=d.get("rationale", ""),
            status=d.get("status", "queued"),
        )


class ContentPlanner:
    """A durable FIFO queue of candidate video topics awaiting a real run.

    Persistence is a simple write-through JSON file (read on each call,
    written on each mutation) — deliberately lightweight, mirroring the
    same choice (and the same "placeholder, not a new state_store table"
    caveat) made in ``pipeline_stages.PipelineStateMachine``. Fine at this
    project's scale (a handful of queued topics at a time, single process).
    """

    def __init__(self, store_path: Optional[Union[Path, str]] = None):
        self.store_path = (
            Path(store_path) if store_path is not None else (HISTORY_DIR / "content_calendar.json")
        )

    # -- storage -----------------------------------------------------

    def _load_all(self) -> dict:
        if not self.store_path.exists():
            return {}
        raw = self.store_path.read_text().strip()
        if not raw:
            return {}
        data = json.loads(raw)
        return {entry_id: CalendarEntry.from_dict(ed) for entry_id, ed in data.items()}

    def _save_all(self, entries: dict) -> None:
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        serializable = {entry_id: entry.to_dict() for entry_id, entry in entries.items()}
        self.store_path.write_text(json.dumps(serializable, indent=2, ensure_ascii=False))

    # -- public API ----------------------------------------------------

    def enqueue(self, topic: str, source: str = "manual", rationale: str = "") -> CalendarEntry:
        """Add `topic` to the queue with status="queued".

        Dedup is exact-string match against currently-``"queued"`` entries
        only (see module docstring for why this is not semantic, and why
        ``"published"``/``"skipped"`` entries never block re-enqueueing).
        If a matching queued entry already exists, that existing entry is
        returned unchanged instead of creating a duplicate.
        """
        entries = self._load_all()
        for entry in entries.values():
            if entry.topic == topic and entry.status == "queued":
                logger.info("Duplicate queued topic %r — reusing entry %s", topic, entry.entry_id)
                return entry

        entry_id = uuid.uuid4().hex[:12]
        entry = CalendarEntry(
            entry_id=entry_id,
            topic=topic,
            added_at=_now_iso(),
            source=source,
            rationale=rationale,
            status="queued",
        )
        entries[entry_id] = entry
        self._save_all(entries)
        return entry

    def enqueue_opportunity(self, opportunity) -> CalendarEntry:
        """Convenience wrapper around `enqueue()` for a ContentOpportunity-
        shaped object.

        Duck-typed: accepts anything with `.topic`, `.source`, and
        `.rationale` attributes. Does NOT import the real
        `content_opportunity.ContentOpportunity` dataclass — see module
        docstring.
        """
        return self.enqueue(
            topic=opportunity.topic,
            source=f"content_opportunity:{opportunity.source}",
            rationale=opportunity.rationale,
        )

    def next_topic(self) -> Optional[CalendarEntry]:
        """Return the oldest still-`"queued"` entry (FIFO by `added_at`), or
        None if the queue is empty. Peeking only — does not mutate status.
        """
        queued = [e for e in self._load_all().values() if e.status == "queued"]
        if not queued:
            return None
        return min(queued, key=lambda e: e.added_at)

    def mark_published(self, entry_id: str) -> CalendarEntry:
        """Mark `entry_id` as "published". Raises ValueError for an unknown id."""
        entries = self._load_all()
        entry = entries.get(entry_id)
        if entry is None:
            raise ValueError(f"No such calendar entry: {entry_id!r}")
        entry.status = "published"
        entries[entry_id] = entry
        self._save_all(entries)
        return entry

    def mark_skipped(self, entry_id: str, reason: str = "") -> CalendarEntry:
        """Mark `entry_id` as "skipped", appending `reason` (if given) to its
        rationale. Raises ValueError for an unknown id.
        """
        entries = self._load_all()
        entry = entries.get(entry_id)
        if entry is None:
            raise ValueError(f"No such calendar entry: {entry_id!r}")
        entry.status = "skipped"
        if reason:
            entry.rationale = f"{entry.rationale} [skipped: {reason}]".strip()
        entries[entry_id] = entry
        self._save_all(entries)
        return entry

    def list_entries(self, status: Optional[str] = None) -> list:
        """All entries, optionally filtered by `status`, oldest first."""
        entries = list(self._load_all().values())
        if status is not None:
            entries = [e for e in entries if e.status == status]
        entries.sort(key=lambda e: e.added_at)
        return entries
