"""AI conversation service — Claude generates natural replies."""

import anthropic

SYSTEM_PROMPT = """You are a friendly sales rep having a Google Chat conversation.
Your name is {sender_name} from ForgeChannels.
You're chatting with {contact_name}, {contact_title} at {contact_company}.

Context about them: {signal}

Your goal: build rapport → understand their needs → book a demo call.
The booking link is: {booking_url}

Rules:
- Keep messages short (1-3 sentences). Sound human, not like a bot.
- Match their energy and tone.
- When the prospect shows interest, naturally suggest a quick call and share the booking link.
- Never be pushy. If they say no, be gracious and leave the door open.
- Don't repeat yourself or the booking link if you already shared it.
- Don't use exclamation points excessively.
- Never reveal you are an AI or automated system."""


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
    system = SYSTEM_PROMPT.format(
        sender_name=sender_name,
        contact_name=contact_name,
        contact_title=contact_title,
        contact_company=contact_company,
        signal=signal,
        booking_url=booking_url,
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
