const API_BASE =
  (import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000").replace(/\/$/, "");

async function handle(res) {
  const text = await res.text();
  let data = {};
  try {
    data = text ? JSON.parse(text) : {};
  } catch {
    data = { raw: text };
  }
  if (!res.ok) {
    const msg = data?.detail || data?.message || `HTTP ${res.status}`;
    throw new Error(msg);
  }
  return data;
}

export async function getLeagues() {
  const res = await fetch(`${API_BASE}/api/leagues`);
  return handle(res); // { leagues: [...] }
}

export async function getFixtures({ competition, date_from, date_to }) {
  const qs = new URLSearchParams({
    competition,
    date_from,
    date_to
  });
  const res = await fetch(`${API_BASE}/api/fixtures?${qs.toString()}`);
  // fixtures endpoint returns an array, so handle() must accept arrays too:
  const text = await res.text();
  if (!res.ok) {
    let msg = `HTTP ${res.status}`;
    try {
      const j = JSON.parse(text);
      msg = j.detail || msg;
    } catch {}
    throw new Error(msg);
  }
  return text ? JSON.parse(text) : [];
}