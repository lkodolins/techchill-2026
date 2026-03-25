"""AI conversation service — Claude generates natural replies."""

from pathlib import Path

import anthropic

# Load agent context from agents.md
_AGENTS_MD = Path(__file__).resolve().parent.parent.parent / "agents.md"
_AGENT_CONTEXT = ""
if _AGENTS_MD.exists():
    _AGENT_CONTEXT = _AGENTS_MD.read_text()

SYSTEM_PROMPT = """You are a friendly sales rep having a Google Chat conversation.
Your name is {sender_name} from ForgeChannels.
You're chatting with {contact_name}, {contact_title} at {contact_company}.

Context about them: {signal}

Your goal: get them on a quick 15 min call.

## Conversation flow:
1. OPENER (already sent): casual ask if they're up for a 15 min call.
2. IF INTERESTED: ask what day/time works for them. Keep it simple — "what day works best?" or "how's Thursday afternoon?"
3. ONCE TIME IS AGREED: the system will create a calendar event with a Meet link. You'll get a [SYSTEM] note with the link — share it naturally: "nice, here's the link: <url>. talk soon"
4. IF NOT INTERESTED: be chill about it. "no worries, appreciate the time" — keep the door open but don't push.

## Style rules:
- Keep messages to 1 sentence, max 2. Short and casual like a real chat.
- Lowercase is fine. Sound human, not salesy.
- Don't use exclamation points excessively.
- Never dump product info unless they ask.
- Never reveal you are an AI or automated.
- Don't repeat yourself.
- Match their energy.{booking_url_section}

## Product Knowledge
{agent_context}"""


def create_client(api_key: str) -> anthropic.Anthropic:
    """Create an Anthropic client."""
    return anthropic.Anthropic(api_key=api_key)


def generate_reply(
    client: anthropic.Anthropic,
    conversation_history: list[dict],
    sender_name: str,
    contact_name: str,
    contact_title: str,
    contact_company: str,
    signal: str,
    booking_url: str,
) -> str:
    """Generate a reply based on conversation history.

    conversation_history: list of {"role": "assistant"|"user", "content": "..."}
      - "assistant" = our messages (the sales rep)
      - "user" = the prospect's messages
    """
    booking_url_section = ""
    if booking_url:
        booking_url_section = f"\n\nThe current meeting link is: {booking_url}"

    system = SYSTEM_PROMPT.format(
        sender_name=sender_name,
        contact_name=contact_name,
        contact_title=contact_title,
        contact_company=contact_company,
        signal=signal,
        booking_url_section=booking_url_section,
        agent_context=_AGENT_CONTEXT,
    )

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=256,
        system=system,
        messages=conversation_history,
    )

    return response.content[0].text


def classify_interest(
    client: anthropic.Anthropic,
    message: str,
) -> str:
    """Classify a prospect's reply. Returns: interested, neutral, not_interested, booked."""
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=20,
        system="""Classify the sales prospect's message into exactly one category. Reply with ONLY the category word.

Categories:
- interested: they're engaging, asking questions, suggesting alternative times, negotiating, or showing curiosity. "That doesn't work for me" or "maybe next week?" = interested (they're open, just not that specific time).
- neutral: short or ambiguous replies like "ok", "hmm", "who are you?"
- not_interested: explicit rejection like "no thanks", "stop messaging me", "not interested", "unsubscribe", "please don't contact me"
- booked: they confirmed a specific time or said they'll join the call

When in doubt, classify as interested or neutral. Only use not_interested for clear, explicit rejections.""",
        messages=[
            {
                "role": "user",
                "content": f"Message: \"{message}\"",
            }
        ],
    )
    result = response.content[0].text.strip().lower()
    if result not in ("interested", "neutral", "not_interested", "booked"):
        return "neutral"
    return result
