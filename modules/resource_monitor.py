"""Memory instrumentation — so a killed run leaves a diagnosis behind.

Two production runs died mid-render with `exit 143` and "The runner has
received a shutdown signal". No traceback, no Python exception, nothing in the
log after "Starting render": the machine went away, the code did not fail.
Memory exhaustion is the leading explanation, and twice it has only been a
guess, because a killed process cannot report on itself afterwards.

So it reports on itself *beforehand*. The sampler writes a line every few
seconds while the render runs; whatever kills the process, the last line
written is the state just before it died, and the trajectory across lines says
whether memory was climbing toward the ceiling or sitting flat.

Everything here is best-effort and must never be the reason a render fails.
Every read is guarded, the sampler thread is a daemon, and on a platform
without /proc (Windows, macOS) it quietly does nothing rather than raising.
"""

import logging
import threading
from pathlib import Path

logger = logging.getLogger(__name__)

PROC_SELF_STATUS = Path("/proc/self/status")
PROC_MEMINFO = Path("/proc/meminfo")

# Long enough that the samples are cheap, short enough that a three-minute
# render still leaves a dozen of them behind.
DEFAULT_INTERVAL_SECONDS = 15.0


def _read_kb(path: Path, key: str) -> float | None:
    """The `key: N kB` field from a /proc file, in kB, or None.

    Returns None for every failure — missing file, unreadable, absent key,
    unparseable value — because a diagnostic that can raise is worse than no
    diagnostic at all.
    """
    try:
        text = path.read_text()
    except OSError:
        return None
    for line in text.splitlines():
        name, _, rest = line.partition(":")
        if name.strip() != key:
            continue
        parts = rest.split()
        if not parts:
            return None
        try:
            return float(parts[0])
        except ValueError:
            return None
    return None


def process_rss_mb(status_path: Path = PROC_SELF_STATUS) -> float | None:
    """Resident memory of this process, in MB."""
    kb = _read_kb(status_path, "VmRSS")
    return None if kb is None else kb / 1024


def system_memory_mb(meminfo_path: Path = PROC_MEMINFO) -> tuple[float | None, float | None]:
    """(total, available) system memory in MB — either may be None.

    `MemAvailable` rather than `MemFree`: free memory on a busy runner is
    always near zero because the page cache holds the rest, and available is
    the number that says how close the machine really is to the wall.
    """
    total = _read_kb(meminfo_path, "MemTotal")
    available = _read_kb(meminfo_path, "MemAvailable")
    return (
        None if total is None else total / 1024,
        None if available is None else available / 1024,
    )


def describe_usage(
    status_path: Path = PROC_SELF_STATUS,
    meminfo_path: Path = PROC_MEMINFO,
) -> str | None:
    """One line of memory state, or None where /proc is not available.

    Unknown values are named as unknown and never printed as 0 — a 0 here
    would read as "no memory used", which is the opposite of what it means.
    """
    rss = process_rss_mb(status_path)
    total, available = system_memory_mb(meminfo_path)
    if rss is None and total is None and available is None:
        return None
    rss_txt = "unknown" if rss is None else f"{rss:.0f} MB"
    if total is None and available is None:
        return f"process RSS {rss_txt}"
    avail_txt = "unknown" if available is None else f"{available:.0f} MB"
    total_txt = "unknown" if total is None else f"{total:.0f} MB"
    return (
        f"process RSS {rss_txt}; system {avail_txt} available of {total_txt}"
    )


def log_usage(label: str) -> None:
    """Log memory state at a named point, if it can be read."""
    line = describe_usage()
    if line is not None:
        logger.info("Memory at %s: %s", label, line)


class MemorySampler:
    """Log memory every `interval` seconds for the duration of a `with` block.

    Used around the render, which is the stage that has twice been killed.
    The thread is a daemon and every sample is guarded, so a failure to read
    /proc costs a missing log line and nothing else.
    """

    def __init__(self, label: str, interval: float = DEFAULT_INTERVAL_SECONDS):
        self.label = label
        self.interval = interval
        self.peak_rss_mb: float | None = None
        self.min_available_mb: float | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def sample(self) -> None:
        """Take and log one sample, updating the peak/floor. Never raises."""
        try:
            rss = process_rss_mb()
            _, available = system_memory_mb()
            if rss is not None:
                self.peak_rss_mb = rss if self.peak_rss_mb is None else max(self.peak_rss_mb, rss)
            if available is not None:
                self.min_available_mb = (
                    available if self.min_available_mb is None
                    else min(self.min_available_mb, available)
                )
            line = describe_usage()
            if line is not None:
                logger.info("Memory during %s: %s", self.label, line)
        except Exception:  # pragma: no cover - a diagnostic must not throw
            pass

    def _run(self) -> None:
        while not self._stop.wait(self.interval):
            self.sample()

    def __enter__(self) -> "MemorySampler":
        self.sample()  # a baseline, before anything the block does
        if describe_usage() is None:
            return self  # no /proc: stay silent rather than spawn a useless thread
        self._thread = threading.Thread(
            target=self._run, name=f"memory-sampler-{self.label}", daemon=True
        )
        self._thread.start()
        return self

    def __exit__(self, *exc_info) -> None:
        self._stop.set()
        thread, self._thread = self._thread, None
        if thread is not None:
            thread.join(timeout=self.interval + 1)
        self.sample()
        if self.peak_rss_mb is not None or self.min_available_mb is not None:
            peak = "unknown" if self.peak_rss_mb is None else f"{self.peak_rss_mb:.0f} MB"
            floor = (
                "unknown" if self.min_available_mb is None
                else f"{self.min_available_mb:.0f} MB"
            )
            logger.info(
                "Memory summary for %s: peak process RSS %s; least system memory "
                "available %s", self.label, peak, floor,
            )
