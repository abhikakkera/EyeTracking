export default function TaskProgress({
  current,
  total,
}: {
  current: number;
  total: number;
}) {
  const pct = total > 0 ? Math.min(100, (current / total) * 100) : 0;
  return (
    <div className="task-progress">
      <div className="task-progress-label">
        Round {Math.max(0, current)} of {total}
      </div>
      <div className="progress" style={{ width: 220 }}>
        <span style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}
