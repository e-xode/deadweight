"""The precision table `deadweight` shows next to each check, held in place.

    python3 -m unittest discover -s tests

The table changes no finding, so it must stay outside the auditor's identity: inside it,
updating a measured precision would change the sha and stop every floor from comparing.
"""
from __future__ import annotations

import importlib.machinery
import importlib.util
import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SCRIPTS = ROOT / "skills" / "config-auditor" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from deadweight_audit.catalog import known_check_ids  # noqa: E402
from deadweight_audit.identity import instrument_files  # noqa: E402

PRECISION = ROOT / "skills" / "config-auditor" / "precision.json"


def command():
    """bin/deadweight has no .py suffix: load it by path."""
    loader = importlib.machinery.SourceFileLoader("deadweight_bin", str(ROOT / "bin" / "deadweight"))
    spec = importlib.util.spec_from_loader("deadweight_bin", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


class PrecisionTable(unittest.TestCase):
    def test_outside_the_auditor_identity(self):
        self.assertNotIn(PRECISION.resolve(), [f.resolve() for f in instrument_files()])

    def test_every_check_is_known_and_counts_are_coherent(self):
        checks = json.loads(PRECISION.read_text(encoding="utf-8"))["checks"]
        known = known_check_ids()
        for check, m in checks.items():
            with self.subTest(check=check):
                # Semantic families are reported by semantic.py, not by the auditor's catalog.
                if not check.startswith(("58-", "59-", "60-", "61-", "62-")):
                    self.assertIn(check, known)
                self.assertGreater(m["n"], 0)
                self.assertTrue(0 <= m["true"] <= m["n"])

    def test_label_shows_the_fraction_and_never_invents_one(self):
        mod = command()
        table = {"20-relative-links": {"true": 24, "n": 25, "repositories": 3, "severity": "ERROR",
                                       "date": "2026-09-27", "auditor": "43b08d90"},
                 "23-agent-tools": {"true": 868, "n": 869, "repositories": 3, "severity": "ERROR",
                                    "date": "2026-09-27", "auditor": "a2649175"},
                 "40-skill-not-loaded": {"true": 1, "n": 1, "date": "2026-09-27", "auditor": None}}
        self.assertEqual(mod.precision_label(table, "20-relative-links", "ERROR", "fe076488"),
                         "precision 24/25 (96 %, 3 repositories, too few to conclude), 2026-09-27, "
                         "earlier auditor 43b08d90")
        self.assertIn("too few to conclude", mod.precision_label(table, "23-agent-tools", "ERROR"))
        self.assertIn("too few to conclude", mod.precision_label(table, "40-skill-not-loaded"))
        self.assertEqual(mod.precision_label(table, "20-relative-links", "WARN"),
                         "precision not measured at WARN (measured at ERROR only)")
        self.assertEqual(mod.precision_label(table, "04-skill-description-brackets"), "precision not measured")


if __name__ == "__main__":
    unittest.main()
