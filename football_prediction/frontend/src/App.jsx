import React, { useEffect, useMemo, useState } from "react";

const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000";

function isoDate(d) {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

function addDaysIso(iso, days) {
  const d = new Date(`${iso}T00:00:00`);
  d.setDate(d.getDate() + days);
  return isoDate(d);
}

function pct(x) {
  const v = Number.isFinite(x) ? x : 0;
  return `${Math.round(v * 100)}%`;
}

function clamp01(x) {
  return Math.max(0, Math.min(1, Number.isFinite(x) ? x : 0));
}

function formatKickoff(utcIso) {
  const dt = new Date(utcIso);
  return dt.toLocaleString(undefined, {
    weekday: "short",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit"
  });
}

function Meter({ label, v }) {
  const w = Math.round(clamp01(v) * 100);
  return (
    <div className="probRow">
      {label ? <span className="key">{label}</span> : <span className="key" />}
      <div className="meter">
        <div className="meterFill" style={{ width: `${w}%` }} />
      </div>
      <span className="pct">{w}%</span>
    </div>
  );
}

function ScorePills({ scores }) {
  const top3 = (scores || []).slice(0, 3);
  return (
    <div className="pills">
      {top3.map((s, i) => (
        <span className="pill" key={i}>
          {s.home_goals}-{s.away_goals} · {pct(s.p)}
        </span>
      ))}
    </div>
  );
}

function FixtureCardSimple({ f }) {
  return (
    <div className="matchCard">
      <div className="cardRow">
        <div className="mono small">{formatKickoff(f.utc_date)}</div>
        <div className="chips">
          <span className="chip">{f.competition}</span>
          <span className="chip">{f.status}</span>
        </div>
      </div>

      <div className="cardTeams">
        <span className="team">{f.home_team}</span>
        <span className="vs">vs</span>
        <span className="team">{f.away_team}</span>
      </div>

      <div className="cardLine">
        <span className="label">Elo 1X2</span>
        <span className="mono">
          {pct(f.elo_p_home)} / {pct(f.elo_p_draw)} / {pct(f.elo_p_away)}
        </span>
      </div>

      <div className="cardMeters">
        <div className="cardMeter">
          <div className="label">Over 2.5</div>
          <Meter label="" v={f.p_over25} />
        </div>
        <div className="cardMeter">
          <div className="label">BTTS</div>
          <Meter label="" v={f.p_btts} />
        </div>
      </div>

      <div className="cardBottom">
        <ScorePills scores={f.top_scores} />
        <div className="small">Captured: {pct(f.mass_captured)}</div>
      </div>
    </div>
  );
}

export default function App() {
  const [leagues, setLeagues] = useState([]);
  const [competition, setCompetition] = useState("BL1");

  // applied (used for fetch)
  const [dateFrom, setDateFrom] = useState(isoDate(new Date()));
  const [dateTo, setDateTo] = useState(() => addDaysIso(isoDate(new Date()), 14));

  // draft (editable)
  const [draftFrom, setDraftFrom] = useState(isoDate(new Date()));
  const [draftTo, setDraftTo] = useState(() => addDaysIso(isoDate(new Date()), 14));

  const [fixtures, setFixtures] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const [sortKey, setSortKey] = useState("confidence");
  const [sortDir, setSortDir] = useState("desc");

  // leagues
  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const res = await fetch(`${API_BASE}/api/leagues`);
        if (!res.ok) throw new Error(`Leagues failed: ${res.status}`);
        const data = await res.json();
        const list = (data.leagues || []).filter((x) => x && x.code);
        if (!alive) return;
        setLeagues(list);

        const hasBL1 = list.some((l) => l.code === "BL1");
        if (!hasBL1 && list.length) setCompetition(list[0].code);
      } catch (e) {
        if (alive) setError(String(e.message || e));
      }
    })();
    return () => {
      alive = false;
    };
  }, []);

  async function loadFixtures(params) {
    const comp = params?.competition ?? competition;
    const df = params?.dateFrom ?? dateFrom;
    const dt = params?.dateTo ?? dateTo;

    setLoading(true);
    setError(null);
    try {
      const qs = new URLSearchParams({
        competition: comp,
        date_from: df,
        date_to: dt
      });

      const res = await fetch(`${API_BASE}/api/fixtures?${qs.toString()}`);
      const text = await res.text();
      if (!res.ok) {
        let msg = `Fixtures failed: ${res.status}`;
        try {
          const j = JSON.parse(text);
          msg = j.detail || msg;
        } catch {}
        throw new Error(msg);
      }
      const arr = JSON.parse(text);
      setFixtures(Array.isArray(arr) ? arr : []);
    } catch (e) {
      setError(String(e.message || e));
      setFixtures([]);
    } finally {
      setLoading(false);
    }
  }

  // initial load
  useEffect(() => {
    loadFixtures({ competition, dateFrom, dateTo });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // if league changes, fetch again (using applied dates)
  useEffect(() => {
    loadFixtures({ competition, dateFrom, dateTo });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [competition]);

  function applyDates() {
    let from = draftFrom;
    let to = draftTo;

    if (!from) from = isoDate(new Date());
    if (!to) to = addDaysIso(from, 14);

    if (to < from) {
      to = addDaysIso(from, 14);
      setDraftTo(to);
    }

    setDateFrom(from);
    setDateTo(to);
    loadFixtures({ competition, dateFrom: from, dateTo: to });
  }

  const sorted = useMemo(() => {
    const copy = [...fixtures];
    const dir = sortDir === "desc" ? -1 : 1;

    const map = {
      confidence: (f) => Math.max(f.elo_p_home || 0, f.elo_p_draw || 0, f.elo_p_away || 0),
      kickoff: (f) => f.utc_date || "",
      p_over25: (f) => f.p_over25 || 0,
      p_btts: (f) => f.p_btts || 0
    };

    copy.sort((a, b) => {
      if (sortKey === "kickoff") return (a.utc_date < b.utc_date ? -1 : 1) * dir;
      const va = map[sortKey] ? map[sortKey](a) : 0;
      const vb = map[sortKey] ? map[sortKey](b) : 0;
      return (va - vb) * dir;
    });

    return copy;
  }, [fixtures, sortKey, sortDir]);

  const kpis = useMemo(() => {
    const n = sorted.length;
    if (!n) return { n: 0, avgOver: 0, avgBtts: 0, maxConf: 0 };

    const avgOver = sorted.reduce((s, f) => s + (f.p_over25 || 0), 0) / n;
    const avgBtts = sorted.reduce((s, f) => s + (f.p_btts || 0), 0) / n;
    const maxConf = Math.max(
      ...sorted.map((f) => Math.max(f.elo_p_home || 0, f.elo_p_draw || 0, f.elo_p_away || 0))
    );

    return { n, avgOver, avgBtts, maxConf };
  }, [sorted]);

  return (
    <div className="page">
      <div className="header">
        <div className="hgroup">
          <h1>Football Predictions</h1>
          <p>
            <br />
            Markets: <b>Over 2.5</b>, <b>BTTS</b>. Baseline: <b>Elo 1X2</b>.
          </p>
        </div>
        <div className="tag">
          <span>Just</span>
          <span className="mono">/Grit</span>
        </div>
      </div>

      <div className="controls">
        <div className="field">
          <label>League</label>
          <select value={competition} onChange={(e) => setCompetition(e.target.value)}>
            {leagues.length ? (
              leagues.map((l) => (
                <option key={l.code} value={l.code}>
                  {l.code} — {l.name || ""}
                </option>
              ))
            ) : (
              <option value="BL1">BL1</option>
            )}
          </select>
        </div>

        <div className="field">
          <label>From</label>
          <input type="date" value={draftFrom} onChange={(e) => setDraftFrom(e.target.value)} />
        </div>

        <div className="field">
          <label>To</label>
          <input
            type="date"
            value={draftTo}
            min={draftFrom || undefined}
            onChange={(e) => setDraftTo(e.target.value)}
          />
        </div>

        <div className="field">
          <label>Sort</label>
          <div className="sortRow">
            <select value={sortKey} onChange={(e) => setSortKey(e.target.value)}>
              <option value="confidence">Confidence (Elo)</option>
              <option value="kickoff">Kickoff</option>
              <option value="p_over25">Over 2.5</option>
              <option value="p_btts">BTTS</option>
            </select>

            <button className="btn" onClick={() => setSortDir((d) => (d === "desc" ? "asc" : "desc"))}>
              {sortDir === "desc" ? "↓" : "↑"}
            </button>

            <button className="btn" onClick={applyDates} disabled={loading}>
              Apply
            </button>

            <button className="btn primary" onClick={() => loadFixtures({ competition, dateFrom, dateTo })} disabled={loading}>
              {loading ? "Loading…" : "Refresh"}
            </button>
          </div>

          <div className="small" style={{ marginTop: 6 }}>
            Showing: <span className="mono">{dateFrom}</span> → <span className="mono">{dateTo}</span>
          </div>
        </div>
      </div>

      {error && (
        <div className="notice">
          <b>Error:</b> {error}
        </div>
      )}

      <div className="kpis">
        <div className="kpi">
          <div className="label">Fixtures</div>
          <div className="value">{kpis.n}</div>
        </div>
        <div className="kpi">
          <div className="label">Avg Over 2.5</div>
          <div className="value">{pct(kpis.avgOver)}</div>
        </div>
        <div className="kpi">
          <div className="label">Avg BTTS</div>
          <div className="value">{pct(kpis.avgBtts)}</div>
        </div>
        <div className="kpi">
          <div className="label">Top Elo Conf</div>
          <div className="value">{pct(kpis.maxConf)}</div>
        </div>
      </div>

      <div className="cardsOnly">
        {sorted.map((f) => (
          <FixtureCardSimple key={f.match_id} f={f} />
        ))}
        {!loading && sorted.length === 0 && <div className="emptyCard">No fixtures found for this range.</div>}
      </div>

      <div className="tableCard tableOnly">
        <div className="tableWrap">
          <table>
            <thead>
              <tr>
                <th>Kickoff</th>
                <th>Match</th>
                <th>Elo 1X2</th>
                <th>Over 2.5</th>
                <th>BTTS</th>
                <th>Top scores</th>
              </tr>
            </thead>
            <tbody>
              {sorted.map((f) => {
                const conf = Math.max(f.elo_p_home || 0, f.elo_p_draw || 0, f.elo_p_away || 0);
                return (
                  <tr key={f.match_id}>
                    <td className="mono">{formatKickoff(f.utc_date)}</td>
                    <td>
                      <div className="matchCell">
                        <div className="teams">
                          {f.home_team} <span className="small">vs</span> {f.away_team}
                        </div>
                        <div className="metaRow">
                          <span className="chip">{f.competition}</span>
                          <span className="chip">{f.status}</span>
                          <span className="chip">Elo Conf: {pct(conf)}</span>
                        </div>
                      </div>
                    </td>
                    <td className="mono">
                      {pct(f.elo_p_home)} / {pct(f.elo_p_draw)} / {pct(f.elo_p_away)}
                    </td>
                    <td><Meter label="" v={f.p_over25} /></td>
                    <td><Meter label="" v={f.p_btts} /></td>
                    <td>
                      <ScorePills scores={f.top_scores} />
                      <div className="small">Captured: {pct(f.mass_captured)}</div>
                    </td>
                  </tr>
                );
              })}

              {!loading && sorted.length === 0 && (
                <tr>
                  <td colSpan={6} style={{ padding: 18, color: "var(--muted)" }}>
                    No fixtures found for this range.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      <div className="footer">Tip: On mobile you’ll see cards; on desktop you’ll see the full table.</div>
    </div>
  );
}