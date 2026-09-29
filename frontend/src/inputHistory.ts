// Recalling earlier messages in the chat box with the arrow keys, like a
// shell. Kept pure so the walk through the list is easy to read
// and reason about.

// Consecutive repeats collapse into one, so ↑ doesn't stall on the same text.
export function recallableMessages(sent: string[]): string[] {
  return sent.filter((message, i) => i === 0 || message !== sent[i - 1]);
}

export interface Recall {
  // null means "not browsing": the box holds whatever the user is typing.
  index: number | null;
  text: string;
}

// ↑ goes to an older message, ↓ to a newer one, and past the newest brings
// back the draft that was being typed when browsing started. Returns null
// when the key changes nothing (nothing to recall, or ↓ while not browsing).
export function step(
  direction: "up" | "down",
  messages: string[],
  index: number | null,
  draft: string,
): Recall | null {
  if (messages.length === 0) return null;
  if (direction === "up") {
    const next = index === null ? messages.length - 1 : Math.max(index - 1, 0);
    return { index: next, text: messages[next] };
  }
  if (index === null) return null;
  const next = index + 1;
  return next >= messages.length ? { index: null, text: draft } : { index: next, text: messages[next] };
}
