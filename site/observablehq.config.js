// Observable Framework config: static site, data = Parquet exported from the DuckLake lake (`nea export`).
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
  globalStylesheets: [
    "https://fonts.googleapis.com/css2?family=Archivo:wdth,wght@62..125,100..900&family=Source+Serif+4:ital,opsz,wght@0,8..60,200..900;1,8..60,200..900&display=swap"
  ],
  footer: "Data: Nepal Electricity Authority, Open-Meteo (ERA5, GloFAS; CC BY 4.0), World Bank, India TradeStat, CERC, news sources for flood damage. Educational, non-commercial.",
  search: true
};
