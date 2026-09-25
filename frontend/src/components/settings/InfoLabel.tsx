import type { ReactNode } from "react";

interface Props {
  label: string;
  // Where the ⓘ links to, and what its tooltip says on hover.
  href: string;
  children: ReactNode;
}

// A section title with a "how do I get this" ⓘ next to it.
function InfoLabel({ label, href, children }: Props) {
  return (
    <div className="settings-label">
      {label}
      <span className="settings-info-wrapper">
        <a className="settings-info" href={href} target="_blank" rel="noopener noreferrer">
          ⓘ
        </a>
        <div className="settings-tooltip">{children}</div>
      </span>
    </div>
  );
}

export default InfoLabel;
