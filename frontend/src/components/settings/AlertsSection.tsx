import { useEffect, useState } from "react";

import { getAlerts, setAlerts, type AlertsState } from "../../api";
import HintLabel from "./HintLabel";

interface Props {
  idToken: string;
}

// Owner-only: the alert email only ever reaches the owner's own inbox
// (terraform/monitoring.tf's notification channel), so muting it is
// purely their own call.
function AlertsSection({ idToken }: Props) {
  const [state, setState] = useState<AlertsState | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getAlerts(idToken)
      .then(setState)
      .catch(() => setError("Couldn't load alert settings."));
  }, [idToken]);

  async function toggle() {
    if (!state) return;
    setBusy(true);
    setError(null);
    try {
      setState(await setAlerts(idToken, { github_poll_alert_muted: !state.github_poll_alert_muted }));
    } catch {
      setError("Couldn't change that.");
    }
    setBusy(false);
  }

  if (!state) return null;

  return (
    <div className="settings-field">
      <HintLabel label="Alerts" variant="section">
        A broken GitHub connection makes every poll cycle fail until someone reconnects it — this only controls
        whether that also emails you (Cloud Monitoring), not whether it's logged or fixed.
      </HintLabel>
      <label className="alerts-mute-row">
        <span>Mute GitHub polling failure emails</span>
        <span className="alerts-switch">
          <input
            type="checkbox"
            checked={state.github_poll_alert_muted}
            onChange={toggle}
            disabled={busy}
            role="switch"
            aria-checked={state.github_poll_alert_muted}
          />
          <span className="alerts-switch-track" />
        </span>
      </label>
      {error && <small className="settings-hint invalid">{error}</small>}
    </div>
  );
}

export default AlertsSection;
