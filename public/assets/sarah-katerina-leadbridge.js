/* Sarah Katerina lead bridge — universal form safety-net for the static
 * VITA Host mirror.
 *
 *   1. For the main contact form (action=*web3forms*): fires a parallel
 *      keepalive POST to sarahkaterina.com/api/lead-notify so the lead
 *      also lands in the SK pipeline (Resend → Gmail → log) even when
 *      the Web3Forms email leg is silently broken.
 *
 *   2. For any other form on the page (newsletter, search, leftover WP
 *      cruft, anything posting to a non-existent endpoint): if the
 *      action resolves to the current-page URL or to a path that
 *      doesn't exist on this static site, the submit is intercepted —
 *      no 405 ever reaches a user. If the form looks like a newsletter
 *      signup (single email input), the email is forwarded to the SK
 *      pipeline as a "Newsletter signup" lead.
 *
 * Loaded on every page that embeds any form on the static VITA Host
 * mirror.
 */
(function () {
  var SK_ENDPOINT = "https://www.sarahkaterina.com/api/lead-notify";

  /* ----------------------------------------------------------------
   * Google Ads conversion tracking.
   *
   * The "VITA - Lead Form Submit" conversion action lives in the
   * Sarah Katerina Google Ads account (AW-18128432743), label
   * hAUDCOODzrUcEOfcp8RD. This static site only had the unrelated tag
   * AW-17471438459 loaded, so the conversion never fired. We
   * additionally configure AW-18128432743 here (gtag.js is already
   * loaded site-wide via GT-PBGB378) and fire the event snippet on the
   * /thank-you/ page that users reach after the Web3Forms contact-form
   * submit.
   *
   * Enhanced conversions: the contact form email is stashed in
   * sessionStorage on submit. The Web3Forms round-trip returns to
   * vitahost.es/thank-you/ — same origin — so the value survives, and
   * we hand it to gtag('set','user_data',…) before the conversion so
   * Google can match it (hashing happens client-side in gtag).
   * ---------------------------------------------------------------- */
  var GADS_ACCOUNT = "AW-18128432743";
  var GADS_LEAD_LABEL = "AW-18128432743/hAUDCOODzrUcEOfcp8RD";
  var EMAIL_KEY = "vh_lead_email";
  var FIRED_KEY = "vh_lead_conv_fired";

  function gtagSafe() {
    return typeof window.gtag === "function" ? window.gtag : null;
  }

  function isThankYou() {
    return /\/thank-you\/?$/.test(location.pathname);
  }

  function captureLeadEmail(form) {
    try {
      var el = form.querySelector(
        'input[type="email"], [name="Email"], [name="E-mail"], [name="email"]'
      );
      var v = el && el.value ? String(el.value).trim().toLowerCase() : "";
      if (v) {
        sessionStorage.setItem(EMAIL_KEY, v);
        sessionStorage.removeItem(FIRED_KEY);
      }
    } catch (e) {
      /* sessionStorage may be unavailable — conversion still fires sans EC */
    }
  }

  function initGoogleAds() {
    var gtag = gtagSafe();
    if (!gtag) return;
    try {
      // Report this site to the correct Google Ads account too.
      gtag("config", GADS_ACCOUNT);

      if (!isThankYou()) return;

      // Guard against double-firing on a thank-you refresh.
      var alreadyFired = false;
      try {
        alreadyFired = sessionStorage.getItem(FIRED_KEY) === "1";
      } catch (e) {}
      if (alreadyFired) return;

      // Enhanced conversions: pass the lead email if we stashed one.
      try {
        var email = sessionStorage.getItem(EMAIL_KEY);
        if (email) {
          gtag("set", "user_data", { email: email });
        }
      } catch (e) {}

      gtag("event", "conversion", { send_to: GADS_LEAD_LABEL });

      try {
        sessionStorage.setItem(FIRED_KEY, "1");
        sessionStorage.removeItem(EMAIL_KEY);
      } catch (e) {}
    } catch (e) {
      /* never break the page over analytics */
    }
  }

  function ping(form, sourceLabel) {
    try {
      if (form.querySelector('[name="botcheck"]')?.checked) return;
      var fd = new FormData(form);
      fd.set("subject", sourceLabel);
      if (!fd.get("from_name")) fd.set("from_name", "VITA Host site");
      fetch(SK_ENDPOINT, {
        method: "POST",
        body: fd,
        mode: "cors",
        keepalive: true,
        credentials: "omit",
      }).catch(function () {});
    } catch (e) {
      /* never block the user */
    }
  }

  function looksLikeNewsletter(form) {
    var inputs = form.querySelectorAll("input");
    if (inputs.length === 0) return false;
    var emailInputs = form.querySelectorAll('input[type="email"], input[name="email"]');
    var textInputs = form.querySelectorAll(
      'input[type="text"], input[type="tel"], textarea'
    );
    // single email input, nothing else meaningful = newsletter pattern
    return emailInputs.length === 1 && textInputs.length === 0;
  }

  function actionGoesNowhereUseful(form) {
    var action = form.getAttribute("action") || "";
    if (!action || action === "#" || action.indexOf("#") === 0) return true;
    if (action.indexOf("javascript:") === 0) return true;
    if (action.indexOf("/wp-comments-post.php") !== -1) return true;
    try {
      var u = new URL(action, location.href);
      // same origin AND same path as current page = posts to itself (405)
      if (u.origin === location.origin && u.pathname === location.pathname) {
        return true;
      }
    } catch (e) {
      return true; // unparsable action = nowhere useful
    }
    return false;
  }

  function attach(form) {
    if (form.dataset.skLeadBridge === "1") return;
    form.dataset.skLeadBridge = "1";

    var action = form.getAttribute("action") || "";

    // Primary contact form — Web3Forms path.
    if (action.indexOf("web3forms") !== -1) {
      form.addEventListener("submit", function () {
        captureLeadEmail(form);
        ping(form, "VITA Host — Contact form");
      });
      return;
    }

    // Any form that would 405 / go nowhere useful — intercept.
    if (actionGoesNowhereUseful(form)) {
      form.addEventListener(
        "submit",
        function (e) {
          e.preventDefault();
          e.stopPropagation();

          if (looksLikeNewsletter(form)) {
            ping(form, "VITA Host — Newsletter signup");
          }

          // Show a tiny inline confirmation so users know something happened.
          try {
            var msg = form.querySelector(".sk-bridge-thanks");
            if (!msg) {
              msg = document.createElement("div");
              msg.className = "sk-bridge-thanks";
              msg.setAttribute("role", "status");
              msg.style.marginTop = "10px";
              msg.style.padding = "8px 12px";
              msg.style.background = "#e6f7ef";
              msg.style.color = "#0b4d2c";
              msg.style.borderRadius = "4px";
              msg.style.fontSize = "14px";
              form.appendChild(msg);
            }
            msg.textContent = "Thanks — we'll be in touch within one business hour.";
            form.querySelectorAll("input, button").forEach(function (el) {
              if (el.type !== "hidden") el.disabled = true;
            });
          } catch (e) {
            /* swallow */
          }

          return false;
        },
        true
      );
      return;
    }

    // Anything else — leave untouched.
  }

  function attachAll() {
    document.querySelectorAll("form").forEach(attach);
  }

  function init() {
    attachAll();
    initGoogleAds();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
