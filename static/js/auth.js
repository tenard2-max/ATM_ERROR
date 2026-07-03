const LS_PASSWORD_HASH = "atm_access_pwd_hash";
const SESSION_AUTH = "atm_authenticated";
export const DEFAULT_PASSWORD = "000000";
const LEGACY_DEFAULT_PASSWORD = "00000";

async function sha256(text) {
  const buf = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
  return [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

export async function ensureDefaultPasswordHash() {
  const stored = localStorage.getItem(LS_PASSWORD_HASH);
  if (!stored) {
    localStorage.setItem(LS_PASSWORD_HASH, await sha256(DEFAULT_PASSWORD));
    return;
  }
  if (stored === (await sha256(LEGACY_DEFAULT_PASSWORD))) {
    localStorage.setItem(LS_PASSWORD_HASH, await sha256(DEFAULT_PASSWORD));
  }
}

export function isAuthenticated() {
  return sessionStorage.getItem(SESSION_AUTH) === "1";
}

export function setAuthenticated(value) {
  if (value) sessionStorage.setItem(SESSION_AUTH, "1");
  else sessionStorage.removeItem(SESSION_AUTH);
}

export async function verifyPassword(plain) {
  await ensureDefaultPasswordHash();
  const hash = await sha256(String(plain ?? ""));
  return hash === localStorage.getItem(LS_PASSWORD_HASH);
}

export async function changePassword(current, newPassword) {
  if (!(await verifyPassword(current))) {
    return { ok: false, message: "현재 비밀번호가 올바르지 않습니다." };
  }
  const next = String(newPassword ?? "").trim();
  if (!next) {
    return { ok: false, message: "새 비밀번호를 입력하세요." };
  }
  localStorage.setItem(LS_PASSWORD_HASH, await sha256(next));
  return { ok: true, message: "비밀번호가 변경되었습니다." };
}
