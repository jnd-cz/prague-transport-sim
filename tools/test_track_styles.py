# SPDX-License-Identifier: AGPL-3.0-or-later
"""The track styles built offline (tools/track_styles.py, #479): python -P -E tools/test_track_styles.py."""
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import geo  # noqa: E402
import track_styles as T  # noqa: E402


def rect(x0, x1, y0, y1, c, l=0, z=200.0):
    return {"c": c, "l": l, "r": [[x0, y0, z], [x1, y0, z], [x1, y1, z], [x0, y1, z]]}


STOPS = [{"name": "A", "s": 0.0}, {"name": "B", "s": 100.0}, {"name": "C", "s": 300.0}, {"name": "B", "s": 400.0}]
DATA = {"line": "x", "path": [[0.0, 0.0], [600.0, 0.0]], "stops": STOPS}


class Styles(unittest.TestCase):
    def test_the_users_mark_runs_from_its_stop_to_the_next_of_the_other_name(self):
        truth = {"trackStyles": [{"line": "y", "from": "A", "to": "B", "style": "ballast"},
                                 {"line": "x", "from": "C", "to": "B", "style": "ballast"}]}
        self.assertEqual(T.sections(DATA, truth, None), [{"s0": 300.0, "s1": 400.0, "style": "ballast", "source": "user", "mark": 1}])

    def test_green_under_the_axis_for_20_m_is_grass_track(self):
        sv = T.Survey({"areas": [rect(100, 160, -5, 5, "green"), rect(200, 212, -5, 5, "green"), rect(0, 600, -20, 20, "road", 1)]})
        secs = T.sections(DATA, {"trackStyles": []}, sv)
        self.assertEqual(secs, [{"s0": 100, "s1": 160, "style": "grass", "source": "survey"}])   # (the 12 m piece is too short)

    def test_short_gaps_are_one_section_and_the_users_marks_win(self):
        sv = T.Survey({"areas": [rect(100, 160, -5, 5, "green"), rect(180, 260, -5, 5, "green"), rect(360, 440, -5, 5, "green")]})
        truth = {"trackStyles": [{"line": "x", "from": "C", "to": "B", "style": "embedded"}]}
        secs = T.sections(DATA, truth, sv)
        self.assertEqual([(x["s0"], x["s1"], x["style"], x["source"]) for x in secs],
                         [(100, 260, "grass", "survey"), (300.0, 400.0, "embedded", "user")])

    def test_the_list_takes_every_pass_and_leaves_the_users_marks_their_track(self):
        stops = [{"name": "A", "s": 0.0}, {"name": "B", "s": 100.0}, {"name": "C", "s": 300.0}, {"name": "B", "s": 400.0},
                 {"name": "A", "s": 550.0}]
        data = {**DATA, "stops": stops}
        truth = {"trackStyles": [{"line": "x", "from": "C", "to": "B", "style": "embedded"}],
                 "grassTrack": {"stretches": [{"from": "A", "to": "B"}, {"from": "C", "to": "B"}, {"at": "C"},
                                              {"from": "B", "to": "C", "removed": 2009}]}}
        secs = T.sections(data, truth, None)
        self.assertEqual([(x["s0"], x["s1"], x["source"], x.get("stretch")) for x in secs],
                         [(0.0, 100.0, "list", 0), (100.0, 300.0, "list", 1), (300.0, 400.0, "user", None),
                          (400.0, 550.0, "list", 0)])   # (C - B both ways; the user's mark keeps the way back)

    @unittest.skipUnless(geo.have_grid(), geo.NO_GRID)
    def test_a_mark_between_two_points_runs_between_their_route_positions(self):
        ll = [list(map(float, T.Frame().ll(x, y))) for x, y in ((420.0, 3.0), (180.0, -2.0))]
        truth = {"trackStyles": [{"line": "x", "between": ll, "style": "grass"}],
                 "grassTrack": {"stretches": [{"from": "B", "to": "C"}]}}
        secs = T.sections(DATA, truth, None)
        self.assertEqual([(round(x["s0"], 3), round(x["s1"], 3), x["source"]) for x in secs],
                         [(100.0, 180.0, "list"), (180.0, 420.0, "user")])
        to_stop = {"trackStyles": [{"line": "x", "between": [ll[1], "B"], "style": "grass"}]}   # (B at 100 and 400: the nearer)
        self.assertEqual([(round(x["s0"], 2), round(x["s1"], 2)) for x in T.sections(DATA, to_stop, None)], [(100.0, 180.0)])
        far = [list(map(float, T.Frame().ll(x, y))) for x, y in ((420.0, 30.0), (180.0, 0.0))]
        self.assertEqual(T.sections(DATA, {"trackStyles": [{"line": "x", "between": far, "style": "grass"}]}, None), [])

    def test_an_area_of_higher_rank_over_the_green_decides(self):
        sv = T.Survey({"areas": [rect(100, 200, -5, 5, "green"), rect(140, 160, -5, 5, "road"), rect(0, 600, -9, 9, "wall")]})
        self.assertEqual(sv.class_at(150, 0), "road")
        self.assertEqual(sv.class_at(120, 0), "green")
        self.assertIsNone(sv.class_at(300, 0))   # (a wall is not ground)


class Junctions(unittest.TestCase):
    """#546: paved track embedded at junctions and over road crossings' full width."""

    def paved(self, survey=None, **extra):
        data = {"line": "x", "path": [[0.0, 0.0], [600.0, 0.0]], "stops": [{"name": "A", "s": 0.0}, {"name": "B", "s": 600.0}],
                **extra}
        return T.sections(data, {}, survey)

    def test_a_car_road_across_is_embedded_over_its_width(self):
        secs = self.paved(roads=[{"p": [[200, -20], [200, 20]], "w": 8, "c": 1}])
        self.assertEqual(spans_of(secs), [(196, 204, "embedded")])

    def test_the_surveys_carriageway_widens_it_and_admits_a_service_road(self):
        sv = T.Survey({"areas": [rect(192, 209, -10, 10, "road"), rect(382, 393.5, -10, 10, "road"),
                                 rect(0, 600, -0.5, 0.5, "cycle")]})
        secs = self.paved(sv, roads=[{"p": [[200, -20], [200, 20]], "w": 8, "c": 1},
                                     {"p": [[388, -20], [388, 20]], "w": 4},            # (service: no car flag)
                                     {"p": [[500, -20], [500, 20]], "w": 5}])           # (a cycleway: no carriageway)
        self.assertEqual(spans_of(secs), [(192, 209, "embedded"), (382, 393, "embedded")])

    def test_a_switch_to_its_frog_and_a_diamond_over_the_beds(self):
        secs = self.paved(switches=[{"s": 100.0, "frog": 12.0}],
                          tracks=[{"p": [[300, -20], [300, 20]]}, {"p": [[400, 0.2], [500, 0.2]]}])   # (across; along)
        self.assertEqual(spans_of(secs), [(97, 115, "embedded"), (299, 301, "embedded")])

    def test_close_pieces_join_grass_yields_and_ballast_keeps_its_switch(self):
        secs = self.paved(switches=[{"s": 100.0, "frog": 12.0}], roads=[{"p": [[125, -20], [125, 20]], "w": 6, "c": 1}])
        self.assertEqual(spans_of(secs), [(97, 128, "embedded")])
        tw = {"switches": [{"s": 100, "frog": 12}], "tracks": [{"p": [[300, -20], [300, 20]]}]}
        self.assertEqual(spans_of(styled("grass", **tw)), [(0, 97, "grass"), (97, 115, "embedded"), (115, 299, "grass"),
                                                          (299, 301, "embedded"), (301, 600, "grass")])
        self.assertEqual(spans_of(styled("ballast", **tw)), [(0, 600, "ballast")])   # (open ballast through them)


class OtherTracks(unittest.TestCase):
    """#546: every drawn track's own sections beyond our route."""

    def test_a_side_track_gets_its_crossings_diamond_and_switch(self):
        side = {"p": [[300.0, 20.0], [300.0, 220.0]]}                        # (40 m off our route at its nearest)
        branch = {"p": [[300.0, 120.0], [400.0, 160.0]]}                     # (leaves the side track at its y 120)
        across = {"p": [[250.0, 180.0], [350.0, 180.0]]}                     # (crosses it square at y 180)
        near = {"p": [[0.0, 3.0], [600.0, 3.0]]}                             # (the opposite track: the route's style)
        data = {"path": [[0.0, 0.0], [600.0, 0.0]], "tracks": [side, branch, across, near],
                "roads": [{"p": [[280, 60], [320, 60]], "w": 8, "c": 1}]}
        own = T.track_sections(data, None)
        self.assertNotIn(3, own)
        s = [(round(a), round(b), st) for a, b, st in own[0]]
        self.assertEqual(s, [(36, 44, "embedded"), (92, 108, "embedded"), (159, 161, "embedded")])   # (the road, the switch, the diamond)
        self.assertEqual([(round(a), round(b)) for a, b, _ in own[1]], [(0, 15)])   # (it leaves the side track)

    def test_green_under_a_side_track_is_grass(self):
        sv = T.Survey({"areas": [rect(290, 310, 40, 120, "green")]})
        own = T.track_sections({"path": [[0.0, 0.0], [600.0, 0.0]], "tracks": [{"p": [[300.0, 20.0], [300.0, 220.0]]}]}, sv)
        self.assertEqual([(a, b, st) for a, b, st in own[0]], [(20.0, 100.0, "grass")])


def styled(style, **extra):
    """A 600 m straight route, one mark of `style` over all of it, and what crosses it."""
    data = {"line": "x", "path": [[0.0, 0.0], [600.0, 0.0]], "stops": [{"name": "A", "s": 0.0}, {"name": "B", "s": 600.0}], **extra}
    return T.sections(data, {"trackStyles": [{"line": "x", "from": "A", "to": "B", "style": style}]}, None)


def spans_of(secs):
    return [(round(x["s0"]), round(x["s1"]), x["style"]) for x in secs]


class Holes(unittest.TestCase):
    PLATFORM = {"platforms": [{"p": [[200, 1.5], [240, 1.5], [240, 4], [200, 4]]}]}
    STREETS = {"roads": [{"p": [[300, -20], [300, 20]], "w": 2, "f": 1}, {"p": [[400, -20], [400, 20]], "w": 8, "c": 1},
                         {"p": [[0, 30], [600, 30]], "w": 8, "c": 1},                                  # (along, away)
                         {"p": [[500, -20], [500, 20]], "w": 8, "c": 1, "b": 1}]}                      # (a bridge over)

    def test_grass_stops_at_a_platform_and_ballast_runs_past_it(self):
        self.assertEqual(spans_of(styled("grass", **self.PLATFORM)), [(0, 197, "grass"), (243, 600, "grass")])
        self.assertEqual(spans_of(styled("ballast", **self.PLATFORM)), [(0, 600, "ballast")])

    def test_both_stop_at_crossings_and_a_street_across_is_embedded(self):
        want = [(0, 296, "{0}"), (304, 388, "{0}"), (388, 412, "embedded"), (412, 600, "{0}")]   # (half the width + HOLE)
        for style in ("grass", "ballast"):
            self.assertEqual(spans_of(styled(style, **self.STREETS)), [(a, b, s.format(style)) for a, b, s in want])

    def test_a_street_under_our_bridge_neither_cuts_nor_embeds(self):
        under = {"roads": [{"p": [[400, -20], [400, 20]], "w": 8, "c": 1}], "bridges": [[350.0, 450.0]]}
        self.assertEqual(spans_of(styled("ballast", **under)), [(0, 600, "ballast")])
        data = {"line": "x", "path": [[0.0, 0.0], [600.0, 0.0]], "stops": [{"name": "A", "s": 0.0}, {"name": "B", "s": 600.0}], **under}
        self.assertEqual(spans_of(T.sections(data, {}, None)), [])

    def test_the_users_surface_answers_lay_setts_and_a_setts_junction_from_fork_to_fork(self):
        # (#574, the user 2026-11-14: a setts junction is setts "from switch fork to the other switch forks")
        ll = lambda x: list(map(float, T.Frame().ll(x, 0.0)))   # noqa: E731
        ans = lambda i, what, a, b, v: {"id": i, "what": what, "line": "x", "between": [ll(a), ll(b)], "answer": v}  # noqa: E731
        truth = {"trackSurfaceReview": {"answers": [ans("st", "stretch", 100, 200, "setts"),
                                                    ans("jn", "junction", 395, 405, "setts")]}}
        data = {"line": "x", "path": [[0.0, 0.0], [600.0, 0.0]], "stops": [{"name": "A", "s": 0.0}, {"name": "B", "s": 600.0}],
                "switches": [{"s": 150, "frog": 12}, {"s": 380, "frog": 12}, {"s": 410, "frog": 12}]}
        got = spans_of(T.sections(data, truth, None))
        # (the stretch keeps its switch; the answered junction's two switches joined, setts from fork to fork)
        self.assertEqual(got, [(100, 200, "setts"), (377, 425, "setts")])
        self.assertEqual(spans_of(T.sections(data, {}, None)), [(147, 165, "embedded"), (377, 425, "embedded")])

    def test_switches_do_not_cut_and_short_pieces_go(self):
        tw = {"switches": [{"s": 100, "frog": 12}], "trackwork": {"trailing": [{"s": 200, "frog": 12}], "crossings": [250.0]}}
        self.assertEqual(spans_of(styled("ballast", **tw)), [(0, 600, "ballast")])   # (open ballast through the switches)
        secs = styled("grass", crossings=[130.0, 145.0])
        self.assertEqual(spans_of(secs), [(0, 125, "grass"), (150, 600, "grass")])   # (the 10 m between them: too short)
        self.assertEqual(spans_of(styled("panels", **self.STREETS)), [(0, 600, "panels")])

    def test_a_platform_passed_twice_has_a_hole_on_each_pass(self):
        data = {"line": "x", "path": [[0.0, 0.0], [600.0, 0.0], [600.0, -3.0], [0.0, -3.0]],
                "stops": [{"name": "A", "s": 0.0}, {"name": "B", "s": 1203.0}], **self.PLATFORM}
        hs = [(round(h["s0"]), round(h["s1"])) for h in T.holes(data) if h["kind"] == "platform"]
        self.assertEqual(hs, [(197, 243), (960, 1006)])


class Lift(unittest.TestCase):
    TRUTH = {"trackHeights": {"railAboveDeck": [
        {"id": "a", "metres": 0.0, "styles": ["embedded", "setts", "panels"], "scope": "all"},
        {"id": "g", "metres": 0.04, "styles": ["grass"], "scope": "all"},
        {"id": "b", "metres": 0.17, "styles": ["ballast"], "scope": "all"}]}}

    def test_the_offset_blends_in_inside_the_section(self):
        off = T.offsets(self.TRUTH)
        secs = [{"s0": 100, "s1": 200, "style": "ballast"}, {"s0": 300, "s1": 310, "style": "grass"}]
        at = lambda s: round(T.lift(secs, off, s), 4)  # noqa: E731
        self.assertEqual([at(s) for s in (99, 100, 107.5, 115, 150, 185, 200, 201)], [0, 0, 0.085, 0.17, 0.17, 0.17, 0, 0])
        self.assertEqual([at(s) for s in (300, 305, 310)], [0, 0.04, 0])   # (a short one: over half its length)

    def test_a_changed_fact_moves_the_lift_and_a_conflict_stops_the_build(self):
        truth = json.loads(json.dumps(self.TRUTH))
        truth["trackHeights"]["railAboveDeck"][1]["metres"] = 0.09
        data = {"path": [[0.0, 0.0], [100.0, 0.0]]}
        series = T.lift_series(data, [{"s0": 0, "s1": 100, "style": "grass"}], T.offsets(truth))
        self.assertEqual((series["step"], series["unit"], series["v"][25]), (2, 0.001, 90))
        truth["trackHeights"]["railAboveDeck"].append({"id": "x", "metres": 0.05, "styles": ["grass"], "scope": "all"})
        with self.assertRaises(SystemExit):
            T.offsets(truth)


if __name__ == "__main__":
    unittest.main()
