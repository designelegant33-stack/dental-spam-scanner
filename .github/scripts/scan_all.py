import asyncio, subprocess, json, re, sys, os, random
from concurrent.futures import ThreadPoolExecutor, as_completed
from playwright.async_api import async_playwright

repo = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
domain_ip = json.loads(open(os.path.join(repo, 'domain_ip.json'), encoding='utf-8-sig').read())

# Allow filtering by IP via FILTER_IP env var (set from GitHub Actions input)
filter_input = os.environ.get('FILTER_IP', 'all').strip()
# Extract just the IP part (input may be "68.178.205.61 (79 domains)")
filter_ip = filter_input.split()[0] if filter_input and filter_input != 'all' else None

if filter_ip:
    domains = [d for d, ip in domain_ip.items() if ip == filter_ip]
    sys.stderr.write(f'Filtering to IP {filter_ip}: {len(domains)} domains\n')
else:
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

# Known spam URL patterns hackers inject (not always in sitemaps)
SPAM_PATHS = [
    '/casino', '/casino/', '/casinos',
    '/gambling', '/gambling/',
    '/slot', '/slots', '/slot-online', '/slot-gacor',
    '/judi', '/judi-bola', '/judi-online',
    '/poker', '/poker-online',
    '/togel', '/togel-online',
    '/betting', '/sports-betting',
    '/pachinko', '/pachislot',
    '/blackjack', '/roulette',
    '/スロット', '/カジノ', '/ギャンブル',
    '/scommesse', '/giochi',
    '/paris-sportifs', '/jeux',
    '/sportwetten', '/spielautomaten',
    '/apuestas', '/tragamonedas',
    '/apostas', '/cassino',
]


def curl_fetch(url, ua, timeout=15):
    try:
        r = subprocess.run(
            ['curl', '-s', '-L', '--max-time', str(timeout), '-A', ua, url],
            capture_output=True, text=True, errors='ignore'
        )
        return r.stdout.lower()
    except Exception:
        return ''


def scan_domain_curl(domain):
    hits = {'hidden': [], 'cloak': [], 'sitemap': []}

    bot = curl_fetch(f'https://{domain}', GOOGLEBOT)
    user = curl_fetch(f'https://{domain}', BROWSER_UA)

    for kw in keywords:
        for m in re.finditer(re.escape(kw), bot):
            win = bot[max(0, m.start()-250):m.end()+250]
            if hide_pat.search(win):
                hits['hidden'].append({'kw': kw, 'ctx': win[:120]})
                break

    for kw in keywords:
        if kw in bot and kw not in user:
            hits['cloak'].append({'kw': kw})
    if user and abs(len(bot)-len(user)) / max(len(user), 1) > 0.20:
        if any(kw in bot for kw in keywords):
            hits['cloak'].append({'kw': 'SIZE_MISMATCH',
                                  'note': f'bot={len(bot)} user={len(user)}'})

    sitemap_urls = []
    sub_sitemaps = []
    for path in ['/sitemap.xml', '/sitemap_index.xml', '/wp-sitemap.xml', '/sitemap1.xml']:
        try:
            r = subprocess.run(
                ['curl', '-s', '-L', '--max-time', '10', f'https://{domain}{path}'],
                capture_output=True, text=True
            )
            # collect sub-sitemap .xml links to follow
            sub_sitemaps += re.findall(r'<loc>([^<]+\.xml)</loc>', r.stdout)
            sitemap_urls += [u for u in re.findall(r'<loc>([^<]+)</loc>', r.stdout)
                             if not u.endswith('.xml')]
        except Exception:
            pass
    # follow sub-sitemaps (e.g. wp-sitemap-posts-post-1.xml, sitemap2.xml)
    for sm in sub_sitemaps[:10]:
        try:
            r = subprocess.run(
                ['curl', '-s', '-L', '--max-time', '10', sm],
                capture_output=True, text=True
            )
            sitemap_urls += [u for u in re.findall(r'<loc>([^<]+)</loc>', r.stdout)
                             if not u.endswith('.xml')]
        except Exception:
            pass
    if not sitemap_urls:
        sitemap_urls = [f'https://{domain}' + p
                        for p in ['/about', '/services', '/contact', '/blog', '/news', '/posts']]
    # take first 50 (newest) + 50 random from the rest for broad coverage
    head = sitemap_urls[:50]
    tail = sitemap_urls[50:]
    sample = random.sample(tail, min(50, len(tail)))
    sitemap_urls = head + sample

    for url in sitemap_urls:
        page = curl_fetch(url, GOOGLEBOT, timeout=10)
        for kw in keywords:
            if kw in page:
                m2 = re.search(re.escape(kw), page)
                ctx = page[max(0, m2.start()-100):m2.end()+100] if m2 else ''
                hits['sitemap'].append({'url': url, 'kw': kw, 'ctx': ctx[:120]})
                break

    # probe known spam URL patterns (catches non-indexed hidden pages)
    for path in SPAM_PATHS:
        url = f'https://{domain}{path}'
        page = curl_fetch(url, GOOGLEBOT, timeout=8)
        if not page or len(page) < 500:
            continue
        for kw in keywords:
            if kw in page:
                m2 = re.search(re.escape(kw), page)
                ctx = page[max(0, m2.start()-100):m2.end()+100] if m2 else ''
                hits['sitemap'].append({'url': url, 'kw': kw, 'ctx': ctx[:120],
                                        'note': 'spam-path-probe'})
                break

    return domain, hits


async def scan_domain_playwright(browser, semaphore, domain, curl_html):
    """JS-rendered scan — catches spam injected by JavaScript after page load."""
    js_hits = []
    async with semaphore:
        try:
            context = await browser.new_context(
                user_agent=GOOGLEBOT,
                ignore_https_errors=True
            )
            page = await context.new_page()
            await page.goto(f'https://{domain}', timeout=20000, wait_until='domcontentloaded')
            await asyncio.sleep(2)
            content = (await page.content()).lower()
            await context.close()

            for kw in keywords:
                if kw in content and kw not in curl_html:
                    m = re.search(re.escape(kw), content)
                    win = content[max(0, m.start()-250):m.end()+250] if m else ''
                    if hide_pat.search(win):
                        js_hits.append({'kw': kw, 'type': 'js_hidden', 'ctx': win[:120]})
                    else:
                        js_hits.append({'kw': kw, 'type': 'js_only'})
        except Exception:
            pass
    return domain, js_hits


async def run_playwright_scan(domains, curl_results):
    sys.stderr.write(f'\nStarting Playwright scan ({len(domains)} domains, 20 concurrent)...\n')
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        semaphore = asyncio.Semaphore(20)
        tasks = [
            scan_domain_playwright(browser, semaphore, d, curl_results.get(d, ''))
            for d in domains
        ]
        results = await asyncio.gather(*tasks)
        await browser.close()
    return dict(results)


# --- Phase 1: parallel curl scan ---
sys.stderr.write('Phase 1: curl scan (25 parallel)...\n')
curl_results = {}
results = {}

with ThreadPoolExecutor(max_workers=25) as pool:
    futures = {pool.submit(scan_domain_curl, d): d for d in domains}
    for future in as_completed(futures):
        domain, hits = future.result()
        results[domain] = hits
        curl_results[domain] = ''  # placeholder
        total = sum(len(v) for v in hits.values())
        sys.stderr.write(f'curl done: {domain}  hits={total}\n')

# --- Phase 2: async Playwright scan ---
sys.stderr.write('\nPhase 2: Playwright JS scan (20 concurrent)...\n')
pw_results = asyncio.run(run_playwright_scan(domains, curl_results))

for domain, js_hits in pw_results.items():
    if js_hits:
        results[domain]['js'] = js_hits
        sys.stderr.write(f'JS hits: {domain}  {js_hits}\n')

print(json.dumps(results, ensure_ascii=False))
