import { KEYWORD_RULES, PASSBOOK_FAULT_CONTENTS } from "./config.js?v=20260703-18";

export function classifyFaultContent(description) {
  const text = String(description || "").trim();
  if (PASSBOOK_FAULT_CONTENTS.has(text)) return "통장부";
  for (const rule of KEYWORD_RULES) {
    if (rule.keywords.some((word) => text.includes(word))) return rule.type;
  }
  return "기타";
}

export function enrichRows(rows) {
  return rows.map((row) => ({
    ...row,
    모듈유형: classifyFaultContent(row.장애내용),
  }));
}
