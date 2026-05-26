/* Sarah Katerina lead bridge — fires a parallel fetch to the
 * Sarah Katerina lead pipeline on contact-form submit, so we get
 * reliable Resend/Gmail/log delivery even if the Web3Forms email
 * leg silently fails. Native submit to Web3Forms still proceeds
 * for the redirect to /thank-you/.
 *
 * Loaded on every page that embeds the static VITA Host contact form.
 */
(function () {
  function bridge() {
    var forms = document.querySelectorAll('form[action*="web3forms"]');
    if (!forms.length) return;

    Array.prototype.forEach.call(forms, function (form) {
      if (form.dataset.skLeadBridge === "1") return;
      form.dataset.skLeadBridge = "1";

      form.addEventListener("submit", function () {
        try {
          if (form.querySelector('[name="botcheck"]')?.checked) return;

          var fd = new FormData(form);
          // Source tag so Sarah's inbox can triage by site of origin.
          if (!fd.get("subject")) {
            fd.set("subject", "VITA Host — Contact form");
          }
          if (!fd.get("from_name")) {
            fd.set("from_name", "VITA Host site");
          }

          // keepalive so the request survives the upcoming page
          // navigation to /thank-you/.
          fetch("https://www.sarahkaterina.com/api/lead-notify", {
            method: "POST",
            body: fd,
            mode: "cors",
            keepalive: true,
            credentials: "omit",
          }).catch(function () {
            /* swallow — Web3Forms native submit is the user-facing path */
          });
        } catch (e) {
          /* never block the user's submit */
        }
      });
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", bridge);
  } else {
    bridge();
  }
})();
