# SPDX-License-Identifier: AGPL-3.0-or-later
"""The board's rules (#280): which files rebuild, what clashes, what a PR asks, the lanes, the rebuild
label, what is ready to start: python -I tools/test_board.py"""
import io
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import board  # noqa: E402

NOW = 1_800_000_000


def row(branch, files, flags=(), tools=frozenset(), lane=None, touched=NOW):
    return {"branch": branch, "issue": board.branch_issue(branch), "head": None, "files": files, "flags": list(flags),
            "rebuilds": board.rebuilds(files, tools), "lane": lane, "touched": touched}


def issue(n, *labels, blockers=(), milestone=None):
    return {"number": n, "title": f"issue {n}", "labels": [{"name": x} for x in labels],
            "blockedBy": {"nodes": [{"number": b, "state": s} for b, s in blockers]},
            "milestone": {"title": milestone} if milestone else None}


class Board(unittest.TestCase):
    def test_build_tools_follow_rebuild_steps_and_their_imports(self):
        with tempfile.TemporaryDirectory() as d:
            files = {"rebuild.py": 'STEPS = ["build_line.py", "geoportal.py"]\nimport sysinfo\n',
                     "build_line.py": "import geo\nfrom di_tracks import TrackGeometry\nimport json\n",
                     "di_tracks.py": "from track_curve import fit\n", "track_curve.py": "", "geo.py": "",
                     "geoportal.py": "", "sysinfo.py": "", "lint_only.py": "import geo\n"}
            for n, s in files.items():
                with open(os.path.join(d, n), "w", encoding="utf-8") as f:
                    f.write(s)
            got = board.build_tools(d)
        self.assertEqual(got, {f"tools/{n}" for n in ("rebuild.py", "build_line.py", "geoportal.py", "sysinfo.py",
                                                      "geo.py", "di_tracks.py", "track_curve.py")})

    def test_rebuilds_by_tool_manifest_or_snapshot_not_by_facts(self):
        tools = {"tools/build_line.py"}
        self.assertEqual(board.rebuilds(["tools/build_line.py", "src/game.js"], tools), ["tools/build_line.py"])
        self.assertEqual(board.rebuilds(["snapshots/2026-11-05.json"], tools), ["snapshots/2026-11-05.json"])
        self.assertEqual(board.rebuilds(["data/truth.json", "tools/lint.js"], tools), [])

    def test_two_rebuilding_branches_clash_without_a_shared_file(self):
        t = {"tools/build_line.py", "tools/line_heights.py"}
        a = row("20-di", ["tools/build_line.py"], tools=t)
        b = row("202-holds", ["tools/line_heights.py"], tools=t)
        c = row("272-glass", ["src/t3h.js"], tools=t)
        cl = board.clashes([a, b, c])
        self.assertEqual([(x["kind"], x["a"]["branch"], x["b"]["branch"]) for x in cl], [("data", "20-di", "202-holds")])

    def test_shared_code_outranks_shared_docs_and_gone_rows_do_not_clash(self):
        a = row("265-spin", ["src/game.js", "docs/knowledge.md"])
        b = row("268-cross", ["src/game.js"])
        c = row("244-load", ["docs/knowledge.md"])
        d = row("204-joins", ["src/game.js"], flags=["gone"])
        cl = board.clashes([a, b, c, d])
        self.assertEqual([(x["kind"], x["files"]) for x in cl], [("code", ["src/game.js"]), ("docs", ["docs/knowledge.md"])])

    def test_questions_take_top_level_items_of_their_section_only(self):
        body = ("Part of #258.\n\n## Questions for the user\n- **The cards**: 47 stops\n  - a sub-point\n"
                "1. **The order** with #218\n\n## What changes\n- not a question\n")
        self.assertEqual(board.questions(body), [("Questions for the user", ["**The cards**: 47 stops",
                                                                             "1. **The order** with #218"[3:]])])
        self.assertEqual(board.questions("## What changes\n- a\n"), [])
        self.assertEqual(board.questions(None), [])

    def test_kind(self):
        self.assertEqual([board.kind(f) for f in ("README.md", "src/game.js", "tools/bench/u3.js", "tools/lint.js",
                                                  "reports/review/stop-signs-9.json", "data/truth.json",
                                                  "tools/build_line.py")],
                         ["docs", "game", "checks", "checks", "review", "data", "tools"])


    def test_lanes_count_live_rows_against_their_limit(self):
        rs = [row("1-a", ["src/traffic.js"], lane="sim"), row("2-b", ["src/tram.js"], lane="sim"),
              row("3-c", ["src/game.js"], lane="sim", flags=["gone"]),
              row("5-e", ["src/game.js"], lane="sim", flags=["ready"]),
              row("6-f", ["src/game.js"], lane="sim", flags=["parked"]),
              row("4-d", ["tools/build_line.py"], lane="world", touched=NOW - 2 * board.STALE)]
        by, over = board.lanes(rs, NOW)
        self.assertEqual({k: [r["issue"] for r in v] for k, v in by.items()}, {"sim": [1, 2]})
        self.assertEqual(list(over), ["sim"])

    def test_a_parked_branch_does_not_clash(self):
        t = {"tools/build_line.py"}
        a = row("237-match", ["tools/build_line.py"], tools=t)
        b = row("202-holds", ["tools/build_line.py"], tools=t, flags=["parked"])
        self.assertEqual(board.clashes([a, b]), [])

    def test_ready_needs_a_lane_no_agent_no_branch_and_closed_blockers(self):
        issues = [issue(276, "lane:world", blockers=[(237, "OPEN")]), issue(237, "lane:world"),
                  issue(210, "lane:world", blockers=[(204, "CLOSED")]), issue(268, "lane:sim", "agent:claude"),
                  issue(206, "lane:world", "parked"), issue(258, "lane:world", "needs-user"), issue(70),
                  issue(239, "lane:tooling")]
        rd = board.ready(issues, [row("239-fix", ["tools/sources.py"])])
        self.assertEqual({k: [i["number"] for i in v] for k, v in rd.items()}, {"world": [210, 237]})

    def test_ready_follows_the_milestones_world_first_backlog_last(self):
        # #297: by number alone, M3's #30 and M4's #16 came before W1's #237, which the cut at 6 dropped
        issues = [issue(16, "lane:world", milestone="M4 Track graph, several lines"),
                  issue(30, "lane:world", milestone="M3 Tiles and streaming"), issue(26, "lane:world", milestone="Backlog"),
                  issue(40, "lane:world"), issue(276, "lane:world", milestone="W3 Ground"),
                  issue(237, "lane:world", milestone="W1 Track network"), issue(22, "lane:world", milestone="W2 On the track"),
                  issue(10, "lane:world", milestone="M1 Hygiene"), issue(258, "lane:world", milestone="W10 Later")]
        rd = board.ready(issues, [])
        self.assertEqual([i["number"] for i in rd["world"]], [237, 22, 276, 258, 10, 30, 16, 40, 26])

    def test_an_agent_label_without_a_branch_is_listed_apart(self):
        issues = [issue(210, "lane:world", "agent:claude"), issue(223, "lane:tooling", "agent:claude"),
                  issue(237, "lane:world")]
        cl = board.claimed(issues, [row("223-terrain-offline", ["tools/build_line.py"])])
        self.assertEqual([i["number"] for i in cl], [210])
        self.assertNotIn(210, [i["number"] for v in board.ready(issues, []).values() for i in v])

    def test_a_paused_lane_shows_its_count_not_its_issues(self):
        issues = [issue(n, "lane:sim", milestone="Backlog") for n in (26, 27, 32)]
        issues += [issue(n, "lane:world", milestone="W1 Track network") for n in range(300, 308)]
        out = io.StringIO()
        with mock.patch.object(board, "PAUSED", {"sim": "until checkpoint W2"}), \
                mock.patch.object(board, "git", return_value="abc main"), mock.patch("sys.stdout", out):
            board.show([], issues, [], NOW)
        text = out.getvalue()
        self.assertIn("sim 0/1 paused", text)
        self.assertIn("sim      paused until checkpoint W2: 3 issues wait", text)
        self.assertNotIn("#26", text)
        self.assertIn("W1      #305", text)
        self.assertNotIn("#306", text)
        self.assertIn("… and 2 more", text)


class RebuildLabel(unittest.TestCase):
    def check(self, held, branch, **kw):
        out = io.StringIO()
        with mock.patch.object(board, "gh", return_value=held):
            board.check_rebuild_label("data-publish", branch=branch, out=out, **kw)
        return out.getvalue()

    def test_the_holder_publishes(self):
        self.assertEqual(self.check([{"number": 237}], "237-di-matching"), "")

    def test_another_branch_is_refused_and_told_who_holds_it(self):
        with self.assertRaises(SystemExit) as e:
            self.check([{"number": 237}], "258-stop-signs")
        self.assertIn("#258", str(e.exception))
        self.assertIn("held by #237", str(e.exception))
        self.assertIn("--without-rebuild-label", str(e.exception))

    def test_main_and_a_label_nobody_holds_are_refused(self):
        with self.assertRaises(SystemExit) as e:
            self.check([], "main")
        self.assertIn("(none)", str(e.exception))
        self.assertIn("nobody holds it", str(e.exception))

    def test_a_local_rebuild_only_warns(self):
        self.assertIn("A local rebuild is fine", self.check([{"number": 237}], "258-stop-signs", warn_only=True))

    def test_without_github_it_says_it_did_not_check(self):
        self.assertIn("not checked", self.check(None, "258-stop-signs"))


if __name__ == "__main__":
    unittest.main()
