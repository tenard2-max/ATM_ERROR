import { BAR_COLORS } from "./config.js?v=20260703-12";

export function renderBarChart(el, labels, values, title, xTitle = "장애건수") {
  const colors = labels.map((_, i) => BAR_COLORS[i % BAR_COLORS.length]);
  const maxLen = Math.max(...labels.map((l) => String(l).length), 10);
  const trace = {
    type: "bar",
    orientation: "h",
    x: values,
    y: labels,
    text: values.map((v) => v.toLocaleString()),
    textposition: "outside",
    marker: { color: colors },
  };
  const layout = {
    title,
    height: Math.max(320, labels.length * 42),
    margin: { l: Math.min(320, Math.max(100, maxLen * 7)), r: 40, t: 50, b: 40 },
    xaxis: { title: xTitle },
    yaxis: { categoryorder: "total ascending" },
    showlegend: false,
  };
  Plotly.newPlot(el, [trace], layout, { responsive: true, displayModeBar: false });
}

export function renderLineChart(el, x, seriesList, title, xTitle = "일") {
  const traces = seriesList.map((s, i) => ({
    type: "scatter",
    mode: "lines+markers",
    name: s.name,
    x,
    y: s.y,
    line: { color: BAR_COLORS[i % BAR_COLORS.length], width: 2 },
  }));
  Plotly.newPlot(
    el,
    traces,
    {
      title,
      height: Math.max(380, 320 + seriesList.length * 10),
      margin: { t: 50, r: seriesList.length > 1 ? 140 : 20, b: 50, l: 50 },
      xaxis: { title: xTitle },
      yaxis: { title: "장애건수" },
      legend: seriesList.length > 1
        ? { orientation: "v", yanchor: "top", y: 1, xanchor: "left", x: 1.02 }
        : undefined,
    },
    { responsive: true, displayModeBar: false },
  );
}

export function renderTrendChart(el, months, values, title) {
  Plotly.newPlot(
    el,
    [{
      type: "scatter",
      mode: "lines+markers",
      x: months,
      y: values,
      line: { color: "#3182ce", width: 2 },
      marker: { size: 8 },
    }],
    { title, height: 360, margin: { t: 50, r: 20, b: 50, l: 50 }, yaxis: { title: "장애건수" } },
    { responsive: true, displayModeBar: false },
  );
}

export function clearChart(el) {
  if (el) Plotly.purge(el);
}
