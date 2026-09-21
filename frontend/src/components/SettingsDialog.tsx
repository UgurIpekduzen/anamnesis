import { useEffect, useState } from "react";

import { getSettings, resetSettings, updateSettings, type SettingsResponse, type SettingsValues } from "../api";
import "./SettingsDialog.css";

interface Props {
  idToken: string;
  onClose: () => void;
  onSaved: () => void;
}

interface FieldSpec {
  name: keyof SettingsValues;
  label: string;
  help: string;
}

const FIELDS: FieldSpec[] = [
  {
    name: "history_turns",
    label: "Conversation memory (messages)",
    help: "How many of your recent messages the assistant remembers. Lower is cheaper; higher remembers further back.",
  },
  {
    name: "daily_message_warning_threshold",
    label: "Daily message warning",
    help: "Show a heads-up once you've sent this many messages in a day. It never blocks you.",
  },
];

function SettingsDialog({ idToken, onClose, onSaved }: Props) {
  const [loaded, setLoaded] = useState<SettingsResponse | null>(null);
  // Held as strings so the field can be empty/mid-edit without a NaN.
  const [form, setForm] = useState<Record<keyof SettingsValues, string> | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  function show(settings: SettingsResponse) {
    setLoaded(settings);
    setForm({
      history_turns: String(settings.history_turns),
      daily_message_warning_threshold: String(settings.daily_message_warning_threshold),
    });
  }

  useEffect(() => {
    getSettings(idToken)
      .then(show)
      .catch(() => setError("Couldn't load your settings."));
  }, [idToken]);

  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  function parse(name: keyof SettingsValues): number | null {
    if (!form || !loaded) return null;
    const value = Number(form[name]);
    const { min, max } = loaded.limits[name];
    return Number.isInteger(value) && form[name].trim() !== "" && value >= min && value <= max ? value : null;
  }

  const values = { history_turns: parse("history_turns"), daily_message_warning_threshold: parse("daily_message_warning_threshold") };
  const valid = values.history_turns !== null && values.daily_message_warning_threshold !== null;
  const changed =
    loaded !== null &&
    (values.history_turns !== loaded.history_turns ||
      values.daily_message_warning_threshold !== loaded.daily_message_warning_threshold);

  // Already at the defaults (nothing stored to drop) — the button would
  // do nothing, so it stays disabled.
  const atDefaults =
    loaded !== null &&
    loaded.history_turns === loaded.defaults.history_turns &&
    loaded.daily_message_warning_threshold === loaded.defaults.daily_message_warning_threshold;

  async function reset() {
    setSaving(true);
    setError(null);
    try {
      show(await resetSettings(idToken));
      onSaved();
    } catch {
      setError("Couldn't reset your settings. Please try again.");
    }
    setSaving(false);
  }

  async function save() {
    if (!valid) return;
    setSaving(true);
    setError(null);
    try {
      await updateSettings(idToken, values as SettingsValues);
      onSaved();
      onClose();
    } catch {
      setError("Couldn't save your settings. Please try again.");
      setSaving(false);
    }
  }

  return (
    <div className="settings-backdrop" onMouseDown={onClose}>
      <div
        className="settings-dialog"
        role="dialog"
        aria-label="Settings"
        onMouseDown={(e) => e.stopPropagation()}
      >
        <h2>Settings</h2>

        {form && loaded ? (
          FIELDS.map(({ name, label, help }) => {
            const { min, max } = loaded.limits[name];
            const invalid = values[name] === null;
            return (
              <label key={name} className="settings-field">
                <span className="settings-label">{label}</span>
                <input
                  type="number"
                  min={min}
                  max={max}
                  step={1}
                  value={form[name]}
                  onChange={(e) => setForm({ ...form, [name]: e.target.value })}
                  aria-invalid={invalid}
                />
                <small className={invalid ? "settings-hint invalid" : "settings-hint"}>
                  {invalid ? `Enter a whole number from ${min} to ${max}.` : help}
                </small>
              </label>
            );
          })
        ) : (
          !error && <p className="settings-hint">Loading…</p>
        )}

        {error && <p className="settings-error">{error}</p>}

        <div className="settings-actions">
          <button className="settings-reset" onClick={reset} disabled={!loaded || atDefaults || saving}>
            Reset to defaults
          </button>
          <div className="settings-actions-right">
            <button onClick={onClose}>Cancel</button>
            <button className="settings-save" onClick={save} disabled={!valid || !changed || saving}>
              {saving ? "Saving…" : "Save"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

export default SettingsDialog;
