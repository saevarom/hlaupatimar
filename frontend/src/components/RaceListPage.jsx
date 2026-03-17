import { useEffect, useRef, useState } from "react";
import { browseRaces } from "../api";
import { formatDuration, formatIsoDate } from "../lib/time";

const PAGE_SIZE = 50;
const ORDER_OPTIONS = [
  { value: "date_desc", label: "Nýjust fyrst" },
  { value: "date_asc", label: "Elst fyrst" },
  { value: "winning_fastest", label: "Stysti sigurtími fyrst" },
  { value: "winning_slowest", label: "Lengsti sigurtími fyrst" },
  { value: "speed_fastest", label: "Lægsti hraðastuðull fyrst" },
  { value: "speed_slowest", label: "Hæsti hraðastuðull fyrst" }
];
const RACE_TYPE_OPTIONS = [
  { value: "", label: "Allir flokkar" },
  { value: "5k", label: "5 km" },
  { value: "10k", label: "10 km" },
  { value: "half_marathon", label: "Hálft maraþon" },
  { value: "marathon", label: "Maraþon" },
  { value: "trail", label: "Utanvegahlaup" },
  { value: "ultra", label: "Ultra" },
  { value: "other", label: "Annað" }
];
const SURFACE_OPTIONS = [
  { value: "", label: "Öll yfirborð" },
  { value: "road", label: "Gata" },
  { value: "trail", label: "Utanvega" },
  { value: "mixed", label: "Blandað" },
  { value: "unknown", label: "Óþekkt" }
];

function normalizeBrowseFilters(filters = {}) {
  const q = typeof filters.q === "string" ? filters.q : "";
  const yearRaw = filters.year;
  const year = yearRaw === null || yearRaw === undefined ? "" : String(yearRaw).trim();
  const raceType = typeof filters.raceType === "string" ? filters.raceType : "";
  const surfaceType = typeof filters.surfaceType === "string" ? filters.surfaceType : "";
  const requireSpeedIndex = Boolean(filters.requireSpeedIndex);
  const orderOptions = new Set(ORDER_OPTIONS.map((option) => option.value));
  const order =
    typeof filters.order === "string" && orderOptions.has(filters.order)
      ? filters.order
      : "date_desc";
  const pageRaw = Number(filters.page);
  const page = Number.isFinite(pageRaw) && pageRaw > 0 ? Math.floor(pageRaw) : 1;
  return { q, year, raceType, surfaceType, requireSpeedIndex, order, page };
}

export default function RaceListPage({ initialBrowse, onPersistBrowse, onOpenRace }) {
  const [query, setQuery] = useState(initialBrowse?.q || "");
  const [year, setYear] = useState(initialBrowse?.year || "");
  const [raceType, setRaceType] = useState(initialBrowse?.raceType || "");
  const [surfaceType, setSurfaceType] = useState(initialBrowse?.surfaceType || "");
  const [requireSpeedIndex, setRequireSpeedIndex] = useState(Boolean(initialBrowse?.requireSpeedIndex));
  const [order, setOrder] = useState(initialBrowse?.order || "date_desc");
  const [pageData, setPageData] = useState({
    items: [],
    total: 0,
    limit: PAGE_SIZE,
    offset: 0,
    has_next: false,
    has_previous: false
  });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const requestRef = useRef(0);

  useEffect(() => {
    const normalized = normalizeBrowseFilters(initialBrowse);
    setQuery(normalized.q);
    setYear(normalized.year);
    setRaceType(normalized.raceType);
    setSurfaceType(normalized.surfaceType);
    setRequireSpeedIndex(normalized.requireSpeedIndex);
    setOrder(normalized.order);

    const requestId = requestRef.current + 1;
    requestRef.current = requestId;

    async function load() {
      setLoading(true);
      setError("");
      try {
        const response = await browseRaces({
          q: normalized.q.trim() || undefined,
          year: normalized.year ? Number(normalized.year) : undefined,
          race_type: normalized.raceType || undefined,
          surface_type: normalized.surfaceType || undefined,
          require_speed_index: normalized.requireSpeedIndex || undefined,
          order_by: normalized.order,
          limit: PAGE_SIZE,
          offset: (normalized.page - 1) * PAGE_SIZE
        });
        if (requestRef.current === requestId) {
          setPageData(response);
        }
      } catch (loadError) {
        if (requestRef.current === requestId) {
          setError(loadError.message || "Ekki tókst að sækja hlaup.");
          setPageData({
            items: [],
            total: 0,
            limit: PAGE_SIZE,
            offset: 0,
            has_next: false,
            has_previous: false
          });
        }
      } finally {
        if (requestRef.current === requestId) {
          setLoading(false);
        }
      }
    }

    void load();
  }, [initialBrowse]);

  const currentPage = Math.max(1, Math.floor((pageData.offset || 0) / PAGE_SIZE) + 1);
  const totalPages = Math.max(1, Math.ceil((pageData.total || 0) / PAGE_SIZE));

  function updateBrowse(nextFilters, historyMode = "push") {
    onPersistBrowse?.(normalizeBrowseFilters(nextFilters), historyMode);
  }

  function onSubmit(event) {
    event.preventDefault();
    updateBrowse({ q: query, year, raceType, surfaceType, requireSpeedIndex, order, page: 1 }, "push");
  }

  function clearFilters() {
    setQuery("");
    setYear("");
    setRaceType("");
    setSurfaceType("");
    setRequireSpeedIndex(false);
    setOrder("date_desc");
    updateBrowse(
      {
        q: "",
        year: "",
        raceType: "",
        surfaceType: "",
        requireSpeedIndex: false,
        order: "date_desc",
        page: 1
      },
      "push"
    );
  }

  function goToPage(nextPage) {
    updateBrowse({ q: query, year, raceType, surfaceType, requireSpeedIndex, order, page: nextPage }, "push");
  }

  return (
    <section className="panel enter-up">
      <div className="panel-header">
        <p className="kicker">Öll hlaup</p>
        <h2>Skoðaðu öll hlaup í tímaröð</h2>
      </div>

      <form className="race-browse-form" onSubmit={onSubmit}>
        <div className="race-browse-form-primary">
          <label>
            Nafn eða staður
            <input
              type="search"
              placeholder="Prófaðu: Reykjavíkurmaraþon, Mosfellsbær..."
              value={query}
              onChange={(event) => setQuery(event.target.value)}
            />
          </label>
          <label>
            Ár
            <input
              type="number"
              min="1900"
              max="2100"
              placeholder="2025"
              value={year}
              onChange={(event) => setYear(event.target.value)}
            />
          </label>
          <button type="submit" disabled={loading}>
            {loading ? "Sæki..." : "Sía"}
          </button>
          <button className="ghost" type="button" onClick={clearFilters}>
            Hreinsa
          </button>
        </div>
        <div className="race-browse-form-secondary">
          <label>
            Flokkur
            <select
              value={raceType}
              onChange={(event) => {
                const nextRaceType = event.target.value;
                setRaceType(nextRaceType);
                updateBrowse(
                  {
                    q: query,
                    year,
                    raceType: nextRaceType,
                    surfaceType,
                    requireSpeedIndex,
                    order,
                    page: 1
                  },
                  "push"
                );
              }}
            >
              {RACE_TYPE_OPTIONS.map((option) => (
                <option key={option.value || "all"} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
          <label>
            Yfirborð
            <select
              value={surfaceType}
              onChange={(event) => {
                const nextSurfaceType = event.target.value;
                setSurfaceType(nextSurfaceType);
                updateBrowse(
                  {
                    q: query,
                    year,
                    raceType,
                    surfaceType: nextSurfaceType,
                    requireSpeedIndex,
                    order,
                    page: 1
                  },
                  "push"
                );
              }}
            >
              {SURFACE_OPTIONS.map((option) => (
                <option key={option.value || "all"} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
          <label>
            Röðun
            <select
              value={order}
              onChange={(event) => {
                const nextOrder = event.target.value;
                setOrder(nextOrder);
                updateBrowse(
                  {
                    q: query,
                    year,
                    raceType,
                    surfaceType,
                    requireSpeedIndex,
                    order: nextOrder,
                    page: 1
                  },
                  "push"
                );
              }}
            >
              {ORDER_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
          <label className="checkbox-label">
            <input
              type="checkbox"
              checked={requireSpeedIndex}
              onChange={(event) => {
                const nextRequireSpeed = event.target.checked;
                setRequireSpeedIndex(nextRequireSpeed);
                updateBrowse(
                  {
                    q: query,
                    year,
                    raceType,
                    surfaceType,
                    requireSpeedIndex: nextRequireSpeed,
                    order,
                    page: 1
                  },
                  "push"
                );
              }}
            />
            <span>Sleppa hlaupum án hraðastuðuls</span>
          </label>
        </div>
      </form>

      <div className="browse-summary">
        <span>{pageData.total} hlaup fundust</span>
        <span>
          Síða {currentPage} af {totalPages}
        </span>
      </div>
      <p className="quiet">
        Hraðastuðull er nú reiknaður fyrir 5 km, 10 km, hálfmaraþon og maraþon á vegi/blönduðu yfirborði.
        `100` er dæmigert sambærilegt hlaup. Lægra gildi er hraðara, hærra gildi hægara.
      </p>

      {error ? <p className="error">{error}</p> : null}

      <div className="results-table-wrap enter-up latest-races-wrap">
        <table className="results-table">
          <thead>
            <tr>
              <th>Dagsetning</th>
              <th className="time-col">Sigurtími</th>
              <th className="time-col">Hraðastuðull</th>
              <th>Hlaup</th>
              <th>Vegalengd</th>
              <th>Staður</th>
            </tr>
          </thead>
          <tbody>
            {pageData.items.map((race) => (
              <tr key={race.id}>
                <td>{formatIsoDate(race.date)}</td>
                <td className="time-col">{formatDuration(race.winning_time)}</td>
                <td className="time-col">
                  {race.speed_index !== null && race.speed_index !== undefined ? (
                    <span
                      className={`speed-index-pill ${
                        race.speed_index < 100
                          ? "speed-index-pill-fast"
                          : race.speed_index > 100
                            ? "speed-index-pill-slow"
                            : "speed-index-pill-neutral"
                      }`}
                      title={
                        race.speed_delta_percentage !== null && race.speed_delta_percentage !== undefined
                          ? `${Math.abs(Number(race.speed_delta_percentage)).toFixed(1)}% ${
                              Number(race.speed_delta_percentage) < 0 ? "hraðara" : "hægara"
                            } en dæmigert sambærilegt hlaup`
                          : "Ekki tiltækt"
                      }
                    >
                      {Number(race.speed_index).toFixed(1)}
                    </span>
                  ) : (
                    "-"
                  )}
                </td>
                <td>
                  <button className="link-button" onClick={() => onOpenRace(race.id)} type="button">
                    {race.name}
                  </button>
                </td>
                <td>{race.distance_km ? `${race.distance_km} km` : "-"}</td>
                <td>{race.location || "-"}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {!loading && !pageData.items.length ? (
          <p className="quiet">Engin hlaup fundust fyrir þessa síu.</p>
        ) : null}
      </div>

      <div className="pagination-row">
        <button
          className="ghost"
          type="button"
          disabled={loading || !pageData.has_previous}
          onClick={() => goToPage(Math.max(1, currentPage - 1))}
        >
          Fyrri síða
        </button>
        <span className="quiet">
          {pageData.total > 0
            ? `${pageData.offset + 1}-${Math.min(pageData.offset + pageData.limit, pageData.total)} af ${pageData.total}`
            : "0 niðurstöður"}
        </span>
        <button
          className="ghost"
          type="button"
          disabled={loading || !pageData.has_next}
          onClick={() => goToPage(currentPage + 1)}
        >
          Næsta síða
        </button>
      </div>
    </section>
  );
}
