"""Search discovery: publicly crawlable pages, canonical URLs and verified ownership."""
import json
import re
import xml.etree.ElementTree as ET

from fastapi.testclient import TestClient
from app.main import app, SITE_URL


def test_sitemap_and_robots_have_public_canonical_urls():
    with TestClient(app) as c:
        robots = c.get('/robots.txt')
        assert robots.status_code == 200
        assert 'Disallow: /api/' in robots.text
        assert 'Sitemap: ' + SITE_URL + '/sitemap.xml' in robots.text
        xml = c.get('/sitemap.xml')
        assert xml.status_code == 200
        assert 'application/xml' in xml.headers['content-type']
        parsed = ET.fromstring(xml.text)
        namespace = {'s': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
        urls = [node.text for node in parsed.findall('s:url/s:loc', namespace)]
        assert urls == [SITE_URL + p for p in ('/', '/resume-job-match', '/guides/how-to-tailor-resume', '/guides/resume-skills-gap', '/builder', '/applications', '/privacy', '/terms')]
        assert not any('/api/' in url or '/tracker' in url for url in urls)


def test_seo_titles_canonicals_and_valid_homepage_structured_data():
    import os
    live_url = os.getenv('SKILLLENS_SITE_URL', 'https://skilllens-beta.onrender.com').rstrip('/')
    expected = {
        '/': ('SkillLens AI', 'https://skilllens-beta.onrender.com/'),
        '/builder': ('Resume Builder', 'https://skilllens-beta.onrender.com/builder'),
        '/applications': ('Application Tracker', 'https://skilllens-beta.onrender.com/applications'),
        '/tracker': ('Application Tracker', 'https://skilllens-beta.onrender.com/applications'),
        '/terms': ('Terms of service', live_url + '/terms'),
        '/privacy': ('Privacy policy', live_url + '/privacy'),
    }
    with TestClient(app) as c:
        for path, (title, canonical) in expected.items():
            page = c.get(path)
            assert page.status_code == 200
            assert title.lower() in page.text.lower()
            assert '<link rel="canonical" href="' + canonical + '"' in page.text
            assert 'name="description"' in page.text
            assert 'name="robots"' in page.text
        homepage = c.get('/').text
        match = re.search(r'<script type="application/ld\+json">(.*?)</script>', homepage, re.S)
        assert match
        schema = json.loads(match.group(1))
        app_schema = next(v for v in schema['@graph'] if v['@type']=='WebApplication')
        assert app_schema['offers'][0]['price'] == '0'
        assert app_schema['offers'][1]['price'] == '199'


def test_google_search_console_html_verification_is_exact_opt_in(monkeypatch):
    filename = 'googleabc123xyz.html'
    monkeypatch.delenv('GOOGLE_SITE_VERIFICATION_FILE', raising=False)
    with TestClient(app) as c:
        assert c.get('/' + filename).status_code == 404
        monkeypatch.setenv('GOOGLE_SITE_VERIFICATION_FILE', filename)
        assert c.get('/' + filename).text == 'google-site-verification: ' + filename
        assert c.get('/googlewrong.html').status_code == 404


def test_original_seo_landing_pages_are_crawlable_and_links_work():
    from html.parser import HTMLParser
    from urllib.parse import urlsplit
    class Parser(HTMLParser):
        def __init__(self):
            super().__init__()
            self.links = []
            self.h1 = 0
            self.h2 = 0
        def handle_starttag(self, tag, attrs):
            d = dict(attrs)
            if tag == 'a' and d.get('href', '').startswith('/'):
                self.links.append(d['href'])
            if tag == 'h1':
                self.h1 += 1
            if tag == 'h2':
                self.h2 += 1
    paths = {
        '/resume-job-match': ('Resume and Job Description Matcher', 'Match your resume'),
        '/guides/how-to-tailor-resume': ('How to Tailor a Resume', 'How to tailor'),
        '/guides/resume-skills-gap': ('How to Find Missing Skills', 'Find the skills'),
    }
    with TestClient(app) as client:
        for url, (title, h1_text) in paths.items():
            response = client.get(url)
            assert response.status_code == 200
            html = response.text
            assert title in html
            assert h1_text in html
            assert '<link rel="canonical" href="https://skilllens-beta.onrender.com' + url + '"' in html
            assert '<meta name="description"' in html
            assert 'name="robots" content="index,follow' in html
            assert '/assets/seo.css' in html
            assert 'not employer ATS scores' in html
            parser = Parser()
            parser.feed(html)
            assert parser.h1 == 1
            assert parser.h2 >= 4
            assert '/#workspace' in parser.links
            assert '/builder' in parser.links
            for href in parser.links:
                path = urlsplit(href).path
                if path != '/':
                    assert client.get(path).status_code == 200, href
        home = client.get('/').text
        assert 'SKILLLENS AI' in home
        for url in paths:
            assert f'href="{url}"' in home
        assert client.get('/assets/seo.css').status_code == 200
