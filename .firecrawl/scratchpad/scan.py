import json, glob, os

with open('keywords.json', encoding='utf-8') as f:
    kw = json.load(f)

lists = {'japanese': kw['japanese'], 'french': kw['french'], 'other': kw['otherGamblingSpamSignals']}

results = []
for path in sorted(glob.glob('.firecrawl/scratchpad/*.json')):
    domain = os.path.basename(path).replace('.json','')
    with open(path, encoding='utf-8') as f:
        data = json.load(f)
    web = data.get('data', {}).get('web', [])
    for idx, item in enumerate(web):
        title = (item.get('title') or '')
        desc = (item.get('description') or item.get('snippet') or '')
        url = item.get('url') or ''
        blob = f"{title} {desc} {url}".lower()
        page = idx // 10 + 1
        for listname, words in lists.items():
            for w in words:
                if w.lower() in blob:
                    results.append({
                        'domain': domain,
                        'keyword': w,
                        'list': listname,
                        'title': title,
                        'snippet': desc,
                        'url': url,
                        'page': page
                    })

for r in results:
    print(json.dumps(r, ensure_ascii=False))
print(f"TOTAL_MATCHES={len(results)}")
