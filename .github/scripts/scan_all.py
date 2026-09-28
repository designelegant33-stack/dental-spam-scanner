import subprocess, json, re, sys, os
from concurrent.futures import ThreadPoolExecutor, as_completed

repo = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
domain_ip = json.loads(open(os.path.join(repo, 'domain_ip.json'), encoding='utf-8-sig').read())
domains = list(domain_ip.keys())

kw_data = json.loads(open(os.path.join(repo, 'keywords.json'), encoding='utf-8-sig').read())
keywords = []
for v in kw_data.values():
    keywords += v
keywords = list(dict.fromkeys(keywords))
sys.stderr.write(f'Domains: {len(domains)}  Keywords: {len(keywords)}\n')

hide_pat = re.compile(
    r'display\s*:\s*none|visibility\s*:\s*hidden|font-size\s*:\s*0'
    r'|color\s*:\s*(#fff|#ffffff|white)|left\s*:\s*-\d{3,}px'
)

GOOGLEBOT = 'Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)'
BROWSER_UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'


def curl_fetch(url, ua, timeout=15):
    try:
        r = subprocess.run(
            ['curl', '-s', '-L', '--max-time', str(timeout), '-A', ua, url],
            capture_output=True, text=True, errors='ignore'
        )
        return r.stdout.lower()
    except Exception:
        return ''


def scan_domain(domain):
    hits = {'hidden': [], 'cloak': [], 'sitemap': []}

    bot = curl_fetch(f'https://{domain}', GOOGLEBOT)
    user = curl_fetch(f'https://{domain}', BROWSER_UA)

    # hidden text
    for kw in keywords:
        for m in re.finditer(re.escape(kw), bot):
            win = bot[max(0, m.start()-250):m.end()+250]
            if hide_pat.search(win):
                hits['hidden'].append({'kw': kw, 'ctx': win[:120]})
                break

    # cloaking
    for kw in keywords:
        if kw in bot and kw not in user:
            hits['cloak'].append({'kw': kw})
    if user and abs(len(bot)-len(user)) / max(len(user), 1) > 0.20:
        if any(kw in bot for kw in keywords):
            hits['cloak'].append({'kw': 'SIZE_MISMATCH',
                                  'note': f'bot={len(bot)} user={len(user)}'})

    # sitemap crawl
    sitemap_urls = []
    for path in ['/sitemap.xml', '/sitemap_index.xml', '/wp-sitemap.xml', '/sitemap1.xml']:
        try:
            r = subprocess.run(
                ['curl', '-s', '-L', '--max-time', '10', f'https://{domain}{path}'],
                capture_output=True, text=True
            )
            sitemap_urls += [u for u in re.findall(r'<loc>([^<]+)</loc>', r.stdout)
                             if not u.endswith('.xml')][:40]
        except Exception:
            pass
    if not sitemap_urls:
        sitemap_urls = [f'https://{domain}' + p
                        for p in ['/about', '/services', '/contact', '/blog']]

    for url in sitemap_urls[:20]:
        page = curl_fetch(url, GOOGLEBOT, timeout=10)
        for kw in keywords:
            if kw in page:
                m2 = re.search(re.escape(kw), page)
                ctx = page[max(0, m2.start()-100):m2.end()+100] if m2 else ''
                hits['sitemap'].append({'url': url, 'kw': kw, 'ctx': ctx[:120]})
                break

    total = sum(len(v) for v in hits.values())
    sys.stderr.write(f'done: {domain}  hits={total}\n')
    return domain, hits


results = {}
with ThreadPoolExecutor(max_workers=25) as pool:
    futures = {pool.submit(scan_domain, d): d for d in domains}
    for future in as_completed(futures):
        domain, hits = future.result()
        results[domain] = hits

print(json.dumps(results, ensure_ascii=False))
