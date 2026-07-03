import { TOP_N, PRIORITY_TOP_N } from "./config.js?v=20260703-18";

export function getMonths(rows) {
  return [...new Set(rows.map((r) => r.연월))].sort();
}

export function monthlyCounts(rows, groupCol) {
  const map = new Map();
  for (const row of rows) {
    const key = `${row.연월}\0${row[groupCol] ?? ""}`;
    map.set(key, (map.get(key) || 0) + 1);
  }
  const out = [];
  for (const [key, count] of map.entries()) {
    const [연월, label] = key.split("\0");
    out.push({ 연월, [groupCol]: label, 장애건수: count });
  }
  return out.sort((a, b) => a.연월.localeCompare(b.연월) || b.장애건수 - a.장애건수);
}

export function topNByMonth(counts, groupCol, n = TOP_N) {
  const byMonth = new Map();
  for (const row of counts) {
    if (!byMonth.has(row.연월)) byMonth.set(row.연월, []);
    byMonth.get(row.연월).push(row);
  }
  const out = [];
  for (const month of [...byMonth.keys()].sort()) {
    byMonth
      .get(month)
      .sort((a, b) => b.장애건수 - a.장애건수)
      .slice(0, n)
      .forEach((row) => out.push(row));
  }
  return out;
}

export function attachBranchName(rows, topRows, month, deviceCol = "기번", branchCol = "지점명") {
  const subset = rows.filter((r) => r.연월 === month);
  const branchMap = new Map();
  for (const row of subset) {
    const id = row[deviceCol];
    if (!branchMap.has(id)) branchMap.set(id, {});
    const name = row[branchCol];
    branchMap.get(id)[name] = (branchMap.get(id)[name] || 0) + 1;
  }
  function pickBranch(id) {
    const counts = branchMap.get(id);
    if (!counts) return "";
    return Object.entries(counts).sort((a, b) => b[1] - a[1])[0][0];
  }
  return topRows.map((row) => ({
    ...row,
    지점이름: pickBranch(row[deviceCol]),
  }));
}

function branchCountsByDevice(rows, deviceCol = "기번", branchCol = "지점명") {
  const map = new Map();
  for (const row of rows) {
    const id = String(row[deviceCol] ?? "");
    if (!id) continue;
    if (!map.has(id)) map.set(id, new Map());
    const branch = String(row[branchCol] ?? "").trim();
    if (!branch) continue;
    const counts = map.get(id);
    counts.set(branch, (counts.get(branch) || 0) + 1);
  }
  return map;
}

export function primaryBranchForDevice(rows, deviceId, deviceCol = "기번", branchCol = "지점명", month = null) {
  let subset = rows;
  if (month) subset = subset.filter((r) => r.연월 === month);
  const counts = branchCountsByDevice(subset, deviceCol, branchCol).get(String(deviceId));
  if (!counts?.size) {
    if (month) {
      return primaryBranchForDevice(rows, deviceId, deviceCol, branchCol);
    }
    return "";
  }
  return [...counts.entries()].sort((a, b) => b[1] - a[1])[0][0];
}

export function formatDeviceLabel(deviceId, branchName) {
  const id = String(deviceId ?? "");
  const branch = String(branchName ?? "").trim();
  return branch ? `${id} (${branch})` : id;
}

function contentCountsByDetail(rows, detailCol = "세부장애", contentCol = "장애내용") {
  const map = new Map();
  for (const row of rows) {
    const code = String(row[detailCol] ?? "");
    if (!code) continue;
    const content = String(row[contentCol] ?? "").trim();
    if (!content) continue;
    if (!map.has(code)) map.set(code, new Map());
    const counts = map.get(code);
    counts.set(content, (counts.get(content) || 0) + 1);
  }
  return map;
}

export function primaryFaultContent(rows, detailCode, detailCol = "세부장애", contentCol = "장애내용") {
  const counts = contentCountsByDetail(rows, detailCol, contentCol).get(String(detailCode));
  if (!counts?.size) return "";
  return [...counts.entries()].sort((a, b) => b[1] - a[1])[0][0];
}

export function formatDetailLabel(rows, detailCode, detailCol = "세부장애", contentCol = "장애내용") {
  const code = String(detailCode ?? "");
  const content = primaryFaultContent(rows, code, detailCol, contentCol);
  if (!content) return code;
  const short = content.length > 22 ? `${content.slice(0, 20)}…` : content;
  return `${code} · ${short}`;
}

export function dailyTrend(rows, month, entityCol, entities) {
  const [year, mon] = month.split("-").map(Number);
  const lastDay = new Date(year, mon, 0).getDate();
  const subset = rows.filter(
    (r) => r.연월 === month && entities.includes(String(r[entityCol])),
  );
  const map = new Map();
  for (const row of subset) {
    const day = new Date(row.발생일자).getDate();
    if (!day) continue;
    const key = `${day}\0${row[entityCol]}`;
    map.set(key, (map.get(key) || 0) + 1);
  }
  const out = [];
  for (const ent of entities) {
    for (let day = 1; day <= lastDay; day += 1) {
      out.push({
        일: day,
        [entityCol]: ent,
        장애건수: map.get(`${day}\0${ent}`) || 0,
      });
    }
  }
  return { rows: out, lastDay };
}

export function monthlyTrend(rows, entityCol, entityValue) {
  const counts = monthlyCounts(
    rows.filter((r) => String(r[entityCol]) === String(entityValue)),
    "연월",
  );
  return counts.map((r) => ({ 연월: r.연월, 장애건수: r.장애건수 }));
}

export function entityOptions(rows, entityCol, month = null) {
  let subset = rows;
  if (month) subset = subset.filter((r) => r.연월 === month);
  const counts = new Map();
  for (const row of subset) {
    const key = String(row[entityCol]);
    counts.set(key, (counts.get(key) || 0) + 1);
  }
  return [...counts.entries()]
    .sort((a, b) => b[1] - a[1])
    .map(([value, count]) => {
      let display = value;
      if (entityCol === "기번") {
        display = formatDeviceLabel(
          value,
          primaryBranchForDevice(rows, value, "기번", "지점명", month),
        );
      }
      return { value, label: `${display} (${count.toLocaleString()}건)`, count };
    });
}

export function computePriority(rows, topN = PRIORITY_TOP_N) {
  const months = getMonths(rows);
  if (!months.length) return [];
  const recent = months.slice(-3);
  const latest = months[months.length - 1];
  const prev = months.length >= 2 ? months[months.length - 2] : null;
  const deviceCounts = monthlyCounts(rows, "기번");
  const meta = new Map();
  for (const row of rows) {
    if (!meta.has(row.기번)) meta.set(row.기번, row.기종);
  }

  const scoreMap = new Map();
  for (const [기번, 기종] of meta.entries()) {
    const 지점명 = primaryBranchForDevice(rows, 기번);
    const recentSum = deviceCounts
      .filter((r) => r.기번 === 기번 && recent.includes(r.연월))
      .reduce((s, r) => s + r.장애건수, 0);
    const cur = deviceCounts.find((r) => r.기번 === 기번 && r.연월 === latest)?.장애건수 || 0;
    const prevCount = prev
      ? deviceCounts.find((r) => r.기번 === 기번 && r.연월 === prev)?.장애건수 || 0
      : 0;
    const growth = prevCount > 0 ? ((cur - prevCount) / prevCount) * 100 : 0;
    scoreMap.set(기번, {
      기번,
      기종,
      지점명,
      기번표시: formatDeviceLabel(기번, 지점명),
      최근3개월건수: recentSum,
      전월대비증가율: growth,
      위험도점수: recentSum * 0.4 + Math.max(growth, 0) * 0.3 + cur * 0.3,
    });
  }
  return [...scoreMap.values()]
    .sort((a, b) => b.위험도점수 - a.위험도점수)
    .slice(0, topN);
}

export function drilldown(rows, filters) {
  let subset = rows;
  if (filters.month) subset = subset.filter((r) => r.연월 === filters.month);
  if (filters.faultType) subset = subset.filter((r) => r.모듈유형 === filters.faultType);
  if (filters.detailCode) subset = subset.filter((r) => r.세부장애 === filters.detailCode);
  if (filters.code2) subset = subset.filter((r) => r.장애코드2 === filters.code2);
  if (filters.branch) subset = subset.filter((r) => r.지점명 === filters.branch);
  if (filters.device) subset = subset.filter((r) => r.기번 === filters.device);
  return subset;
}

export function distribution(rows, groupCol, limit = 15) {
  const counts = new Map();
  for (const row of rows) {
    const key = String(row[groupCol] ?? "");
    counts.set(key, (counts.get(key) || 0) + 1);
  }
  return [...counts.entries()]
    .sort((a, b) => b[1] - a[1])
    .slice(0, limit)
    .map(([label, count]) => ({ [groupCol]: label, 장애건수: count }));
}
