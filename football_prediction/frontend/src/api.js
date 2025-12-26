const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000";

async function handle(res) {
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(JSON.stringify(data, null, 2));
  return data;
}

export async function getSchema() {
  // backend returns: numeric_features, categorical_features, categorical_values
  const res = await fetch(`${API_BASE}/schema`);
  const s = await handle(res);

  // Adapt to what the dashboard expects:
  return {
    numeric: s.numeric_features || [],
    categorical: s.categorical_values || {},
  };
}

export async function predictSimple(payload) {
  const res = await fetch(`${API_BASE}/predict_simple`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return handle(res);
}