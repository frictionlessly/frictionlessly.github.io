"""Parse supplied measurements without making network requests or estimating data."""

from datetime import datetime
import math
from typing import Any
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


class EvidenceError(ValueError):
    pass


def number(value: Any, name: str, maximum: float | None = None) -> float | int | None:
    if value is None:
        return None
    try:
        finite = isinstance(value, (float, int)) and math.isfinite(value)
    except OverflowError:
        finite = False
    if (
        isinstance(value, bool)
        or not isinstance(value, (float, int))
        or not finite
        or value < 0
        or (maximum is not None and value > maximum)
    ):
        raise EvidenceError(f"{name} must be a nonnegative finite number or null")
    return value


def text(value: Any, name: str, required: bool = False) -> str | None:
    if value is None and not required:
        return None
    if not isinstance(value, str) or not value.strip() or len(value) > 2000:
        raise EvidenceError(f"{name} must be a nonempty string of at most 2000 characters")
    return value


def parse_evidence(kind: str, raw: Any, month: str) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise EvidenceError("Evidence must be a JSON object")
    if kind == "metrics":
        if raw.get("period") != month:
            raise EvidenceError("Metrics period must match the run month")
        result: dict[str, Any] = {
            "period": month,
            "source": text(raw.get("source"), "source", required=True),
            "sessions": number(raw.get("sessions"), "sessions"),
            "converted_sessions": number(raw.get("converted_sessions"), "converted_sessions"),
            "enquiries": number(raw.get("enquiries"), "enquiries"),
            "conversion_event": text(raw.get("conversion_event"), "conversion_event"),
            "cohort": text(raw.get("cohort"), "cohort"),
            "timezone": text(raw.get("timezone", "UTC"), "timezone", required=True),
            "hosting_note": text(raw.get("hosting_note"), "hosting_note"),
            "note": text(raw.get("note"), "note"),
        }
        try:
            ZoneInfo(result["timezone"])
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise EvidenceError("timezone must be a valid IANA timezone") from exc
        for key in ("sessions", "converted_sessions", "enquiries"):
            if result[key] is not None and int(result[key]) != result[key]:
                raise EvidenceError(f"{key} must be a whole count")
        sessions, converted = result["sessions"], result["converted_sessions"]
        rate = None
        if converted is not None:
            if sessions is None or converted > sessions:
                raise EvidenceError("converted_sessions requires a matching sessions count and cannot exceed it")
            if not result["conversion_event"] or not result["cohort"]:
                raise EvidenceError("A converted_sessions count requires the verified event and same-cohort definition")
            if sessions > 0:
                rate = round(100 * (converted / sessions), 4)
        supplied_rate = number(raw.get("conversion_rate_percent"), "conversion_rate_percent", 100)
        if supplied_rate is not None and (rate is None or not math.isclose(supplied_rate, rate, abs_tol=0.0001)):
            raise EvidenceError("Supplied conversion rate must match converted_sessions / sessions; use null if unavailable")
        result["conversion_rate_percent"] = rate
        return result
    if kind != "lighthouse":
        raise EvidenceError("Unknown evidence kind")
    lighthouse = raw.get("lighthouseResult", raw)
    if not isinstance(lighthouse, dict) or lighthouse.get("runtimeError"):
        raise EvidenceError("Lighthouse result is missing or contains a runtime error")
    url = text(
        lighthouse.get("finalUrl") or lighthouse.get("requestedUrl"),
        "Lighthouse URL", required=True,
    )
    assert url is not None
    try:
        parsed_url = urlsplit(url)
    except ValueError as exc:
        raise EvidenceError("Invalid Lighthouse measurement URL") from exc
    if parsed_url.scheme not in ("http", "https") or not parsed_url.hostname:
        raise EvidenceError("Lighthouse URL must be an HTTP(S) measurement URL")
    if parsed_url.username or parsed_url.password:
        raise EvidenceError("Credential-bearing measurement URLs are not accepted")
    fetched = text(lighthouse.get("fetchTime"), "fetchTime", required=True)
    assert fetched is not None
    try:
        timestamp = datetime.fromisoformat(fetched.replace("Z", "+00:00"))
        if timestamp.tzinfo is None:
            raise ValueError("Timezone missing")
    except ValueError as exc:
        raise EvidenceError("Lighthouse fetchTime must be an ISO timestamp with a timezone") from exc
    categories = lighthouse.get("categories", {})
    audits = lighthouse.get("audits", {})
    settings = lighthouse.get("configSettings", {})
    if not all(isinstance(item, dict) for item in (categories, audits, settings)):
        raise EvidenceError("Invalid Lighthouse categories, audits, or settings")
    performance = categories.get("performance", {})
    if not isinstance(performance, dict):
        raise EvidenceError("Invalid Lighthouse performance category")
    score = number(performance.get("score"), "performance.score", 1)
    result = {
        "measurement_source": "PageSpeed Insights" if "lighthouseResult" in raw else "Lighthouse export",
        "lighthouse_version": text(lighthouse.get("lighthouseVersion"), "lighthouseVersion"),
        "url": url,
        "measured_at": fetched,
        "form_factor": settings.get("formFactor") or settings.get("emulatedFormFactor"),
        "throttling_method": settings.get("throttlingMethod"),
        "performance_score": None if score is None else round(score * 100, 2),
    }
    for label, audit_id in {
        "lcp_ms": "largest-contentful-paint",
        "fcp_ms": "first-contentful-paint",
        "cls": "cumulative-layout-shift",
        "tbt_ms": "total-blocking-time",
        "speed_index_ms": "speed-index",
    }.items():
        audit = audits.get(audit_id, {})
        if not isinstance(audit, dict):
            raise EvidenceError(f"Invalid Lighthouse audit: {audit_id}")
        result[label] = number(audit.get("numericValue"), audit_id)
    for key in ("form_factor", "throttling_method"):
        result[key] = text(result[key], key)
    return result
