import { BAR_COLORS } from "./config.js?v=20260703-16";

export function renderBarChart(el, labels, values, title, xTitle = "장애건수") {
  if (!el || !labels.length) return;
  const yLabels = labels.map((l) => String(l ?? ""));
  const colors = yLabels.map((_, i) => BAR_COLORS[i % BAR_COLORS.length]);
  const trace = {
    type: "bar",
    orientation: "h",
    x: values,
    y: yLabels,
    text: values.map((v) => v.toLocaleString()),
    textposition: "outside",
    cliponaxis: false,
    marker: { color: colors },
  };
  const layout = {
    title,
    height: Math.max(360, yLabels.length * 44 + 80),
    margin: { l: 40, r: 72, t: 56, b: 48 },
    xaxis: { title: xTitle, rangemode: "tozero" },
    yaxis: {
      type: "category",
      categoryorder: "total ascending",
      automargin: true,
      title: "",
    },
    showlegend: false,
    bargap: 0.25,
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
