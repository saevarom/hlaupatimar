const API_BASE = import.meta.env.VITE_API_BASE ?? "";

async function requestJson(path, { params, method = "GET", body } = {}) {
  const normalizedBase = String(API_BASE).replace(/\/+$/, "");
  const normalizedPath =
    path.startsWith("/api/") && normalizedBase.endsWith("/api")
      ? path.replace(/^\/api/, "")
      : path;
  const url = new URL(`${normalizedBase}${normalizedPath}`, window.location.origin);
  if (params) {
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== "") {
        url.searchParams.set(key, String(value));
      }
    });
  }

  const response = await fetch(url, {
    method,
    headers: {
      Accept: "application/json",
      ...(body !== undefined ? { "Content-Type": "application/json" } : {})
    },
    ...(body !== undefined ? { body: JSON.stringify(body) } : {})
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

async function fetchJson(path, params) {
  return requestJson(path, { params });
}

export function searchRunners(filters) {
  return fetchJson("/api/races/runners/search", filters);
}

export function searchRaces(filters) {
  return fetchJson("/api/races/search", filters);
}

export function browseRaces(filters) {
  return fetchJson("/api/races/browse", filters);
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

export function getRaceStats(raceId, options = {}) {
  return fetchJson(`/api/races/${encodeURIComponent(raceId)}/stats`, {
    gender: options.gender
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

export function createRaceCorrectionSuggestion(raceId, payload) {
  return requestJson(`/api/races/${encodeURIComponent(raceId)}/correction-suggestions`, {
    method: "POST",
    body: payload
  });
}
