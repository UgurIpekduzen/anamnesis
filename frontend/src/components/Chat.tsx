import { useEffect, useRef, useState } from "react";

import { chatSocketUrl } from "../api";
import "./Chat.css";

interface Props {
  idToken: string;
  tenantId: string | null;
  onMessageSent?: () => void;
}

interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  isError?: boolean;
}

interface TraceEntry {
  type: "tool_call" | "tool_result";
  name: string;
}

function Chat({ idToken, tenantId, onMessageSent }: Props) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [trace, setTrace] = useState<TraceEntry[]>([]);
  const [input, setInput] = useState("");
  const [isThinking, setIsThinking] = useState(false);
  const socketRef = useRef<WebSocket | null>(null);
  // Read inside onclose without re-subscribing the effect on every
  // isThinking flip — a ref mirrors the latest value for that purpose.
  const isThinkingRef = useRef(false);
  isThinkingRef.current = isThinking;
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ block: "end" });
  }, [messages, trace, isThinking]);

  useEffect(() => {
    // No project selected yet (e.g. right after switching accounts,
    // or an account with no projects at all) — keep the input visible
    // but there's nothing to connect to.
    if (!tenantId) return;
    const currentTenantId = tenantId;

    let cancelled = false;

    function connect() {
      const socket = new WebSocket(chatSocketUrl(idToken, currentTenantId));
      socketRef.current = socket;

      socket.onmessage = (event) => {
        const data = JSON.parse(event.data);
        if (data.type === "tool_call" || data.type === "tool_result") {
          setTrace((prev) => [...prev, { type: data.type, name: data.name }]);
        } else if (data.type === "final") {
          setMessages((prev) => [...prev, { role: "assistant", content: data.text }]);
          setIsThinking(false);
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
      // vanishing — mirrors app/chat.py's try/except in the Streamlit UI.
      socket.onclose = (event) => {
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
        }
        if (!cancelled && event.code !== 1008) connect();
      };
    }

    connect();
    return () => {
      cancelled = true;
      socketRef.current?.close();
    };
  }, [idToken, tenantId]);

  function sendMessage() {
    const question = input.trim();
    if (!question || !socketRef.current || !tenantId) return;

    setMessages((prev) => [...prev, { role: "user", content: question }]);
    setTrace([]);
    setIsThinking(true);
    setInput("");
    socketRef.current.send(JSON.stringify({ message: question }));
    onMessageSent?.();
  }

  function clearChat() {
    setMessages([]);
    setTrace([]);
  }

  return (
    <div className="chat">
      <div className="chat-messages">
        {messages.map((msg, i) => (
          <div key={i} className={`chat-bubble ${msg.role}${msg.isError ? " error" : ""}`}>
            {msg.content}
          </div>
        ))}

        {isThinking && (
          <div className="chat-trace">
            <span>Thinking…</span>
            {trace.map((entry, i) => (
              <span key={i} className="chat-trace-entry">
                {entry.type === "tool_call" ? "🔧" : "✅"} {entry.name}
              </span>
            ))}
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      <div className="chat-input-row">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && sendMessage()}
          placeholder={tenantId ? "Ask or record something" : "Select a project first"}
          disabled={!tenantId}
        />
        <button onClick={sendMessage} disabled={!tenantId} title="Send" className="send-button">
          <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <line x1="22" y1="2" x2="11" y2="13" />
            <polygon points="22 2 15 22 11 13 2 9 22 2" />
          </svg>
        </button>
        <button onClick={clearChat} title="Clear chat" className="icon-button">
          <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <polyline points="3 6 5 6 21 6" />
            <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
            <line x1="10" y1="11" x2="10" y2="17" />
            <line x1="14" y1="11" x2="14" y2="17" />
          </svg>
        </button>
      </div>
    </div>
  );
}

export default Chat;
