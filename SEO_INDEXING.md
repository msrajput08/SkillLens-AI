# SkillLens AI — Google Search indexing checklist

**Canonical domain (free):** https://skilllens-beta.onrender.com/

**Goal:** Let Google discover and index the public pages of SkillLens AI. Technical SEO improves eligibility; no search engine guarantees immediate indexing or top rankings. Chrome is the browser; Google Search determines search results.

## Implemented in the app

- `/robots.txt` permits public pages, disallows private `/api/` endpoints and links to `/sitemap.xml`.
- `/sitemap.xml` lists the real public URLs: homepage, resume builder, job application tracker, terms, and privacy.
- Each public page has a descriptive search title, a unique meta description and a **canonical** URL. The legacy `/tracker` route has canonical `/applications` to avoid a duplicate listing.
- The homepage includes relevant descriptive content, Open Graph/Twitter metadata, and valid Schema.org `WebSite` / `WebApplication` JSON-LD without fabricated reviews.
- Google Search Console ownership verification can be done without a custom domain or a credit card.

## Operator action: Google Search Console verification

1. Sign in to **https://search.google.com/search-console/** with your Google account.
2. Choose **Add property → URL prefix**, paste **https://skilllens-beta.onrender.com/** (include `https://` and the final slash). This is a URL-prefix property for the Render subdomain, **not** a Domain property.
3. Choose **HTML file** verification. Google provides a filename like `googleabc123xyz.html` and says what content it expects. Do **not** upload the file to another website.
4. In Render → `skilllens-beta` → Environment, set **`GOOGLE_SITE_VERIFICATION_FILE`** to that **exact filename** (including `.html`). Save and deploy. Do not change billing variables. The app serves the exact required text only for the configured filename.
5. Open `https://skilllens-beta.onrender.com/googleabc123xyz.html` (replace with the actual filename) in a private browser tab; it must show `google-site-verification: googleabc123xyz.html`.
6. In Search Console select **Verify**. Keep the variable in Render so future ownership checks continue working.
7. Open **Sitemaps**, enter `sitemap.xml`, click **Submit**.
8. Open **URL inspection**, inspect `https://skilllens-beta.onrender.com/`, click **Request indexing** when offered. Repeat for `/builder` and `/applications` after inspection; avoid excessive repeated requests.
9. Check the **Pages** and **Performance** reports over subsequent days/weeks for discovered URLs, impressions and search queries.

## Verifying progress

- On-site checks:
  - https://skilllens-beta.onrender.com/robots.txt
  - https://skilllens-beta.onrender.com/sitemap.xml
- Search Google for `site:skilllens-beta.onrender.com` (not an exhaustive or real-time index report).
- Search Console URL Inspection is the **authoritative place** to inspect Google's view of indexing for this property. It may take days to weeks, and visibility for high-competition keywords requires useful content and relevant links.
- Share the actual app URL (not only screenshots) in launch posts, LinkedIn profile, README and other genuinely relevant channels.

## Search terms to target naturally

- SkillLens AI resume analyzer (branded)
- resume and job description matcher
- free resume analyzer
- online resume builder
- job application tracker

**Do not** buy fake backlinks, stuff keywords, claim an official ATS score, or pretend that search appearance/rank has already been achieved.

## Notes

- Currently the app runs on Render Free; inactive instances can sleep and delay Googlebot access. Keep a working public HTTPS address and consider real operational reliability before expecting stable crawling at scale.
- If a custom domain is later adopted, set `SKILLLENS_SITE_URL`, update page canonical metadata and redirects consistently, and add the new domain as a new Search Console property; otherwise duplicate domains may compete.
