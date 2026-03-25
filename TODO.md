# ForgeChannels — Task Split

4 parallel workstreams. Each person owns one area end-to-end.

---

## Person 1: Channel Detection Research
**Goal:** Figure out how to detect which messaging platform an email is on.

- [ ] Research Google Chat API — how to check if an external email is reachable via Google Chat
  - Can you probe without actually sending a message?
  - What scopes / permissions needed?
  - Does the person need to be on Google Workspace?
- [ ] Research Microsoft Teams / Graph API — how to check if an email is an M365 user with Teams external access
- [ ] Research Slack API — `users.lookupByEmail` across workspaces
- [ ] Document findings: what works, what doesn't, what requires admin access
- [ ] Build `channel_detector.py` — takes an email, returns which channels it's reachable on + confidence
- [ ] Handle edge cases: email not found, API rate limits, permission denied

**Deliverable:** A function `detect_channel(email) → { channel, confidence, identifier }` that works for at least Google Chat.

---

## Person 2: Google Chat API — Send & Receive Messages
**Goal:** Actually send messages via Google Chat and read replies.

- [ ] Set up Google Cloud project with Chat API enabled
- [ ] Implement Google OAuth 2.0 installed app flow (opens browser, saves token)
  - Scopes: `chat.messages.create`, `chat.messages.readonly`, `userinfo.email`
- [ ] Send a DM to an external email via Google Chat API
  - Figure out: do you create a space first? Or DM directly?
  - Test with a real external Google Workspace account
- [ ] Read replies from a conversation (poll or push)
- [ ] Build `google_chat_service.py` with methods:
  - `send_message(to_email, body) → message_id`
  - `get_replies(space_id) → list of messages`
  - `list_active_conversations() → list`
- [ ] Create `demo_contacts.csv` with test emails you can actually message

**Deliverable:** Can send a Google Chat message to a real person and read their reply back programmatically.

---

## Person 3: Free LLM Conversation Engine
**Goal:** Set up a free LLM that handles ongoing chat replies to make the conversation feel natural.

- [ ] Evaluate free options:
  - **Gemini 2.0 Flash** — 15 RPM, 1M tokens/day free via `google-generativeai` SDK
  - **Groq (Llama 3.3 70B)** — 30 RPM free via `groq` SDK
  - **Ollama local** — unlimited but needs local setup
- [ ] Pick one and get it working with a simple prompt → response
- [ ] Write conversation system prompt:
  - Friendly sales rep tone
  - Short messages (1-3 sentences)
  - Context-aware (knows the opener that was sent, the contact info)
  - Goal: build rapport → book a call
- [ ] Build `ai_conversation.py`:
  - `generate_reply(conversation_history, contact_info, booking_url) → reply_text`
  - Maintain conversation context per contact
- [ ] Add interest detection: classify each prospect reply as `interested` / `neutral` / `not_interested`
- [ ] When interested → naturally weave in the booking link
- [ ] Also set up Claude API call for the initial opener (higher quality first message)

**Deliverable:** Given a conversation history, generates a natural-sounding next reply. Knows when to drop the booking link.

---

## Person 4: CLI App + Schedule Call Integration
**Goal:** Wire everything together into the terminal tool + handle the booking flow.

- [ ] Python project scaffold: `setup.py`, `requirements.txt`, typer + rich
- [ ] Setup wizard:
  - Google OAuth sign-in (calls Person 2's auth code)
  - API key prompts (Anthropic, optional Groq/Gemini key)
  - Booking link input (Calendly/Cal.com URL)
  - Save to `~/.forgechannels/config.json`
- [ ] CSV loading + rich table display
- [ ] Main orchestration loop:
  1. Load contacts from CSV
  2. Detect channels (Person 1's code)
  3. Generate + send openers (Person 2 sends, Person 3 generates)
  4. Poll for replies → auto-respond (Person 2 reads, Person 3 replies)
  5. Track state per contact: `opener_sent → in_conversation → call_proposed → booked`
- [ ] Rich terminal UI:
  - Progress bars for detection + sending
  - Message preview panels
  - Conversation thread view
  - Summary dashboard (contacted / replied / booked)
- [ ] `--dry-run` flag
- [ ] Demo prep: README, rehearsal

**Deliverable:** Running `forgechannels` walks through the full flow from setup to booked calls.

---

## Integration Points

```
Person 1 (detection) ──→ Person 4 (CLI) calls detect_channel()
Person 2 (Google Chat) ──→ Person 4 (CLI) calls send_message() / get_replies()
Person 3 (LLM) ──→ Person 4 (CLI) calls generate_reply()
Person 2 (OAuth) ──→ Person 4 (CLI) calls auth flow in setup wizard
```

**Shared interfaces to agree on early:**
- `Contact` dataclass: `email, first_name, last_name, company, title, signal`
- `ChannelResult`: `channel, confidence, identifier, reachable`
- `ConversationState`: `contact, messages[], status, booking_url`
