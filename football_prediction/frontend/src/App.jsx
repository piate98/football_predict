import React, { useEffect, useMemo, useState } from "react";
import { getLeagues, getFixtures } from "./api";

/* ---------------- helpers ---------------- */

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
    minute: "2-digit",
  });
}

/* ---------------- UI components ---------------- */

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

      <div className="cardMeters">
        <Meter label="Over 2.5" v={f.p_over25} />
        <Meter label="BTTS" v={f.p_btts} />
      </div>

      <ScorePills scores={f.top_scores} />
    </div>
  );
}

/* ---------------- APP ---------------- */

export default function App() {
  const [leagues, setLeagues] = useState([]);
  const [competition, setCompetition] = useState("BL1");

  const [dateFrom, setDateFrom] = useState(isoDate(new Date()));
  const [dateTo, setDateTo] = useState(addDaysIso(isoDate(new Date()), 14));

  const [draftFrom, setDraftFrom] = useState(dateFrom);
  const [draftTo, setDraftTo] = useState(dateTo);

  const [fixtures, setFixtures] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  /* -------- load leagues -------- */

  useEffect(() => {
    (async () => {
      try {
        const data = await getLeagues();
        setLeagues(data.leagues || []);
      } catch (e) {
        setError(e.message);
      }
    })();
  }, []);

  /* -------- load fixtures -------- */

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const data = await getFixtures({
        competition,
        dateFrom,
        dateTo,
      });
      setFixtures(data);
    } catch (e) {
      setError(e.message);
      setFixtures([]);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, [competition]);

  function applyDates() {
    setDateFrom(draftFrom);
    setDateTo(draftTo);
    load();
  }

  /* -------- render -------- */

  return (
    <div className="page">
      <div className="header">
        <h1>Football Predictions</h1>
      </div>

      <div className="controls">
        <select value={competition} onChange={(e) => setCompetition(e.target.value)}>
          {leagues.map((l) => (
            <option key={l.code} value={l.code}>
              {l.code} — {l.name}
            </option>
          ))}
        </select>

        <input type="date" value={draftFrom} onChange={(e) => setDraftFrom(e.target.value)} />
        <input type="date" value={draftTo} onChange={(e) => setDraftTo(e.target.value)} />

        <button onClick={applyDates} disabled={loading}>
          Apply
        </button>
      </div>

      {error && <div className="notice">{error}</div>}

      <div className="cardsOnly">
        {fixtures.map((f) => (
          <FixtureCardSimple key={f.match_id} f={f} />
        ))}
      </div>

      {!loading && fixtures.length === 0 && (
        <div className="emptyCard">No fixtures found</div>
      )}
    </div>
  );
}