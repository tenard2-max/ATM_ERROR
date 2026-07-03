export const TOP_N = 10;
export const PRIORITY_TOP_N = 20;
export const FAULT_TYPES = ["현금부", "카드부", "통장부", "통신", "기타"];

export const PASSBOOK_FAULT_CONTENTS = new Set([
  "통장 Jam 또는 잔류",
  "통장 미수취",
  "통장걸림",
  "통장부 매체 인식 불가(MS)",
]);

export const KEYWORD_RULES = [
  { keywords: ["통장", "통장부"], type: "통장부" },
  { keywords: ["카드", "명세", "IC"], type: "카드부" },
  { keywords: ["현금", "입금", "출금", "지폐", "동전", "캐시"], type: "현금부" },
  { keywords: ["통신", "네트워크", "LAN", "회선", "접속", "링크"], type: "통신" },
  { keywords: ["기구", "도어", "잠금", "센서", "프린터", "키보드", "화면", "디스플레이"], type: "기타" },
];

export const NAV_ITEMS = [
  { id: "home", label: "홈", tone: "blue" },
  { id: "compare", label: "전체비교", tone: "blue" },
  { id: "flow", label: "장애다발기기분석", tone: "orange" },
  { id: "code", label: "모듈별장애분석", tone: "purple" },
  { id: "priority", label: "중점장애관리", tone: "red" },
  { id: "data", label: "데이터관리", tone: "green" },
];

export const BAR_COLORS = [
  "#e53e3e", "#dd6b20", "#d69e2e", "#38a169", "#3182ce",
  "#4c51bf", "#805ad5", "#e11d48", "#0891b2", "#c026d3",
];
