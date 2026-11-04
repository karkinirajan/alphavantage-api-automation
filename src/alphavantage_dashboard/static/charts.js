// The charts page: four SVG charts drawn from the JSON of /api/candles and /api/compare.
// No chart library: the first version loaded an unpinned ApexCharts from a CDN. Text is set with textContent only.
// Each chart is drawn at the width of its box (so its text keeps its real size on a phone) and redrawn on resize.
(() => {
  const controls = document.getElementById("chartControls");
  if (!controls) return;
  const NS = "http://www.w3.org/2000/svg";
  const M = { l: 58, r: 14, t: 14, b: 28 };
  const byId = (id) => document.getElementById(id);
  const message = byId("chartMessage");
  const number = (v) => v.toLocaleString(undefined, { maximumFractionDigits: 2 });
  let current = null; // the candles on screen, so a colour change redraws without asking the API again
  let compared = null; // the comparison on screen
  let touched = false; // true once the person has picked a candle colour: the theme no longer sets them

  // The default candle colours are the theme's blue and orange (the CSS variables), so they keep their contrast
  // against the card in the light and the dark theme. A colour input needs #rrggbb.
  function themeColours() {
    const css = getComputedStyle(document.documentElement);
    byId("bullish").value = css.getPropertyValue("--blue").trim();
    byId("bearish").value = css.getPropertyValue("--orange").trim();
  }

  function svgEl(name, attrs, text) {
    const node = document.createElementNS(NS, name);
    for (const [key, value] of Object.entries(attrs || {})) node.setAttribute(key, String(value));
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function ticks(min, max, count = 5) {
    if (min === max) { min -= 1; max += 1; }
    const raw = (max - min) / count;
    const magnitude = 10 ** Math.floor(Math.log10(raw));
    const step = [1, 2, 5, 10].map((m) => m * magnitude).find((s) => s >= raw) || 10 * magnitude;
    const out = [];
    for (let v = Math.floor(min / step) * step; v <= Math.ceil(max / step) * step + step / 2; v += step) {
      out.push(Number(v.toFixed(10)));
    }
    return out;
  }

  // An empty chart with axes, as wide as its box. x is the position of a day (0..n-1), y is a price.
  // `top` is the space above the plot (a legend goes there).
  function frame(container, label, dates, low, high, top = M.t) {
    container.replaceChildren();
    const W = Math.max(280, Math.floor(container.clientWidth || 800));
    const H = Math.round(Math.min(380, Math.max(240, W * 0.4)));
    const svg = svgEl("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": label });
    const yTicks = ticks(low, high);
    const yMin = yTicks[0], yMax = yTicks[yTicks.length - 1];
    const plotW = W - M.l - M.r, plotH = H - top - M.b;
    const x = (i) => M.l + (dates.length < 2 ? plotW / 2 : (i / (dates.length - 1)) * plotW);
    const y = (v) => top + plotH - ((v - yMin) / (yMax - yMin)) * plotH;
    for (const t of yTicks) {
      svg.append(svgEl("line", { class: "grid", x1: M.l, x2: W - M.r, y1: y(t), y2: y(t) }));
      svg.append(svgEl("text", { class: "tick", x: M.l - 6, y: y(t) + 4, "text-anchor": "end" }, number(t)));
    }
    const marks = new Set([0, Math.floor((dates.length - 1) / 2), dates.length - 1]);
    for (const i of marks) {
      svg.append(svgEl("text", { class: "tick", x: x(i), y: H - 8, "text-anchor": i === 0 ? "start" : i === dates.length - 1 ? "end" : "middle" }, dates[i]));
    }
    container.append(svg);
    return { svg, x, y, plotW };
  }

  const summary = (what, symbol, c) => `${what} of ${symbol}, ${c.length} trading days from ${c[0].t} to ${c[c.length - 1].t}; last close ${number(c[c.length - 1].c)}`;

  function drawCandles(data) {
    const c = data.candles, dates = c.map((d) => d.t);
    const { svg, x, y, plotW } = frame(byId("candles"), summary("Candlestick chart", data.symbol, c), dates, Math.min(...c.map((d) => d.l)), Math.max(...c.map((d) => d.h)));
    const up = byId("bullish").value, down = byId("bearish").value;
    const width = Math.max(1.5, (plotW / c.length) * 0.6);
    c.forEach((d, i) => {
      const rising = d.c >= d.o, colour = rising ? up : down;
      const g = svgEl("g");
      g.append(svgEl("title", {}, `${d.t}  open ${number(d.o)}  high ${number(d.h)}  low ${number(d.l)}  close ${number(d.c)}  ${rising ? "up" : "down"}`));
      g.append(svgEl("line", { x1: x(i), x2: x(i), y1: y(d.h), y2: y(d.l), stroke: colour, "stroke-width": 1.5 }));
      // Rising days are hollow and falling days are filled, so the two differ by more than colour
      g.append(svgEl("rect", { x: x(i) - width / 2, y: y(Math.max(d.o, d.c)), width, height: Math.max(1, Math.abs(y(d.o) - y(d.c))), stroke: colour, "stroke-width": 1.5, fill: rising ? "none" : colour }));
      svg.append(g);
    });
  }

  function drawLine(data) {
    const c = data.candles, dates = c.map((d) => d.t);
    const { svg, x, y } = frame(byId("line"), summary("Line chart of closing prices", data.symbol, c), dates, Math.min(...c.map((d) => d.c)), Math.max(...c.map((d) => d.c)));
    svg.append(svgEl("polyline", { class: "series-a", points: c.map((d, i) => `${x(i)},${y(d.c)}`).join(" ") }));
    c.forEach((d, i) => {
      const dot = svgEl("circle", { cx: x(i), cy: y(d.c), r: 5, fill: "transparent" });
      dot.append(svgEl("title", {}, `${d.t}  close ${number(d.c)}`));
      svg.append(dot);
    });
  }

  function drawRange(data) {
    const c = data.candles, dates = c.map((d) => d.t);
    const { svg, x, y } = frame(byId("range"), summary("Chart of the daily high and low", data.symbol, c), dates, Math.min(...c.map((d) => d.l)), Math.max(...c.map((d) => d.h)));
    c.forEach((d, i) => {
      const g = svgEl("g");
      g.append(svgEl("title", {}, `${d.t}  low ${number(d.l)}  high ${number(d.h)}`));
      g.append(svgEl("line", { class: "range", x1: x(i), x2: x(i), y1: y(d.h), y2: y(d.l) }));
      svg.append(g);
    });
  }

  function drawCompare(data) {
    const first = new Map(data.a.closes.map((d) => [d.t, d.c]));
    const days = data.b.closes.filter((d) => first.has(d.t)).map((d) => d.t).sort();
    const container = byId("compare");
    if (days.length < 2) { container.replaceChildren(); note("The two symbols have too few trading days in common to compare."); return; }
    const second = new Map(data.b.closes.map((d) => [d.t, d.c]));
    // Each series is set to 100 on the first common day: prices on different scales cannot share an axis otherwise
    const a = days.map((t) => (first.get(t) / first.get(days[0])) * 100);
    const b = days.map((t) => (second.get(t) / second.get(days[0])) * 100);
    const label = `Comparison of ${data.a.symbol} and ${data.b.symbol}, closing prices set to 100 on ${days[0]}; ${days[days.length - 1]}: ${number(a[a.length - 1])} and ${number(b[b.length - 1])}`;
    // 40px above the plot hold the legend, so that it never covers the lines
    const { svg, x, y } = frame(container, label, days, Math.min(...a, ...b), Math.max(...a, ...b), 40);
    svg.append(svgEl("polyline", { class: "series-a", points: a.map((v, i) => `${x(i)},${y(v)}`).join(" ") }));
    svg.append(svgEl("polyline", { class: "series-b", points: b.map((v, i) => `${x(i)},${y(v)}`).join(" ") }));
    svg.append(svgEl("text", { class: "legend-a", x: M.l, y: 14 }, `${data.a.symbol} (solid line)`));
    svg.append(svgEl("text", { class: "legend-b", x: M.l, y: 31 }, `${data.b.symbol} (dashed line)`));
  }

  function drawAll() {
    if (current) { drawCandles(current); drawLine(current); drawRange(current); }
    if (compared) drawCompare(compared);
  }

  function note(text) { message.hidden = !text; message.textContent = text || ""; }

  async function getJson(url) {
    const response = await fetch(url, { headers: { Accept: "application/json" } });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.error || "The data could not be loaded.");
    return data;
  }

  async function showSymbol() {
    const symbol = byId("symbol").value.trim();
    note("Loading " + symbol + "...");
    try {
      current = await getJson(`${controls.dataset.candlesUrl}?symbol=${encodeURIComponent(symbol)}`);
      note("");
      drawCandles(current); drawLine(current); drawRange(current);
    } catch (error) {
      current = null;
      for (const id of ["candles", "line", "range"]) byId(id).replaceChildren();
      note(error.message);
    }
  }

  async function showComparison() {
    const a = byId("first").value.trim(), b = byId("second").value.trim();
    try {
      compared = await getJson(`${controls.dataset.compareUrl}?a=${encodeURIComponent(a)}&b=${encodeURIComponent(b)}`);
      drawCompare(compared);
    } catch (error) {
      compared = null;
      byId("compare").replaceChildren();
      note(error.message);
    }
  }

  controls.addEventListener("submit", (event) => { event.preventDefault(); showSymbol(); });
  byId("compareControls").addEventListener("submit", (event) => { event.preventDefault(); showComparison(); });
  for (const id of ["bullish", "bearish"]) {
    byId(id).addEventListener("input", () => { touched = true; if (current) drawCandles(current); });
  }
  themeColours();
  window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => {
    if (!touched) { themeColours(); if (current) drawCandles(current); }
  });
  let resizing;
  window.addEventListener("resize", () => { clearTimeout(resizing); resizing = setTimeout(drawAll, 150); });
  showSymbol().then(showComparison);
})();
