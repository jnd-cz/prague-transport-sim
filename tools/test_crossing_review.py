"""Place-based held-patch queue: python -I tools/test_crossing_review.py."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from crossing_review import findings


class CrossingReview(unittest.TestCase):
    def test_duplicate_layers_share_a_place_and_rebuilds_keep_its_identity(self):
        site={'x':10.01,'y':20.02,'s':100,'ux':1,'uy':0,'area':7,'sourceId':8}
        report={'line':'17','result':{'reviewCandidates':[site,{**site,'area':9,'sourceId':10}]}}
        lines={'17':{'stops':[{'name':'Test stop','s':90}]}}
        rows=findings([report],lines)
        self.assertEqual(len(rows),1)
        self.assertEqual(len(rows[0]['candidates']),2)
        self.assertEqual(rows[0]['status'],'review')
        self.assertIn('Test stop',rows[0]['info'])
        self.assertIn('review=',rows[0]['review_url'])
        report['result']['reviewCandidates']=[{**site,'area':77,'sourceId':88}]
        self.assertEqual(rows[0]['id'],findings([report],lines)[0]['id'])


if __name__=='__main__':
    unittest.main(verbosity=2)
