import type { ReactNode } from "react";

export default function FeatureCard({
  icon,
  title,
  children,
}: {
  icon: string;
  title: string;
  children: ReactNode;
}) {
  return (
    <div className="card card-hover feature">
      <div className="ic" aria-hidden>
        {icon}
      </div>
      <h3>{title}</h3>
      <p>{children}</p>
    </div>
  );
}
