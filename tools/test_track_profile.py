# SPDX-License-Identifier: AGPL-3.0-or-later
"""Vertical profile rule (#188): python -P -E tools/test_track_profile.py."""
import math
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parent))

from track_profile import banded_profile, chains, vertical_profile, implied_radii, radii, _solve, whittaker

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
        self.assertEqual(radii(),{'street':500,'open':1000,'switch':1000,'min':500})

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


class BandRule(unittest.TestCase):
    s = [2.5+5*k for k in range(60)]

    def test_a_noisy_curve_at_the_radius_fits_the_band_and_its_noise_is_not_followed(self):
        true = [100+(x-150)**2/1500 for x in self.s]                       # a 750 m sag
        z = [t+(.04 if k % 2 else -.04) for k,t in enumerate(true)]        # +-4 cm of noise
        out = banded_profile(self.s,z,500,.10)
        self.assertTrue(out['fits'])
        self.assertLess(max(abs(a-b) for a,b in list(zip(out['z'],true))[2:-2]),.015)  # (a free end follows its point)
        self.assertGreater(out['min_radius'],490)

    def test_a_sag_tighter_than_the_radius_does_not_fit_and_says_where(self):
        z = [100-.06*x if x < 144 else 100-.06*144+.06*(x-156) if x > 156 else 100-.06*x+(x-144)**2/200 for x in self.s]
        out = banded_profile(self.s,z,500,.10)
        self.assertFalse(out['fits'])
        worst = max(range(len(z)),key=lambda i: out['excess'][i])
        self.assertLess(abs(self.s[worst]-150),25)  # (in the sag or the ends of its wider 500 m transition)
        self.assertTrue(banded_profile(self.s,z,100,.10)['fits'])

    def test_a_point_without_band_and_weight_does_not_pull(self):
        z = [100.0]*len(self.s)
        z[30] = 101.0                                                      # a lone bad point, given no band
        tol = [.10]*len(z)
        tol[30] = None
        out = banded_profile(self.s,z,500,tol,weight=[0.0 if k == 30 else 1.0 for k in range(len(z))])
        self.assertTrue(out['fits'])
        self.assertLess(abs(out['z'][30]-100),.05)


class Whittaker(unittest.TestCase):
    def s(self):
        return [i * 5.0 for i in range(200)]

    def test_a_grade_and_a_vertical_curve_stay(self):
        for z in ([100 + .03 * v for v in self.s()], [100 + v * v / 1000 for v in self.s()]):
            self.assertLess(max(abs(a - b) for a, b in zip(whittaker(self.s(), z, 70), z)), .001)

    def test_a_short_wave_goes_and_a_long_one_stays(self):
        amp = lambda L: max(abs(v) for v in whittaker(self.s(), [math.sin(2 * math.pi * v / L) for v in self.s()], 70)[40:160])
        self.assertLess(amp(30), .05)
        self.assertGreater(amp(256), .95)

    def test_a_bad_point_does_not_pull_its_neighbours(self):
        z = [100 + .01 * v for v in self.s()]
        z[100] += 1.0
        f = whittaker(self.s(), z, 70)
        self.assertLess(abs(f[100] - (100 + .01 * self.s()[100])), .02)


class Chains(unittest.TestCase):
    def test_ends_a_centimetre_apart_across_a_cell_boundary_are_one_track(self):
        # (0.149 and 0.151 m: rounded to a 0.3 m grid they fell in two cells, and the track was two chains, #358)
        paths = {'a': [(-100.0, 0.0), (0.149, 0.0)], 'b': [(0.151, 0.0), (100.0, 0.0)]}
        self.assertEqual(chains(paths), [[('a', False), ('b', False)]])

    def test_ends_further_apart_stay_two_tracks(self):
        paths = {'a': [(-100.0, 0.0), (0.0, 0.0)], 'b': [(0.5, 0.0), (100.0, 0.0)]}
        self.assertEqual(len(chains(paths)), 2)

    def test_a_diverging_path_starts_its_own_chain(self):
        paths = {'a': [(-100.0, 0.0), (0.0, 0.0)], 'b': [(0.0, 0.0), (100.0, 0.0)], 'c': [(0.0, 0.0), (100.0, 20.0)]}
        out = chains(paths)
        self.assertIn([('a', False), ('b', False)], out)
        self.assertIn([('c', False)], out)


class BandedSystem(unittest.TestCase):
    def test_banded_system_solves_as_a_dense_one(self):
        """#516: the ADMM steps' system solved by its banded Cholesky factor (LAPACK) as a dense solve of it, pins and all."""
        import numpy as np
        import track_profile as tp
        rng = np.random.default_rng(3)
        s = np.cumsum(rng.uniform(3, 7, 400))
        D = tp._D(s)
        w = rng.uniform(0, 1, 400)
        w[::50] = 1e6
        lam = np.full(398, 2*np.median(np.diff(s))**4)
        b = rng.normal(0, 1, 400)*w
        m = np.zeros((398, 400))
        i = np.arange(398)
        m[i, i], m[i, i+1], m[i, i+2] = D.l, D.c, D.r
        dense = np.linalg.solve(np.diag(w)+(m.T*lam)@m, b)
        self.assertLess(np.max(np.abs(D.system(w, lam)(b)-dense)), 1e-9)


if __name__=='__main__':
    unittest.main(verbosity=2)
