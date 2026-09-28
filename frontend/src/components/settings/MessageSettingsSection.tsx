import { useEffect, useState } from "react";

import { getSharedSettings, setSharedSettings, type SharedSettingsResponse, type SharedSettingsValues } from "../../api";

interface Props {
  idToken: string;
}

interface FieldSpec {
  name: keyof SharedSettingsValues;
  label: string;
  help: string;
}

const FIELDS: FieldSpec[] = [
  {
    name: "history_turns",
    label: "Conversation memory (messages)",
    help: "How many recent messages the assistant resends as context on every turn, for everyone — the main cost lever (APPCE-124).",
  },
  {
    name: "daily_message_warning_threshold",
    label: "Daily message warning",
    help: "Shows a heads-up once someone has sent this many messages today. Never blocks them.",
  },
];

// Owner-only, shared by every user — replaces the old self-service
// Settings fields (APPCE-124): history_turns scales the tokens resent to
// the shared agent_sa on every message, so it's one knob the owner sets,
// not something each invited user tunes for themselves.
function MessageSettingsSection({ idToken }: Props) {
  const [loaded, setLoaded] = useState<SharedSettingsResponse | null>(null);
  const [form, setForm] = useState<Record<keyof SharedSettingsValues, string> | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  function show(settings: SharedSettingsResponse) {
    setLoaded(settings);
    setForm({
      history_turns: String(settings.history_turns),
      daily_message_warning_threshold: String(settings.daily_message_warning_threshold),
    });
  }

  useEffect(() => {
    getSharedSettings(idToken)
      .then(show)
      .catch(() => setError("Couldn't load message settings."));
  }, [idToken]);

  function parse(name: keyof SharedSettingsValues): number | null {
    if (!form || !loaded) return null;
    const value = Number(form[name]);
    const { min, max } = loaded.limits[name];
    return Number.isInteger(value) && form[name].trim() !== "" && value >= min && value <= max ? value : null;
  }

  const values = {
    history_turns: parse("history_turns"),
    daily_message_warning_threshold: parse("daily_message_warning_threshold"),
  };
  const valid = values.history_turns !== null && values.daily_message_warning_threshold !== null;
  const changed =
    loaded !== null &&
    (values.history_turns !== loaded.history_turns ||
      values.daily_message_warning_threshold !== loaded.daily_message_warning_threshold);

  async function save() {
    if (!valid) return;
    setSaving(true);
    setError(null);
    try {
      show(await setSharedSettings(idToken, values as SharedSettingsValues));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't save message settings.");
    }
    setSaving(false);
  }

  return (
    <div className="settings-field">
      <div className="settings-label">Message settings</div>
      <small className="settings-hint">Applies to every user, including you.</small>

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
                disabled={saving}
              />
              <small className={invalid ? "settings-hint invalid" : "settings-hint"}>
                {invalid ? `Enter a whole number from ${min} to ${max}.` : help}
              </small>
            </label>
          );
        })
      ) : (
        !error && <small className="settings-hint">Loading…</small>
      )}

      {error && <small className="settings-hint invalid">{error}</small>}

      <button onClick={save} disabled={!valid || !changed || saving}>
        {saving ? "Saving…" : "Save"}
      </button>
    </div>
  );
}

export default MessageSettingsSection;
