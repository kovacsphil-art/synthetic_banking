"""Fabricated aggregates only; the candidate is not an active generation mode."""
import unittest
import numpy as np
from synthetic_banking.dependency_sampling import mean_matched_quantile_candidate


class MeanCalibrationTests(unittest.TestCase):
    def test_matches_population_mean_without_moving_quantile_knots(self):
        p=np.array([0,.25,.5,.75,1.]); q=np.array([0,5,15,30,80.])
        x=np.linspace(0,80,5001)
        result,d=mean_matched_quantile_candidate(x,p,q,23.)
        self.assertAlmostEqual(d['implied_calibrated_mean'],23.,places=12)
        self.assertTrue(np.all(np.diff(result)>=0))
        knots,_=mean_matched_quantile_candidate(q,p,q,23.)
        np.testing.assert_array_equal(knots,q)
        self.assertEqual(result[0],0);self.assertEqual(result[-1],80)
        # Numerically integrate the transformed inverse CDF independently.
        u=(np.arange(200000)+.5)/200000
        draws=np.interp(u,p,q)
        transformed,_=mean_matched_quantile_candidate(draws,p,q,23.)
        self.assertAlmostEqual(transformed.mean(),23.,places=4)

    def test_constant_tied_quantiles_nulls_and_repeatability(self):
        q=[0,0,5,5,10];p=[0,.1,.5,.9,1]
        x=np.array([0,1,5,9,10,np.nan])
        y,_=mean_matched_quantile_candidate(x,p,q,4.)
        repeated,_=mean_matched_quantile_candidate(x,p,q,4.)
        np.testing.assert_array_equal(y,repeated);self.assertTrue(np.isnan(y[-1]))
        constant,_=mean_matched_quantile_candidate([4,np.nan],[0,1],[4,4],4.)
        np.testing.assert_array_equal(constant,[4,np.nan])

    def test_invalid_evidence_is_rejected_without_extrapolation(self):
        for p,q,mean,x in (([0,1],[0,10],-1,[1]),([0,1],[0,10],10,[1]),
                            ([0,.5,.5,1],[0,1,2,3],1,[1]),([0,1],[10,0],5,[1]),
                            ([0,1],[0,np.inf],5,[1]),([0,1],[0,10],5,[11]),
                            ([0,1],[4,4],5,[4]),([0,1],[0,10],5,[np.inf])):
            with self.subTest(p=p,q=q,mean=mean),self.assertRaises(ValueError):
                mean_matched_quantile_candidate(x,p,q,mean)

    def test_fitted_candidate_does_not_change_active_registry(self):
        from synthetic_banking.rules import _SAMPLING_IMPLEMENTATIONS
        self.assertEqual(_SAMPLING_IMPLEMENTATIONS['TKQ_ACCOUNT_BALANCE','CURRENT_BALANCE_AMT'][3].__name__,
                         'conditional_numeric_rank_v1')
