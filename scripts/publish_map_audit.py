"""Build the committed map allowlist and a human-readable remediation report."""
import collections
import json
import hashlib
import re
from datetime import datetime, timezone
from pathlib import Path
from server import storage
ROOT=storage.ROOT/'.cache/map-audit'

def advice(error):
    text=error.lower()
    if 'varint' in text: return 'Inspect oversized numeric identifiers or placeholder values (including postal-number fields). Clean invalid values or encode identifiers as strings before MapLibre tiles the GeoJSON.'
    if 'not yet available' in text or 'mirror' in text: return 'Complete or repair the R2 upload, then rerun the audit. Conversion may not be needed.'
    if 'limit' in text or 'deadline' in text or 'memory' in text or 'timeout' in text or 'timed out' in text: return 'Split by year/area, preaggregate records, simplify geometry or publish vector tiles; keep each response within the interactive limits.'
    if 'zero mapped' in text or 'no recognized' in text: return 'Inspect location fields and CRS. Add a coordinate parser or join district, neighbourhood, street or address identifiers to municipal reference geometry.'
    if 'no visible features' in text: return 'Inspect geometry types and extent; explode GeometryCollections and repair/reproject features into Barcelona WGS84 geometry.'
    if 'json' in text or 'xml' in text or 'structure' in text: return 'Inspect the actual payload (including possible HTML error pages); convert its record structure to a supported CSV or GeoJSON schema.'
    if 'archive' in text or 'worksheet' in text or 'layer' in text: return 'Extract the relevant archive member/worksheet/GIS layer and export it as a standalone CSV or GeoJSON resource.'
    if 'no records' in text or 'empty' in text: return 'Confirm the source contains records for this edition; omit empty periods or obtain a corrected source.'
    return 'Inspect the linked original, repair field types/geometry/encoding, and rerun both parser and browser checks.'

def clean(value): return str(value or '').replace('|','\\|').replace('\n',' ').replace('`','\'')

def runner_failure(checked):
    return any(text in checked.get('error','') for text in ('Execution context','Target page','browser has been closed','auditLayer is not a function','Page crashed','Target crashed'))

def main():
    catalog=json.loads((ROOT/'catalog.json').read_text())
    renderer_hash=hashlib.sha256((storage.ROOT/'src/mapOverlay.ts').read_bytes()).hexdigest()
    coverage=[];filter_counts=collections.Counter()
    resources={}; failures=collections.defaultdict(list); total_cases=0; color_checks=0; filtered_color_checks=0; service_checks=0; parsed_resources=0; pending=[]
    audited=[]
    for d in catalog['datasets']:
        if not d.get('mapMethods') or not any(r['previewSupported'] for r in d['resources']):continue
        audited.append(d)
        for r in d['resources']:
            if not r['previewSupported']: continue
            file=ROOT/'resources'/r['id']/'result.json'
            if not file.exists(): pending.append(r['id']);continue
            result=json.loads(file.read_text())
            if not result.get('complete'):pending.append(r['id']);continue
            parsed_resources+=1; approved=[]
            for case in result['cases']:
                total_cases+=1
                service_checks+=bool(case.get('serviceProbe'))
                if case['status']=='failed': failures[d['id']].append((r,case,case['error']));continue
                if ('seconds' not in case or case['seconds']>90) and case.get('serviceProbe',{}).get('status')!='passed':
                    pending.append(r['id']);continue
                render=Path(case['payload'].replace('.json.gz','.render.json'))
                if not render.exists():pending.append(r['id']);continue
                checked=json.loads(render.read_text())
                if checked.get('rendererHash')!=renderer_hash:pending.append(r['id']);continue
                if runner_failure(checked):pending.append(r['id']);continue
                checks=checked.get('checks',[])
                color_checks+=sum(bool(c.get('metric')) for c in checks)
                metrics=[c['metric'] for c in checks if c.get('metric') and c['status']=='passed']
                rejected_metrics={c['metric'] for c in checks if c.get('metric') and c['status']=='failed'}
                modes=[c['render'] for c in checks if not c.get('metric') and c['status']=='passed']
                errors=[c.get('error','Unknown rendering failure')+' ('+(c.get('metric') or c.get('render',''))+')' for c in checks if c['status']=='failed']
                if checked.get('error'):errors.append(checked['error'])
                if 'geometry' not in modes or (case['metrics'] and not metrics):
                    failures[d['id']].append((r,case,'; '.join(errors) or 'No verified rendering mode or colour attribute'));continue
                filter_summary={'mode':'exhaustive','testedCombinations':1,'totalCombinations':'1'}
                if case.get('filters'):
                    filter_file=file.with_name('filters.json')
                    if not filter_file.exists():pending.append(r['id']);continue
                    filtered=json.loads(filter_file.read_text())
                    fc=next((c for c in filtered.get('cases',[]) if c['member']==case['member'] and c['year']==case['year']),None)
                    if not filtered.get('complete'):pending.append(r['id']);continue
                    if filtered.get('resourceError'):
                        failures[d['id']].append((r,case,'Category filter audit failed: '+filtered['resourceError']));continue
                    if not fc or fc.get('status')=='running':pending.append(r['id']);continue
                    filter_errors=[];filter_pending=False;extra_metrics=set();extra_metric_errors={}
                    for sample in fc['checks']:
                        filter_counts[sample['status']]+=1
                        if sample['status']=='failed':filter_errors.append(sample['error']+'; filters='+json.dumps(sample['filters'],ensure_ascii=False))
                        if sample['status']!='parsed':continue
                        fp=Path(sample['payload'].replace('.json.gz','.render.json'))
                        if not fp.exists():filter_pending=True;continue
                        fr=json.loads(fp.read_text())
                        if fr.get('rendererHash')!=renderer_hash:filter_pending=True;continue
                        if runner_failure(fr):filter_pending=True;continue
                        filtered_color_checks+=sum(bool(check.get('metric')) for check in fr.get('checks',[]))
                        if fr.get('error'):filter_errors.append(fr['error']+'; filters='+json.dumps(sample['filters'],ensure_ascii=False))
                        for check in fr.get('checks',[]):
                            if check['status']=='passed' and check.get('metric'):extra_metrics.add(check['metric'])
                            if check['status']=='failed' and check.get('metric') and check['metric'] not in metrics:
                                extra_metric_errors[check['metric']]=check['error']+'; filters='+json.dumps(sample['filters'],ensure_ascii=False)
                            if check['status']=='failed' and (not check.get('metric') or check['metric'] in metrics):filter_errors.append(check['error']+'; attribute='+str(check.get('metric') or check['render'])+'; filters='+json.dumps(sample['filters'],ensure_ascii=False))
                    filter_summary={'mode':fc['mode'],'testedCombinations':len(fc['checks']),'totalCombinations':fc['totalCombinations']}
                    coverage.append((d,r,case,filter_summary,'failed' if filter_errors else 'passed'))
                    if filter_errors:
                        failures[d['id']].append((r,case,'Category filter failure: '+'; '.join(dict.fromkeys(filter_errors))));continue
                    if filter_pending:pending.append(r['id']);continue
                    metrics.extend(sorted(extra_metrics-set(metrics)-set(extra_metric_errors)-rejected_metrics))
                    errors.extend('Filter-specific attribute '+name+': '+error for name,error in extra_metric_errors.items())
                approved.append({'member':case['member'],'year':case['year'],'metrics':metrics,'renderModes':modes,'filterAudit':filter_summary})
                if errors:failures[d['id']].append((r,case,'Only the failing modes/attributes were hidden: '+'; '.join(errors)))
            if approved:resources[r['id']]={'sha256':result['sha256'],'cases':approved}
    if pending:raise SystemExit(f'Audit incomplete: {len(set(pending))} resources have unfinished parser/browser checks. Pending IDs (first 20): '+', '.join(sorted(set(pending))[:20])+'. No production manifest written.')
    kept={d['id'] for d in audited if any(r['id'] in resources for r in d['resources'])}
    now=datetime.now(timezone.utc).isoformat()
    manifest={'schemaVersion':1,'auditedAt':now,'parserVersion':storage.PARSER_VERSION,'referenceKey':storage.SPATIAL_REFERENCE_KEY,'excludedDatasets':[d['id'] for d in audited if d['id'] not in kept],'rendererSha256':renderer_hash,'resources':resources}
    (storage.ROOT/'config/map-render-audit.json').write_text(json.dumps(manifest,ensure_ascii=False,separators=(',',':'))+'\n')
    lines=['# Map rendering review','',f'Audited at {now}.','',
      f'- Listed datasets audited: **{len(audited)}**; retained: **{len(kept)}**; removed entirely: **{len(audited)-len(kept)}**.',
      f'- Supported resource files audited: **{parsed_resources}**; resources with a verified edition: **{len(resources)}**.',
      f'- Member/year cases: **{total_cases}**; baseline numeric colour-attribute render checks: **{color_checks}**.',
      f'- Category-selection numeric colour checks: **{filtered_color_checks}** (including verified identical-input reuse).',
      f'- Full production-reader checks: **{service_checks}** on near-limit editions or early evidence without timing data.','',
      '## Method and limits','',
      'Each supported resource was read from the R2 snapshot using the production parser and immutable spatial reference. Read failures stop dependent checks and exclude the resource. For readable resources, discovered archive members, worksheets/GIS layers and record years were inspected; a processing deadline can exclude a resource before every dependent choice is reached. Successful payloads were rendered in headless Chromium with the same MapLibre layer-building function used by the app, testing every numeric colour attribute and supported geometry/density mode when the base geometry renders. A base-geometry failure stops dependent attribute checks and excludes that edition. Byte-identical rendering inputs reuse a verified browser result. The audit checks that features render in the Barcelona viewport without map errors; it does not certify the statistical meaning of an attribute or the accuracy of source records.','',
      'The committed allowlist retains only verified resource/member/year combinations and colour attributes. Failed editions are hidden while working editions of the same dataset remain. Original R2 source objects are retained for manual work. Source checksums prevent silently showing a changed, unaudited payload. For retained editions, category spaces with at most 64 legal combinations are checked exhaustively. Larger spaces use a deterministic representative sample (individual field extremes spread across up to 12 fields, adjacent pairs and combined selections of up to 12 fields). Those editions are explicitly incomplete, as requested. Empty row intersections are legitimate no-result selections and are handled without a red error. Selections yielding identical source rows reuse their prepared/rendered result. See [filter coverage](filter-audit-coverage.md) for per-edition coverage; combination totals are upper bounds before request-length restrictions.','',
      '## Datasets removed from the map list','', '| Dataset | Failed editions |', '| --- | --- |']
    for d in audited:
        if d['id'] not in kept:lines.append(f"| [{clean(d['title'])}]({d['url']}) (`{d['id']}`) | {len(failures[d['id']])} |")
    reasons=collections.Counter(error for entries in failures.values() for _,_,error in entries)
    lines += ['', '## Most frequent failures', '', '| Failure | Cases |', '| --- | --- |']
    for error,count in reasons.most_common(15): lines.append(f'| {clean(error)[:220]} | {count} |')
    lines += ['', 'Raw originals remain at `'+storage.raw_bucket()+'/'+storage.raw_prefix()+'/raw/<dataset-id>/<resource-id>/source`.', '']
    lines+=['','## Failed editions and attributes','', 'Each source link below opens the original published resource. A retained dataset may still have excluded historical editions.','']
    for d in audited:
        if not failures[d['id']]:continue
        lines += [f"### {clean(d['title'])}",'',f"Dataset: [{d['id']}]({d['url']}) · **{'Retained with verified editions' if d['id'] in kept else 'Removed from map list'}**",'']
        if d['id']=='arbrat-viari':
            lines += ['The original application used reduced point snapshots for street trees. Investigate reusing those snapshots or publishing a reduced attribute set; full inventory editions are audited here through the general resource loader.','']
        grouped={}
        for r,c,error in failures[d['id']]:
            key=(r['id'],c.get('member'),error)
            if key not in grouped:grouped[key]=[r,c,error,[]]
            grouped[key][3].append(c.get('year') or 'all / undated')
        for r,c,error,years in grouped.values():
            lines += [f"- [{clean(r['name'])}]({r['url']}) — `{r['id']}` ({r['format']}); member: `{clean(c.get('member')) or 'default'}`; record years: **{', '.join(sorted(set(years)))}**.",f"  - Failure: {clean(error)}",f"  - Suggested investigation: {advice(error)}"]
            if c.get('rows') is not None:lines.append(f"  - Source rows inspected: {c['rows']}; without recognized geometry: {c.get('unmapped', 'unknown')}.")
            if c.get('fields'):
                fields=c['fields']
                relevant=[f for f in fields if re.search(r'lat|lon|utm|coord|geom|distr|barri|cens|aeb|address|adre|carrer|postal|year|any|data|seccio',f,re.I)]
                shown=list(dict.fromkeys([*relevant,*fields]))[:50]
                lines.append('  - Fields (location/date fields first): '+', '.join('`'+clean(f)+'`' for f in shown)+('.' if len(shown)==len(fields) else f"; {len(fields)-len(shown)} additional fields in the original."))
        lines.append('')
    lines+=['## Unsupported formats (not offered by the parser)', '', 'These spatial catalog resources were not browser-tested because the application has no reader for their declared format. Convert or integrate them before requesting a new audit.', '', '| Dataset | Resource | Format |', '| --- | --- | --- |']
    for d in catalog['datasets']:
        if not d.get('mapMethods'):continue
        for r in d['resources']:
            if not r['previewSupported']:lines.append(f"| [{clean(d['title'])}]({d['url']}) | [{clean(r['name'])}]({r['url']}) (`{r['id']}`) | {clean(r['format'])} |")
    lines+=['', '## Reproduce / reinstate','',
      'Run `.venv/bin/python -m scripts.audit_map_catalog`, start Vite on port 5174, run `node --expose-gc --max-old-space-size=2048 scripts/audit_map_render.mjs`, run `.venv/bin/python -m scripts.audit_map_filters` and `node --expose-gc --max-old-space-size=2048 scripts/audit_map_render.mjs 0 1 --filters` (or pass shard numbers before `--filters`), then `.venv/bin/python -m scripts.audit_map_service` and `.venv/bin/python -m scripts.publish_map_audit`. Evidence and compressed payloads are under `.cache/map-audit/`. Delete the affected resource evidence and its render cache before rerunning after a parser change. Refresh `.cache/map-audit/reference.json.gz` when the spatial reference changes. Regenerate the allowlist only after all checks complete. Do not manually mark an untested resource as verified.','']
    coverage_lines=['# Category-filter audit coverage','',f'Audited at {now}.','',
        '**Representative means incomplete.** It is not a guarantee that every untested combination works. Passed exhaustive entries cover every legal combination in spaces of at most 64. Empty intersections are verified as no-result selections without constructing meaningless map features. Equivalent source-row selections share rendering evidence. Failed selections exclude the edition, and dependent checks stop after a confirmed failure.','',
        'Editions without category controls require only their baseline rendering check and are omitted from this table. Sources that fail before category checks are listed in [the rendering review](map-rendering-review.md).','',
        f"Selection checks: {sum(filter_counts.values())}; empty selections: {filter_counts['empty']}; selections with a prepared payload (including reuse): {filter_counts['parsed']}.",'',
        '| Dataset / resource | Member / year | Coverage | Checked selections | Combination upper bound | Outcome |','| --- | --- | --- | --- | --- | --- |']
    for d,r,c,summary,outcome in coverage:
        label='Stopped after failure' if outcome=='failed' else '**INCOMPLETE: representative**' if summary['mode']=='representative' else 'Exhaustive'
        coverage_lines.append(f"| [{clean(d['title'])}]({d['url']}) / [{clean(r['name'])}]({r['url']}) | {clean(c.get('member')) or 'default'} / {c.get('year') or 'all / undated'} | {label} | {summary['testedCombinations']} | {summary['totalCombinations']} | {outcome} |")
    (storage.ROOT/'docs/filter-audit-coverage.md').write_text('\n'.join(coverage_lines)+'\n')
    (storage.ROOT/'docs/map-rendering-review.md').write_text('\n'.join(lines))
    print(json.dumps({'datasets':len(audited),'kept':len(kept),'resources':parsed_resources,'approvedResources':len(resources),'cases':total_cases,'colorChecks':color_checks,'filteredColorChecks':filtered_color_checks,'serviceChecks':service_checks}))

if __name__=='__main__':main()
