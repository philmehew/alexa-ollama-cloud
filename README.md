# alexa-ollama-cloud

An Alexa Skill that lets you have voice conversations with Ollama Cloud LLMs, with web search support for up-to-date answers.

Forked from [paulotruta/alexa-skill-llm-intent](https://github.com/paulotruta/alexa-skill-llm-intent) — heavily modified.

## Features

- **Voice conversations** with Ollama Cloud LLMs through any Alexa device
- **Web search** — every question searches the Ollama Web Search API first, grounding responses in current information
- **Conversation history** — follow-up questions ("yes", "tell me more") maintain context within a session
- **Search context reuse** — follow-up questions reuse the search results from the first question, preserving topic context and saving latency
- **8-second timeout budget** — search (~1-3s) + LLM (~3-5s) stays within Alexa's response limit
- **Graceful degradation** — if web search fails or times out, the skill falls back to the LLM's training data
- **Voice-optimised system prompt** — short answers, no bullet points, no visual formatting

## Alexa Developer Console

- **Skill name:** AI chat
- **Invocation:** "Alexa, open AI chat"
- **Hosting:** Alexa-hosted (Python), EU region
- **Locale:** en-GB
- **Skill ID:** `amzn1.ask.skill.046b9830-a6f0-40a5-8272-5ff76f34d9c6`

## Configuration

Copy `lambda/config.example.json` to `lambda/config.json` and fill in your details:

```json
{
  "llm_url": "https://ollama.com/api/chat",
  "web_search_url": "https://ollama.com/api/web_search",
  "llm_model": "ministral-3:14b-cloud",
  "llm_key": "YOUR_OLLAMA_API_KEY",
  "invocation_name": "ai chat",
  "llm_system_prompt": "You are Ollama, a voice assistant on an Alexa device..."
}
```

| Field | Description |
|---|---|
| `llm_url` | Ollama Cloud chat API endpoint |
| `web_search_url` | Ollama Cloud web search API endpoint |
| `llm_model` | Model to use (fast models like `ministral-3:14b-cloud` work best within Alexa's 8-second timeout) |
| `llm_key` | Your Ollama API key |
| `invocation_name` | Skill invocation name (must match the interaction model) |
| `llm_system_prompt` | System prompt for the LLM (optional, has a sensible default) |

## Deployment

### Option 1: Alexa Developer Console (recommended)

1. Create a new Alexa Skill in the [Developer Console](https://developer.amazon.com/alexa/console/ask) — choose **Alexa-hosted (Python)**, **EU region**, locale **English (UK)**
2. In the **Build** tab → **JSON Editor**, paste the contents of `skill-package/interactionModels/custom/en-GB.json`
3. Click **Save Model** → **Build Model**
4. In the **Code** tab, replace the files:
   - `lambda_function.py` → contents of `lambda/lambda_function.py`
   - `llm_intent/llm_client.py` → contents of `lambda/llm_intent/llm_client.py`
   - `llm_intent/utils.py` → contents of `lambda/llm_intent/utils.py`
   - `requirements.txt` → contents of `lambda/requirements.txt`
5. Create `config.json` in the `lambda/` directory with your Ollama API credentials
6. Click **Deploy**

### Option 2: Makefile (ASK CLI)

If you have the ASK CLI installed and configured:

```bash
# Create a new Alexa-hosted skill
make new

# Or import an existing skill
make init id=amzn1.ask.skill.046b9830-a6f0-40a5-8272-5ff76f34d9c6

# Deploy the code
make update skill=<your_skill_slug>
```

### Option 3: Build package

```bash
make package
```

This creates `build/package/alexa-skill-llm-intent-release.zip` that you can import via the Alexa Developer Console's **Code** tab → **Import Code**.

## Usage

Once deployed, try:

- "Alexa, open AI chat"
- "Alexa, ask AI chat what's the latest on artemis two"
- "Alexa, ask AI chat to search for the latest news"
- "Alexa, tell AI chat about quantum computing"

Within a session:
- **Follow up:** "yes" / "tell me more" / "what about the crew"
- **Exit:** "no" / "stop" / "cancel"

## Architecture

### `lambda/lambda_function.py` — Main skill handler

- **QuestionIntentHandler** — on the first question in a session, calls the Ollama Web Search API then passes results to the LLM; on follow-ups, reuses stored search context
- **YesIntentHandler** — continues conversation, reuses stored search context
- **NoIntentHandler** — ends the session
- **Conversation history** — up to 10 messages stored in session attributes
- **Web search** — every question triggers a search on first ask, results stored in session for follow-ups
- **System prompt** — optimised for voice: short answers, no formatting, no "As an AI"

### `lambda/llm_intent/llm_client.py` — LLM and search client

- **`api_request_with_messages()`** — sends conversation history to Ollama Chat API (7s timeout)
- **`web_search()`** — queries Ollama Web Search API (3s timeout), returns empty list on failure
- Uses `urllib.request` only — no external HTTP dependencies

### `lambda/llm_intent/utils.py` — Config loader and canned responses

### `lambda/config.json` — API credentials (not committed, use `config.example.json` as template)

### `skill-package/interactionModels/custom/en-GB.json` — Alexa interaction model

- 90+ sample utterances including search-oriented phrases ("search for", "look up", "check online for", "what's the latest on")
- Contractions supported ("what's", "who's", "where's")
- `AMAZON.SearchQuery` slot type for free-form text capture
- `AMAZON.YesIntent` and `AMAZON.NoIntent` for conversation flow

## Key Constraint: 8-Second Timeout

Alexa gives skills exactly 8 seconds to respond. The Lambda timeout is set to 7 seconds. This means:

- Fast cloud models only: `ministral-3:14b-cloud`, `gpt-oss:20b`, `qwen3:8b`
- Large models (e.g. `gpt-oss:120b`) risk timing out
- Search (~1-3s) + LLM (~3-5s) = ~4-8s total — tight but feasible
- Follow-up questions skip the search (reuse cached results), giving the LLM the full time budget

## Alexa Intent Model Limitation

Alexa's interaction model decides which intent to route to **before** your Lambda code runs. If it can't match input to an intent, your code never sees the text. This means:

- Users need carrier phrases like "tell me about X" or "what is X"
- Bare text like "capital of France" falls to FallbackIntent — the original text is lost
- This is a fundamental Alexa platform limitation, not a bug in this skill
- The workaround: extensive sample utterances + `AMAZON.SearchQuery` slot type for free-form capture

## Requirements

- [Alexa Developer Account](https://developer.amazon.com/alexa)
- [Ollama Cloud API key](https://ollama.com) with access to cloud models
- Python 3.8+ (for local development)
- `ask-sdk-core==1.19.0` (the only dependency)

## Credits

Forked from [paulotruta/alexa-skill-llm-intent](https://github.com/paulotruta/alexa-skill-llm-intent) by Paulo Truta. The original project provided the Alexa skill scaffolding, intent handling, and LLM proxy pattern.

## License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.
