"""Vertical profile rule (#188): python -P -E tools/test_track_profile.py."""
import math
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parent))

from track_profile import vertical_profile, implied_radii, radii, _solve

S = [float(x) for x in range(0,201,5)]


class VerticalProfile(unittest.TestCase):
    def test_a_sharp_break_of_grade_becomes_a_curve_of_the_design_radius(self):
        z = [200+.02*x if x <= 100 else 202-.02*(x-100) for x in S]
        out = vertical_profile(S,z,500)
        self.assertGreaterEqual(out['min_radius']*1.02,500)
        # (least change: under the 0.10 m a 500 m curve through the tangents' intersection lies below it)
        self.assertLess(max(abs(a-b) for a,b in zip(out['z'],z)),.1)
        self.assertAlmostEqual(out['z'][0],200,places=2)  # (the grades away from the break stay)

    def test_a_lone_bump_is_dropped_not_spread(self):
        # (Hlavní nádraží: 0.27 m over 7 m at an archive record joint)
        z = [200+.01*x+(.27 if x == 100 else 0) for x in S]
        out = vertical_profile(S,z,500)
        self.assertLess(out['z'][20]-201,.05)
        self.assertLess(max(abs(out['z'][i]-z[i]) for i in range(len(S)) if i != 20),.005)
        self.assertEqual([m['s'] for m in out['moved']],[100])

    def test_a_real_curve_and_a_steady_steep_grade_are_kept(self):
        for z in ([200-(x-100)**2/(2*600) for x in S],   # a 600 m crest
                  [200-.058*x for x in S]):               # Klárov: -5.8 % straight
            out = vertical_profile(S,z,500)
            self.assertLess(max(abs(a-b) for a,b in zip(out['z'],z)),1e-3)
            self.assertEqual(out['moved'],[])

    def test_a_pinned_point_holds_and_the_tighter_radius_applies_where_given(self):
        z = [200+.02*x if x <= 100 else 202-.02*(x-100) for x in S]
        out = vertical_profile(S,z,[500]*10+[1000]*(len(S)-10),pins=[20])
        self.assertAlmostEqual(out['z'][20],202,places=3)
        r = implied_radii(S,out['z'])
        self.assertGreaterEqual(min(r[9:])*1.02,1000)

    def test_radii_come_from_the_truth_facts(self):
        self.assertEqual(radii(),{'street':500,'open':1000,'switch':1000})

    def test_the_banded_solver_matches_a_dense_one(self):
        import numpy as np
        s = [0,4,9,15,18,24,31,35,41,46]
        z = [200,200.1,200.3,200.2,200.5,200.4,200.9,201,201.1,201.5]
        w = [1,2,1,.5,1,1,3,1,1,1]
        lam = [0,5,10,1,0,20,3,7,2,0]
        n = len(s)
        D = np.zeros((n,n))
        for i in range(1,n-1):
            h0, h1 = s[i]-s[i-1], s[i+1]-s[i]
            c = 2/(h0+h1)
            D[i,i-1], D[i,i], D[i,i+1] = c/h0, -c*(1/h0+1/h1), c/h1
        dense = np.linalg.solve(np.diag(w)+D.T@np.diag(lam)@D,np.array(w)*np.array(z))
        self.assertLess(max(abs(a-b) for a,b in zip(dense,_solve(s,z,w,lam))),1e-9)


if __name__=='__main__':
    unittest.main(verbosity=2)
