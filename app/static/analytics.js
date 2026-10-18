/* SkillLens AI — privacy-first Google Analytics 4, enabled only by opt-in. */
(() => {
  'use strict';
  const ID = 'G-Z9VPVPS0CP';
  const STORAGE_KEY = 'skilllens.analytics.consent.v1';
  let loaded = false;
  let banner = null;

  function readChoice() {
    try {
      const value = localStorage.getItem(STORAGE_KEY);
      return value === 'accept' || value === 'decline' ? value : null;
    } catch (_) { return null; }
  }

  function saveChoice(value) {
    try { localStorage.setItem(STORAGE_KEY, value); } catch (_) { /* session-only decision */ }
  }

  function clearAnalyticsCookies() {
    document.cookie.split(';').forEach((entry) => {
      const name = entry.split('=')[0].trim();
      if (!/^_ga(?:_|$)/.test(name)) return;
      document.cookie = name + '=; Max-Age=0; Path=/; SameSite=Lax';
      document.cookie = name + '=; Max-Age=0; Path=/; SameSite=Lax; Domain=' + location.hostname;
    });
  }

  function enableAnalytics() {
    if (loaded) return;
    loaded = true;
    window['ga-disable-' + ID] = false;
    window.dataLayer = window.dataLayer || [];
    window.gtag = function () { window.dataLayer.push(arguments); };
    window.gtag('consent', 'default', {
      analytics_storage: 'granted',
      ad_storage: 'denied',
      ad_user_data: 'denied',
      ad_personalization: 'denied'
    });
    window.gtag('js', new Date());
    window.gtag('config', ID, {
      // Don't expose pasted resumes, draft identifiers or search/query parameters.
      page_location: location.origin + location.pathname,
      allow_google_signals: false,
      allow_ad_personalization_signals: false
    });
    const tag = document.createElement('script');
    tag.async = true;
    tag.src = 'https://www.googletagmanager.com/gtag/js?id=' + encodeURIComponent(ID);
    document.head.appendChild(tag);
  }

  function choose(value) {
    saveChoice(value);
    if (value === 'accept') enableAnalytics();
    else {
      window['ga-disable-' + ID] = true;
      clearAnalyticsCookies();
    }
    if (banner) { banner.remove(); banner = null; }
  }

  function openChoices() {
    if (banner) { banner.querySelector('button')?.focus(); return; }
    banner = document.createElement('section');
    banner.className = 'skilllens-analytics-consent';
    banner.setAttribute('role', 'region');
    banner.setAttribute('aria-label', 'Analytics privacy choices');
    banner.innerHTML = '<div class="skilllens-analytics-copy"><strong>Help us improve SkillLens</strong><p>With your permission, Google Analytics measures visits and pages viewed. We do not send resume text, job descriptions or application notes. <a href="/privacy">Privacy details</a></p></div><div class="skilllens-analytics-actions"><button type="button" data-ga-choice="decline">Decline</button><button type="button" data-ga-choice="accept">Allow analytics</button></div>';
    banner.addEventListener('click', (event) => {
      const button = event.target.closest('button[data-ga-choice]');
      if (button) choose(button.getAttribute('data-ga-choice'));
    });
    document.body.appendChild(banner);
  }

  function init() {
    document.querySelectorAll('[data-analytics-settings]').forEach((button) => {
      button.addEventListener('click', openChoices);
    });
    const choice = readChoice();
    if (choice === 'accept') enableAnalytics();
    else if (choice === 'decline') window['ga-disable-' + ID] = true;
    else openChoices();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
