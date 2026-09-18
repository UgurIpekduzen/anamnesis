import { useEffect, useRef, useState } from "react";

import { chatSocketUrl } from "../api";

interface Props {
  ownerUid: string;
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

function Chat({ ownerUid, tenantId }: Props) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [trace, setTrace] = useState<TraceEntry[]>([]);
  const [input, setInput] = useState("");
  const [isThinking, setIsThinking] = useState(false);
  const socketRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    const socket = new WebSocket(chatSocketUrl(ownerUid, tenantId));
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

    return () => socket.close();
  }, [ownerUid, tenantId]);

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
