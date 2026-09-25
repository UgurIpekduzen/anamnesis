import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";

import { chatSocketUrl, deleteFact, getChatHistory, setTenantLink, updateFact } from "../api";
import type { ChatEvent } from "../trace";
import { describeArgs } from "../traceView";
import ConfirmDialog from "./ConfirmDialog";
import "./Chat.css";

// Shown instead of the raw tool name (APPCE-91) — every entry here is a
// tool wrapped with require_confirmation=True in agent/agent.py.
const CONFIRM_TOOL_LABELS: Record<string, string> = {
  publish_fact: "Save this fact",
};

// Mirrors the backend's MAX_MESSAGE_CHARS default (api/main.py) purely as
// a convenience — the server enforces it either way.
const MAX_MESSAGE_CHARS = 4000;

// The model's replies are markdown. react-markdown renders raw HTML as
// text and drops unsafe URL schemes, so model output can't inject markup;
// links additionally open in a new tab so they don't replace the app.
const markdownComponents = {
  a: ({ node: _node, ...props }: React.ComponentProps<"a"> & { node?: unknown }) => (
    <a {...props} target="_blank" rel="noopener noreferrer" />
  ),
};

interface Props {
  idToken: string;
  tenantId: string | null;
  // One channel for everything the parent cares about (usage counter,
  // facts refresh, Trace tab) instead of a callback per concern.
  onEvent?: (event: ChatEvent) => void;
  // The server closes with 1008 when the token it was handed doesn't check
  // out (expired, not on the allowlist, ...) or the project doesn't belong
  // to this user, and a fresh connect keeps failing the same way, so this
  // is the app's cue to stop reconnecting quietly and ask the user to sign
  // in again instead (APPCE-69).
  onAuthFailed?: () => void;
  // A proposal card's button changed the project (linked a repo or key,
  // edited or deleted a fact), so the project list and the facts must be
  // refetched.
  onApplied?: () => void;
}

interface FactText {
  content: string;
  category: string;
}

// What the model's propose_* tools return (agent/agent.py): nothing has been
// changed — the button on the card is what does it.
type Proposal =
  | { proposal: "link"; kind: "github_repo" | "jira_project_key"; value: string; current: string | null }
  | { proposal: "fact_update"; fact_id: string; old: FactText; new: FactText }
  | { proposal: "fact_delete"; fact_id: string; old: FactText };

interface ProposalCard {
  proposal: Proposal;
  status: "open" | "applying" | "done" | "dismissed";
  error?: string;
}

const LINK_LABELS = { github_repo: "GitHub repo", jira_project_key: "Jira project" } as const;
const PROPOSAL_TOOLS = ["propose_link", "propose_fact_update", "propose_fact_delete"];

function proposalTitle(p: Proposal): string {
  if (p.proposal === "link") return `${p.current ? "Change" : "Link"} the ${LINK_LABELS[p.kind]}?`;
  return p.proposal === "fact_update" ? "Update this fact?" : "Delete this fact?";
}

function proposalButton(p: Proposal): string {
  if (p.proposal === "link") return p.current ? "Change" : "Link";
  return p.proposal === "fact_update" ? "Update" : "Delete";
}

function proposalDone(p: Proposal): string {
  if (p.proposal === "link") return "Linked.";
  return p.proposal === "fact_update" ? "Updated." : "Deleted.";
}

// Old text struck through when it changed, so the difference is visible at a glance.
function FactLine({ label, before, after }: { label: string; before: string; after?: string }) {
  const changed = after !== undefined && after !== before;
  return (
    <div className="chat-proposal-change">
      <span className="chat-proposal-label">{label}</span>{" "}
      {changed ? (
        <>
          <span className="chat-proposal-old">{before}</span> → <strong>{after}</strong>
        </>
      ) : (
        before
      )}
    </div>
  );
}

function ProposalBody({ proposal: p }: { proposal: Proposal }) {
  if (p.proposal === "link") {
    return (
      <div className="chat-proposal-change">
        {p.current && <span className="chat-proposal-old">{p.current} → </span>}
        <strong>{p.value}</strong>
      </div>
    );
  }
  const after = p.proposal === "fact_update" ? p.new : undefined;
  return (
    <>
      <FactLine label="Text" before={p.old.content} after={after?.content} />
      <FactLine label="Category" before={p.old.category} after={after?.category} />
    </>
  );
}

interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  isError?: boolean;
  card?: ProposalCard;
}

interface SimilarFact {
  fact_id: string;
  content: string;
  category: string;
}

interface PendingConfirmation {
  toolName: string;
  args: unknown;
  // Saved facts that say (nearly) the same as the one awaiting approval —
  // computed by the server, only for publish_fact (APPCE-111).
  similar: SimilarFact[];
}

function Chat({ idToken, tenantId, onEvent, onAuthFailed, onApplied }: Props) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [isThinking, setIsThinking] = useState(false);
  // Clear chat asks first: it deletes the saved conversation for good.
  const [confirmingClear, setConfirmingClear] = useState(false);
  // Set when a require_confirmation=True tool (APPCE-91) is waiting on an
  // approve/reject — blocks the input row until answered, since the agent
  // can't do anything else until this one round trip resolves.
  const [pendingConfirmation, setPendingConfirmation] = useState<PendingConfirmation | null>(null);
  // Whether the socket is open right now. A browser silently drops a send()
  // on a socket that isn't, so sending is gated on this — otherwise a
  // message typed during a reconnect vanishes and the UI thinks forever.
  const [connected, setConnected] = useState(false);
  const socketRef = useRef<WebSocket | null>(null);
  // Read inside onclose without re-subscribing the effect on every
  // isThinking flip — a ref mirrors the latest value for that purpose.
  const isThinkingRef = useRef(false);
  isThinkingRef.current = isThinking;
  const messagesEndRef = useRef<HTMLDivElement>(null);
  // The socket handlers below live as long as a connection does, so they
  // read the latest callback through a ref instead of capturing one.
  const onEventRef = useRef(onEvent);
  onEventRef.current = onEvent;
  const onAuthFailedRef = useRef(onAuthFailed);
  onAuthFailedRef.current = onAuthFailed;
  // The history load below runs once per project; it shouldn't restart
  // every time the ID token silently refreshes, so it reads the latest
  // token from a ref instead of depending on it.
  const idTokenRef = useRef(idToken);
  idTokenRef.current = idToken;
  // Set by Clear chat so a slow history response can't bring back a
  // conversation the user just cleared.
  const clearedRef = useRef(false);

  // Saved conversation (APPCE-60): survives page reloads, live-reload
  // during development, switching projects, and other devices.
  useEffect(() => {
    if (!tenantId) return;
    let cancelled = false;

    getChatHistory(idTokenRef.current, tenantId)
      .then((turns) => {
        if (cancelled || clearedRef.current || turns.length === 0) return;
        const restored: ChatMessage[] = turns.flatMap((turn) => [
          { role: "user" as const, content: turn.question },
          { role: "assistant" as const, content: turn.answer },
        ]);
        // Prepend: anything already typed while this loaded stays after it.
        setMessages((prev) => [...restored, ...prev]);
      })
      .catch(() => {
        // History is a convenience — the chat itself works without it.
      });

    return () => {
      cancelled = true;
    };
  }, [tenantId]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ block: "end" });
  }, [messages, isThinking]);

  useEffect(() => {
    // No project selected yet (e.g. right after switching accounts,
    // or an account with no projects at all) — keep the input visible
    // but there's nothing to connect to.
    if (!tenantId) return;
    const currentTenantId = tenantId;

    let cancelled = false;
    let attempt = 0;
    let retryTimer: ReturnType<typeof setTimeout> | undefined;

    function connect() {
      const socket = new WebSocket(chatSocketUrl(currentTenantId));
      socketRef.current = socket;

      // The token goes in the first frame, not the URL, so it never lands
      // in an access log. The socket only counts as connected once the
      // server answers "ready" (i.e. the token and the project checked out).
      socket.onopen = () => {
        if (socketRef.current !== socket) return;
        socket.send(JSON.stringify({ type: "auth", token: idToken }));
      };

      socket.onmessage = (event) => {
        const data = JSON.parse(event.data);
        // Only the current socket may flip the state: a superseded one
        // (React dev mode mounts effects twice; a token refresh swaps
        // sockets) can report in after its replacement is already up.
        if (data.type === "ready") {
          if (socketRef.current !== socket) return;
          attempt = 0;
          setConnected(true);
        } else if (data.type === "tool_result" && PROPOSAL_TOOLS.includes(data.name) && data.result?.proposal) {
          setMessages((prev) => [...prev, { role: "assistant", content: "", card: { proposal: data.result, status: "open" } }]);
        } else if (data.type === "tool_call" || data.type === "tool_result") {
          onEventRef.current?.(
            data.type === "tool_call"
              ? { type: "tool_call", id: data.id, name: data.name, args: data.args }
              : { type: "tool_result", id: data.id, name: data.name, result: data.result },
          );
        } else if (data.type === "confirm_required") {
          // Still "thinking" — the turn isn't done, it's just paused on
          // the user. Not sent to the Trace tab: it isn't a completed
          // tool call, and the backend already excludes ADK's synthetic
          // adk_request_confirmation call from tool_call/tool_result.
          setPendingConfirmation({ toolName: data.tool_name, args: data.args, similar: data.similar ?? [] });
        } else if (data.type === "final") {
          setMessages((prev) => [...prev, { role: "assistant", content: data.text }]);
          setIsThinking(false);
          onEventRef.current?.({ type: "answered" });
        } else if (data.type === "error") {
          // The backend rejected the message or the agent failed — the
          // connection stays open, so just show why and stop "thinking".
          setMessages((prev) => [...prev, { role: "assistant", content: data.message, isError: true }]);
          setIsThinking(false);
          setPendingConfirmation(null);
          onEventRef.current?.({ type: "failed" });
        }
      };

      // A closed socket usually means the ID token expired mid-session
      // (see APPCE-54) — idToken itself gets refreshed in the
      // background by Auth.tsx, so reconnecting picks up the new one
      // automatically instead of forcing the user to sign in again.
      // Code 1008 (policy violation) means the backend rejected the
      // token outright (e.g. not on the allowlist) — reconnecting won't
      // help there, so don't loop on it.
      //
      // A close that interrupts an in-flight question (isThinking still
      // true) is surfaced as a friendly error instead of silently
      // vanishing.
      socket.onclose = (event) => {
        if (socketRef.current === socket) setConnected(false);
        setPendingConfirmation(null);
        if (isThinkingRef.current) {
          setMessages((prev) => [
            ...prev,
            {
              role: "assistant",
              content: "Something went wrong while talking to the agent. Please try again.",
              isError: true,
            },
          ]);
          setIsThinking(false);
          onEventRef.current?.({ type: "failed" });
        }
        // Back off instead of retrying instantly — with the server down
        // that would be a tight loop of failed connections.
        if (!cancelled && event.code !== 1008) {
          retryTimer = setTimeout(connect, Math.min(1000 * 2 ** attempt, 10_000));
          attempt += 1;
        } else if (event.code === 1008) {
          onAuthFailedRef.current?.();
        }
      };
    }

    connect();
    return () => {
      cancelled = true;
      clearTimeout(retryTimer);
      socketRef.current?.close();
    };
  }, [idToken, tenantId]);

  function sendMessage() {
    const question = input.trim();
    if (!question || !tenantId || !!pendingConfirmation || socketRef.current?.readyState !== WebSocket.OPEN) return;

    setMessages((prev) => [...prev, { role: "user", content: question }]);
    setIsThinking(true);
    setInput("");
    socketRef.current.send(JSON.stringify({ message: question }));
    onEvent?.({ type: "sent", question });
  }

  function respondToConfirmation(confirmed: boolean) {
    if (!pendingConfirmation || socketRef.current?.readyState !== WebSocket.OPEN) return;
    setPendingConfirmation(null);
    socketRef.current.send(JSON.stringify({ type: "confirm_response", confirmed }));
  }

  function updateCard(index: number, changes: Partial<ProposalCard>) {
    setMessages((prev) =>
      prev.map((msg, i) => (i === index && msg.card ? { ...msg, card: { ...msg.card, ...changes } } : msg)),
    );
  }

  async function applyProposal(index: number, p: Proposal) {
    if (!tenantId) return;
    updateCard(index, { status: "applying", error: undefined });
    try {
      const token = idTokenRef.current;
      if (p.proposal === "link") await setTenantLink(token, tenantId, p.kind, p.value);
      else if (p.proposal === "fact_update") await updateFact(token, tenantId, p.fact_id, p.new);
      else await deleteFact(token, tenantId, p.fact_id);
      updateCard(index, { status: "done" });
      onApplied?.();
    } catch (err) {
      updateCard(index, { status: "open", error: err instanceof Error ? err.message : "Couldn't do that." });
    }
  }

  function clearChat() {
    // Also drop the server-side session — clearing only the UI would
    // leave the model still seeing (and billing for) the old history.
    // Only once authenticated: any frame before "ready" is taken for a
    // failed login and closes the socket. (The button is disabled until then.)
    if (connected && socketRef.current?.readyState === WebSocket.OPEN) {
      socketRef.current.send(JSON.stringify({ type: "reset" }));
    }
    clearedRef.current = true;
    setPendingConfirmation(null);
    setIsThinking(false);
    setMessages([]);
    onEvent?.({ type: "cleared" });
  }

  return (
    <div className="chat">
      <div className="chat-messages">
        {messages.map((msg, i) =>
          msg.card ? (
            <div key={i} className="chat-confirm chat-proposal">
              <div className="chat-confirm-title">{proposalTitle(msg.card.proposal)}</div>
              <ProposalBody proposal={msg.card.proposal} />
              {msg.card.error && <p className="chat-proposal-error">{msg.card.error}</p>}
              {msg.card.status === "done" ? (
                <div className="chat-proposal-outcome">{proposalDone(msg.card.proposal)}</div>
              ) : msg.card.status === "dismissed" ? (
                <div className="chat-proposal-outcome">Dismissed.</div>
              ) : (
                <div className="chat-confirm-actions">
                  <button onClick={() => updateCard(i, { status: "dismissed" })} disabled={msg.card.status === "applying"}>
                    Dismiss
                  </button>
                  <button
                    className="chat-confirm-approve"
                    onClick={() => applyProposal(i, msg.card!.proposal)}
                    disabled={msg.card.status === "applying"}
                  >
                    {proposalButton(msg.card.proposal)}
                  </button>
                </div>
              )}
            </div>
          ) : (
          <div key={i} className={`chat-bubble ${msg.role}${msg.isError ? " error" : ""}`}>
            {msg.role === "assistant" && !msg.isError ? (
              <ReactMarkdown components={markdownComponents}>{msg.content}</ReactMarkdown>
            ) : (
              msg.content
            )}
          </div>
          ),
        )}

        {isThinking && !pendingConfirmation && (
          <div className="chat-thinking">Thinking…</div>
        )}

        {pendingConfirmation && (
          <div className="chat-confirm">
            <div className="chat-confirm-title">
              {CONFIRM_TOOL_LABELS[pendingConfirmation.toolName] ?? pendingConfirmation.toolName}?
            </div>
            {(() => {
              const view = describeArgs(pendingConfirmation.args);
              return view.kind === "table" ? (
                <table className="chat-confirm-args">
                  <tbody>
                    {view.rows.map(([name, value]) => (
                      <tr key={name}>
                        <td>{name}</td>
                        <td>{value}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              ) : null;
            })()}
            {pendingConfirmation.similar.length > 0 && (
              <div className="chat-confirm-similar">
                <div>Already saved — this may be a duplicate:</div>
                <ul>
                  {pendingConfirmation.similar.map((fact) => (
                    <li key={fact.fact_id}>
                      {fact.content} <span className="chat-proposal-label">({fact.category})</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
            <div className="chat-confirm-actions">
              <button onClick={() => respondToConfirmation(false)}>Reject</button>
              <button className="chat-confirm-approve" onClick={() => respondToConfirmation(true)}>
                Approve
              </button>
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      <div className="chat-input-row">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && sendMessage()}
          placeholder={
            !tenantId
              ? "Select a project first"
              : pendingConfirmation
                ? "Approve or reject the pending action above"
                : connected
                  ? "Ask or record something"
                  : "Connecting…"
          }
          disabled={!tenantId || !connected || !!pendingConfirmation}
          maxLength={MAX_MESSAGE_CHARS}
        />
        <button
          onClick={sendMessage}
          disabled={!tenantId || !connected || !!pendingConfirmation}
          title="Send"
          className="send-button"
        >
          <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <line x1="22" y1="2" x2="11" y2="13" />
            <polygon points="22 2 15 22 11 13 2 9 22 2" />
          </svg>
        </button>
        <button onClick={() => setConfirmingClear(true)} disabled={!connected} title="Clear chat" className="icon-button">
          <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <polyline points="3 6 5 6 21 6" />
            <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
            <line x1="10" y1="11" x2="10" y2="17" />
            <line x1="14" y1="11" x2="14" y2="17" />
          </svg>
        </button>
      </div>

      {confirmingClear && (
        <ConfirmDialog
          title="Clear this chat?"
          message="This deletes the whole conversation for this project, including its saved copy. This can't be undone."
          confirmLabel="Clear"
          cancelLabel="Keep"
          onCancel={() => setConfirmingClear(false)}
          onConfirm={() => {
            setConfirmingClear(false);
            clearChat();
          }}
        />
      )}
    </div>
  );
}

export default Chat;
