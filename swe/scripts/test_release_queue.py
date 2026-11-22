import argparse
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import release_queue as queue


def row(task, status="todo", **extra):
    return dict(short_id=task, id="id-" + task, status=status, **extra)


class ReleaseQueueTests(unittest.TestCase):
    def test_parallel_builds_skip_overlapping_paths_and_fill_available_slots(self):
        rows = [row("AA-1", "in_progress"), row("AA-2"), row("AA-3"),
                row("AA-4"), row("AA-5"), row("AA-6")]
        batch = [queue.item(value) for value in (
            "AA-1=src/board", "AA-2=src/board/server.py", "AA-3=src/installer",
            "AA-4=src/check.py", "AA-5=src/other.py",
        )]
        result = queue.preview(rows, batch, 3, 2)
        self.assertEqual(result["suggested"], ["AA-3", "AA-4"])
        self.assertEqual(result["held"], {
            "AA-2": "write scope overlaps AA-1", "AA-5": "build limit reached",
        })

    def test_full_handoffs_hold_new_builds_and_show_reviews_outside_batch(self):
        rows = [row("AA-1", "in_review"), row("AA-2", "in_review"),
                row("AA-3"), row("AA-4", "in_review")]
        batch = [queue.item(f"AA-{number}=src/{number}") for number in (1, 2, 3)]
        result = queue.preview(rows, batch, 3, 2)
        self.assertEqual(result["handoffs"], ["AA-1", "AA-2"])
        self.assertEqual(result["unscoped_reviews"], ["AA-4"])
        self.assertEqual(result["suggested"], [])
        self.assertEqual(result["held"], {"AA-3": "owner handoff limit reached"})

    def test_omitted_reviews_hold_new_work_until_scoped_or_explicitly_deferred(self):
        rows = [row("AA-1"), row("AA-2", "in_review"), row("AA-3", "in_review")]
        batch = [queue.item("AA-1=src/a")]
        self.assertEqual(queue.preview(rows, batch, 3, 2)["suggested"], [])
        result = queue.preview(rows, batch, 3, 2, deferred=("AA-2",))
        self.assertEqual(result["held"], {"AA-1": "scope or defer the outside reviews"})
        result = queue.preview(rows, batch, 3, 2, deferred=("AA-2", "AA-3"))
        self.assertEqual(result["suggested"], ["AA-1"])
        self.assertEqual(result["deferred_reviews"], ["AA-2", "AA-3"])
        with self.assertRaisesRegex(ValueError, "defer only reviews"):
            queue.preview(rows, batch, 3, 2, deferred=("AA-1",))

    def test_owner_flag_assignment_and_missing_dependency_hold_candidates(self):
        rows = [row("AA-1", needs_human={"reason": "Need: approve plan"}),
                row("AA-2", relationships_out=[{"type": "depends_on", "target_task_id": "absent"}]),
                row("AA-3", assigned_to="agent:worker"),
                row("AA-4", relationships_out=[{"type": "depends_on", "target_task_id": "id-AA-5"}]),
                row("AA-5", "done", archived=True)]
        batch = [queue.item(f"AA-{number}=src/{number}") for number in (1, 2, 3, 4)]
        result = queue.preview(rows, batch, 3, 2)
        self.assertEqual(result["suggested"], ["AA-4"])
        self.assertEqual(result["held"], {"AA-1": "waiting for the owner",
                                        "AA-2": "open or missing dependency",
                                        "AA-3": "already assigned"})

    def test_board_subproject_id_is_accepted(self):
        batch = [queue.item("AA-OPS-123=src/app")]
        self.assertEqual(queue.preview([row("AA-OPS-123")], batch, 3, 2)["suggested"], ["AA-OPS-123"])

    def test_incoming_blocks_holds_work_until_the_blocker_is_done(self):
        blocked = row("AA-1")
        relation = {"type": "blocks", "target_task_id": "id-AA-1"}
        batch = [queue.item("AA-1=src/a")]
        rows = [blocked, row("AA-2", "backlog", relationships_out=[relation])]
        self.assertEqual(queue.preview(rows, batch, 3, 2)["held"],
                         {"AA-1": "open or missing dependency"})
        rows[1]["status"] = "done"
        self.assertEqual(queue.preview(rows, batch, 3, 2)["suggested"], ["AA-1"])

    def test_a_symlink_scope_requires_the_underlying_repo_path(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "alias").symlink_to(root / "docs")
            with self.assertRaisesRegex(ValueError, "underlying repo path"):
                queue.check_scopes(root, [queue.item("AA-1=alias/sub.md")])
            queue.check_scopes(root, [queue.item("AA-1=docs/sub.md")])

    def test_missing_or_ambiguous_scope_stops_preview(self):
        batch = [queue.item("AA-1=src/1")]
        with self.assertRaisesRegex(ValueError, "active builds need a scope"):
            queue.preview([row("AA-1"), row("AA-2", "in_progress")], batch, 3, 2)
        with self.assertRaisesRegex(ValueError, "listed twice"):
            queue.preview([row("AA-1")], batch * 2, 3, 2)
        with self.assertRaisesRegex(ValueError, "unknown or archived"):
            queue.preview([row("AA-1", archived=True)], batch, 3, 2)
        for value in ("AA-1", "AA-1=.", "AA-1=src/../other", "AA-1=/etc", "AA-1=src,"):
            with self.subTest(value=value), self.assertRaises(argparse.ArgumentTypeError):
                queue.item(value)

    def test_cli_only_calls_board_list(self):
        reply = SimpleNamespace(stdout=json.dumps({"data": [row("AA-1")]}))
        with patch("sys.argv", ["release_queue.py", "--workers", "2", "AA-1=src/a"]), \
                patch.dict("os.environ", {"LATTICE_ROOT": "/fixture"}), \
                patch.object(queue.subprocess, "run", return_value=reply) as run, \
                patch("builtins.print") as printed:
            queue.main()
        run.assert_called_once()
        self.assertEqual(run.call_args.args[0], ["lattice", "list", "--include-archived", "--json"])
        self.assertEqual(run.call_args.kwargs["env"]["LATTICE_NO_UPDATE_CHECK"], "1")
        self.assertEqual(json.loads(printed.call_args.args[0])["suggested"], ["AA-1"])
