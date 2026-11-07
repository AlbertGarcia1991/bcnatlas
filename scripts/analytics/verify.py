"""Independently verify a completed evidence bundle before publication."""
import hashlib,json
from pathlib import Path
import numpy as np
from scipy import stats

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'.cache/analytics/published'

def main():
    manifest=json.loads((OUT/'manifest.json').read_text())
    totals={'comparisons':0,'spatialTests':0,'supported':0};sampled=0
    for period,meta in manifest['periods'].items():
        variables={v['index']:v for v in json.loads((OUT/f'variables/{period}.json').read_text())}
        counts=dict.fromkeys(totals,0)
        for shard in meta['shards']:
            rows=json.loads((OUT/f'pairs/{period}-{shard}.json').read_text())
            for a,b,n,rho,pearson,partial,p,q in rows:
                assert a<b and a%32==shard and a in variables and b in variables
                assert variables[a]['dataset']!=variables[b]['dataset']
                assert 8<=n<=len(manifest['areas'][meta['areaLevel']])
                assert abs(rho)<=1.000001 and abs(pearson)<=1.000001
                assert partial is None or abs(partial)<=1.000001
                assert (p is None)==(q is None)
                if p is not None:
                    assert 1/(manifest['permutations']+1)<=p<=1 and p<=q<=1
                    assert n>=manifest['minAreas'] and meta['areaLevel']=='neighbourhood' and meta['year']
                    assert variables[a]['testable'] and variables[b]['testable']
                counts['comparisons']+=1;counts['spatialTests']+=p is not None;counts['supported']+=q is not None and q<=.05
            for idx in sorted({0,len(rows)//2,len(rows)-1}) if rows else []:
                a,b,n,rho,pearson,*_=rows[idx]
                x=np.array(variables[a]['values'],dtype=float);y=np.array(variables[b]['values'],dtype=float)
                mask=np.isfinite(x)&np.isfinite(y);assert int(mask.sum())==n
                assert abs(stats.spearmanr(x[mask],y[mask]).statistic-rho)<.00000051
                assert abs(stats.pearsonr(x[mask],y[mask]).statistic-pearson)<.00000051
                sampled+=1
        for k,v in counts.items():assert v==meta[k],(period,k,v,meta[k]);totals[k]+=v
    for k,v in totals.items():assert v==manifest['counts'][k]
    assert manifest['counts']['failedEditions']==0
    report={'analysisCodeSha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'scripts/analytics').glob('*.py')},'geographicReferenceSha256':hashlib.sha256((ROOT/'.cache/map-audit/reference.json.gz').read_bytes()).hexdigest(),'manifestSha256':hashlib.sha256((OUT/'manifest.json').read_bytes()).hexdigest(),'allRowsValidated':totals,'independentlyRecomputedPairs':sampled,'checks':['partition/index integrity','same-period/geography membership','coverage and bounded effects','inference eligibility and probability bounds','full family totals','sampled Spearman/Pearson against SciPy']}
    (ROOT/'docs/analytics-bundle-validation.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))
if __name__=='__main__':main()
