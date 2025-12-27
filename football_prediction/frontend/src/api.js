// frontend/src/api.jsx

const API_BASE =
  import.meta.env.VITE_API_BASE_URL?.replace(/\/$/, "") || "http://127.0.0.1:8000";

// Generic response handler
async function handle(res) {
  const contentType = res.headers.get("content-type") || "";

  // try parse json if possible
  let data = null;
  if (contentType.includes("application/json")) {
    data = await res.json().catch(() => null);
  } else {
    const text = await res.text().catch(() => "");
    // if backend returns JSON but content-type is weird, try parse
    try {
      data = JSON.parse(text);
    } catch {
      data = text || null;
    }
  }

  if (!res.ok) {
    // FastAPI often returns {detail: "..."}
    const msg =
      (data && typeof data === "object" && data.detail) ||
      (typeof data === "string" && data) ||
      `Request failed: ${res.status}`;
    throw new Error(msg);
  }

  return data;
}

// --- API calls (backend routes are under /api/*) ---

export async function getLeagues() {
  const res = await fetch(`${API_BASE}/api/leagues`, {
    method: "GET",
    headers: { Accept: "application/json" }
  });
  return handle(res);
}

export async function getFixtures({ competition, date_from, date_to }) {
  const qs = new URLSearchParams({
    competition,
    date_from,
    date_to
  });

  const res = await fetch(`${API_BASE}/api/fixtures?${qs.toString()}`, {
    method: "GET",
    headers: { Accept: "application/json" }
  });

  return handle(res);
}

// Optional: keep these for later manual training buttons if you want
export async function trainOne({ competition, days_back = 60 }) {
  const res = await fetch(`${API_BASE}/api/train`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify({ competition, days_back })
  });
  return handle(res);
}

export async function trainAll({ competitions = null, days_back = 60 } = {}) {
  const res = await fetch(`${API_BASE}/api/train_all`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify({ competitions, days_back })
  });
  return handle(res);
}

export async function dbStats() {
  const res = await fetch(`${API_BASE}/api/db_stats`, {
    method: "GET",
    headers: { Accept: "application/json" }
  });
  return handle(res);
}

export async function teamRating({ competition }) {
  const qs = new URLSearchParams({ competition });
  const res = await fetch(`${API_BASE}/api/team_rating?${qs.toString()}`, {
    method: "GET",
    headers: { Accept: "application/json" }
  });
  return handle(res);
}