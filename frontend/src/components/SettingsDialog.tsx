import { useEffect, useState } from "react";

import {
  connectGithub,
  connectJira,
  disconnectGithub,
  disconnectJira,
  getGithubConnection,
  getJiraConnection,
  getSettings,
  resetSettings,
  updateSettings,
  type GithubConnection,
  type JiraConnection,
  type SettingsResponse,
  type SettingsValues,
} from "../api";
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

  const [github, setGithub] = useState<GithubConnection | null>(null);
  const [githubToken, setGithubToken] = useState("");
  const [githubError, setGithubError] = useState<string | null>(null);
  const [githubBusy, setGithubBusy] = useState(false);

  const [jira, setJira] = useState<JiraConnection | null>(null);
  const [jiraEmail, setJiraEmail] = useState("");
  const [jiraToken, setJiraToken] = useState("");
  const [jiraBaseUrl, setJiraBaseUrl] = useState("");
  const [jiraError, setJiraError] = useState<string | null>(null);
  const [jiraBusy, setJiraBusy] = useState(false);

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
    getGithubConnection(idToken)
      .then(setGithub)
      .catch(() => setGithubError("Couldn't load your GitHub connection."));
  }, [idToken]);

  async function connect() {
    setGithubBusy(true);
    setGithubError(null);
    try {
      setGithub(await connectGithub(idToken, githubToken.trim()));
      setGithubToken("");
    } catch (e) {
      setGithubError(e instanceof Error ? e.message : "Couldn't connect GitHub.");
    }
    setGithubBusy(false);
  }

  async function disconnect() {
    setGithubBusy(true);
    setGithubError(null);
    try {
      setGithub(await disconnectGithub(idToken));
    } catch {
      setGithubError("Couldn't disconnect GitHub. Please try again.");
    }
    setGithubBusy(false);
  }

  useEffect(() => {
    getJiraConnection(idToken)
      .then(setJira)
      .catch(() => setJiraError("Couldn't load your Jira connection."));
  }, [idToken]);

  async function connectJiraAccount() {
    setJiraBusy(true);
    setJiraError(null);
    try {
      setJira(await connectJira(idToken, jiraEmail.trim(), jiraToken.trim(), jiraBaseUrl.trim()));
      setJiraEmail("");
      setJiraToken("");
      setJiraBaseUrl("");
    } catch (e) {
      setJiraError(e instanceof Error ? e.message : "Couldn't connect Jira.");
    }
    setJiraBusy(false);
  }

  async function disconnectJiraAccount() {
    setJiraBusy(true);
    setJiraError(null);
    try {
      setJira(await disconnectJira(idToken));
    } catch {
      setJiraError("Couldn't disconnect Jira. Please try again.");
    }
    setJiraBusy(false);
  }

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

        <div className="settings-field">
          <div className="settings-label">
            GitHub
            <span className="settings-info-wrapper">
              <a
                className="settings-info"
                href="https://github.com/settings/tokens?type=beta"
                target="_blank"
                rel="noopener noreferrer"
              >
                ⓘ
              </a>
              <div className="settings-tooltip">
                <strong>Create a fine-grained token:</strong>
                <ul>
                  <li>Select only the repos you want</li>
                  <li>Grant read-only access: Contents, Metadata, Pull requests, Issues</li>
                </ul>
              </div>
            </span>
          </div>
          {github?.connected ? (
            <>
              <p className="settings-hint">Connected.</p>
              <button onClick={disconnect} disabled={githubBusy}>
                {githubBusy ? "Disconnecting…" : "Disconnect"}
              </button>
            </>
          ) : (
            <>
              <input
                type="password"
                placeholder="Fine-grained token (e.g. github_pat_11AB...)"
                value={githubToken}
                onChange={(e) => setGithubToken(e.target.value)}
                aria-invalid={!!githubError}
              />
              <small className={githubError ? "settings-hint invalid" : "settings-hint"}>
                {githubError ||
                  "Only fine-grained personal access tokens (github_pat_...) are accepted. Create one with read-only access to just the repos you want — never a classic token."}
              </small>
              <button onClick={connect} disabled={!githubToken.trim() || githubBusy}>
                {githubBusy ? "Connecting…" : "Connect"}
              </button>
            </>
          )}
        </div>

        <div className="settings-field">
          <div className="settings-label">
            Jira
            <span className="settings-info-wrapper">
              <a
                className="settings-info"
                href="https://id.atlassian.com/manage-profile/security/api-tokens"
                target="_blank"
                rel="noopener noreferrer"
              >
                ⓘ
              </a>
              <div className="settings-tooltip">
                <strong>Connect your Atlassian account:</strong>
                <ul>
                  <li>Create an API token</li>
                  <li>Use the email address you sign in with</li>
                  <li>Enter your workspace's URL</li>
                </ul>
              </div>
            </span>
          </div>
          {jira?.connected ? (
            <>
              <p className="settings-hint">Connected.</p>
              <button onClick={disconnectJiraAccount} disabled={jiraBusy}>
                {jiraBusy ? "Disconnecting…" : "Disconnect"}
              </button>
            </>
          ) : (
            <>
              <input
                placeholder="Account email (e.g. you@example.com)"
                value={jiraEmail}
                onChange={(e) => setJiraEmail(e.target.value)}
                aria-invalid={!!jiraError}
              />
              <input
                type="password"
                placeholder="API token (e.g. ATATT3xFfGF0...)"
                value={jiraToken}
                onChange={(e) => setJiraToken(e.target.value)}
                aria-invalid={!!jiraError}
              />
              <input
                placeholder="Workspace URL (e.g. https://your-workspace.atlassian.net)"
                value={jiraBaseUrl}
                onChange={(e) => setJiraBaseUrl(e.target.value)}
                aria-invalid={!!jiraError}
              />
              <small className={jiraError ? "settings-hint invalid" : "settings-hint"}>
                {jiraError ||
                  "Create a token at id.atlassian.com/manage-profile/security/api-tokens."}
              </small>
              <button
                onClick={connectJiraAccount}
                disabled={!jiraEmail.trim() || !jiraToken.trim() || !jiraBaseUrl.trim() || jiraBusy}
              >
                {jiraBusy ? "Connecting…" : "Connect"}
              </button>
            </>
          )}
        </div>

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
