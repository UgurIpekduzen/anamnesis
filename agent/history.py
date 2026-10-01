"""Trims the conversation history sent to the model on each turn, so a
long-running chat session's token cost stays bounded by the user's
configured history window instead of growing with the whole conversation.
"""

from google.adk.agents.callback_context import CallbackContext
from google.adk.models.llm_request import LlmRequest
from google.genai import types

from src.accounts.settings import get_settings

# The window size is a per-user setting (src/accounts/settings.py); it
# caps how many past user turns are sent to the model on each call, so a
# long-running session's token cost doesn't grow without bound. A plain
# window instead of summarization on purpose — summarizing costs an extra
# LLM call, which defeats the point at this usage scale.


def _starts_user_turn(content: types.Content) -> bool:
    # function_response parts also carry role="user" in Gemini's format,
    # so role alone can't tell a real user message from a tool result.
    if content.role != "user" or not content.parts:
        return False
    has_text = any(part.text for part in content.parts)
    has_tool_result = any(part.function_response for part in content.parts)
    return has_text and not has_tool_result


def trim_to_last_turns(contents: list[types.Content], max_turns: int) -> list[types.Content]:
    """Keep only the last max_turns user turns (and everything after each).

    The cut always lands on a user-turn boundary: slicing between a
    function_call and its function_response makes Gemini reject the
    request, and a turn's tool-call loop must stay intact while it's
    still in progress.

    Args:
        contents (list[types.Content]): The full conversation history, in
            Gemini's Content format, to trim.
        max_turns (int): The number of most recent user turns to keep
            (everything from that point on is kept too).
    """
    starts = [i for i, content in enumerate(contents) if _starts_user_turn(content)]
    if len(starts) <= max_turns:
        return contents
    return contents[starts[-max_turns] :]


def make_history_limiter():
    """Build a before_model_callback that trims to the shared history_turns
    setting.

    The setting is read on each call rather than captured once, so an admin
    change takes effect on the next turn without rebuilding the cached
    Runner (which would throw away every user's in-memory conversation).
    """

    def limit_history(callback_context: CallbackContext, llm_request: LlmRequest) -> None:
        """Trim llm_request.contents in place to the current history_turns setting.

        Args:
            callback_context (CallbackContext): ADK's per-invocation callback
                context (unused here beyond satisfying the callback
                signature).
            llm_request (LlmRequest): ADK's request object for this model
                call; its contents list is mutated in place.
        """
        max_turns = get_settings()["history_turns"]
        llm_request.contents = trim_to_last_turns(llm_request.contents, max_turns)
        return None

    return limit_history
