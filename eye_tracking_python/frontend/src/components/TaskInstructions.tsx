import type { TaskType } from "@/lib/types";

const TEXT: Record<TaskType, { title: string; body: string }> = {
  prosaccade: {
    title: "Look Toward the Dot",
    body: "Look at the center dot. As soon as another dot appears to the side, look at it as quickly as you can — then back to the center.",
  },
  antisaccade: {
    title: "Look Away from the Dot",
    body: "Look at the center dot. When another dot appears, quickly look to the OPPOSITE side of the screen.",
  },
  gap_overlap: {
    title: "Quick Reaction Dot Task",
    body: "Keep your eyes on the center dot. When a new dot appears to the side, look at it as soon as you can.",
  },
  smooth_pursuit: {
    title: "Follow the Moving Dot",
    body: "Keep your eyes on the moving dot and follow it as smoothly as you can. Try not to let your eyes jump ahead.",
  },
};

export default function TaskInstructions({
  taskType,
  compact = false,
}: {
  taskType: TaskType;
  compact?: boolean;
}) {
  const t = TEXT[taskType];
  if (compact) {
    return <p className="task-instr-compact">{t.body}</p>;
  }
  return (
    <div>
      <h2 style={{ marginBottom: 8 }}>{t.title}</h2>
      <p className="muted" style={{ marginBottom: 0 }}>
        {t.body}
      </p>
    </div>
  );
}
