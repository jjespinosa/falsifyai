interface CurveChartProps {
  x: number[];
  h0: number[];
  h1: number[];
  delta: number[];
  h0Label?: string;
  h1Label?: string;
  caption?: string;
}

export function CurveChart({
  x,
  h0,
  h1,
  delta,
  h0Label = "H₀",
  h1Label = "H₁",
  caption = "Model prediction — not experimental data.",
}: CurveChartProps) {
  const width = 640;
  const height = 280;
  const pad = 32;
  const ys = [...h0, ...h1, ...delta];
  const minX = Math.min(...x);
  const maxX = Math.max(...x);
  const minY = Math.min(...ys);
  const maxY = Math.max(...ys);
  const sx = (value: number) => pad + ((value - minX) / (maxX - minX || 1)) * (width - pad * 2);
  const sy = (value: number) => height - pad - ((value - minY) / (maxY - minY || 1)) * (height - pad * 2);
  const path = (values: number[]) =>
    values.map((value, index) => `${index === 0 ? "M" : "L"} ${sx(x[index]).toFixed(1)} ${sy(value).toFixed(1)}`).join(" ");

  return (
    <figure className="chart">
      <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Model prediction curves for H0, H1, and delta">
        <path d={path(h0)} className="curve h0" />
        <path d={path(h1)} className="curve h1" />
        <path d={path(delta)} className="curve delta" />
      </svg>
      <figcaption>
        <span className="swatch h0">{h0Label}</span>
        <span className="swatch h1">{h1Label}</span>
        <span className="swatch delta">delta</span>
        <span>{caption}</span>
      </figcaption>
    </figure>
  );
}
