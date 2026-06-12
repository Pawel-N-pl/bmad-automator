from __future__ import annotations

import shlex
from pathlib import Path

from ..core.junit import parse_junit
from ..core.runtime_policy import PolicyError, load_policy_unresolved, test_config
from ..core.utils import ensure_dir, run_cmd, write_json
from .basic import _resolve_story_file, _section_bounds

TEST_COUNTS_HEADING = "### Test Counts"


def _render_test_counts(counts: dict) -> list[str]:
    body = [
        f"- Tests: {counts['tests']}",
        f"- Failures: {counts['failures']}",
        f"- Errors: {counts['errors']}",
        f"- Skipped: {counts['skipped']}",
    ]
    if counts.get("assertions") is not None:  # PHPUnit-only; omit the line entirely otherwise
        body.append(f"- Assertions: {counts['assertions']}")
    return body


# Rewrite `heading`'s body deterministically (leaving other sections untouched),
# appending the section at EOF when absent. Mirrors the File List reconcile so a
# re-run with identical counts is a byte-for-byte no-op.
def _replace_or_append_section(text: str, heading: str, body: list[str]) -> str:
    lines = text.splitlines()
    suffix = "\n" if text.endswith("\n") else ""
    bounds = _section_bounds(lines, heading)
    if bounds is None:
        tail = ["", heading, "", *body]
        new_lines = [*lines, *tail] if lines else [heading, "", *body]
        return "\n".join(new_lines) + suffix
    start, end = bounds
    rest = lines[end:]
    block = ["", *body]
    if rest:  # blank separator only when another section follows
        block.append("")
    new_lines = [*lines[: start + 1], *block, *rest]
    return "\n".join(new_lines) + suffix


# The junit path comes from policy config and is joined to the repo before the
# rerun reads/writes it. Confine it to the repo: an absolute path would discard
# the repo prefix and `..` could escape the project, letting a misconfigured
# policy read/write outside the repo. Returns False if `rel` is not repo-relative.
def _junit_path_within_repo(repo: Path, rel: str) -> bool:
    if Path(rel).is_absolute():
        return False
    try:
        (repo / rel).resolve().relative_to(repo.resolve())
    except ValueError:
        return False
    return True


def cmd_test_counts(args: list[str]) -> int:
    if args and args[0] in {"--help", "-h"}:
        print("Usage: test-counts --repo PATH --story KEY [--since EPOCH] [--write]")
        return 0
    repo = ""
    story = ""
    since: float | None = None
    do_write = False
    idx = 0
    while idx < len(args):
        arg = args[idx]
        if arg == "--repo" and idx + 1 < len(args):
            repo = args[idx + 1]
            idx += 2
        elif arg == "--story" and idx + 1 < len(args):
            story = args[idx + 1]
            idx += 2
        elif arg == "--since" and idx + 1 < len(args):
            # --since is always machine-supplied (date +%s); a non-numeric value
            # is a contract break. Fail loud rather than silently dropping the
            # staleness gate, which would let a stale artifact pass as fresh.
            try:
                since = float(args[idx + 1])
            except ValueError:
                write_json({"ok": False, "error": "since_invalid", "value": args[idx + 1]})
                return 1
            idx += 2
        elif arg == "--write":
            do_write = True
            idx += 1
        else:
            idx += 1
    if not repo or not story:
        write_json({"ok": False, "error": "missing_args"})
        return 1
    if not Path(repo).is_dir():
        write_json({"ok": False, "error": "repo_not_found"})
        return 1
    story_file, story_id, err = _resolve_story_file(repo, story)
    if story_file is None:
        write_json(err)
        return 1
    try:
        cfg = test_config(load_policy_unresolved(repo))
    except PolicyError:
        write_json({"ok": False, "error": "policy_invalid"})
        return 1
    junit_rel = cfg["junitPath"]
    command = cfg["command"]
    if not junit_rel:  # Tier 3: nothing configured — File List reconcile still ran independently
        write_json({"ok": True, "skipped": True, "reason": "test_not_configured", "test_counts": None, "wrote": False})
        return 0
    junit_rel = junit_rel.replace("{story}", story_id)
    if not _junit_path_within_repo(Path(repo), junit_rel):
        write_json({"ok": False, "error": "junit_path_invalid", "junit_path": junit_rel})
        return 1
    junit_path = Path(repo) / junit_rel
    fresh = junit_path.is_file() and (since is None or junit_path.stat().st_mtime >= since)
    rerun_exit: int | None = None
    if fresh:  # Tier 1: trust the artifact emitted by this dev run
        source = "capture"
    elif command:  # Tier 2: deterministic floor — re-run and parse what it emits
        # Shell-quote substitutions: the placeholders must be left UNquoted in the
        # command template (paths with spaces/metacharacters would break bash -c).
        resolved = command.replace("{junit}", shlex.quote(str(junit_path))).replace("{story}", shlex.quote(story_id))
        ensure_dir(junit_path.parent)
        rerun_exit = run_cmd("bash", "-c", resolved, cwd=repo).exit_code  # non-zero is expected when tests fail
        if not junit_path.is_file():
            write_json(
                {"ok": True, "skipped": True, "reason": "test_artifact_not_emitted", "command_exit": rerun_exit, "test_counts": None, "wrote": False}
            )
            return 0
        source = "rerun"
    else:  # Tier 3: stale/missing artifact and no runner to fall back on
        reason = "test_artifact_stale" if junit_path.is_file() else "test_artifact_missing"
        write_json({"ok": True, "skipped": True, "reason": reason, "test_counts": None, "wrote": False})
        return 0
    try:
        counts = parse_junit(junit_path)
    except ValueError:
        write_json({"ok": False, "error": "junit_parse_failed", "junit_path": str(junit_path)})
        return 1
    text = story_file.read_text(encoding="utf-8")
    new_text = _replace_or_append_section(text, TEST_COUNTS_HEADING, _render_test_counts(counts))
    wrote = False
    if do_write and new_text != text:
        story_file.write_text(new_text, encoding="utf-8")
        wrote = True
    payload = {
        "ok": True,
        "skipped": False,
        "story_file": str(story_file),
        "source": source,
        "junit_path": str(junit_path),
        "test_counts": counts,
        "wrote": wrote,
    }
    if rerun_exit is not None:
        payload["command_exit"] = rerun_exit
    write_json(payload)
    return 0
