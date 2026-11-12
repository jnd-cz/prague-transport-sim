"""tools/osm_local.py: the extract's index answers as a pass over the extract does (#511).

    python -P -E tools/test_osm_local.py

A small extract written here: tagged and untagged nodes, ways with every node located, with one node missing from
the file and with a single located node, relations with and without tags. Each query from the index is compared with
the same query as a pass over a copy of the file (a src other than the extract's path takes the pass).
"""
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    import osmium
    import osm_local
except ImportError:  # (pyosmium: python -P -E)
    osmium = None


@unittest.skipIf(osmium is None, "needs pyosmium (python -P -E)")
class IndexTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="test_osm_local_")
        self.addCleanup(shutil.rmtree, self.dir, True)
        pbf = os.path.join(self.dir, "praha.osm.pbf")
        M = osmium.osm.mutable
        w = osmium.SimpleWriter(pbf)
        pts = {1: (14.40, 50.08), 2: (14.41, 50.081), 3: (14.42, 50.082), 4: (14.50, 50.10), 5: (14.51, 50.101),
               6: (14.6, 50.2), 7: (14.43, 50.083)}
        tags = {1: {"highway": "traffic_signals"}, 3: {"kerb": "lowered", "name": "Žižkov"},
                4: {"railway": "tram_stop", "name": "A"}, 6: {"public_transport": "stop_position", "tram": "yes"}}
        for i, (lon, lat) in pts.items():
            w.add_node(M.Node(id=i, location=(lon, lat), tags=tags.get(i, {})))
        ways = [(10, [1, 2, 3], {"railway": "tram"}), (11, [4, 5], {"building": "yes", "name": "Dům"}),
                (12, [2, 99, 3], {"highway": "residential"}),  # (node 99 not in the file)
                (13, [5, 98], {"highway": "service"}),  # (one located node: no way for the queries)
                (14, [1, 7], {}),  # (untagged)
                (15, [6, 4], {"leisure": "park"}), (16, [3, 7], {"railway": "platform"})]
        for i, nds, t in ways:
            w.add_way(M.Way(id=i, nodes=nds, tags=t))
        w.add_relation(M.Relation(id=100, members=[("w", 10, ""), ("n", 4, "stop")], tags={"type": "route", "route": "tram", "ref": "9"}))
        w.add_relation(M.Relation(id=101, members=[("w", 14, "outer")], tags={}))
        w.close()
        self.copy = os.path.join(self.dir, "copy.osm.pbf")
        shutil.copy(pbf, self.copy)
        for k, v in {"PRAHA": pbf, "DIR": self.dir, "_INDEX": None, "_STORE": None}.items():
            p = mock.patch.object(osm_local, k, v)
            p.start()
            self.addCleanup(p.stop)
        p = mock.patch.dict(os.environ, {"TRAMDATA_CACHE": os.path.join(self.dir, "cache")})
        p.start()
        self.addCleanup(p.stop)

    def test_ways(self):
        for match in (lambda t: True, lambda t: "highway" in t, lambda t: t.get("railway") == "tram", lambda t: False):
            for bbox in (None, (50.0795, 14.395, 50.0805, 14.405), (50.09, 14.45, 50.2, 14.6), (51, 15, 52, 16)):
                self.assertEqual(osm_local.ways(match, bbox), osm_local.ways(match, bbox, src=self.copy), bbox)
        self.assertEqual([w["id"] for w in osm_local.ways(lambda t: True)], [10, 11, 12, 15, 16])

    def test_nodes_relations(self):
        for match in (lambda t: True, lambda t: t.get("kerb") == "lowered", lambda t: False):
            self.assertEqual(osm_local.nodes(match), osm_local.nodes(match, src=self.copy))
            self.assertEqual(osm_local.relations(match), osm_local.relations(match, src=self.copy))
        self.assertEqual(osm_local.nodes(lambda t: "kerb" in t)[0]["tags"]["name"], "Žižkov")

    def test_store(self):
        st = osm_local._store()
        every = osm_local.ways(lambda t: True, src=self.copy)
        for k, ws in st["kinds"].items():
            want = [w for w in every if k in osm_local._kinds(w["tags"])]
            self.assertEqual([osm_local._way(w) for w in ws], want, k)
        self.assertEqual(osm_local._ways_by_id({12, 10, 16}), [w for w in every if w["id"] in (10, 12, 16)])
        # (the file sequence among the tagged ways: 13 counted though it is no way for the queries, 14 untagged not)
        self.assertEqual([w[0] for w in st["ways"].values()], [1, 2, 3, 5, 6])
        self.assertEqual(st["node_tags"], {n["id"]: __import__("json").dumps(n["tags"]) for n in osm_local.nodes(lambda t: True, src=self.copy)})
        self.assertEqual([n["id"] for n in st["points"]], [1])
        self.assertEqual([n["id"] for n in st["stoppos"]], [4, 6])

    def test_index_written_once(self):
        osm_local.ways(lambda t: True)
        d = osm_local._index_dir()
        self.assertTrue(os.path.exists(os.path.join(d, "done")))
        self.assertTrue(d.startswith(os.path.join(self.dir, "cache", "osm-index")))
        osm_local._INDEX = None
        with mock.patch.object(osm_local, "_build_index", side_effect=AssertionError("built again")):
            # (the index's key holds _build_index's source: patched, it would be another key; the folder is the same one)
            with mock.patch.object(osm_local, "_index_dir", return_value=d):
                osm_local.ways(lambda t: True)
        self.assertFalse(os.path.exists(f"{d}.lock"))


if __name__ == "__main__":
    unittest.main()
