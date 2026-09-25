import { useEffect, useState } from "react";

import { connectJira, disconnectJira, getJiraConnection, type JiraConnection } from "../../api";
import InfoLabel from "./InfoLabel";

interface Props {
  idToken: string;
}

function JiraSection({ idToken }: Props) {
  const [jira, setJira] = useState<JiraConnection | null>(null);
  const [jiraEmail, setJiraEmail] = useState("");
  const [jiraToken, setJiraToken] = useState("");
  const [jiraBaseUrl, setJiraBaseUrl] = useState("");
  const [jiraError, setJiraError] = useState<string | null>(null);
  const [jiraBusy, setJiraBusy] = useState(false);

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

  return (
    <div className="settings-field">
      <InfoLabel label="Jira" href="https://id.atlassian.com/manage-profile/security/api-tokens">
        <strong>Connect your Atlassian account:</strong>
        <ul>
          <li>Create an API token</li>
          <li>Use the email address you sign in with</li>
          <li>Enter your workspace's URL</li>
        </ul>
      </InfoLabel>
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
            {jiraError || "Create a token at id.atlassian.com/manage-profile/security/api-tokens."}
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
  );
}

export default JiraSection;
