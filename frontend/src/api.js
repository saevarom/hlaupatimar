const API_BASE = import.meta.env.VITE_API_BASE ?? "";

async function fetchJson(path, params) {
  const url = new URL(`${API_BASE}${path}`, window.location.origin);
  if (params) {
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== "") {
        url.searchParams.set(key, String(value));
      }
    });
  }

  const response = await fetch(url, {
    headers: { Accept: "application/json" }
  });

  if (!response.ok) {
    let message = `Beiðni mistókst (${response.status})`;
    try {
      const body = await response.json();
      if (body?.detail) {
        message = body.detail;
      }
    } catch {
      // Keep default error message if response is not JSON.
    }
    throw new Error(message);
  }

  return response.json();
}

export function searchRunners(filters) {
  return fetchJson("/api/races/runners/search", filters);
}

export function searchRaces(filters) {
  return fetchJson("/api/races/search", filters);
}

export function getRunnerDetail(runnerId) {
  return fetchJson(`/api/races/runners/${encodeURIComponent(runnerId)}`);
}

export function getRaceDetail(raceId) {
  return fetchJson(`/api/races/${encodeURIComponent(raceId)}`);
}

export function getRaceResultsTable(raceId, options = {}) {
  return fetchJson(`/api/races/${encodeURIComponent(raceId)}/results-table`, {
    limit: options.limit ?? 500,
    offset: options.offset ?? 0,
    gender: options.gender,
    status: options.status
  });
}

export function getEventRaces(raceId, options = {}) {
  return fetchJson(`/api/races/${encodeURIComponent(raceId)}/event-races`, {
    limit: options.limit ?? 20
  });
}

export function getLatestEvents(options = {}) {
  return fetchJson("/api/races/events/latest", {
    limit: options.limit ?? 12
  });
}
