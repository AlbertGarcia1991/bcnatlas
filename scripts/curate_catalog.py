"""Apply reviewed exclusions and expose location evidence without trusting geolocation alone."""
import json
import re
from server import storage
from server.spatial import spatial_methods, RELATIONS

def curate(catalog):
    exclusions = json.loads((storage.ROOT / 'config/catalog-exclusions.json').read_text())
    evidence = json.loads((storage.ROOT / 'config/catalog-spatial-evidence.json').read_text())
    datasets = []
    for dataset in catalog['datasets']:
        if dataset['id'] in exclusions: continue
        methods = spatial_methods(evidence.get(dataset['id'], {}).get('fields', []))
        if dataset['id'] in RELATIONS: methods.append(RELATIONS[dataset['id']][0])
        if dataset['geographic'] and not methods: methods = ['geometry']
        # A declared geographic breakdown is a candidate, not proof that every
        # resource has already been parsed. Never delete it on a failed probe.
        if not methods:
            description = ' '.join([dataset['title'], dataset['description'], *dataset['tags']]).lower()
            for pattern, method in [(r'\b(neighbourhoods?|neighborhoods?|barris)\b', 'neighbourhood'), (r'\b(districts?|districtes)\b', 'district'), (r'\b(census sections?|seccions censals)\b', 'section'), (r'\b(streets?|carrers|addresses|adreces)\b', 'address')]:
                if re.search(pattern, description): methods.append(method)
        datasets.append({**dataset, 'mapMethods': methods, 'mapStatus': 'location-fields' if methods else 'needs-inspection'})
    return {**catalog, 'count': len(datasets), 'mapDatasetCount': sum(bool(d['mapMethods']) for d in datasets), 'resourceCount': sum(len(d['resources']) for d in datasets), 'geographicCount': sum(d['geographic'] for d in datasets), 'datasets': datasets,
            'curation': {'excludedDatasets': len(exclusions), 'policy': 'Reviewed non-spatial datasets excluded. Location evidence is independent of the publisher geographic flag; missing or unsupported sources are not deleted.'}}

if __name__ == '__main__':
    path = storage.ROOT / 'public/data/catalog.json'
    result = curate(json.loads(path.read_text()))
    path.write_text(json.dumps(result, ensure_ascii=False, separators=(',', ':')))
    print('Map catalog:', result['count'], 'datasets /', result['resourceCount'], 'resources')
