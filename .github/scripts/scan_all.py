import subprocess, json, re, sys, os
from playwright.sync_api import sync_playwright

# Load all domains from domain_ip.json
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


def curl_fetch(url, ua):
    try:
        r = subprocess.run(
            ['curl', '-s', '-L', '--max-time', '15', '-A', ua, url],
            capture_output=True, text=True, errors='ignore'
        )
        return r.stdout.lower()
    except Exception:
        return ''


def pw_fetch(page, url):
    try:
        page.goto(url, timeout=20000, wait_until='domcontentloaded')
        page.wait_for_timeout(2000)
        return page.content().lower()
    except Exception:
        return ''


def get_sitemap_urls(domain):
    urls = []
    for path in ['/sitemap.xml', '/sitemap_index.xml', '/wp-sitemap.xml', '/sitemap1.xml']:
        try:
            r = subprocess.run(
                ['curl', '-s', '-L', '--max-time', '10', f'https://{domain}{path}'],
                capture_output=True, text=True
            )
            urls += [u for u in re.findall(r'<loc>([^<]+)</loc>', r.stdout)
                     if not u.endswith('.xml')][:40]
        except Exception:
            pass
    if not urls:
        urls = [f'https://{domain}' + p for p in ['/about', '/services', '/contact', '/blog']]
    return urls[:40]


results = {}

with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True)
    context = browser.new_context(
        user_agent=GOOGLEBOT,
        ignore_https_errors=True,
        extra_http_headers={'Accept-Language': 'en-US,en;q=0.9'}
    )
    page = context.new_page()

    for domain in domains:
        hits = {'hidden': [], 'cloak': [], 'sitemap': [], 'js_hidden': [], 'js_cloak': []}

        bot_curl = curl_fetch(f'https://{domain}', GOOGLEBOT)
        user_curl = curl_fetch(f'https://{domain}', BROWSER_UA)

        # --- curl hidden text check ---
        for kw in keywords:
            for m in re.finditer(re.escape(kw), bot_curl):
                win = bot_curl[max(0, m.start()-250):m.end()+250]
                if hide_pat.search(win):
                    hits['hidden'].append({'kw': kw, 'ctx': win[:120]})
                    break

        # --- curl cloaking check ---
        for kw in keywords:
            if kw in bot_curl and kw not in user_curl:
                hits['cloak'].append({'kw': kw})
        if user_curl and abs(len(bot_curl)-len(user_curl))/max(len(user_curl), 1) > 0.20:
            if any(kw in bot_curl for kw in keywords):
                hits['cloak'].append({'kw': 'SIZE_MISMATCH',
                                      'note': f'bot={len(bot_curl)} user={len(user_curl)}'})

        # --- Playwright JS-rendered check ---
        bot_js = pw_fetch(page, f'https://{domain}')
        for kw in keywords:
            if kw in bot_js and kw not in bot_curl:
                for m in re.finditer(re.escape(kw), bot_js):
                    win = bot_js[max(0, m.start()-250):m.end()+250]
                    if hide_pat.search(win):
                        hits['js_hidden'].append({'kw': kw, 'ctx': win[:120]})
                        break
                else:
                    hits['js_cloak'].append({'kw': kw, 'note': 'JS-only (not in curl)'})

        # --- sitemap crawl ---
        for url in get_sitemap_urls(domain):
            page_html = curl_fetch(url, GOOGLEBOT)
            for kw in keywords:
                if kw in page_html:
                    m2 = re.search(re.escape(kw), page_html)
                    ctx = page_html[max(0, m2.start()-100):m2.end()+100] if m2 else ''
                    hits['sitemap'].append({'url': url, 'kw': kw, 'ctx': ctx[:120]})
                    break

        results[domain] = hits
        total = (len(hits['hidden']) + len(hits['cloak']) +
                 len(hits['sitemap']) + len(hits['js_hidden']) + len(hits['js_cloak']))
        sys.stderr.write(f'done: {domain}  hits={total}\n')

    browser.close()

print(json.dumps(results, ensure_ascii=False))
