import { BAR_COLORS } from "./config.js?v=20260703-17";

const BAR_ROW_HEIGHT = 56;
const BAR_GAP = 0.01;
const BAR_WIDTH = 0.98;

export function renderBarChart(el, labels, values, title, xTitle = "장애건수", yTitle = "") {
  if (!el || !labels.length) return;
  const pairs = labels.map((label, i) => ({
    label: String(label ?? ""),
    value: Number(values[i]) || 0,
  }));
  // 장애건수 적은 항목 → 아래, 많은 항목 → 위
  pairs.sort((a, b) => a.value - b.value);
  const yLabels = pairs.map((p) => p.label);
  const xValues = pairs.map((p) => p.value);
  const colors = yLabels.map((_, i) => BAR_COLORS[i % BAR_COLORS.length]);
  const trace = {
    type: "bar",
    orientation: "h",
    x: xValues,
    y: yLabels,
    text: xValues.map((v) => v.toLocaleString()),
    textposition: "outside",
    cliponaxis: false,
    width: BAR_WIDTH,
    marker: {
      color: colors,
      line: { width: 10, color: colors },
    },
  };
  const layout = {
    title,
    height: Math.max(420, yLabels.length * BAR_ROW_HEIGHT + 100),
    margin: { l: 48, r: 80, t: 56, b: 48 },
    xaxis: { title: xTitle, rangemode: "tozero" },
    yaxis: {
      type: "category",
      categoryorder: "array",
      categoryarray: yLabels,
      automargin: true,
      title: yTitle,
    },
    showlegend: false,
    bargap: BAR_GAP,
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
