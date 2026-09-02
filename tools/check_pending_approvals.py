#!/usr/bin/env python3
"""CLI to notify a human that pipeline runs are waiting for approval.

This is a notification tool, not a pass/fail check: a run sitting at
HUMAN_APPROVAL is the pipeline working as designed (see
modules/pipeline_stages.py), not an error condition. It always exits 0.

Usage:
  python tools/check_pending_approvals.py

Configuration (all optional — with nothing set, this still prints to stdout
and logs via the always-on `log` channel):
  SLACK_WEBHOOK_URL   Post the summary to this Slack incoming webhook.

Wiring this into a schedule (a new GitHub Actions workflow, or a step added
to an existing one) is a deliberate follow-up decision for the repo owner —
not done by this script or by adding it.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from modules.notifier import Notifier, build_pending_approval_summary


def main() -> int:
    summary = build_pending_approval_summary()

    if not summary:
        print("No runs pending approval.")
        return 0

    print(summary)
    Notifier().send(summary)
    return 0


if __name__ == "__main__":
    sys.exit(main())
