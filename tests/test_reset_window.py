import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills/repo-neighbor/scripts"))
import reset_window as window


def usage(used=10):
    return {"accountId": "participant", "ordinaryUsageAllowed": True, "rateLimits": {
        "limitId": "codex",
        "primary": {"windowDurationMins": 300, "usedPercent": used, "resetsAt": 3600},
        "secondary": {"windowDurationMins": 10080, "usedPercent": 20, "resetsAt": 40000},
    }}


class ResetWindowTests(unittest.TestCase):
    def test_suggest_requires_more_than_five_percent_in_each_window(self):
        for short_used, weekly_used, should_suggest in ((94, 94, True), (95, 94, False), (94, 95, False)):
            with self.subTest(short_used=short_used, weekly_used=weekly_used):
                data = usage(short_used)
                data["rateLimits"]["secondary"]["usedPercent"] = weekly_used
                with patch.object(sys, "argv", ["reset_window.py", "suggest", "--included-only"]), \
                     patch.object(window, "limits", return_value=data), \
                     patch.object(window.time, "time", return_value=100), \
                     patch.object(window, "suggest", return_value=None) as suggest:
                    window.main()
                if should_suggest:
                    suggest.assert_called_once()
                else:
                    suggest.assert_not_called()

    def test_window_and_both_reserves(self):
        self.assertEqual(window.decision(usage(), "weekly", 10, 30, 100), ("early", 40000))
        self.assertEqual(window.decision(usage(), "weekly", 12, 30, 100), ("ready", 40000))
        self.assertEqual(window.decision(usage(70), "weekly", 12, 30, 100)[0], "reserve")
        self.assertEqual(window.decision(usage(), "monthly", 10, 30, 100)[0], "unavailable")
        self.assertEqual(window.decision(usage(), "weekly", 10, 30, 3600)[0], "unavailable")
        for value in (None, False):
            self.assertEqual(window.decision(dict(usage(), ordinaryUsageAllowed=value),
                                             "weekly", 12, 30, 100)[0], "unavailable")

    def test_reminder_suppresses_repeat_and_rechecks_before_start(self):
        with TemporaryDirectory() as tmp, patch.object(window.sys.stdin, "isatty", return_value=True), \
             patch.object(window, "desk_tasks", return_value=[dict(title="Translate", lang="French", repo="org/docs")]), \
             patch.object(window, "series") as launch:
            args = SimpleNamespace(account_id="a", period="weekly", output=Path(tmp),
                                   minutes=45, issue="https://github.com/test/docs/issues/1")
            reset = int(time.time()) + 3000
            with patch("builtins.input", return_value="skip") as answer:
                window.suggest(args, reset)
                window.suggest(args, reset)
                self.assertEqual(answer.call_count, 1)
            args.account_id = "b"
            with patch("builtins.input", return_value="start"), patch.object(window, "status_now", return_value=("reserve", None)):
                window.suggest(args, reset)
            launch.assert_not_called()

    def test_series_requires_receipt_before_next_model_request(self):
        tasks = [dict(id=f"task-{i}", repo="org/docs", title="Translate",
                      source="Text", lang="French", available=True) for i in (1, 2)]
        actions = []
        def call(path, data=None):
            if path == "desk":
                return {"tasks": tasks[1:]}
            actions.append((path, data["id"]))
            return dict(id=data["id"], state={"claim": "held", "submit": "pending"}.get(path))
        def launch(args, reset, prompt, *, output, stop_at):
            self.assertIn("untrusted", prompt)
            actions.append(("model", output.stem))
            output.write_text("Texte")
        with TemporaryDirectory() as temp, patch.object(window, "status_now", return_value=("ready", 1000)), \
             patch.object(window, "launch", side_effect=launch), patch.object(window.time, "time", return_value=100):
            args = SimpleNamespace(output=Path(temp), minutes=45, issue=None)
            with patch.object(window, "desk_tasks", side_effect=[[tasks[1]], []]):
                window.series(args, 1000, SimpleNamespace(call=call), tasks[0])
            self.assertEqual(actions, [(action, task["id"]) for task in tasks
                                      for action in ("claim", "model", "submit", "release")])
            actions.clear()
            with patch.object(window, "launch", side_effect=KeyboardInterrupt):
                with self.assertRaises(KeyboardInterrupt):
                    window.series(args, 1000, SimpleNamespace(call=call), tasks[0])
            self.assertEqual(actions, [("claim", tasks[0]["id"]), ("release", tasks[0]["id"])])

    def test_account_change(self):
        args = SimpleNamespace(account_id="original")
        with patch.object(window, "limits", return_value=usage()):
            self.assertEqual(window.status_now(args), ("unavailable", None))

    def test_stub_cli_and_duplicate_start(self):
        with TemporaryDirectory() as d:
            root = Path(d)
            cli = root / "codex"
            cli.write_text("#!" + sys.executable + "\n" + """
import json, sys
from pathlib import Path
if sys.argv[1] == "app-server":
    for line in sys.stdin:
        m = json.loads(line)
        if "id" in m:
            print(json.dumps({"id": m["id"], "result": %s}), flush=True)
else:
    assert "untrusted" in sys.stdin.read()
    Path(sys.argv[sys.argv.index("-o")+1]).write_text("draft")
""" % repr(usage()))
            cli.chmod(0o700)
            args = SimpleNamespace(period="weekly", output=root / "out", minutes=1)
            end = int(time.time()) + 120
            with patch.dict(os.environ, PATH=str(root) + os.pathsep + os.environ["PATH"]):
                self.assertEqual(window.limits(), usage())
                window.launch(args, end, "untrusted data")
                self.assertEqual(next(args.output.glob("*.md")).read_text(), "draft")
                with self.assertRaisesRegex(ValueError, "already"):
                    window.launch(args, end, "untrusted data")
