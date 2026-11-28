# SPDX-License-Identifier: AGPL-3.0-or-later
"""tools/features.py: the feature layer's records from the survey's points and shelter footprints (#14).

    python -P -E tools/test_features.py
"""
import json
import pathlib
import sys
import unittest
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import features as F  # noqa: E402
import rebuild  # noqa: E402
import sources  # noqa: E402
from geo import ORIGIN, ROOT  # noqa: E402


def point(oid, code, x, y):
    """A raw survey point whose `lat`, `lon` are the frame's y, x (the tests' to_xy turns them back)."""
    return {"attributes": {"objectid": oid, "ctmtp_kod": code}, "geometry": {"x": x, "y": y}}


XY = lambda lat, lon: (lon, lat)  # noqa: E731
EAST = [{"p": [[0, 0], [100, 0]], "c": 1, "f": 0}]  # a carriageway running east
LINE = {"roads": EAST, "path": [[0, 5], [100, 5]], "pathBack": [[100, 9], [0, 9]]}


class Points(unittest.TestCase):
    def test_a_record_has_the_sources_id_its_kind_place_and_mount(self):
        recs = F.survey_points({"features": [point(7, 106200, 10.004, 2.0), point(8, 606561, 3, 4), point(9, 999999, 0, 0),
                                             {"attributes": {"objectid": 10, "ctmtp_kod": 606010}}]}, XY)
        self.assertEqual(recs, [
            {"id": "dtmp:7", "kind": "manhole", "x": 10.0, "y": 2.0, "mount": "ground", "source": "dtmpoints"},
            {"id": "dtmp:8", "kind": "light_on_building", "x": 3, "y": 4, "mount": "wall", "source": "dtmpoints"}])  # (a code not kept, a point with no place)

    def test_one_cover_per_shaft_and_every_lamp(self):
        raw = {"features": [point(1, 106200, 0, 0), point(2, 406081, 0.2, 0.29), point(3, 106200, 0.31, 0),  # two networks' codes of one shaft; the next
                            point(4, 406140, 0.1, 0.1),  # another kind at the same place stays
                            point(5, 606560, 50, 0), point(6, 606560, 50.1, 0)]}  # two lamps 0.1 m apart: both
        kept, dropped = F.merge(F.survey_points(raw, XY))
        self.assertEqual((sorted(o["id"] for o in kept), dropped), (["dtmp:1", "dtmp:3", "dtmp:4", "dtmp:5", "dtmp:6"], 1))

    def test_a_grate_lies_along_the_nearest_street(self):
        roads = EAST + [{"p": [[50, 30], [50, 80]], "c": 1, "f": 0}, {"p": [[0, 2], [100, 2.5]], "c": 0, "f": 1}]  # (a footway is no street)
        recs = [{"id": "a", "kind": "gutter_inlet", "x": 20, "y": 3}, {"id": "b", "kind": "gutter_inlet", "x": 52, "y": 60},
                {"id": "c", "kind": "gutter_inlet", "x": 20, "y": 500}, {"id": "d", "kind": "manhole", "x": 20, "y": 3}]
        F.along_streets(recs, roads)
        self.assertEqual([(o.get("heading"), o.get("headingFrom")) for o in recs], [(90.0, "street"), (0.0, "street"), (None, None), (None, None)])


class Shelters(unittest.TestCase):
    FOOT = {"x": 40.0, "y": 2.0, "length": 4.07, "width": 1.43, "bearing": 0.0, "z": 193.2, "stop": {"name": "Dvorce", "code": "B", "id": "U110Z2P"}}

    def test_it_faces_the_nearer_track(self):
        south = F.shelters([self.FOOT], [[[0, -3], [100, -3]]])[0]
        north = F.shelters([self.FOOT], [[[0, -30], [100, -30]], [[0, 7], [100, 7]]])[0]
        self.assertEqual((south["heading"], north["heading"], north["headingFrom"]), (180.0, 0.0, "footprint"))

    def test_its_id_is_its_place_whichever_line_sees_it(self):
        a = F.shelters([self.FOOT], [])[0]
        b = F.shelters([self.FOOT | {"x": 40.6, "y": 1.7, "stop": None}], [[[0, 9], [9, 9]]])[0]  # (another line's survey of it, 0.7 m off)
        self.assertEqual(a["id"], f"shelter:zps:{round((40 + ORIGIN[0]) / 2) * 2},{round((2 + ORIGIN[1]) / 2) * 2}")
        self.assertEqual(a["id"], b["id"])
        self.assertEqual((a["kind"], a["source"], a["stop"], b["stop"], a["length"], a["width"], a["z"]), ("shelter", "zps", "U110Z2P", None, 4.07, 1.43, 193.2))


class File(unittest.TestCase):
    RAW = {"features": [point(1, 106200, 10, 1), point(2, 106300, 30, 1), point(3, 106300, 20, 900), point(4, 606561, 5, 5), point(5, 606560, 6, 6)]}

    def test_the_groups_give_the_records_back(self):
        out, n_pts, n_shel = F.compile_line(self.RAW, LINE, {"shelters": [Shelters.FOOT]}, XY)
        self.assertEqual((out["version"], n_pts, n_shel, out["merged"]), (F.VERSION, 5, 1, 0))
        self.assertEqual([(g["kind"], g["source"], g["mount"], len(g["id"])) for g in out["groups"]],
                         [("gutter_inlet", "dtmpoints", "ground", 2), ("light_on_building", "dtmpoints", "wall", 1),
                          ("light_on_pole", "dtmpoints", "ground", 1), ("manhole", "dtmpoints", "ground", 1), ("shelter", "zps", "ground", 1)])
        inlets = out["groups"][0]
        self.assertEqual((inlets["heading"], inlets["headingFrom"], inlets["xy"]), ([None, 90.0], "street", [20, 900, 30, 1]))  # (one far from any street)
        self.assertNotIn("heading", out["groups"][3])
        recs = F.records(json.loads(json.dumps(out["groups"])))
        self.assertEqual(len(recs), 6)
        self.assertIn({"id": "dtmp:2", "kind": "gutter_inlet", "x": 30, "y": 1, "mount": "ground", "source": "dtmpoints", "heading": 90.0, "headingFrom": "street"}, recs)
        self.assertIn({"id": "dtmp:3", "kind": "gutter_inlet", "x": 20, "y": 900, "mount": "ground", "source": "dtmpoints"}, recs)
        shelter = next(o for o in recs if o["kind"] == "shelter")
        self.assertEqual((shelter["heading"], shelter["stop"], shelter["length"]), (0.0, "U110Z2P", 4.07))

    def test_two_features_with_one_id_stop_the_build(self):
        with self.assertRaises(ValueError):
            F.compile_line({"features": [point(1, 106200, 10, 1), point(1, 606560, 60, 1)]}, LINE, None, XY)

    def test_the_review_export_is_in_the_citys_grid(self):
        gj = F.geojson([{"id": "dtmp:2", "kind": "gutter_inlet", "x": 30, "y": 1.5, "mount": "ground", "source": "dtmpoints", "heading": 90.0}], "17")
        f = gj["features"][0]
        self.assertEqual(f["geometry"]["coordinates"], [30 + ORIGIN[0], 1.5 + ORIGIN[1]])
        self.assertEqual(f["properties"], {"id": "dtmp:2", "kind": "gutter_inlet", "mount": "ground", "source": "dtmpoints", "heading": 90.0, "type": "gutter_inlet"})
        self.assertIn("5514", gj["crs"]["properties"]["name"])


class Build(unittest.TestCase):
    def test_the_layer_is_built_after_the_survey_and_its_sources_are_the_chains(self):
        for line in ("9", "17", "22", "23", "37"):
            self.assertEqual(rebuild.after(line)[-1], ["features.py", "--line", line])
            self.assertNotIn("dtm_points.py", [w[0] for w in rebuild.writers(line)])  # (it fetches; the layer is features.py's)
        self.assertEqual(sources.LAYERS["furniture"][:2], ("dtmpoints", "zps"))

    def test_the_page_and_the_build_know_the_same_kinds(self):
        """Every kind the build writes is one the page draws (src/streets.js) or has a placeholder for (src/features.js)."""
        js = pathlib.Path(ROOT, "src", "features.js").read_text(encoding="utf-8")
        streets = pathlib.Path(ROOT, "src", "streets.js").read_text(encoding="utf-8")
        placeholder = js[js.index("export const PLACEHOLDER"):js.index("};", js.index("export const PLACEHOLDER"))]
        drawn = streets[streets.index("const kinds = {"):streets.index("};", streets.index("const kinds = {"))]
        for kind in sorted(set(F.DTMP.values()) | {"shelter"}):
            self.assertTrue(f"{kind}: {{" in placeholder or f"{kind}: {{" in drawn, kind)
        self.assertIn(f"export const VERSION = {F.VERSION};", js)


if __name__ == "__main__":
    unittest.main()
