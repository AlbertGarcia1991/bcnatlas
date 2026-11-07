import unittest
from unittest.mock import patch
import numpy as np
from scipy import stats
from scripts.analytics.statistics import standardized,weights,spectrum,moran,spatial_pvalues,partial_rank,cluster_interval
from scripts.analytics.extract import role,locate

class AnalyticsStatisticsTests(unittest.TestCase):
    def test_rank_correlation_matches_scipy_with_ties(self):
        x=np.array([1,1,2,3,7,8]);y=np.array([9,2,4,6,7,1])
        z=standardized(np.column_stack([x,y]),True)
        self.assertAlmostEqual(z[:,0]@z[:,1],stats.spearmanr(x,y).statistic,places=12)
    def test_spectral_null_preserves_spatial_energy_variance_and_mean(self):
        rng=np.random.default_rng(3);w=weights(rng.normal(size=(73,2)));_,mem=spectrum(w)
        z=standardized(rng.normal(size=73),True);surrogate=mem@(rng.choice([-1,1],72)*(mem.T@z))
        self.assertAlmostEqual(float(surrogate.mean()),0,places=12)
        self.assertAlmostEqual(float(surrogate@surrogate),float(z@z),places=12)
        self.assertAlmostEqual(moran(z,w),moran(surrogate,w),places=12)
    def test_spatial_pvalues_are_reproducible_and_symmetric(self):
        rng=np.random.default_rng(7);coords=rng.normal(size=(45,2));x=rng.normal(size=(45,2));y=rng.normal(size=(45,2))
        p=spatial_pvalues(x,y,coords,n_perm=199)
        np.testing.assert_array_equal(p,spatial_pvalues(x,y,coords,n_perm=199))
        np.testing.assert_array_equal(p,spatial_pvalues(y,x,coords,n_perm=199))
        self.assertTrue(np.all((p>=1/200)&(p<=1)))
    def test_known_signal_and_independent_negative_control(self):
        rng=np.random.default_rng(101);coords=rng.normal(size=(73,2));x=rng.normal(size=(73,1))
        self.assertLessEqual(spatial_pvalues(x,x,coords,n_perm=999)[0],.01)
        self.assertGreater(spatial_pvalues(x,rng.normal(size=(73,1)),coords,n_perm=999)[0],.05)
    def test_adjustment_removes_a_pure_district_effect(self):
        district=np.repeat(np.arange(10),7);x=district.astype(float);y=x.copy()
        self.assertIsNone(partial_rank(x,y,district))
    def test_block_interval_and_sparse_blocks(self):
        x=np.arange(70,dtype=float);d=np.repeat(np.arange(10),7)
        ci=cluster_interval(x,x,d,reps=199)
        np.testing.assert_allclose(ci,[1,1],atol=1e-12)
        self.assertIsNone(cluster_interval(x,x,np.zeros(70)))
    def test_geographic_codes_are_not_outcomes(self):
        for name in ['cat_especie_id','addresses_zip_code','values_value','Coordenada_UTM_X','Telefon_Preferent','_records']:
            self.assertNotEqual(role(name),'candidate')
        for name in ['Import_Euros','Mesura','Mesura_mínima','mesde84']:
            self.assertEqual(role(name),'candidate')
    def test_district_totals_are_never_replicated_into_neighbourhoods(self):
        with patch('scripts.analytics.extract.INDEX',{'neighbourhood':{},'district':{'1':0}}),patch('scripts.analytics.extract.REF',{'names':{}}):
            n,d=locate({'Codi_Districte':'1','Valor':32})
        self.assertIsNone(n);self.assertEqual(d,0)

if __name__=='__main__':unittest.main()
