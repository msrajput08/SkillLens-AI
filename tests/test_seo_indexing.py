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
        assert urls == [SITE_URL + p for p in ('/', '/builder', '/applications', '/privacy', '/terms')]
        assert not any('/api/' in url or '/tracker' in url for url in urls)


def test_seo_titles_canonicals_and_valid_homepage_structured_data():
    expected = {
        '/': ('SkillLens AI', 'https://skilllens-beta.onrender.com/'),
        '/builder': ('Resume Builder', 'https://skilllens-beta.onrender.com/builder'),
        '/applications': ('Application Tracker', 'https://skilllens-beta.onrender.com/applications'),
        '/tracker': ('Application Tracker', 'https://skilllens-beta.onrender.com/applications'),
        '/terms': ('Terms of service', SITE_URL + '/terms'),
        '/privacy': ('Privacy policy', SITE_URL + '/privacy'),
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
        match = re.search(r'<script type="application/ld\\+json">(.*?)</script>', homepage, re.S)
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
