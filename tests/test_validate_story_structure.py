from __future__ import annotations

import io
import json
import tempfile
import textwrap
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from story_automator.commands.basic import cmd_validate_story_structure

# A structurally complete story, mirroring the real bmad story template headings
# (Story 4.1 is the live passing fixture this is modelled on). Each test mutates
# one section to drive a single failure mode.
COMPLETE_STORY = textwrap.dedent(
    """\
    # Story 1.2: Example

    ## Tasks / Subtasks

    - [x] Task one
    - [x] Task two

    ## Dev Agent Record

    ### Agent Model Used

    claude-opus-4-8 (Opus 4.8, 1M context)

    ### File List

    - src/a.py

    ## Senior Developer Review (AI)

    **Reviewer:** auto — adversarial review, 2026-06-08. Outcome: Approve.

    ## Change Log

    - 2026-06-08 — Story 1.2 implemented.
    """
)


class ValidateStoryStructureTests(unittest.TestCase):
    """AI-4.2 / TD-16: assert the story body is structurally complete before `done`.
    Read-only — flags missing/placeholder sections and unchecked dev tasks; the
    review section and unchecked tasks cannot be auto-synthesized, only held."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        self.artifacts = self.repo / "_bmad-output" / "implementation-artifacts"
        self.artifacts.mkdir(parents=True)
        self.story = self.artifacts / "1-2-example.md"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _run(self, body: str, story: str = "1-2") -> dict:
        self.story.write_text(body, encoding="utf-8")
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            code = cmd_validate_story_structure(["--repo", str(self.repo), "--story", story])
        self.assertEqual(code, 0, stdout.getvalue())
        return json.loads(stdout.getvalue())

    def test_complete_story_is_in_sync(self) -> None:
        payload = self._run(COMPLETE_STORY)
        self.assertTrue(payload["in_sync"])
        self.assertEqual(payload["missing_sections"], [])
        self.assertEqual(payload["placeholder_sections"], [])
        self.assertEqual(payload["unchecked_tasks"], 0)

    def test_missing_senior_review_fails(self) -> None:
        # The Story 4.4 / 5.2 case: File List is followed straight by Change Log.
        body = COMPLETE_STORY.replace(
            "## Senior Developer Review (AI)\n\n"
            "**Reviewer:** auto — adversarial review, 2026-06-08. Outcome: Approve.\n\n",
            "",
        )
        payload = self._run(body)
        self.assertFalse(payload["in_sync"])
        self.assertIn("## Senior Developer Review (AI)", payload["missing_sections"])

    def test_placeholder_agent_model_fails(self) -> None:
        body = COMPLETE_STORY.replace("claude-opus-4-8 (Opus 4.8, 1M context)", "{{agent_model}}")
        payload = self._run(body)
        self.assertFalse(payload["in_sync"])
        self.assertIn("### Agent Model Used", payload["placeholder_sections"])
        self.assertEqual(payload["missing_sections"], [])

    def test_todo_agent_model_fails(self) -> None:
        body = COMPLETE_STORY.replace("claude-opus-4-8 (Opus 4.8, 1M context)", "TODO")
        payload = self._run(body)
        self.assertIn("### Agent Model Used", payload["placeholder_sections"])

    def test_unchecked_task_fails(self) -> None:
        body = COMPLETE_STORY.replace("- [x] Task two", "- [ ] Task two")
        payload = self._run(body)
        self.assertFalse(payload["in_sync"])
        self.assertEqual(payload["unchecked_tasks"], 1)

    def test_indented_unchecked_subtask_counted(self) -> None:
        body = COMPLETE_STORY.replace("- [x] Task two", "- [x] Task two\n  - [ ] Subtask a")
        payload = self._run(body)
        self.assertEqual(payload["unchecked_tasks"], 1)

    def test_deferred_ai_review_followup_is_exempt(self) -> None:
        # An open `[AI-Review]` action item may legitimately remain on a done story
        # (HIGH/MEDIUM, non-blocking) — it must NOT count as an undone dev task.
        body = COMPLETE_STORY.replace(
            "- [x] Task two",
            "- [x] Task two\n- [ ] [AI-Review][Med] Tidy error message [src/a.py:10]",
        )
        payload = self._run(body)
        self.assertEqual(payload["unchecked_tasks"], 0)
        self.assertTrue(payload["in_sync"])

    def test_empty_change_log_fails(self) -> None:
        body = COMPLETE_STORY.replace("- 2026-06-08 — Story 1.2 implemented.\n", "")
        payload = self._run(body)
        self.assertFalse(payload["in_sync"])
        self.assertIn("## Change Log", payload["placeholder_sections"])

    def test_missing_multiple_sections(self) -> None:
        payload = self._run("# Story 1.2: Example\n\nNothing here.\n")
        self.assertFalse(payload["in_sync"])
        self.assertEqual(
            set(payload["missing_sections"]),
            {
                "### Agent Model Used",
                "## Tasks / Subtasks",
                "### File List",
                "## Senior Developer Review (AI)",
                "## Change Log",
            },
        )

    def test_story_not_found(self) -> None:
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            code = cmd_validate_story_structure(["--repo", str(self.repo), "--story", "9-9"])
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(stdout.getvalue())["error"], "story_file_not_found")

    def test_missing_args(self) -> None:
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            code = cmd_validate_story_structure(["--repo", str(self.repo)])
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(stdout.getvalue())["error"], "missing_args")


if __name__ == "__main__":
    unittest.main()
