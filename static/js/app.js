import { FLOW_MODES, NAV_ITEMS, TOP_N, FAULT_TYPES } from "./config.js";
import {
  attachBranchName,
  computePriority,
  dailyTrend,
  distribution,
  drilldown,
  entityOptions,
  getMonths,
  monthlyCounts,
  monthlyTrend,
  topNByMonth,
} from "./analyzer.js";
import { renderBarChart, renderLineChart, renderTrendChart } from "./charts.js";
import {
  applyMapping,
  clearExtraRows,
  getMeta,
  getRows,
  initStore,
  loadMapping,
  replaceMonthRows,
} from "./store.js";

const state = { page: "compare", params: new URLSearchParams() };

function esc(text) {
  return String(text ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function setRoute(page, params = {}) {
  const qs = new URLSearchParams();
  for (const [key, val] of Object.entries(params)) {
    if (val == null || val === "") continue;
    if (Array.isArray(val)) {
      val.forEach((item) => {
        if (item != null && item !== "") qs.append(key, item);
      });
    } else {
      qs.set(key, val);
    }
  }
  const query = qs.toString();
  location.hash = query ? `#/${page}?${query}` : `#/${page}`;
}

function parseFlowValues(params, options, fallback = "") {
  let selected = params.getAll("value");
  if (!selected.length) {
    const legacy = params.get("value") || "";
    if (legacy.includes(",")) selected = legacy.split(",").map((v) => v.trim()).filter(Boolean);
    else if (legacy) selected = [legacy];
  }
  const valid = new Set(options.map((o) => String(o.value)));
  selected = selected.filter((v) => valid.has(String(v)));
  if (!selected.length && fallback) selected = [fallback];
  if (!selected.length && options[0]) selected = [String(options[0].value)];
  return selected;
}

function flowLabel(values) {
  if (values.length <= 3) return values.join(", ");
  return `${values.slice(0, 3).join(", ")} 외 ${values.length - 3}개`;
}

const NAV_STORAGE_KEY = "atmNavContext";

function saveNavContext(type, value, month) {
  if (!value || !month) return;
  sessionStorage.setItem(NAV_STORAGE_KEY, JSON.stringify({ type, value, month }));
}

function flowModeFromNavType(type) {
  if (type === "지점") return "지점";
  if (type === "기종") return "기종 (모델 전체)";
  return "기번 (개별 ATM)";
}

function navColFromType(type) {
  if (type === "지점") return "지점명";
  if (type === "기종") return "기종";
  return "기번";
}

function buildNavLinks(navType, value, month) {
  const rows = getRows();
  const col = navColFromType(navType);
  const scoped = rows.filter((r) => r.연월 === month && String(r[col]) === String(value));
  let topFault = "";
  if (scoped.length) {
    const counts = new Map();
    for (const row of scoped) {
      counts.set(row.세부장애, (counts.get(row.세부장애) || 0) + 1);
    }
    topFault = [...counts.entries()].sort((a, b) => b[1] - a[1])[0]?.[0] || "";
  }

  const flowLink = `#/flow?${new URLSearchParams({
    mode: flowModeFromNavType(navType),
    value,
    flow_month: month,
    view: "daily",
  }).toString()}`;

  const codeParams = { month };
  if (navType === "지점") {
    codeParams.branch = value;
  } else if (navType === "기번") {
    codeParams.device = value;
    if (topFault) codeParams.detail = topFault;
  }
  const codeLink = codeHref(codeParams);

  return { flowLink, codeLink, priorityLink: "#/priority" };
}

function renderNavActions({ month, navType, options, selectedValue }) {
  if (!month || !options?.length) return "";
  const sel = selectedValue || options[0];
  saveNavContext(navType, sel, month);
  const optsHtml = options
    .map(
      (o) =>
        `<option value="${esc(o)}"${String(o) === String(sel) ? " selected" : ""}>${esc(o)}</option>`,
    )
    .join("");
  return `
    <section class="card nav-actions" data-nav-month="${esc(month)}" data-nav-type="${esc(navType)}">
      <h3>선택 항목 → 다른 화면 이동</h3>
      <label>${esc(navType)} 선택
        <select class="nav-entity-select">${optsHtml}</select>
      </label>
      <div class="nav-btn-row">
        <a class="nav-link-btn" data-nav-target="flow" href="#">장애다발기기분석</a>
        <a class="nav-link-btn secondary" data-nav-target="code" href="#">모듈별장애분석</a>
        <a class="nav-link-btn secondary" data-nav-target="priority" href="#/priority">중점장애관리</a>
      </div>
    </section>
  `;
}

function bindNavActions() {
  document.querySelectorAll(".nav-actions").forEach((section) => {
    const month = section.dataset.navMonth;
    const navType = section.dataset.navType;
    const select = section.querySelector(".nav-entity-select");
    if (!select) return;
    const update = () => {
      const value = select.value;
      saveNavContext(navType, value, month);
      const links = buildNavLinks(navType, value, month);
      section.querySelector('[data-nav-target="flow"]').href = links.flowLink;
      section.querySelector('[data-nav-target="code"]').href = links.codeLink;
      section.querySelector('[data-nav-target="priority"]').href = links.priorityLink;
    };
    select.addEventListener("change", update);
    update();
  });
}

function codeHref(overrides = {}) {
  const merged = {
    month: state.params.get("month") || "",
    fault_type: state.params.get("fault_type") || FAULT_TYPES[0],
    detail: state.params.get("detail") || "",
    code2: state.params.get("code2") || "",
    branch: state.params.get("branch") || "",
    device: state.params.get("device") || "",
    ...overrides,
  };
  if ("fault_type" in overrides && !("detail" in overrides)) {
    merged.detail = "";
    merged.code2 = "";
    merged.branch = "";
    merged.device = "";
  }
  if ("detail" in overrides && !overrides.detail) {
    merged.code2 = "";
    merged.branch = "";
    merged.device = "";
  }
  if ("code2" in overrides && !overrides.code2) {
    merged.branch = "";
    merged.device = "";
  }
  if ("branch" in overrides && !overrides.branch) {
    merged.device = "";
  }
  const clean = {};
  for (const [key, val] of Object.entries(merged)) {
    if (val != null && val !== "") clean[key] = val;
  }
  const qs = new URLSearchParams(clean).toString();
  return qs ? `#/code?${qs}` : "#/code";
}

function parseRoute() {
  const raw = location.hash.replace(/^#\/?/, "") || "compare";
  const [page, query = ""] = raw.split("?");
  state.page = page || "compare";
  state.params = new URLSearchParams(query);
}

function tableHtml(rows, columns) {
  if (!rows.length) return '<p class="muted">표시할 데이터가 없습니다.</p>';
  const head = columns.map((c) => `<th>${esc(c.label || c)}</th>`).join("");
  const body = rows
    .map((row) => {
      const cells = columns
        .map((c) => {
          const key = c.key || c;
          const val = row[key];
          return `<td>${esc(typeof val === "number" ? val.toLocaleString() : val)}</td>`;
        })
        .join("");
      return `<tr>${cells}</tr>`;
    })
    .join("");
  return `<table class="data-table"><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>`;
}

function renderNav() {
  const nav = document.getElementById("main-nav");
  nav.innerHTML = NAV_ITEMS.map(
      (item) =>
        `<a href="#/${item.id}" class="nav-tile nav-${item.tone}${state.page === item.id ? " active" : ""}">${esc(item.label)}</a>`,
    )
    .join("");
}

function renderHome() {
  const meta = getMeta();
  return `
    <section class="portal-card">
      <h2>📊 전체기기 월별비교 PoC</h2>
      <p class="caption">GitHub Pages · 브라우저에서 바로 분석 (샘플 ${meta.rowCount.toLocaleString()}건)</p>
      ${
        meta.monthCount
          ? `<p class="caption">적재 <strong>${meta.monthCount}개월</strong> (${esc(meta.months.join(", "))})</p>
             <p class="caption"><a href="#/compare">전체비교</a>에서 분석을 시작하세요.</p>`
          : `<p class="caption">데이터가 없습니다. <a href="#/data">데이터관리</a>에서 Excel을 업로드하세요.</p>`
      }
    </section>`;
}

function renderCompare() {
  const rows = getRows();
  const months = getMonths(rows);
  if (!months.length) return `<div class="alert warn">데이터가 없습니다. <a href="#/data">데이터관리</a>에서 업로드하세요.</div>`;

  const month = state.params.get("month") || months[months.length - 1];
  const tab = state.params.get("tab") || "지점";
  const dailyEntity = state.params.get("daily_entity") || "";
  const tabs = {
    지점: { col: "지점명", navType: "지점" },
    기번: { col: "기번", navType: "기번" },
    기종: { col: "기종", navType: "기종", all: true },
  };
  const cfg = tabs[tab] || tabs.지점;
  const counts = monthlyCounts(rows, cfg.col);
  let monthData = counts.filter((r) => r.연월 === month);
  if (!cfg.all) monthData = monthData.slice(0, TOP_N);
  if (tab === "기번") monthData = attachBranchName(rows, monthData, month);

  const labels = monthData.map((r) =>
    tab === "기번" && r.지점이름 ? `${r.기번} (${r.지점이름})` : r[cfg.col],
  );
  const values = monthData.map((r) => r.장애건수);

  const tabLinks = Object.keys(tabs)
    .map(
      (key) =>
        `<a href="#/compare?month=${encodeURIComponent(month)}&tab=${encodeURIComponent(key)}" class="tab${tab === key ? " active" : ""}">${esc(key)}${key !== "기종" ? ` TOP${TOP_N}` : ""}</a>`,
    )
    .join("");

  const monthOpts = months
    .map((m) => `<option value="${esc(m)}"${m === month ? " selected" : ""}>${esc(m)}</option>`)
    .join("");

  let dailySection = "";
  if (tab === "지점" && monthData.length) {
    const entities = dailyEntity
      ? [dailyEntity]
      : monthData.slice(0, TOP_N).map((r) => r.지점명);
    const dailyOpts = monthData
      .map(
        (r) =>
          `<option value="${esc(r.지점명)}"${r.지점명 === dailyEntity ? " selected" : ""}>${esc(r.지점명)}</option>`,
      )
      .join("");
    dailySection = `
      <h3>${esc(month)} 일별 장애 추이</h3>
      <form class="inline-form card" onsubmit="return false">
        <label>지점 선택
          <select id="daily-select">
            <option value="">(TOP${TOP_N} 전체)</option>${dailyOpts}
          </select>
        </label>
      </form>
      <div id="chart-daily" class="chart-box"></div>`;
    queueMicrotask(() => {
      const { rows: dailyRows } = dailyTrend(rows, month, "지점명", entities);
      const days = [...new Set(dailyRows.map((r) => r.일))].sort((a, b) => a - b);
      const series = entities.map((ent) => ({
        name: ent,
        y: days.map((d) => dailyRows.find((r) => r.일 === d && r.지점명 === ent)?.장애건수 || 0),
      }));
      renderLineChart(document.getElementById("chart-daily"), days, series, `${month} 일별 추이`);
      document.getElementById("daily-select")?.addEventListener("change", (e) => {
        const val = e.target.value;
        const p = { month, tab };
        if (val) p.daily_entity = val;
        setRoute("compare", p);
      });
    });
  }

  queueMicrotask(() => {
    renderBarChart(
      document.getElementById("chart-compare"),
      labels.slice().reverse(),
      values.slice().reverse(),
      `${month} — ${tab}별 ${cfg.all ? "전체" : `TOP${TOP_N}`}`,
    );
  });

  return `
    <h2>📊 전체기기 월별비교</h2>
    <p class="caption">지점별 / 기번별 / 기종별 월간 장애건수 TOP10</p>
    <form class="inline-form" onsubmit="return false">
      <label>조회 연월
        <select id="month-select">${monthOpts}</select>
      </label>
    </form>
    <div class="tabs">${tabLinks}</div>
    <div class="metrics">
      <div class="metric"><span>표시</span><strong>${monthData.length}개</strong></div>
      <div class="metric"><span>합계</span><strong>${values.reduce((a, b) => a + b, 0).toLocaleString()}건</strong></div>
    </div>
    <div id="chart-compare" class="chart-box"></div>
    <h3>TOP 목록</h3>
    ${tableHtml(monthData, [
      { key: cfg.col, label: tab },
      ...(tab === "기번" ? [{ key: "지점이름", label: "지점" }] : []),
      { key: "장애건수", label: "장애건수" },
    ])}
    ${dailySection}
    ${renderNavActions({
      month,
      navType: cfg.navType,
      options: monthData.map((r) => String(r[cfg.col])),
      selectedValue: monthData[0] ? String(monthData[0][cfg.col]) : "",
    })}
  `;
}

function renderFlow() {
  const rows = getRows();
  const months = getMonths(rows);
  if (!months.length) return `<div class="alert warn">데이터가 없습니다.</div>`;

  const mode = state.params.get("mode") || "기번 (개별 ATM)";
  const col = mode === "기종 (모델 전체)" ? "기종" : mode === "지점" ? "지점명" : "기번";
  const multiSelect = col === "기번" || col === "지점명";
  const options = entityOptions(rows, col, state.params.get("flow_month") || months[months.length - 1]);
  const selectedValues = parseFlowValues(state.params, options);
  const flowMonth = state.params.get("flow_month") || months[months.length - 1];
  const view = state.params.get("view") || "daily";
  const monthTotal = rows.filter(
    (r) => r.연월 === flowMonth && selectedValues.includes(String(r[col])),
  ).length;
  const labelShort = flowLabel(selectedValues);
  const chartTitle =
    view === "monthly" ? `${labelShort} — 월별 추이` : `${labelShort} — ${flowMonth} 일별 추이`;

  queueMicrotask(() => {
    const el = document.getElementById("chart-flow");
    if (view === "monthly") {
      const allMonths = getMonths(rows);
      const series = selectedValues.map((value) => ({
        name: value,
        y: allMonths.map((m) => {
          const hit = monthlyTrend(rows, col, value).find((r) => r.연월 === m);
          return hit ? hit.장애건수 : 0;
        }),
      }));
      renderLineChart(el, allMonths, series, chartTitle, "연월");
    } else {
      const { rows: dailyRows, lastDay } = dailyTrend(rows, flowMonth, col, selectedValues);
      const days = Array.from({ length: lastDay }, (_, i) => i + 1);
      renderLineChart(
        el,
        days,
        selectedValues.map((value) => ({
          name: value,
          y: days.map(
            (day) =>
              dailyRows.find((r) => r.일 === day && String(r[col]) === String(value))?.장애건수 || 0,
          ),
        })),
        chartTitle,
        "일",
      );
    }
  });

  const modeRadios = FLOW_MODES
    .map(
      (m) =>
        `<label><input type="radio" name="mode" value="${esc(m)}"${mode === m ? " checked" : ""}> ${esc(m)}</label>`,
    )
    .join(" ");
  const monthOpts = months
    .map((m) => `<option value="${esc(m)}"${m === flowMonth ? " selected" : ""}>${esc(m)}</option>`)
    .join("");

  const selectionControl = multiSelect
    ? `<div class="check-grid">
        ${options
          .slice(0, 50)
          .map(
            (o) =>
              `<label class="check-item"><input type="checkbox" name="value" value="${esc(o.value)}"${selectedValues.includes(String(o.value)) ? " checked" : ""}> ${esc(o.label)}</label>`,
          )
          .join("")}
      </div>
      <button type="button" id="flow-apply">선택 적용</button>`
    : `<select name="value">${options
        .map(
          (o) =>
            `<option value="${esc(o.value)}"${selectedValues[0] === String(o.value) ? " selected" : ""}>${esc(o.label)}</option>`,
        )
        .join("")}</select>`;

  return `
    <h2>📈 장애다발기기분석</h2>
    <p class="caption">기본 일별 분석 · 기번/지점 복수 선택 가능</p>
    <form id="flow-form" class="inline-form card">
      <fieldset><legend>분석 단위</legend>${modeRadios}</fieldset>
      <label>${esc(col)} 선택 ${multiSelect ? "(복수)" : ""}
        ${selectionControl}
      </label>
      <label>조회 연월 <select name="flow_month">${monthOpts}</select></label>
      <fieldset>
        <legend>분석 보기</legend>
        <label><input type="radio" name="view" value="daily"${view === "daily" ? " checked" : ""}> 일별</label>
        <label><input type="radio" name="view" value="monthly"${view === "monthly" ? " checked" : ""}> 월별</label>
      </fieldset>
    </form>
    <div class="metrics">
      <div class="metric"><span>선택</span><strong>${selectedValues.length}개</strong></div>
      <div class="metric"><span>분석 대상</span><strong>${esc(labelShort)}</strong></div>
      <div class="metric"><span>조회 연월</span><strong>${esc(flowMonth)}</strong></div>
      <div class="metric"><span>해당 월 장애</span><strong>${monthTotal.toLocaleString()}건</strong></div>
    </div>
    <h3>${esc(chartTitle)}</h3>
    <div id="chart-flow" class="chart-box"></div>
    ${
      view === "monthly" && selectedValues.length === 1
      && getMonths(rows.filter((r) => String(r[col]) === String(selectedValues[0]))).length < 2
        ? '<div class="alert info">추세 분석을 위해 더 많은 월별 데이터가 필요합니다.</div>'
        : ""
    }
    ${renderNavActions({
      month: flowMonth,
      navType: col === "지점명" ? "지점" : col === "기종" ? "기종" : "기번",
      options: selectedValues.length ? selectedValues : options.map((o) => String(o.value)),
      selectedValue: selectedValues[0] || options[0]?.value || "",
    })}
  `;
}

function renderCode() {
  const rows = getRows();
  const months = getMonths(rows);
  if (!months.length) return `<div class="alert warn">데이터가 없습니다.</div>`;

  const month = state.params.get("month") || months[months.length - 1];
  const faultType = state.params.get("fault_type") || FAULT_TYPES[0];
  const detailCode = state.params.get("detail") || "";
  const code2 = state.params.get("code2") || "";
  const branch = state.params.get("branch") || "";
  const device = state.params.get("device") || "";

  const moduleScope = drilldown(rows, { month, faultType });
  if (!moduleScope.length) {
    return `<h2>🧩 모듈별장애분석</h2>
      <form id="code-form" class="inline-form card">
        <label>연월 <select name="month">${months.map((m) => `<option value="${esc(m)}"${m === month ? " selected" : ""}>${esc(m)}</option>`).join("")}</select></label>
        <label>모듈 <select name="fault_type">${FAULT_TYPES.map((t) => `<option value="${esc(t)}"${t === faultType ? " selected" : ""}>${esc(t)}</option>`).join("")}</select></label>
      </form>
      <div class="alert warn">${esc(month)} · ${esc(faultType)} 데이터가 없습니다.</div>`;
  }

  const faultList = distribution(moduleScope, "세부장애", 30);
  const activeDetail = detailCode || faultList[0]?.세부장애 || "";
  const detailScope = activeDetail ? drilldown(moduleScope, { detailCode: activeDetail }) : moduleScope;
  const code2List = distribution(detailScope, "장애코드2", 20).filter((d) => d.장애코드2);
  const activeCode2 = code2 || code2List[0]?.장애코드2 || "";
  const code2Scope = activeCode2 ? drilldown(detailScope, { code2: activeCode2 }) : detailScope;
  const branchList = distribution(code2Scope, "지점명", 15);
  const activeBranch = branch;
  const branchScope = activeBranch ? drilldown(code2Scope, { branch: activeBranch }) : code2Scope;
  const deviceList = activeBranch ? distribution(branchScope, "기번", 20) : [];
  const activeDevice = device;
  const deviceScope = activeDevice ? drilldown(branchScope, { device: activeDevice }) : branchScope;

  queueMicrotask(() => {
    if (faultList.length) {
      renderBarChart(
        document.getElementById("chart-code-fault"),
        faultList.map((d) => d.세부장애).slice().reverse(),
        faultList.map((d) => d.장애건수).slice().reverse(),
        `${faultType} — 세부장애 분포`,
      );
    }
    if (code2List.length) {
      renderBarChart(
        document.getElementById("chart-code2"),
        code2List.map((d) => d.장애코드2).slice().reverse(),
        code2List.map((d) => d.장애건수).slice().reverse(),
        `${activeDetail} — 장애코드2 분포`,
      );
    }
    if (branchList.length) {
      renderBarChart(
        document.getElementById("chart-code-branch"),
        branchList.map((d) => d.지점명).slice().reverse(),
        branchList.map((d) => d.장애건수).slice().reverse(),
        `${activeCode2} — 지점별 분포`,
      );
    }
    if (deviceList.length) {
      renderBarChart(
        document.getElementById("chart-code-device"),
        deviceList.map((d) => deviceWithBranch({ 기번: d.기번, 지점명: activeBranch })).slice().reverse(),
        deviceList.map((d) => d.장애건수).slice().reverse(),
        `${activeBranch} — 기번별 분포`,
      );
    }
    if (activeDevice && deviceScope.length) {
      const dailyMap = new Map();
      for (const row of deviceScope) {
        const day = String(row.발생일자).slice(0, 10);
        dailyMap.set(day, (dailyMap.get(day) || 0) + 1);
      }
      const days = [...dailyMap.keys()].sort();
      renderLineChart(
        document.getElementById("chart-code-daily"),
        days,
        [{ name: activeDevice, y: days.map((d) => dailyMap.get(d) || 0) }],
        `${activeDevice} — 일별 추이`,
        "발생일",
      );
    }
  });

  const monthOpts = months
    .map((m) => `<option value="${esc(m)}"${m === month ? " selected" : ""}>${esc(m)}</option>`)
    .join("");
  const typeOpts = FAULT_TYPES.map(
    (t) => `<option value="${esc(t)}"${t === faultType ? " selected" : ""}>${esc(t)}</option>`,
  ).join("");

  return `
    <h2>🧩 모듈별장애분석</h2>
    <form id="code-form" class="inline-form card">
      <label>연월 <select name="month">${monthOpts}</select></label>
      <label>모듈 <select name="fault_type">${typeOpts}</select></label>
      ${detailCode ? `<input type="hidden" name="detail" value="${esc(detailCode)}">` : ""}
      ${code2 ? `<input type="hidden" name="code2" value="${esc(code2)}">` : ""}
      ${branch ? `<input type="hidden" name="branch" value="${esc(branch)}">` : ""}
      ${device ? `<input type="hidden" name="device" value="${esc(device)}">` : ""}
    </form>

    <section class="card">
      <h3>Step 2 · 세부장애 <span class="muted">(${moduleScope.length.toLocaleString()}건)</span></h3>
      <div class="grid-2">
        <div id="chart-code-fault" class="chart-box"></div>
        <div>
          <div class="chip-row">
            ${faultList
              .map(
                (d) =>
                  `<a class="chip${d.세부장애 === (detailCode || activeDetail) ? " active" : ""}" href="${codeHref({ detail: d.세부장애, code2: "", branch: "", device: "" })}">${esc(d.세부장애)} (${d.장애건수})</a>`,
              )
              .join("")}
          </div>
          ${tableHtml(faultList, [{ key: "세부장애", label: "세부장애" }, { key: "장애건수", label: "장애건수" }])}
        </div>
      </div>
    </section>

    ${
      detailCode && code2List.length
        ? `<section class="card">
            <h3>Step 3 · 장애코드2</h3>
            <div class="chip-row">
              ${code2List
                .map(
                  (d) =>
                    `<a class="chip${d.장애코드2 === activeCode2 ? " active" : ""}" href="${codeHref({ detail: activeDetail, code2: d.장애코드2, branch: "", device: "" })}">${esc(d.장애코드2)} (${d.장애건수})</a>`,
                )
                .join("")}
            </div>
            <div class="grid-2">
              <div id="chart-code2" class="chart-box"></div>
              <div>${tableHtml(code2List, [{ key: "장애코드2", label: "장애코드2" }, { key: "장애건수", label: "장애건수" }])}</div>
            </div>
          </section>`
        : ""
    }

    ${
      detailCode && branchList.length
        ? `<section class="card">
            <h3>Step 4 · 지점별 분포</h3>
            <div class="chip-row">
              ${branchList
                .map(
                  (d) =>
                    `<a class="chip${d.지점명 === activeBranch ? " active" : ""}" href="${codeHref({ detail: activeDetail, code2: activeCode2, branch: d.지점명, device: "" })}">${esc(d.지점명)} (${d.장애건수})</a>`,
                )
                .join("")}
            </div>
            <div id="chart-code-branch" class="chart-box"></div>
          </section>`
        : ""
    }

    ${
      activeBranch && deviceList.length
        ? `<section class="card">
            <h3>Step 5 · ${esc(activeBranch)} 기번별 분포</h3>
            <div class="chip-row">
              ${deviceList
                .map(
                  (d) =>
                    `<a class="chip${d.기번 === activeDevice ? " active" : ""}" href="${codeHref({ detail: activeDetail, code2: activeCode2, branch: activeBranch, device: d.기번 })}">${esc(d.기번)} (${d.장애건수})</a>`,
                )
                .join("")}
            </div>
            <div class="grid-2">
              <div id="chart-code-device" class="chart-box"></div>
              <div>${tableHtml(deviceList, [{ key: "기번", label: "기번" }, { key: "장애건수", label: "장애건수" }])}</div>
            </div>
          </section>`
        : ""
    }

    ${
      activeDevice
        ? `<section class="card">
            <h3>Step 6 · ${esc(activeDevice)} 일별 추이</h3>
            <div id="chart-code-daily" class="chart-box"></div>
          </section>`
        : ""
    }
    ${renderNavActions({
      month,
      navType: activeDevice ? "기번" : activeBranch ? "지점" : "기번",
      options: activeDevice
        ? [activeDevice]
        : activeBranch
          ? [activeBranch]
          : faultList.slice(0, 10).map((d) => String(d.세부장애)),
      selectedValue: activeDevice || activeBranch || faultList[0]?.세부장애 || "",
    })}
  `;
}

function deviceWithBranch(row) {
  return row.지점명 ? `${row.기번} (${row.지점명})` : row.기번;
}

function renderPriority() {
  const rows = getRows();
  const ranked = computePriority(rows);
  if (!ranked.length) return `<div class="alert warn">데이터가 없습니다.</div>`;

  queueMicrotask(() => {
    renderBarChart(
      document.getElementById("chart-priority"),
      ranked.map((r) => deviceWithBranch(r)).reverse(),
      ranked.map((r) => Math.round(r.위험도점수)).reverse(),
      `위험도 TOP${ranked.length} (기번)`,
      "위험도",
    );
  });

  return `
    <h2>🎯 중점장애관리</h2>
    <div id="chart-priority" class="chart-box"></div>
    ${tableHtml(ranked, [
      { key: "기번", label: "기번" },
      { key: "지점명", label: "지점" },
      { key: "기종", label: "기종" },
      { key: "최근3개월건수", label: "최근3개월" },
      { key: "전월대비증가율", label: "증가율(%)" },
      { key: "위험도점수", label: "위험도" },
    ])}
    ${renderNavActions({
      month: getMonths(getRows()).slice(-1)[0] || "",
      navType: "기번",
      options: ranked.map((r) => String(r.기번)),
      selectedValue: ranked[0] ? String(ranked[0].기번) : "",
    })}
  `;
}

function renderData() {
  const meta = getMeta();
  return `
    <h2>📁 데이터관리</h2>
    <p class="caption">브라우저에 Excel(.xlsx) 업로드 · 샘플 ${meta.rowCount.toLocaleString()}건 내장</p>
    <div class="metrics">
      <div class="metric"><span>월 수</span><strong>${meta.monthCount}</strong></div>
      <div class="metric"><span>총 건수</span><strong>${meta.rowCount.toLocaleString()}</strong></div>
    </div>
    <p class="caption">월: ${esc(meta.months.join(", ") || "-")}</p>
    <form id="upload-form" class="card">
      <label>장애리스트 Excel 업로드 (.xlsx)
        <input type="file" id="upload-file" accept=".xlsx,.xls">
      </label>
      <button type="submit">업로드·적재</button>
    </form>
    <button id="clear-extra" class="secondary" type="button">브라우저 추가 데이터 초기화</button>
    <p id="upload-msg" class="caption"></p>
  `;
}

function bindForms() {
  document.getElementById("month-select")?.addEventListener("change", (e) => {
    setRoute("compare", { month: e.target.value, tab: state.params.get("tab") || "지점" });
  });
  const flowForm = document.getElementById("flow-form");
  flowForm?.addEventListener("change", (event) => {
    if (event.target.name === "value" && event.target.type === "checkbox") return;
    const fd = new FormData(flowForm);
    const params = {};
    for (const [key, val] of fd.entries()) {
      if (key === "value" && flowForm.querySelector('input[name="value"][type="checkbox"]')) {
        if (!params.value) params.value = [];
        params.value.push(val);
      } else {
        params[key] = val;
      }
    }
    if (!params.value && flowForm.querySelector('select[name="value"]')) {
      params.value = fd.get("value");
    }
    setRoute("flow", params);
  });
  document.getElementById("flow-apply")?.addEventListener("click", () => {
    const fd = new FormData(flowForm);
    const params = {};
    for (const [key, val] of fd.entries()) {
      if (key === "value") {
        if (!params.value) params.value = [];
        params.value.push(val);
      } else {
        params[key] = val;
      }
    }
    if (!params.value) params.value = [];
    setRoute("flow", params);
  });
  const codeForm = document.getElementById("code-form");
  codeForm?.addEventListener("change", (e) => {
    const target = e.target;
    if (!(target instanceof HTMLSelectElement)) return;
    const fd = new FormData(codeForm);
    const month = fd.get("month");
    const faultType = fd.get("fault_type");
    if (target.name === "fault_type") {
      setRoute("code", { month, fault_type: faultType });
      return;
    }
    if (target.name === "month") {
      const params = { month, fault_type: faultType };
      for (const key of ["detail", "code2", "branch", "device"]) {
        const val = fd.get(key);
        if (val) params[key] = val;
      }
      setRoute("code", params);
    }
  });
  document.getElementById("upload-form")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const msg = document.getElementById("upload-msg");
    const file = document.getElementById("upload-file").files[0];
    if (!file) {
      msg.textContent = "파일을 선택하세요.";
      return;
    }
    try {
      const mapping = await loadMapping();
      const buffer = await file.arrayBuffer();
      const wb = XLSX.read(buffer, { type: "array" });
      const sheet = wb.Sheets[wb.SheetNames[0]];
      const raw = XLSX.utils.sheet_to_json(sheet, { defval: "" });
      const required = ["점번", "지점명", "기번", "기종", "발생일자", "세부장애", "장애내용"];
      for (const col of required) {
        if (!(col in (raw[0] || {}))) throw new Error(`필수 컬럼 누락: ${col}`);
      }
      let rows = raw.map((r) => {
        const d = new Date(r.발생일자);
        const 연월 = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
        return {
          연월,
          점번: String(r.점번),
          지점명: String(r.지점명),
          기번: String(r.기번),
          기종: String(r.기종),
          발생일자: String(r.발생일자).slice(0, 10),
          세부장애: String(r.세부장애),
          장애내용: String(r.장애내용),
          장애코드2: String(r.장애코드2 || ""),
        };
      });
      rows = applyMapping(rows, mapping);
      const month = rows[0]?.연월;
      replaceMonthRows(month, rows);
      msg.textContent = `${file.name} — ${month} ${rows.length.toLocaleString()}건 저장 (브라우저)`;
      render();
    } catch (err) {
      msg.textContent = err.message || String(err);
    }
  });
  document.getElementById("clear-extra")?.addEventListener("click", () => {
    clearExtraRows();
    document.getElementById("upload-msg").textContent = "브라우저 추가 데이터를 초기화했습니다.";
    render();
  });
  bindNavActions();
}

function render() {
  parseRoute();
  renderNav();
  const app = document.getElementById("app");
  const views = {
    home: renderHome,
    compare: renderCompare,
    flow: renderFlow,
    code: renderCode,
    priority: renderPriority,
    data: renderData,
  };
  const fn = views[state.page] || views.compare;
  app.innerHTML = fn();
  bindForms();
  document.getElementById("subtitle").textContent =
    `GitHub Pages · ${getMeta().rowCount.toLocaleString()}건 · ${location.hostname}`;
}

async function boot() {
  const app = document.getElementById("app");
  app.innerHTML = '<p class="caption">데이터 로딩 중…</p>';
  try {
    await initStore();
    if (!location.hash || location.hash === "#" || location.hash === "#/") {
      location.replace("#/compare");
    }
    render();
    window.addEventListener("hashchange", render);
  } catch (err) {
    app.innerHTML = `<div class="alert error">로드 실패: ${esc(err.message)}</div>`;
  }
}

boot();
