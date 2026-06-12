from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

# Universal across phpunit/pytest/jest/gotestsum/etc. `assertions` is PHPUnit-only,
# so it is reported separately and stays nullable when no suite carries it.
_COUNT_ATTRS = ("tests", "failures", "errors", "skipped")


# Aggregate {tests, failures, errors, skipped, assertions|None} from a JUnit
# report. Reads only standard testsuite/testsuites attrs (the project decides HOW
# its runner emits them); raises ValueError on unreadable/non-JUnit XML, or on a
# present-but-malformed/negative count attribute, so the caller can degrade
# cleanly instead of recording a fabricated total.
def parse_junit(path: str | Path) -> dict[str, Any]:
    try:
        root = ET.parse(str(path)).getroot()
    except (ET.ParseError, OSError) as exc:
        raise ValueError(f"junit parse failed: {path}") from exc
    if root.tag == "testsuite":
        suites = [root]
    elif root.tag == "testsuites":
        # Sum DIRECT children only: phpunit nests <testsuite> groups whose parent
        # already carries subtree totals, so a recursive sum would double-count.
        # A bare aggregate-only <testsuites> (no children) is read directly.
        suites = root.findall("testsuite")
        if not suites and root.get("tests") is not None:
            suites = [root]
    else:
        raise ValueError(f"not a junit report (root <{root.tag}>): {path}")
    counts: dict[str, Any] = {key: 0 for key in _COUNT_ATTRS}
    assertions = 0
    has_assertions = False
    for suite in suites:
        for key in _COUNT_ATTRS:
            counts[key] += _int_attr(suite.get(key))
        raw = suite.get("assertions")
        if raw is not None:
            has_assertions = True
            assertions += _int_attr(raw)
    counts["assertions"] = assertions if has_assertions else None
    return counts


def _int_attr(value: str | None) -> int:
    # Absent attrs contribute nothing. A present attr must be a non-negative
    # integer: these counts become the machine-owned story record, so malformed
    # output (non-numeric, empty, float) or a negative value fails closed with a
    # ValueError rather than silently coercing to 0 or passing a bogus total.
    if value is None:
        return 0
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid junit count attribute: {value!r}") from exc
    if parsed < 0:
        raise ValueError(f"negative junit count attribute: {value!r}")
    return parsed
