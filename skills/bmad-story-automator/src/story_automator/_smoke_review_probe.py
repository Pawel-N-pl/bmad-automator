"""Throwaway review-pipeline smoke probe — DELETE WITH THIS BRANCH.

This module deliberately violates the seeded house-style rules so we can confirm
CodeRabbit (and later Augment) actually apply the .coderabbit.yaml path_instructions.
It is never imported by the package and exists only on the chore/review-pipeline-smoke
branch. It must NOT be merged.
"""
from __future__ import annotations

from typing import Optional


def greet(name: Optional[str]) -> str:
    """Return a greeting (docstring + Optional + .format are all intentional violations)."""
    return "hello, {}".format(name or "world")


def safe_int(value: str) -> int:
    try:
        return int(value)
    except:  # noqa
        return 0
