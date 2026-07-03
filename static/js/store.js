import { enrichRows } from "./classify.js?v=20260703-18";

const LS_KEY = "atm_fault_extra_rows";

let baseRows = [];
let extraRows = [];

function dataUrl(name) {
  return new URL(`../data/${name}`, import.meta.url).href;
}

function loadExtraFromStorage() {
  try {
    const raw = localStorage.getItem(LS_KEY);
    extraRows = raw ? JSON.parse(raw) : [];
  } catch {
    extraRows = [];
  }
}

function saveExtraToStorage() {
  localStorage.setItem(LS_KEY, JSON.stringify(extraRows));
}

export async function initStore() {
  loadExtraFromStorage();
  const res = await fetch(dataUrl("incidents.json"));
  if (!res.ok) throw new Error(`데이터 로드 실패 (${res.status})`);
  baseRows = enrichRows(await res.json());
}

export function getRows() {
  return enrichRows([...baseRows, ...extraRows]);
}

export function getMeta() {
  const rows = getRows();
  const months = [...new Set(rows.map((r) => r.연월))].sort();
  return { rowCount: rows.length, months, monthCount: months.length };
}

export function replaceMonthRows(month, newRows) {
  extraRows = extraRows.filter((r) => r.연월 !== month);
  extraRows.push(...enrichRows(newRows));
  saveExtraToStorage();
}

export function clearExtraRows() {
  extraRows = [];
  saveExtraToStorage();
}

export async function loadMapping() {
  const res = await fetch(dataUrl("mapping.json"));
  if (!res.ok) return [];
  return res.json();
}

export function applyMapping(rows, mappingRows) {
  const map = new Map(mappingRows.map((r) => [String(r.세부장애), String(r.장애코드2)]));
  return rows.map((row) => ({
    ...row,
    장애코드2: row.장애코드2 || map.get(String(row.세부장애)) || String(row.세부장애),
  }));
}
