"""Multi-source USD/PEN rate fetcher with prioritized fallback.

Source priority:
    1. SUNAT API      (Peruvian tax authority)     -> parses ``venta``
    2. CDN currency-api (@fawazahmed0)            -> parses ``usd.pen``
    3. ExchangeRate-API (backup)                   -> parses ``rates.USD`` (inverse)

Only ``urllib`` from the standard library is used so this module works before
``requirements.txt`` is installed. Each fetched rate is range-validated before
being accepted; an out-of-range value from one source is treated as failure
and the fallback chain continues.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

import config
from lib.validators import validate_rate

# Timeout (seconds) for every HTTP request in the chain.
_HTTP_TIMEOUT = 15


class FetchError(Exception):
    """Raised when every source in the fallback chain has failed."""

    def __init__(self, message: str, failed_sources: list[str] | None = None) -> None:
        super().__init__(message)
        self.failed_sources = failed_sources or []


def _get_json(url: str, timeout: int = _HTTP_TIMEOUT) -> dict:
    """GET ``url`` and return decoded JSON, raising on non-200 or parse error."""
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (trusted URLs from config)
        if resp.status != 200:
            raise ValueError(f"unexpected status {resp.status} from {url}")
        body = resp.read().decode("utf-8")
    return json.loads(body)


def _fetch_sunat() -> float:
    """Primary source: SUNAT via apis.net.pe. Raises on failure/invalid rate."""
    data = _get_json(config.SUNAT_ENDPOINT)
    rate = float(data["venta"])
    if not validate_rate(rate):
        raise ValueError(f"SUNAT returned out-of-range rate: {rate}")
    return rate


def _fetch_cdn(date: str | None = None) -> float:
    """CDN currency-api. ``date`` (YYYY-MM-DD) selects a historical snapshot."""
    url = config.CDN_HISTORICAL_TEMPLATE.format(date=date) if date else config.CDN_ENDPOINT
    data = _get_json(url)
    rate = float(data["usd"]["pen"])

    # The historical endpoint occasionally returns a forward-dated snapshot;
    # `date` metadata may lag by a day. We validate the numeric value only.
    if not validate_rate(rate):
        raise ValueError(f"CDN returned out-of-range rate: {rate}")
    return rate


def _fetch_backup() -> float:
    """Backup source: ExchangeRate-API v4. USD is quoted per PEN, inverted."""
    data = _get_json(config.BACKUP_ENDPOINT)
    usd_per_pen = float(data["rates"]["USD"])
    if usd_per_pen <= 0:
        raise ValueError(f"backup returned non-positive USD/PEN rate: {usd_per_pen}")
    rate = 1.0 / usd_per_pen
    if not validate_rate(rate):
        raise ValueError(f"backup resolved to out-of-range rate: {rate}")
    return rate


def fetch_current_rate() -> tuple[float, str]:
    """Try sources in priority order, returning ``(rate, source)``.

    Raises :class:`FetchError` listing every failed source if the whole chain
    fails.
    """
    sources: list[tuple[str, callable]] = [
        ("sunat", _fetch_sunat),
        ("cdn", _fetch_cdn),  # type: ignore[arg-type]
        ("backup", _fetch_backup),
    ]
    failures: list[str] = []
    for source, fetcher in sources:
        try:
            rate = fetcher()  # type: ignore[operator]
            return rate, source
        except (urllib.error.URLError, urllib.error.HTTPError, ValueError,
                KeyError, TypeError, json.JSONDecodeError) as exc:
            failures.append(f"{source}: {exc}")

    raise FetchError(
        "All rate sources failed",
        failed_sources=failures,
    )


def fetch_cdn_historical(date_str: str) -> float:
    """Fetch a single historical rate from the CDN for ``date_str`` (YYYY-MM-DD).

    Used by ``backfill.py``. Raises ``ValueError`` on any failure so the caller
    can skip that date and continue.
    """
    try:
        return _fetch_cdn(date=date_str)
    except (urllib.error.URLError, urllib.error.HTTPError,
            json.JSONDecodeError, KeyError, TypeError) as exc:
        raise ValueError(f"CDN historical fetch for {date_str} failed: {exc}") from exc