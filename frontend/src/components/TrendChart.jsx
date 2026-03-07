import { useMemo, useState } from "react";
import { formatDuration, formatSecondsToDuration, formatIsoDate } from "../lib/time";

const MIN_NEIGHBORS = 5;
const NEIGHBOR_FRACTION = 0.35;

function percentile(sortedValues, quantile) {
  if (!sortedValues.length) {
    return 0;
  }
  if (sortedValues.length === 1) {
    return sortedValues[0];
  }
  const clampedQuantile = Math.min(Math.max(quantile, 0), 1);
  const position = clampedQuantile * (sortedValues.length - 1);
  const lowerIndex = Math.floor(position);
  const upperIndex = Math.ceil(position);
  const weight = position - lowerIndex;
  return (
    sortedValues[lowerIndex] * (1 - weight) + sortedValues[upperIndex] * weight
  );
}

function scaleX(dateValue, width, padding, minX, maxX) {
  const xSpan = Math.max(maxX - minX, 1);
  return padding + ((dateValue - minX) / xSpan) * (width - padding * 2);
}

function scaleY(value, height, padding, minY, maxY) {
  const ySpan = Math.max(maxY - minY, 1);
  return height - padding - ((value - minY) / ySpan) * (height - padding * 2);
}

function buildLinePath(points, width, height, padding, minY, maxY, minX, maxX, valueKey) {
  return points
    .map((point, index) => {
      const x = scaleX(point.dateValue, width, padding, minX, maxX);
      const y = scaleY(point[valueKey], height, padding, minY, maxY);
      return `${index === 0 ? "M" : "L"} ${x.toFixed(2)} ${y.toFixed(2)}`;
    })
    .join(" ");
}

function buildAreaPath(
  points,
  width,
  height,
  padding,
  minY,
  maxY,
  minX,
  maxX,
  lowerKey,
  upperKey
) {
  if (points.length < 2) {
    return "";
  }

  const upperPoints = points
    .map((point, index) => {
      const x = scaleX(point.dateValue, width, padding, minX, maxX);
      const y = scaleY(point[upperKey], height, padding, minY, maxY);
      return `${index === 0 ? "M" : "L"} ${x.toFixed(2)} ${y.toFixed(2)}`;
    })
    .join(" ");

  const lowerPoints = [...points]
    .reverse()
    .map((point) => {
      const x = scaleX(point.dateValue, width, padding, minX, maxX);
      const y = scaleY(point[lowerKey], height, padding, minY, maxY);
      return `L ${x.toFixed(2)} ${y.toFixed(2)}`;
    })
    .join(" ");

  return `${upperPoints} ${lowerPoints} Z`;
}

function yTicks(minY, maxY, count = 4) {
  const ticks = [];
  const span = Math.max(maxY - minY, 1);
  const step = span / count;

  for (let index = 0; index <= count; index += 1) {
    ticks.push(minY + step * index);
  }
  return ticks;
}

function buildTrendStatistics(sortedPoints) {
  if (!sortedPoints.length) {
    return [];
  }

  const neighborCount = Math.min(
    sortedPoints.length,
    Math.max(MIN_NEIGHBORS, Math.ceil(sortedPoints.length * NEIGHBOR_FRACTION))
  );

  return sortedPoints.map((point) => {
    const neighborhood = [...sortedPoints]
      .map((candidate) => ({
        candidate,
        distance: Math.abs(candidate.dateValue - point.dateValue)
      }))
      .sort((left, right) => left.distance - right.distance)
      .slice(0, neighborCount);

    const maxDistance = neighborhood[neighborhood.length - 1]?.distance || 1;
    const neighborhoodValues = neighborhood
      .map(({ candidate }) => candidate.finishSeconds)
      .sort((left, right) => left - right);

    let weightedTotal = 0;
    let weightTotal = 0;

    neighborhood.forEach(({ candidate, distance }) => {
      const ratio = maxDistance === 0 ? 0 : Math.min(distance / maxDistance, 1);
      const weight = (1 - ratio ** 3) ** 3; // tricube kernel for local smoothing
      weightedTotal += candidate.finishSeconds * weight;
      weightTotal += weight;
    });

    const trendSeconds =
      weightTotal > 0 ? weightedTotal / weightTotal : point.finishSeconds;

    return {
      ...point,
      trendSeconds,
      p10: percentile(neighborhoodValues, 0.1),
      p25: percentile(neighborhoodValues, 0.25),
      p75: percentile(neighborhoodValues, 0.75),
      p90: percentile(neighborhoodValues, 0.9),
      sampleSize: neighborhood.length
    };
  });
}

export default function TrendChart({ points, title }) {
  const [tooltip, setTooltip] = useState(null);

  if (!points?.length) {
    return <p className="quiet">Engin úrslit tiltæk til að teikna graf fyrir þennan flokk.</p>;
  }

  const trendPoints = useMemo(() => {
    const sortedPoints = [...points].sort((left, right) => left.dateValue - right.dateValue);
    return buildTrendStatistics(sortedPoints);
  }, [points]);

  const width = 860;
  const height = 320;
  const padding = 44;
  const minY = Math.min(...trendPoints.map((point) => Math.min(point.finishSeconds, point.p10)));
  const maxY = Math.max(...trendPoints.map((point) => Math.max(point.finishSeconds, point.p90)));
  const minX = Math.min(...trendPoints.map((point) => point.dateValue));
  const maxX = Math.max(...trendPoints.map((point) => point.dateValue));

  const tickValues = useMemo(() => yTicks(minY, maxY), [minY, maxY]);
  const rawPath = useMemo(
    () =>
      buildLinePath(
        trendPoints,
        width,
        height,
        padding,
        minY,
        maxY,
        minX,
        maxX,
        "finishSeconds"
      ),
    [trendPoints, width, height, padding, minY, maxY, minX, maxX]
  );
  const trendPath = useMemo(
    () =>
      buildLinePath(
        trendPoints,
        width,
        height,
        padding,
        minY,
        maxY,
        minX,
        maxX,
        "trendSeconds"
      ),
    [trendPoints, width, height, padding, minY, maxY, minX, maxX]
  );
  const outerBandPath = useMemo(
    () =>
      buildAreaPath(
        trendPoints,
        width,
        height,
        padding,
        minY,
        maxY,
        minX,
        maxX,
        "p10",
        "p90"
      ),
    [trendPoints, width, height, padding, minY, maxY, minX, maxX]
  );
  const innerBandPath = useMemo(
    () =>
      buildAreaPath(
        trendPoints,
        width,
        height,
        padding,
        minY,
        maxY,
        minX,
        maxX,
        "p25",
        "p75"
      ),
    [trendPoints, width, height, padding, minY, maxY, minX, maxX]
  );

  function showTooltip(event, point) {
    const svgRect = event.currentTarget.ownerSVGElement?.getBoundingClientRect();
    if (!svgRect) {
      return;
    }
    setTooltip({
      x: event.clientX - svgRect.left,
      y: event.clientY - svgRect.top,
      point
    });
  }

  function hideTooltip() {
    setTooltip(null);
  }

  return (
    <figure className="trend-chart enter-up">
      <figcaption>{title}</figcaption>
      <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label={title} onMouseLeave={hideTooltip}>
        <defs>
          <linearGradient id="runner-trend-line" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stopColor="#4ea6ff" />
            <stop offset="100%" stopColor="#8ac8ff" />
          </linearGradient>
        </defs>

        {tickValues.map((tick) => {
          const y = scaleY(tick, height, padding, minY, maxY);
          return (
            <g key={tick}>
              <line x1={padding} y1={y} x2={width - padding} y2={y} />
              <text x={10} y={y + 5}>
                {formatSecondsToDuration(tick)}
              </text>
            </g>
          );
        })}

        {outerBandPath ? (
          <path className="trend-band trend-band-outer" d={outerBandPath} />
        ) : null}
        {innerBandPath ? (
          <path className="trend-band trend-band-inner" d={innerBandPath} />
        ) : null}
        <path className="trend-raw-line" d={rawPath} />
        <path className="trend-line" d={trendPath} />

        {trendPoints.map((point) => {
          const x = scaleX(point.dateValue, width, padding, minX, maxX);
          const y = scaleY(point.finishSeconds, height, padding, minY, maxY);
          return (
            <g key={`${point.dateValue}-${point.raceName}`}>
              <circle
                cx={x}
                cy={y}
                r="4"
                onMouseMove={(event) => showTooltip(event, point)}
                onMouseEnter={(event) => showTooltip(event, point)}
              />
              <title>
                {`${formatIsoDate(point.date)} | ${point.raceName} | ${formatDuration(
                  point.finishTime
                )} | Miðlína: ${formatSecondsToDuration(point.trendSeconds)}`}
              </title>
            </g>
          );
        })}
      </svg>
      {tooltip ? (
        <div
          className="chart-tooltip"
          style={{
            left: tooltip.x + 12,
            top: tooltip.y - 12
          }}
        >
          <strong>{tooltip.point.raceName}</strong>
          <span>{formatIsoDate(tooltip.point.date)}</span>
          <span>Tími: {formatDuration(tooltip.point.finishTime)}</span>
          <span>Miðlína: {formatSecondsToDuration(tooltip.point.trendSeconds)}</span>
          <span>
            Bil (25-75%): {formatSecondsToDuration(tooltip.point.p25)}-{formatSecondsToDuration(tooltip.point.p75)}
          </span>
          <span>
            Bil (10-90%): {formatSecondsToDuration(tooltip.point.p10)}-{formatSecondsToDuration(tooltip.point.p90)}
          </span>
          <span>Úrtak: {tooltip.point.sampleSize} hlaup</span>
          <span>
            Vegalengd:{" "}
            {tooltip.point.distanceKm || tooltip.point.distanceKm === 0
              ? `${tooltip.point.distanceKm} km`
              : "-"}
          </span>
        </div>
      ) : null}
    </figure>
  );
}
