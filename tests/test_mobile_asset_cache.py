"""Regression checks for versioned mobile CSS and accessible navigation."""
from fastapi.testclient import TestClient

from app.main import app


STYLE_VERSION = "20261018-mobile2"
PAGES = {
    "/": "styles.css",
    "/builder": "product.css",
    "/applications": "product.css",
    "/resume-job-match": "seo.css",
    "/guides/how-to-tailor-resume": "seo.css",
    "/guides/resume-skills-gap": "seo.css",
}


def test_all_product_pages_request_current_mobile_stylesheet():
    with TestClient(app) as client:
        for page, css in PAGES.items():
            response = client.get(page)
            assert response.status_code == 200, page
            url = f"/assets/{css}?v={STYLE_VERSION}"
            assert f'href="{url}"' in response.text, page
            static = client.get(url)
            assert static.status_code == 200, url
            assert "text/css" in static.headers["content-type"], url


def test_guide_pages_offer_phone_navigation_without_losing_desktop_links():
    with TestClient(app) as client:
        for page in (
            "/resume-job-match",
            "/guides/how-to-tailor-resume",
            "/guides/resume-skills-gap",
        ):
            html = client.get(page).text
            assert html.count('class="guide-mobile-menu"') == 1, page
            assert html.count('class="guide-mobile-links"') == 1, page
            assert "<summary>" in html, page
            assert html.count('href="/builder"') >= 2, page
            assert html.count('href="/applications"') >= 2, page
        css = client.get(f"/assets/seo.css?v={STYLE_VERSION}").text
        assert ".guide-mobile-menu{display:none}" in css
        assert ".site-header .nav-links{display:none}" in css
        assert "@media(max-width:760px)" in css
        assert ".guide-mobile-links" in css


def test_homepage_mobile_navigation_is_accessible():
    with TestClient(app) as client:
        html = client.get("/").text
        assert 'class="mobile-menu"' in html
        assert 'aria-label="Mobile navigation"' in html
        css = client.get(f"/assets/styles.css?v={STYLE_VERSION}").text
        assert ".mobile-menu{display:none}" in css
        assert ".topbar .toplinks{display:none}" in css
