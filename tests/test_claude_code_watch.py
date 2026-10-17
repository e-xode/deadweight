"""The Claude Code release watch, held in place without the network.

    python3 -m unittest tests.test_claude_code_watch

Every input is a fictional fixture under tests/fixtures/watch/: a changelog in the
upstream format (versions 7.4.x of an invented CLI), a registry document, an issue
list and a two-file plugin. Nothing here fetches, and nothing calls gh.
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / ".github" / "scripts"))

import claude_code_watch as watch  # noqa: E402

FIX = HERE / "fixtures" / "watch"
PLUGIN = FIX / "plugin"


def sections() -> dict[str, list[str]]:
    return watch.split_sections((FIX / "CHANGELOG.md").read_text(encoding="utf-8"))


def run(*argv: str) -> tuple[int, str]:
    out = io.StringIO()
    env = {k: v for k, v in os.environ.items() if k not in ("GITHUB_OUTPUT", "GITHUB_REPOSITORY")}
    with mock.patch.dict(os.environ, env, clear=True), \
            mock.patch.object(watch, "fetch", side_effect=AssertionError("network")), \
            mock.patch.object(watch.subprocess, "run", side_effect=AssertionError("subprocess")), \
            contextlib.redirect_stdout(out):
        code = watch.main(["--root", str(PLUGIN), "--changelog", str(FIX / "CHANGELOG.md"),
                           "--npm-json", str(FIX / "npm.json"), *argv])
    return code, out.getvalue()


class Extractor(unittest.TestCase):
    """What one line yields: identifiers inside the backtick span, whatever surrounds them."""

    def setUp(self) -> None:
        all_sections = sections()
        self.found = watch.analyse(all_sections, ["7.4.10", "7.4.11", "7.4.12", "7.4.13"],
                                   watch.known_from_tree(PLUGIN),
                                   watch.load_exclusions(watch.EXCLUSIONS))

    def test_key_inside_a_quoted_json_pair(self) -> None:
        self.assertEqual(watch.identifiers('`"quietRetries": false` in settings.json')[0],
                         ["quietRetries"])
        self.assertIn("quietRetries", self.found["unknown"])

    def test_key_before_a_quoted_value(self) -> None:
        self.assertEqual(watch.identifiers('Added `onStall: "pause"` for hooks')[0], ["onStall"])
        self.assertIn("onStall", self.found["unknown"])

    def test_known_key_is_not_reported(self) -> None:
        for word in ("autoCompactWindow", "previewMode", "orderTimeout"):
            self.assertNotIn(word, self.found["unknown"])

    def test_env_var_is_listed_apart(self) -> None:
        self.assertIn("SHOP_WATCH_DEPTH", self.found["env"])
        self.assertNotIn("SHOP_WATCH_DEPTH", self.found["unknown"])

    def test_excluded_payload_field_and_builtin(self) -> None:
        for word in ("agentId", "toString"):
            self.assertNotIn(word, self.found["unknown"])
            self.assertIn(word, self.found["excluded_seen"])

    def test_removed_and_deprecated_lines(self) -> None:
        lines = [line for _, line in self.found["removals"]]
        self.assertTrue(any(line.startswith("Removed the legacy") for line in lines))
        self.assertTrue(any(line.startswith("Deprecated the `basketLimit`") for line in lines))
        self.assertIn("cartPreview", self.found["unknown"])

    def test_surface_line_without_unknown_key(self) -> None:
        lines = [line for _, line in self.found["surfaces"]]
        self.assertTrue(any("subagent frontmatter" in line for line in lines))
        self.assertTrue(any("marketplace list" in line for line in lines))

    def test_line_without_backtick_or_surface_is_invisible(self) -> None:
        everything = ([line for _, line in self.found["removals"] + self.found["surfaces"]]
                      + [line for hits in self.found["unknown"].values() for _, line in hits])
        self.assertFalse(any("4,096" in line for line in everything))


class VersionRange(unittest.TestCase):

    def test_baseline_is_the_highest_tested_version(self) -> None:
        evidence = json.loads((PLUGIN / "skills/config-auditor/evidence.json").read_text())
        self.assertEqual(watch.baseline_from_evidence(evidence), "7.4.10")

    def test_first_run_starts_after_the_baseline(self) -> None:
        floor = watch.floor_version("7.4.10", watch.covered_upto([]))
        self.assertEqual(watch.new_versions(sections(), floor, "7.4.13"),
                         ["7.4.11", "7.4.12", "7.4.13"])

    def test_issue_range_already_covered(self) -> None:
        issues = json.loads((FIX / "issues.json").read_text())
        self.assertEqual(watch.covered_upto(issues), "7.4.11")
        floor = watch.floor_version("7.4.10", watch.covered_upto(issues))
        self.assertEqual(watch.new_versions(sections(), floor, "7.4.13"), ["7.4.12", "7.4.13"])
        self.assertEqual(watch.new_versions(sections(), "7.4.13", "7.4.13"), [])

    def test_versions_compare_as_numbers(self) -> None:
        self.assertGreater(watch.vkey("7.4.10"), watch.vkey("7.4.9"))

    def test_npm_latest_and_date(self) -> None:
        doc = json.loads((FIX / "npm.json").read_text())
        self.assertEqual(watch.npm_latest(doc), ("7.4.13", "2031-03-04T09:30:00.000Z"))


class Rendering(unittest.TestCase):

    def test_body_and_title(self) -> None:
        code, body = run("--issues-json", str(FIX / "issues.json"))
        self.assertEqual(code, 0)
        self.assertTrue(body.startswith("# Claude Code drift: 7.4.12..7.4.13\n"))
        self.assertIn("npm `latest`: **7.4.13** (published 2031-03-04T09:30:00.000Z)", body)
        self.assertIn("- [ ] `quietRetries` - 7.4.13:", body)
        self.assertIn("- [ ] `onStall` - 7.4.13:", body)
        self.assertIn("`SHOP_WATCH_DEPTH` (7.4.13)", body)
        self.assertIn("## What this watch cannot see", body)
        self.assertIn("<details>", body)
        self.assertNotIn("basketLimit", body)  # 7.4.11 is covered by issue #3

    def test_nothing_new(self) -> None:
        code, out = run("--after", "7.4.13")
        self.assertEqual(code, 0)
        self.assertTrue(out.startswith("nothing new"))

    def test_quoted_line_cannot_mention(self) -> None:
        self.assertEqual(watch.clip("Thanks @shop-team, see `@scope/pkg`"),
                         "Thanks @​shop-team, see `@scope/pkg`")

    def test_long_body_is_cut_on_a_line(self) -> None:
        many = {"7.4.12": [f"Fixed a permission prompt number {i} " + "x" * 300
                           for i in range(400)]}
        found = watch.analyse(many, ["7.4.12"], set(), set())
        body = watch.render(["7.4.12"], found, latest="7.4.12", published="", floor=None,
                            floor_source="test", known_source="test")
        self.assertLess(len(body), 65536)
        self.assertIn("truncated", body)
        self.assertTrue(body.rstrip().endswith("</details>"))


class CreateIssueIsOptIn(unittest.TestCase):

    def test_flag_defaults_to_off(self) -> None:
        self.assertFalse(watch.parse_args([]).create_issue)

    def test_default_run_calls_no_subprocess(self) -> None:
        # run() makes subprocess.run raise: a default run that tried gh would fail here.
        code, body = run("--issues-json", str(FIX / "issues.json"))
        self.assertEqual(code, 0)
        self.assertIn("Claude Code drift", body)

    def test_create_issue_needs_a_repository(self) -> None:
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            code, _ = run("--create-issue")
        self.assertEqual(code, 2)

    def test_notify_is_silent_without_webhook(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=True), \
                mock.patch.object(watch.urllib.request, "urlopen",
                                  side_effect=AssertionError("network")):
            self.assertEqual(watch.notify("t", "u"), 0)


class NoBacklink(unittest.TestCase):
    """C-00: a quoted upstream line must not link to another repository's issues."""

    AUTOLINK = re.compile(r"(?<![\w`/])[\w.-]+/[\w.-]+#\d|(?<![\w`\u200b])#\d|(?<!`)https?://")

    def outside_code(self, text: str) -> str:
        return " ".join(text.split("`")[0::2])

    def test_references_and_urls_are_neutralised(self) -> None:
        line = ("Fixed a `shop-cli` crash (shop-org/shop-cli#96300), see #12, GH-7 and "
                "https://github.com/shop-org/shop-cli/issues/41; thanks @shop-team")
        out = watch.clip(line)
        outside = self.outside_code(out)
        self.assertNotRegex(outside, self.AUTOLINK)
        self.assertNotRegex(outside, r"GH-\d")
        self.assertNotIn("@shop", outside)
        self.assertIn("`shop-org/shop-cli#\u200b96300`", out)
        self.assertIn("`https://github.com/shop-org/shop-cli/issues/41`", out)
        self.assertIn("`shop-cli`", out)    # an existing code span is kept as it was

    def test_the_rendered_body_holds_no_live_reference(self) -> None:
        many = {"7.4.12": ["Removed `cartPreview` (shop-org/shop-cli#4411)",
                           "Fixed hooks timing out, see #18 and https://github.com/shop-org/shop-cli/pull/9"]}
        found = watch.analyse(many, ["7.4.12"], set(), set())
        body = watch.render(["7.4.12"], found, latest="7.4.12", published="", floor=None,
                            floor_source="test", known_source="test")
        self.assertNotRegex(self.outside_code(body), self.AUTOLINK)


class ClipBoundary(unittest.TestCase):
    """C-02: a long line is cut on a word and never leaves a code span open."""

    def test_cut_on_a_word_with_balanced_backticks(self) -> None:
        line = "Added " + ", ".join(f"`shopKey{i:02d}`" for i in range(60))
        out = watch.clip(line)
        self.assertLessEqual(len(out), watch.LINE_LIMIT)
        self.assertTrue(out.endswith("…"))
        self.assertEqual(out.count("`") % 2, 0)
        self.assertRegex(out, r"`shopKey\d\d`,?…$")

    def test_a_short_line_is_unchanged(self) -> None:
        self.assertEqual(watch.clip("Added `shopKey` to settings.json"),
                         "Added `shopKey` to settings.json")


class SecretWebhook(unittest.TestCase):
    """C-03: a malformed webhook must not print its URL, key or token."""

    FAKE_TOKEN = "SHOPFAKETOKEN456"
    FAKE_KEY = "SHOPFAKEKEY123"

    def notify_with(self, hook: str, **patches: object) -> tuple[int, str]:
        err, out = io.StringIO(), io.StringIO()
        with mock.patch.dict(os.environ, {"GOOGLE_CHAT_WEBHOOK": hook}, clear=True), \
                contextlib.redirect_stderr(err), contextlib.redirect_stdout(out):
            if patches:
                with mock.patch.object(watch.urllib.request, "urlopen", **patches):
                    code = watch.notify("Claude Code drift: 7.4.12", "https://example.com/i/1")
            else:
                code = watch.notify("Claude Code drift: 7.4.12", "https://example.com/i/1")
        return code, err.getvalue() + out.getvalue()

    def assert_no_secret(self, printed: str) -> None:
        for secret in (self.FAKE_TOKEN, self.FAKE_KEY, "chat.example.com", "spaces/SHOP"):
            self.assertNotIn(secret, printed)

    def test_a_url_without_scheme(self) -> None:
        code, printed = self.notify_with(
            f"chat.example.com/v1/spaces/SHOP/messages?key={self.FAKE_KEY}&token={self.FAKE_TOKEN}")
        self.assertEqual(code, 1)
        self.assertIn("ValueError", printed)
        self.assert_no_secret(printed)

    def test_a_url_with_a_control_character(self) -> None:
        import http.client
        hook = (f"https://chat.example.com/v1/spaces/SHOP/messages?key={self.FAKE_KEY}"
                f"&token={self.FAKE_TOKEN}")
        code, printed = self.notify_with(hook, side_effect=http.client.InvalidURL(
            f"URL can't contain control characters. {hook!r}"))
        self.assertEqual(code, 1)
        self.assertIn("InvalidURL", printed)
        self.assert_no_secret(printed)

    def test_any_exception_is_caught(self) -> None:
        hook = f"https://chat.example.com/v1/spaces/SHOP/messages?token={self.FAKE_TOKEN}"
        code, printed = self.notify_with(hook, side_effect=RuntimeError(hook))
        self.assertEqual(code, 1)
        self.assert_no_secret(printed)


class HeadingFormat(unittest.TestCase):
    """C-04: a changelog whose version headings no longer parse fails loudly."""

    def run_on(self, text: str, *argv: str) -> tuple[int, str]:
        with tempfile.TemporaryDirectory() as tmp:
            changelog = Path(tmp) / "CHANGELOG.md"
            changelog.write_text(text, encoding="utf-8")
            out = io.StringIO()
            env = {k: v for k, v in os.environ.items() if k not in ("GITHUB_OUTPUT", "GITHUB_REPOSITORY")}
            with mock.patch.dict(os.environ, env, clear=True), \
                    mock.patch.object(watch, "fetch", side_effect=AssertionError("network")), \
                    mock.patch.object(watch.subprocess, "run", side_effect=AssertionError("subprocess")), \
                    contextlib.redirect_stdout(out):
                code = watch.main(["--root", str(PLUGIN), "--changelog", str(changelog),
                                   "--through", "7.4.13", *argv])
        return code, out.getvalue()

    def test_no_heading_parsed_from_a_non_empty_changelog(self) -> None:
        code, out = self.run_on("# Changelog\n\n### Shop CLI 7.4.13\n\n- Added `shopKey`\n")
        self.assertEqual(code, watch.EXIT_FORMAT)
        self.assertIn("::error::", out)
        self.assertNotIn("nothing new", out)

    def test_a_new_heading_in_another_shape(self) -> None:
        text = (FIX / "CHANGELOG.md").read_text(encoding="utf-8")
        code, out = self.run_on("## 7.4.13 (2031-03-04)\n\n- Added `shopKey`\n\n" + text,
                                "--after", "7.4.12")
        self.assertEqual(code, watch.EXIT_FORMAT)
        self.assertIn("7.4.13 (2031-03-04)", out)

    def test_an_old_heading_in_another_shape_is_tolerated(self) -> None:
        text = (FIX / "CHANGELOG.md").read_text(encoding="utf-8")
        code, _out = self.run_on(text + "\n## 0.9.0 (legacy)\n\n- Old\n", "--after", "7.4.13")
        self.assertEqual(code, 0)

    def test_the_fixture_parses(self) -> None:
        text = (FIX / "CHANGELOG.md").read_text(encoding="utf-8")
        self.assertEqual(watch.format_problem(text, watch.split_sections(text), "7.4.10"), "")


if __name__ == "__main__":
    unittest.main()
