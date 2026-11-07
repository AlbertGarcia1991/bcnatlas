"""Area-level association statistics; no causal claims.

Moran spectral randomization (singleton sign flips) follows Wagner & Dray
(2015), using the full centred spectrum of symmetric five-nearest-neighbour
weights. Randomization preserves the observed rank vector's variance and
Moran quadratic form. The null is conditional on that spatial spectrum.
"""
import numpy as np
from scipy import linalg, stats
from scipy.spatial.distance import cdist

SEED=20261107
PERMUTATIONS=9999
MIN_AREAS=30

def weights(coordinates,k=5):
    d=cdist(coordinates,coordinates);np.fill_diagonal(d,np.inf)
    w=np.zeros_like(d);nearest=np.argsort(d,axis=1)[:,:min(k,len(d)-1)]
    w[np.arange(len(d))[:,None],nearest]=1
    return np.maximum(w,w.T)

def spectrum(w):
    q=linalg.null_space(np.ones((1,len(w))))
    eigenvalues,vectors=linalg.eigh(q.T@w@q)
    return eigenvalues,q@vectors

def standardized(x,rank=False):
    z=stats.rankdata(x,axis=0) if rank else np.asarray(x,dtype=float)
    z=z-z.mean(axis=0);length=np.linalg.norm(z,axis=0)
    return np.divide(z,length,out=np.zeros_like(z),where=length>1e-12)

def moran(x,w):
    z=np.asarray(x)-np.mean(x)
    return float(len(z)/w.sum()*(z@w@z)/(z@z)) if z@z>0 else None

def partial_rank(x,y,districts,population=None):
    groups=np.unique(districts)
    controls=np.column_stack([np.ones(len(x)),*[districts==g for g in groups[1:]]])
    if population is not None and np.isfinite(population).all():controls=np.column_stack([controls,stats.rankdata(population)])
    rank=stats.rankdata(np.column_stack([x,y]),axis=0)
    residual=rank-controls@np.linalg.lstsq(controls,rank,rcond=None)[0]
    if np.any(np.linalg.norm(residual,axis=0)<1e-9):return None
    return float(standardized(residual)[:,0]@standardized(residual)[:,1])

def spatial_pvalues(x,y,coordinates,seed=SEED,n_perm=PERMUTATIONS):
    """Columns are paired variables with the same complete-case geographic mask."""
    w=weights(coordinates);_,mem=spectrum(w)
    zx=standardized(x,True);zy=standardized(y,True)
    observed=np.sum(zx*zy,axis=0)
    products=(mem.T@zx)*(mem.T@zy)
    rng=np.random.default_rng(seed);exceed=np.zeros(len(observed),dtype=int)
    for start in range(0,n_perm,256):
        signs=rng.choice([-1.,1.],size=(min(256,n_perm-start),mem.shape[1]))
        simulated=signs@products
        exceed+=(np.abs(simulated)>=np.abs(observed)-1e-12).sum(axis=0)
    return (exceed+1)/(n_perm+1)

def cluster_interval(x,y,districts,seed=SEED,reps=1999):
    """District-block percentile bootstrap; 10 or fewer blocks, exploratory CI."""
    groups=np.unique(districts)
    if len(groups)<6:return None
    rng=np.random.default_rng(seed);draws=[]
    indices=[np.flatnonzero(districts==g) for g in groups]
    for _ in range(reps):
        selected=np.concatenate([indices[i] for i in rng.integers(len(groups),size=len(groups))])
        if len(np.unique(x[selected]))<2 or len(np.unique(y[selected]))<2:continue
        z=standardized(np.column_stack([x[selected],y[selected]]),True);draws.append(float(z[:,0]@z[:,1]))
    return np.quantile(draws,[.025,.975]).tolist() if len(draws)>.9*reps else None
