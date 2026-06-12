from __future__ import annotations

import os
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path

from story_automator.core.utils import get_project_slug


@contextmanager
def chdir(path: str):
    prev = os.getcwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(prev)


class GetProjectSlugTests(unittest.TestCase):
    def test_absolute_root_uses_dir_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "demo-service"
            target.mkdir()
            self.assertEqual(get_project_slug(str(target)), "demoserv")

    def test_symlinked_root_keeps_link_identity_not_target(self) -> None:
        # Regression (PR #38 review): identity must not follow symlinks. A
        # symlinked root must keep the LINK's basename, not the target's, so
        # existing sa-{slug}- sessions named under the link stay visible.
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "linked-target"
            target.mkdir()
            link = Path(tmp) / "linked-root"
            link.symlink_to(target, target_is_directory=True)
            self.assertEqual(get_project_slug(str(link)), "linkedro")

    def test_relative_dot_resolves_instead_of_collapsing_to_generic(self) -> None:
        # Regression: `Path(".").name == ""` previously collapsed to "project".
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "myproject"
            target.mkdir()
            with chdir(str(target)):
                self.assertEqual(get_project_slug("."), "myprojec")

    def test_empty_name_still_falls_back_to_project(self) -> None:
        # A root that resolves to a non-alphanumeric name keeps the safe default.
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "___"
            target.mkdir()
            self.assertEqual(get_project_slug(str(target)), "project")


if __name__ == "__main__":
    unittest.main()
