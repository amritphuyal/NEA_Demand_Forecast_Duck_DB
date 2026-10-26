// Observable Framework config: static site, data = Parquet exported from the DuckLake lake (`nea export`).

// Enlarge button on every chart, the map and the overview figure: real fullscreen where supported,
// a full-page overlay otherwise (iPhone Safari). Esc or the button closes it.
const ZOOM = `<script type="module">
const SEL = '.nea-mirror, .observablehq--block:has(svg[class^="plot-"], .leaflet-container)';
let open = null;
function label(el, on) {
  const b = el.querySelector(":scope > .nea-zoom");
  if (b) { b.textContent = on ? "✕" : "⤢"; b.title = on ? "Close (Esc)" : "Enlarge"; b.setAttribute("aria-label", b.title); }
}
function set(el, on) {
  el.classList.toggle("nea-zoomed", on);
  document.documentElement.classList.toggle("nea-noscroll", on);
  label(el, on);
  dispatchEvent(new Event("resize"));  // Leaflet re-measures the map
}
function toggle(el) {
  if (open) { const o = open; open = null; if (document.fullscreenElement) document.exitFullscreen().catch(() => {}); set(o, false); return; }
  open = el; set(el, true);
  el.requestFullscreen?.().catch(() => {});
}
document.addEventListener("fullscreenchange", () => { if (!document.fullscreenElement && open) toggle(open); });
document.addEventListener("keydown", (e) => { if (e.key === "Escape" && open && !document.fullscreenElement) toggle(open); });
function scan() {
  for (const el of document.querySelectorAll(SEL)) {
    if (el.matches(".observablehq--block") && el.closest(".nea-mirror")) continue;
    if (el.querySelector(":scope > .nea-zoom")) continue;
    const b = Object.assign(document.createElement("button"), {type: "button", className: "nea-zoom"});
    b.onclick = () => toggle(el);
    el.prepend(b);
    label(el, el === open);
  }
}
let queued = false;
new MutationObserver(() => { if (!queued) { queued = true; requestAnimationFrame(() => { queued = false; scan(); }); } })
  .observe(document.body, {childList: true, subtree: true});
scan();
</script>`;

export default {
  title: "Nepal Electricity: Winter Outlook",
  pages: [
    {name: "How it works", path: "/architecture"},
    {name: "Map", path: "/map"},
    {name: "Data", path: "/data"},
    {name: "Analysis", path: "/analysis"},
    {name: "Models", path: "/models"},
    {name: "Forecast", path: "/forecast"},
    {name: "SQL explorer", path: "/sql"},
    {name: "Method & limits", path: "/method"}
  ],
  root: "src",
  style: "theme.css",
  head: ZOOM,
  globalStylesheets: [
    "https://fonts.googleapis.com/css2?family=Archivo:wdth,wght@62..125,100..900&family=Source+Serif+4:ital,opsz,wght@0,8..60,200..900;1,8..60,200..900&display=swap"
  ],
  footer: "Data: Nepal Electricity Authority, Open-Meteo (ERA5, GloFAS; CC BY 4.0), World Bank, India TradeStat, CERC, news sources for flood damage. Educational, non-commercial.",
  search: true
};
