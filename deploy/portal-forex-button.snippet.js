/**
 * JM TECH SOLUTION — Forex Trading nav button
 *
 * Add this to the sidebar `.nav` in the jmtechsolution.cloud portal SPA.
 * Opens the JM Forex desk hosted at forex.jmtechsolution.cloud
 */

const FOREX_URL = "https://forex.jmtechsolution.cloud";

// htm / React style (matches JM Tech portal patterns):
html`<button
  type="button"
  className=${page === "forex" ? "act" : ""}
  onClick=${() => window.open(FOREX_URL, "_blank", "noopener,noreferrer")}
>
  <span aria-hidden="true">FX</span> Forex Trading
</button>`;

// Plain HTML fallback:
// <a href="https://forex.jmtechsolution.cloud" target="_blank" rel="noopener noreferrer">Forex Trading</a>
