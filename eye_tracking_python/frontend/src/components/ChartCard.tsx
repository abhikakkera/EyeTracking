export interface ChartRow {
  label: string;
  value: number;
  max: number;
  unit?: string;
}

// Dependency-free horizontal bar chart.
export default function ChartCard({
  title,
  rows,
}: {
  title: string;
  rows: ChartRow[];
}) {
  return (
    <div className="card">
      <h3 className="mb-2">{title}</h3>
      <div className="chart">
        {rows.map((r) => {
          const pct =
            r.max > 0 ? Math.max(0, Math.min(100, (r.value / r.max) * 100)) : 0;
          return (
            <div className="row" key={r.label}>
              <span className="lab">{r.label}</span>
              <span className="bar">
                <span style={{ width: `${pct}%` }} />
              </span>
              <span className="val">
                {Number.isFinite(r.value) ? Math.round(r.value) : "—"}
                {r.unit ? <span className="u"> {r.unit}</span> : null}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
