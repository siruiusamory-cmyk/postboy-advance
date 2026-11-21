"""The release workflow: a version tag builds the download and opens a draft release."""

from __future__ import annotations

from pathlib import Path
import re

import yaml

PATH = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "release.yml"
TEXT = PATH.read_text(encoding="utf-8")
DOCUMENT = yaml.safe_load(TEXT)
STEPS = DOCUMENT["jobs"]["package"]["steps"]


def _step(fragment: str) -> dict:
    (found,) = [step for step in STEPS if fragment in step["name"]]
    return found


def test_it_runs_for_a_version_tag_or_by_hand_and_never_for_a_branch():
    assert DOCUMENT[True] == {"push": {"tags": ["v*"]}, "workflow_dispatch": None}


def test_only_the_one_job_may_write_and_every_action_is_pinned():
    assert DOCUMENT["permissions"] == {"contents": "read"}
    assert DOCUMENT["jobs"]["package"]["permissions"] == {"contents": "write"}
    uses = re.findall(r"^\s*uses:\s*(\S+)", TEXT, re.MULTILINE)
    assert len(uses) == 3
    assert all(re.fullmatch(r"[\w.-]+/[\w.-]+@[0-9a-f]{40}", use) for use in uses), uses
    assert _step("Check out")["with"]["persist-credentials"] is False


def test_a_tag_must_name_the_product_version_before_anything_is_built():
    names = [step["name"] for step in STEPS]
    refuse = _step("Refuse a tag")
    assert refuse["if"] == "github.ref_type == 'tag'"
    assert "tools.webfoot.release_identity --json" in refuse["run"] and "throw" in refuse["run"]
    assert names.index(refuse["name"]) < names.index("Freeze the program")


def test_the_release_is_a_draft_made_only_for_a_tag_from_the_packaged_zip():
    release = _step("draft release")
    assert release["if"] == "github.ref_type == 'tag'"
    assert "--draft" in release["run"] and "--verify-tag" in release["run"]
    assert STEPS[-1] is release
    assert "scripts/package-postboy-advance.ps1 -SkipRomProbe" in _step("Stage, census")["run"]
    assert _step("upload-artifact")["with"]["if-no-files-found"] == "error"
