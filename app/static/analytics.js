/* SkillLens aggregate analytics: first party, no consent banner, no trackers/cookies. */
(() => {
  'use strict';

  const ENDPOINT = '/api/analytics/event';
  const OPT_OUT_KEY = 'skilllens.analytics.optout.v1';
  const OLD_CHOICE_KEY = 'skilllens.analytics.consent.v1';
  const EVENTS = new Set([
    'analysis_started', 'preview_completed', 'analysis_completed',
    'signup_cta_clicked', 'signup_submitted', 'login_completed',
    'quota_exhausted', 'rewrite_completed', 'upgrade_cta_clicked',
    'checkout_started', 'checkout_verified', 'pro_activated'
  ]);
  const SOURCES = new Set(['preview', 'pricing', 'quota', 'account', 'report']);
  const FEATURES = new Set(['analysis', 'rewrite']);
  const CHANNELS = new Set([
    'whatsapp', 'telegram', 'linkedin', 'x', 'email', 'instagram', 'youtube', 'reddit'
  ]);
  function acquisitionChannel() {
    try {
      const value = new URLSearchParams(location.search).get('utm_source');
      if (!value) return 'direct';
      return CHANNELS.has(value.toLowerCase()) ? value.toLowerCase() : 'other';
    } catch { return 'direct'; }
  }
  const PAGES = new Set([
    '/', '/builder', '/applications', '/resume-job-match',
    '/guides/how-to-tailor-resume', '/guides/resume-skills-gap',
    '/privacy', '/terms'
  ]);

  function preference(key) {
    try { return localStorage.getItem(key); } catch { return null; }
  }
  function savePreference(key, value) {
    try {
      if (value == null) localStorage.removeItem(key);
      else localStorage.setItem(key, value);
    } catch { /* Private browsing: still works without persistence. */ }
  }
  function browserRequestsNoTracking() {
    return navigator.globalPrivacyControl === true ||
           navigator.doNotTrack === '1' ||
           window.doNotTrack === '1';
  }
  function disabled() {
    // Do not override explicit decisions made before this no-banner release.
    return browserRequestsNoTracking() ||
      preference(OPT_OUT_KEY) === 'true' ||
      preference(OLD_CHOICE_KEY) === 'decline';
  }

  function cleanUpLegacyAnalyticsCookies() {
    // The old opt-in GA4 version used _ga cookies. This version does not.
    document.cookie.split(';').forEach((entry) => {
      const name = entry.split('=')[0].trim();
      if (!/^_ga(?:_|$)/.test(name)) return;
      document.cookie = name + '=; Max-Age=0; Path=/; SameSite=Lax';
      document.cookie = name + '=; Max-Age=0; Path=/; SameSite=Lax; Domain=' + location.hostname;
    });
  }

  function send(eventName, attributes = {}) {
    if (disabled() || (eventName !== 'page_view' && !EVENTS.has(eventName))) return;
    const path = location.pathname === '/tracker' ? '/applications' : location.pathname;
    const data = {
      event: eventName,
      page: PAGES.has(path) ? path : '/other',
      source: SOURCES.has(attributes.source) ? attributes.source : 'none',
      feature: FEATURES.has(attributes.feature) ? attributes.feature : 'none',
      channel: acquisitionChannel()
    };
    // Browser intentionally sends no resume, JD, email, visitor ID, page query
    // string, referrer, or session cookie. Server stores only daily counters.
    fetch(ENDPOINT, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(data),
      credentials: 'omit',
      cache: 'no-store',
      keepalive: true
    }).catch(() => { /* Analytics must never block the product. */ });
  }

  window.skilllensTrack = (eventName, attributes = {}) => send(eventName, attributes);

  function updatePreferenceButtons() {
    for (const button of document.querySelectorAll('[data-analytics-optout]')) {
      const off = disabled();
      button.textContent = browserRequestsNoTracking()
        ? 'Analytics disabled by browser privacy setting'
        : off ? 'Enable anonymous analytics' : 'Disable anonymous analytics';
      button.disabled = browserRequestsNoTracking();
      button.setAttribute('aria-pressed', String(off));
    }
  }

  function init() {
    cleanUpLegacyAnalyticsCookies();
    for (const button of document.querySelectorAll('[data-analytics-optout]')) {
      button.addEventListener('click', () => {
        if (browserRequestsNoTracking()) return;
        if (disabled()) {
          savePreference(OPT_OUT_KEY, null);
          savePreference(OLD_CHOICE_KEY, null);
        } else {
          savePreference(OPT_OUT_KEY, 'true');
        }
        updatePreferenceButtons();
      });
    }
    updatePreferenceButtons();
    send('page_view');
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
