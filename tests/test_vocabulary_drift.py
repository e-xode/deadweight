"""The vocabulary drift check, held in place without the network.

    python3 -m unittest tests.test_vocabulary_drift

The pages under tests/fixtures/drift/pages/ are invented (an imaginary shop CLI) in the
table formats of the Claude Code docs; the vocabulary is a matching dict. Nothing here
fetches, and nothing calls gh for real.
"""
from __future__ import annotations

import contextlib
import http.client
import io
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / ".github" / "scripts"))

import claude_code_watch as watch  # noqa: E402
import vocabulary_drift as drift  # noqa: E402

PAGES = HERE / "fixtures" / "drift" / "pages"


def matching() -> dict[str, set[str]]:
    return {
        "KNOWN_TOOLS": {"Basket", "Checkout", "Refund"},
        "AGENT_KNOWN_KEYS": {"name", "description", "model", "permissionMode", "cartLimit"},
        "SKILL_KNOWN_KEYS": {"name", "description", "price-hint"},
        "KNOWN_HOOK_EVENTS": {"OrderPlaced", "OrderShipped", "CartEmptied"},
        "KNOWN_MODEL_TIERS": {"small", "large", "inherit"},
        "SETTINGS_KNOWN_KEYS": {"shopTheme", "shopLock", "shopCurrency", "shopDrafts",
                                "shopTips", "shopHome", "storeTheme", "storeLock"},
        "HOOK_HANDLER_TYPES": {"command", "webhook", "agent"},
        "HOOK_EVENTS_ALL_TYPES": {"OrderPlaced", "CartEmptied"},
        "HOOK_EVENTS_CMD_HTTP_MCP": {"OrderShipped"},
        "AGENT_PERMISSION_MODES": {"ask", "trust", "lock"},
        "SETTINGS_SCOPES": set(drift.SCOPE_LISTS),
        "SETTINGS_KEYS_ANY": {"shopTheme", "storeTheme"},
        "SETTINGS_KEYS_MANAGED": {"shopLock", "storeLock"},
        "SETTINGS_KEYS_USER": {"shopHome"},
        "SETTINGS_KEYS_USER_MANAGED": {"shopCurrency"},
        "SETTINGS_KEYS_USER_LOCAL_MANAGED": {"shopDrafts"},
        "SETTINGS_KEYS_GLOBAL": {"shopTips"},
    }


def run(vocab: dict[str, set[str]], *argv: str) -> tuple[int, str]:
    out = io.StringIO()
    with mock.patch.object(drift, "load_vocabulary", return_value=vocab), \
            mock.patch.object(drift, "fetch_page", side_effect=AssertionError("network")), \
            mock.patch.object(drift.subprocess, "run", side_effect=AssertionError("subprocess")), \
            contextlib.redirect_stdout(out):
        code = drift.main(list(argv))
    return code, out.getvalue()


def by_name(results: list[drift.Result]) -> dict[str, drift.Result]:
    return {r.name: r for r in results}


class NoDrift(unittest.TestCase):
    def test_every_list_in_step(self) -> None:
        code, out = run(matching(), "--pages", str(PAGES), "--json")
        doc = json.loads(out)
        self.assertEqual(code, 0)
        self.assertEqual({r["verdict"] for r in doc["results"]}, {"ok"})
        self.assertEqual(len(doc["results"]), len(drift.COMPARISONS))

    def test_prose_aliases_count_as_keys_but_not_as_a_scope(self) -> None:
        results = by_name(drift.compare(drift.directory_reader(PAGES), matching()))
        self.assertEqual(results["SETTINGS_KNOWN_KEYS"].docs, 8)
        self.assertEqual(results["SETTINGS_KEYS_ANY"].ours, 1)

    def test_the_decoy_bullet_list_is_not_read(self) -> None:
        text = (PAGES / "hooks.md").read_text(encoding="utf-8")
        self.assertEqual(drift.bullets_after(text, "Events that support all five hook types"),
                         {"OrderPlaced", "CartEmptied"})


class Drift(unittest.TestCase):
    def test_both_directions_and_the_drift_exit(self) -> None:
        vocab = matching()
        vocab["KNOWN_TOOLS"] = {"Basket", "Checkout", "Coupon"}
        vocab["SETTINGS_KEYS_MANAGED"] = {"shopLock", "storeLock", "shopCurrency"}
        code, out = run(vocab, "--pages", str(PAGES))
        self.assertEqual(code, drift.EXIT_DRIFT)
        self.assertIn("in the docs, not in the package: Refund", out)
        self.assertIn("in the package, not in the docs: Coupon", out)
        self.assertIn("in the package, not in the docs: shopCurrency", out)
        self.assertIn("2 list(s) out of step", out)

    def test_markdown_section_names_the_lists(self) -> None:
        vocab = matching()
        vocab["AGENT_PERMISSION_MODES"] = {"ask", "trust"}
        code, out = run(vocab, "--pages", str(PAGES), "--markdown")
        self.assertEqual(code, drift.EXIT_DRIFT)
        self.assertTrue(out.startswith(drift.START))
        self.assertIn(drift.END, out)
        self.assertIn("`AGENT_PERMISSION_MODES` (sub-agents): docs 3, package 2", out)
        self.assertIn("`lock`", out)

    def test_a_page_without_its_table_is_unparsed_and_counts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            shutil.copytree(PAGES, tmp, dirs_exist_ok=True)
            (Path(tmp) / "skills.md").write_text("# Shop recipes\n\nNo table today.\n",
                                                 encoding="utf-8")
            code, out = run(matching(), "--pages", tmp)
        self.assertEqual(code, drift.EXIT_DRIFT)
        self.assertIn("UNPARSED  SKILL_KNOWN_KEYS", out)


class CouldNotCheck(unittest.TestCase):
    def test_a_failed_download_is_not_drift(self) -> None:
        def read(name: str) -> str:
            if name == "hooks":
                raise urllib.error.HTTPError(drift.DOCS.format(name), 503, "unavailable",
                                             None, None)
            return drift.directory_reader(PAGES)(name)
        results = drift.compare(read, matching())
        verdicts = {r.name: r.verdict for r in results}
        hook_lists = [c.name for c in drift.COMPARISONS if c.page == "hooks"]
        self.assertEqual({verdicts[n] for n in hook_lists}, {"unchecked"})
        self.assertNotIn("drift", verdicts.values())
        self.assertEqual(drift.exit_code(results), drift.EXIT_UNCHECKED)
        self.assertIn("HTTPError 503", by_name(results)["KNOWN_HOOK_EVENTS"].error)
        markdown = drift.render_markdown(results)
        self.assertIn("(0 of", markdown)
        self.assertIn("Could not be checked (page not downloaded - not drift)", markdown)

    def test_a_missing_saved_page_exits_3_not_1(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            shutil.copytree(PAGES, tmp, dirs_exist_ok=True)
            (Path(tmp) / "settings-reference.md").unlink()
            code, out = run(matching(), "--pages", tmp)
        self.assertEqual(code, 3)
        self.assertIn("UNCHECKED SETTINGS_KNOWN_KEYS", out)
        self.assertNotIn("DRIFT", out)

    def test_drift_wins_over_unchecked(self) -> None:
        vocab = matching()
        vocab["KNOWN_TOOLS"] = {"Basket"}

        def read(name: str) -> str:
            if name == "hooks":
                raise urllib.error.URLError("offline")
            return drift.directory_reader(PAGES)(name)
        self.assertEqual(drift.exit_code(drift.compare(read, vocab)), drift.EXIT_DRIFT)


class Issue(unittest.TestCase):
    def test_merge_replaces_the_previous_section(self) -> None:
        body = "# Claude Code drift: 7.4.1\n\nwatch body\n"
        once = drift.merge_section(body, f"{drift.START}\nfirst\n{drift.END}")
        twice = drift.merge_section(once, f"{drift.START}\nsecond\n{drift.END}")
        self.assertEqual(twice.count(drift.START), 1)
        self.assertIn("second", twice)
        self.assertNotIn("first", twice)
        self.assertTrue(twice.startswith(body.rstrip()))

    def test_merge_stays_under_the_body_limit(self) -> None:
        body = "x" * (watch.BODY_LIMIT - 500)
        section = drift.START + "\n" + "\n".join(f"- line {i}" for i in range(400)) + "\n" + drift.END
        merged = drift.merge_section(body, section)
        self.assertLessEqual(len(merged), watch.BODY_LIMIT)
        self.assertIn("truncated", merged)

    def test_the_standing_title_is_not_a_version_range(self) -> None:
        issues = [{"title": drift.STANDING_TITLE, "labels": [{"name": watch.LABEL}]}]
        self.assertIsNone(watch.covered_upto(issues))

    def test_attach_edits_the_watch_issue(self) -> None:
        url = "https://github.com/shop-org/shop-cli/issues/12"
        calls: list[list[str]] = []
        edits: list[str] = []

        def gh(*args: str) -> str:
            calls.append(list(args))
            return json.dumps({"body": "# watch body"})

        def run_(cmd: list[str], **kw: object) -> object:
            edits.append(str(kw["input"]))
            return mock.Mock(stdout="")
        with mock.patch.object(watch, "gh", side_effect=gh), \
                mock.patch.object(drift.subprocess, "run", side_effect=run_), \
                mock.patch.object(watch, "write_output"):
            self.assertEqual(drift.attach(f"{drift.START}\nx\n{drift.END}", "shop-org/shop-cli",
                                          url), url)
        self.assertEqual(calls[0][:3], ["issue", "view", url])
        self.assertTrue(edits[0].startswith("# watch body"))
        self.assertIn(drift.START, edits[0])

    def test_attach_without_an_issue_opens_the_standing_one(self) -> None:
        with mock.patch.object(watch, "gh", return_value="[]"), \
                mock.patch.object(watch, "create_issue", return_value="u") as create, \
                mock.patch.object(watch, "write_output"):
            self.assertEqual(drift.attach(f"{drift.START}\ns\n{drift.END}", "shop-org/shop-cli", ""), "u")
        self.assertEqual(create.call_args.args[1], drift.STANDING_TITLE)


class CrashIsNotDrift(unittest.TestCase):
    """C-01: Python exits 1 on a traceback, so drift must be another code, and --attach must
    refuse what a crash leaves behind (an empty file) without touching any issue."""

    def test_drift_exit_cannot_be_produced_by_a_traceback(self) -> None:
        self.assertNotIn(drift.EXIT_DRIFT, (0, 1, 2))
        done = subprocess.run([sys.executable, "-B", "-c", "raise RuntimeError('shop crash')"],
                              capture_output=True)
        self.assertNotEqual(done.returncode, drift.EXIT_DRIFT)

    def test_a_partial_download_is_unchecked_not_a_crash(self) -> None:
        def read(name: str) -> str:
            if name == "hooks":
                raise http.client.IncompleteRead(b"## Shop", 99982)
            return drift.directory_reader(PAGES)(name)
        results = drift.compare(read, matching())
        self.assertIn("unchecked", {r.verdict for r in results})
        self.assertEqual(drift.exit_code(results), drift.EXIT_UNCHECKED)

    def test_attach_refuses_an_empty_or_partial_file_and_touches_no_issue(self) -> None:
        for text in ("", "\n", f"{drift.START}\n", "Traceback (most recent call last):\n",
                     f"{drift.START}\n{drift.END}"):
            with self.subTest(text=text), tempfile.TemporaryDirectory() as tmp:
                section = Path(tmp) / "drift.md"
                section.write_text(text, encoding="utf-8")
                gh = mock.Mock(side_effect=AssertionError("gh called"))
                with mock.patch.object(watch, "gh", gh), \
                        mock.patch.object(watch, "create_issue", gh), \
                        mock.patch.object(drift.subprocess, "run", gh):
                    code, out = run(matching(), "--attach", str(section), "--repo", "shop-org/shop-cli")
                self.assertEqual(code, 2)
                self.assertIn("no issue was touched", out)
                gh.assert_not_called()
        with self.assertRaises(ValueError):
            drift.attach("", "shop-org/shop-cli", "")

    def test_the_workflow_attaches_only_on_the_drift_code(self) -> None:
        workflow = (HERE.parent / ".github" / "workflows" / "claude-code-watch.yml").read_text(
            encoding="utf-8")
        step = workflow.split("vocabulary_drift.py --markdown", 1)[1].split("esac", 1)[0]
        attach_case = next(line for line in step.splitlines() if "--attach" in line)
        self.assertEqual(attach_case.strip().split(")")[0], str(drift.EXIT_DRIFT))
        self.assertNotRegex(step, r"^\s*1\)", "exit 1 is a traceback, never drift")
        self.assertIn('*) echo "::error::', step)


class DriftLines(unittest.TestCase):
    """C-02: a drift line keeps every name shown() lists and closes its code spans."""

    def test_forty_names_survive_and_backticks_balance(self) -> None:
        names = [f"shopSettingKey{i:02d}" for i in range(55)]
        results = [drift.Result("SETTINGS_KNOWN_KEYS", "settings-reference", "drift", docs=55,
                                ours=0, missing=names, extra=["shopLegacyKey"])]
        line = next(raw for raw in drift.render_markdown(results).splitlines()
                    if raw.startswith("- [ ] `SETTINGS_KNOWN_KEYS`"))
        for name in names[:drift.NAMES_SHOWN]:
            self.assertIn(f"`{name}`", line)
        self.assertIn(f"(+{len(names) - drift.NAMES_SHOWN} more)", line)
        self.assertIn("In the package, not in the docs: `shopLegacyKey`", line)
        self.assertEqual(line.count("`") % 2, 0)


class RealPackage(unittest.TestCase):
    def test_every_compared_list_loads_from_the_checkout(self) -> None:
        vocab = drift.load_vocabulary(drift.PLUGIN)
        for comp in drift.COMPARISONS:
            self.assertTrue(vocab.get(comp.name), comp.name)


if __name__ == "__main__":
    unittest.main()
