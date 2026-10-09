"""A forced `--layout none` on a repository that holds only a `.mcp.json`.

    python3 -m unittest discover -s tests

The labelled corpus cannot pass `--layout`, so this is held here. Fictional shop.
"""
from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "skills" / "config-auditor" / "scripts"))

from deadweight_audit.cli import main  # noqa: E402

MCP = {"mcpServers": {"shop-db": {"command": "npx", "args": ["-y", "shop-db-mcp"]}}}


class LayoutNoneMcpTest(unittest.TestCase):
    def test_forced_none_does_not_claim_a_security_audit(self) -> None:
        # audit externe 3, g8-04: "whose project-scoped servers are audited" next to a
        # clean summary, while the security check that flags an unpinned npx never ran.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "shop-api"
            root.mkdir()
            (root / ".mcp.json").write_text(json.dumps(MCP), encoding="utf-8")
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                main(["--root", str(root), "--json", "--all", "--layout", "none"])
        findings = json.loads(out.getvalue())["findings"]
        layout = [f["message"] for f in findings if f["check"] == "00-layout"]
        self.assertTrue(layout, findings)
        self.assertNotIn("are audited", layout[0])
        self.assertIn("50-security-mcp", layout[0])


if __name__ == "__main__":
    unittest.main()
