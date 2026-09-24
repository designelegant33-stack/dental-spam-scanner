import json, sys, os
from datetime import date

raw_path = sys.argv[1]
results = json.loads(open(raw_path).read())

repo = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
reports_dir = os.path.join(repo, 'reports')
os.makedirs(reports_dir, exist_ok=True)

today = date.today().isoformat()
out_path = os.path.join(reports_dir, f'{today}.md')

flagged = {d: h for d, h in results.items()
           if any(h[k] for k in ['hidden', 'cloak', 'sitemap', 'js_hidden', 'js_cloak'])}
clean = [d for d in results if d not in flagged]

lines = [
    f'# Spam Scan Report — {today}',
    '',
    f'**Domains scanned:** {len(results)}  |  **Flagged:** {len(flagged)}  |  **Clean:** {len(clean)}',
    '',
]

if flagged:
    lines += ['## Flagged Domains', '']
    for domain, hits in flagged.items():
        lines.append(f'### {domain}')
        for hit_type in ['hidden', 'cloak', 'sitemap', 'js_hidden', 'js_cloak']:
            for h in hits[hit_type]:
                kw = h.get('kw', '')
                ctx = h.get('ctx', h.get('note', ''))
                url = h.get('url', '')
                label = {'hidden': 'Hidden text', 'cloak': 'Cloaking',
                         'sitemap': 'Sitemap page', 'js_hidden': 'JS hidden text',
                         'js_cloak': 'JS-only keyword'}[hit_type]
                loc = f' @ {url}' if url else ''
                lines.append(f'- **{label}**: `{kw}`{loc}')
                if ctx:
                    lines.append(f'  > {ctx[:100]}')
        lines.append('')
else:
    lines += ['## Result', '', 'No spam signals detected across all domains.', '']

lines += ['## Clean Domains', '']
lines.append(', '.join(clean))

open(out_path, 'w').write('\n'.join(lines) + '\n')
print(f'Report written: {out_path}')
print(f'Flagged: {len(flagged)} / {len(results)}')
