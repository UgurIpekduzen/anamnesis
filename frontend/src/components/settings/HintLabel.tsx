import type { ReactNode } from "react";

interface Props {
  label: string;
  children: ReactNode;
  // "section" for a top-level heading like "Users" or "Message settings"
  // (styled larger, distinct from the field labels under it); omitted for
  // an ordinary field label like "Conversation memory".
  variant?: "section";
}

// Like InfoLabel, but for an explanation rather than an external "how do I
// get this" link — a ⓘ that reveals the detail on hover instead of a
// paragraph sitting under the heading all the time.
function HintLabel({ label, children, variant }: Props) {
  return (
    <div className={variant === "section" ? "settings-section-label" : "settings-label"}>
      {label}
      <span className="settings-info-wrapper">
        <span className="settings-info">ⓘ</span>
        <div className="settings-tooltip">{children}</div>
      </span>
    </div>
  );
}

export default HintLabel;
