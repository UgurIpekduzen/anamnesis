import { useEffect, useState } from "react";

import { connectGithub, disconnectGithub, getGithubConnection, type GithubConnection } from "../../api";
import InfoLabel from "./InfoLabel";

interface Props {
  idToken: string;
}

// The signed-in user's own GitHub connection: connect with a fine-grained
// PAT, or disconnect.
function GithubSection({ idToken }: Props) {
  const [github, setGithub] = useState<GithubConnection | null>(null);
  const [githubToken, setGithubToken] = useState("");
  const [githubError, setGithubError] = useState<string | null>(null);
  const [githubBusy, setGithubBusy] = useState(false);

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

  return (
    <div className="settings-field">
      <InfoLabel label="GitHub" href="https://github.com/settings/tokens?type=beta">
        <strong>Create a fine-grained token:</strong>
        <ul>
          <li>Select only the repos you want</li>
          <li>Grant read-only access: Contents, Metadata, Pull requests, Issues</li>
        </ul>
      </InfoLabel>
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
  );
}

export default GithubSection;
