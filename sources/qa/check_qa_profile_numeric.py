import sys, yaml, json, math
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from core.connectors import load_connector
import core.extractors.profiler as profiler

with (ROOT / 'project.yaml').open('r', encoding='utf-8', errors='replace') as pf:
    proj = yaml.safe_load(pf) or {}

paths = {'sources': ROOT / 'sources' / 'generated', 'targets': ROOT / 'targets'}

# load connections file (utf-8 safe)
with (ROOT / (proj.get('connections_file', 'connections.yaml'))).open('r', encoding='utf-8', errors='replace') as cf:
    conns = yaml.safe_load(cf) or {}

datasets = []
for s in proj.get('sources', []): datasets.append(('sources', s['name']))
for t in proj.get('targets', []): datasets.append(('targets', t['name']))

issues = []
for kind, ds in datasets:
    cat_path = paths[kind] / f"{ds}.yaml"
    if not cat_path.exists():
        print(f"Catalog missing for {kind}/{ds}")
        continue
    # open with utf-8 and replace invalid characters to avoid decode errors
    with cat_path.open('r', encoding='utf-8', errors='replace') as fh:
        cat = yaml.safe_load(fh) or {}
    for schema in cat.get('schemas', []):
        schema_name = schema.get('name') or schema.get('schema_name')
        for tbl in schema.get('tables', []):
            # build payload and run profiler
            payload = {'name': schema_name, 'tables': [tbl]}
            # resolve connection config from project
            conn_name = None
            for s in proj.get('sources', []):
                if s.get('name') == ds:
                    conn_name = s.get('connection', ds)
                    break
            if not conn_name:
                for t in proj.get('targets', []):
                    if t.get('name') == ds:
                        conn_name = t.get('connection', ds)
                        break
            conn_cfg = None
            for c in conns.get('connections', []):
                if c.get('name') == conn_name:
                    conn_cfg = c
                    break
            if conn_cfg is None:
                issues.append((ds, f"no-conn:{conn_name}"))
                continue
            try:
                conn = load_connector(conn_cfg)
                conn.connect()
                profiled = profiler.enrich_schemas(conn, [payload])
                conn.close()
            except Exception as e:
                issues.append((ds, f"error profiling {schema_name}.{tbl.get('table_name') or tbl.get('name') or tbl.get('table')}: {e}"))
                continue
            # inspect profiled result for any non-finite floats
            for sres in profiled:
                for t in sres.get('tables', []):
                    tname = f"{sres.get('name')}.{t.get('table_name') or t.get('name') or t.get('table')}"
                    def find_nonfinite(o, path=''):
                        found = []
                        if isinstance(o, dict):
                            for k,v in o.items():
                                found += find_nonfinite(v, path + ('.' + k if path else k))
                        elif isinstance(o, list):
                            for i,elem in enumerate(o):
                                found += find_nonfinite(elem, f"{path}[{i}]")
                        elif isinstance(o, float):
                            if not math.isfinite(o):
                                found.append((path, o))
                        return found
                    nf = find_nonfinite(t)
                    if nf:
                        issues.append((ds, tname, nf))

# Print summary
if not issues:
    print('OK: no non-finite numeric values found in profiler output across datasets')
else:
    print('FOUND ISSUES:')
    print(json.dumps(issues, indent=2, default=str))
