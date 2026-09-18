import { useEffect, useRef, useState } from "react";

import { chatSocketUrl } from "../api";

interface Props {
  idToken: string;
  tenantId: string;
}

interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

interface TraceEntry {
  type: "tool_call" | "tool_result";
  name: string;
}

function Chat({ idToken, tenantId }: Props) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [trace, setTrace] = useState<TraceEntry[]>([]);
  const [input, setInput] = useState("");
  const [isThinking, setIsThinking] = useState(false);
  const socketRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    let cancelled = false;

    function connect() {
      const socket = new WebSocket(chatSocketUrl(idToken, tenantId));
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
      socket.onclose = (event) => {
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
    if (!question || !socketRef.current) return;

    setMessages((prev) => [...prev, { role: "user", content: question }]);
    setTrace([]);
    setIsThinking(true);
    setInput("");
    socketRef.current.send(JSON.stringify({ message: question }));
  }

  return (
    <div>
      <div>
        {messages.map((msg, i) => (
          <p key={i}>
            <strong>{msg.role === "user" ? "You" : "Anamnesis"}:</strong> {msg.content}
          </p>
        ))}
      </div>

      {isThinking && (
        <div>
          <em>Thinking...</em>
          {trace.map((entry, i) => (
            <div key={i}>
              {entry.type === "tool_call" ? "🔧" : "✅"} {entry.name}
            </div>
          ))}
        </div>
      )}

      <input
        value={input}
        onChange={(e) => setInput(e.target.value)}
        onKeyDown={(e) => e.key === "Enter" && sendMessage()}
        placeholder="Ask or record something"
      />
      <button onClick={sendMessage}>Send</button>
    </div>
  );
}

export default Chat;
