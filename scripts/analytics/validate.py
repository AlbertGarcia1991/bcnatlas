"""Independent numerical calibration report for the implemented spatial null."""
import json
import numpy as np
from scipy import stats
from scripts.analytics.statistics import weights,spectrum,spatial_pvalues,standardized,moran
from server.storage import ROOT

def main():
    rng=np.random.default_rng(43);coordinates=rng.normal(size=(73,2));_,mem=spectrum(weights(coordinates));scale=1/(1+np.arange(72))[::-1]
    x=mem@(rng.normal(size=(72,1000))*scale[:,None]);y=mem@(rng.normal(size=(72,1000))*scale[:,None])
    p=spatial_pvalues(x,y,coordinates,n_perm=999)
    rejected=int((p<=.05).sum());ci=stats.binomtest(rejected,1000).proportion_ci(confidence_level=.95)
    z=standardized(x[:,0],True);surrogate=mem@(rng.choice([-1.,1.],72)*(mem.T@z));w=weights(coordinates)
    report={'seed':43,'pairs':1000,'areas':73,'randomizationsPerPair':999,'nominalAlpha':.05,'rejections':rejected,'empiricalRate':rejected/1000,'binomial95PercentInterval':[ci.low,ci.high],'nominalRateWithinInterval':bool(ci.low<=.05<=ci.high),'maximumInvariantError':max(abs(float(z.mean()-surrogate.mean())),abs(float(z@z-surrogate@surrogate)),abs(moran(z,w)-moran(surrogate,w))),'scope':'Independent strongly spatial Gaussian fields on one simulated 73-area graph; implementation calibration only, not a guarantee of calibration for all municipal data or spatial processes.'}
    (ROOT/'docs/analytics-validation.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
