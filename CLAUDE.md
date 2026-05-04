# Project: alexa-ollama-cloud — Alexa Skill for Ollama Cloud

An Alexa skill that lets you have voice conversations with Ollama Cloud LLMs through your Alexa device. Fork of [paulotruta/alexa-skill-llm-intent](https://github.com/paulotruta/alexa-skill-llm-intent), heavily modified.

## Alexa Developer Console
- Skill name: AI chat
- Invocation name: `ai chat` ("Alexa, open AI chat")
- Hosting: Alexa-hosted (Python), EU region
- Skill ID: `amzn1.ask.skill.046b9830-a6f0-40a5-8272-5ff76f34d9c6`

## Ollama Cloud Config
- API endpoint: `https://ollama.com/api/chat` (native Ollama API, not OpenAI-compatible)
- Authentication: Bearer token via Ollama API key
- Model: `ministral-3:14b-cloud` (chosen for speed — must respond within Alexa's 8-second timeout)
- Web Search API: `https://ollama.com/api/web_search` (not yet integrated)
- Web Fetch API: `https://ollama.com/api/web_fetch` (not yet integrated)

## Key Constraint: 8-Second Timeout
Alexa gives skills exactly 8 seconds to respond. The Lambda timeout is set to 7 seconds. This means:
- Small/fast cloud models work (ministral-3:14b, gpt-oss:20b, qwen3:8b)
- Large models (gpt-oss:120b) risk timing out
- Multi-step flows (search → LLM) must be carefully timed

## Current State: WORKING MVP

Working features:
1. **Open skill**: "Alexa, open AI chat" → "AI chat ready. What would you like to know?"
2. **Ask questions**: "tell me about dinosaurs" → Ollama responds
3. **Conversation history**: LLM receives full conversation context, so follow-ups make sense
4. **"Yes" to continue**: "yes" sends "Yes, please tell me more." with history → LLM continues
5. **"No"/"Stop" to exit**: Ends the session
6. **Fallback handling**: If Alexa can't match input, user gets rephrasing guidance

## Architecture

### `lambda/lambda_function.py` — Main skill handler
- Removed all `requests` library references (uses `urllib.request` instead)
- Removed `LLMQuestionProxy` class (was double-parsing responses)
- Conversation history via session attributes (max 10 messages)
- `ask_ollama()` helper manages history + API calls
- `YesIntentHandler` — sends "Yes, please tell me more" with history
- `NoIntentHandler` — ends session
- `FallbackIntentHandler` — guides user to rephrase with carrier phrases
- System prompt optimized for voice (no bullet points, round numbers, under 3 sentences)

### `lambda/llm_intent/llm_client.py` — LLM client
- Uses `urllib.request` (no external dependency beyond ask-sdk-core)
- Messages use simple string content (Ollama native format), not OpenAI array format
- `api_request()` — single prompt + question
- `api_request_with_messages()` — full conversation history
- Both methods handle Ollama native API response format (`response["message"]["content"]`) with OpenAI format fallback
- 7-second timeout on all API calls
- Error handling returns user-friendly voice messages

### `lambda/llm_intent/utils.py` — Utilities
- Unchanged from original

### `lambda/config.json` — Ollama Cloud configuration
```json
{
  "llm_url": "https://ollama.com/api/chat",
  "llm_model": "ministral-3:14b-cloud",
  "llm_key": "[user's Ollama API key]",
  "invocation_name": "ai chat",
  "llm_system_prompt": "..."
}
```

### `lambda/requirements.txt`
```
ask-sdk-core==1.19.0
```

### Interaction Model (Alexa Developer Console)
- Invocation name: `ai chat`
- Added `AMAZON.YesIntent` and `AMAZON.NoIntent`
- Removed bare utterances that match QuestionIntent without filling the searchQuery slot
- Added many carrier phrases for QuestionIntent including conversational glue words
- `AMAZON.SearchQuery` slot type captures free-form text once the intent is matched

## Alexa Intent Model Limitation (Important Context)

Alexa's interaction model is a gatekeeper — it decides which intent to route to BEFORE your Lambda code runs. If it can't match input to an intent, your code never sees the text. This means:
- Users need carrier phrases like "tell me about X", "what is X", "who is X"
- Bare text like "capital of France" won't match anything → falls to FallbackIntent
- FallbackIntent does NOT include the original user text (it's lost)
- This is a fundamental Alexa platform limitation, not a bug in our skill
- The workaround: lots of carrier phrases + dialog slot elicitation for "open skill first, then answer prompt" flow
- `AMAZON.SearchQuery` slot type captures free-form text once the intent is matched

## Next Step: Add Ollama Web Search

The original goal: "Alexa, ask Ollama what happened in the news today" with web search.

**Ollama Web Search API:**
- Endpoint: `POST https://ollama.com/api/web_search`
- Auth: Bearer token (same API key)
- Request: `{"query": "what happened in the news today", "max_results": 5}`
- Response: `{"results": [{"title": "...", "url": "...", "content": "..."}, ...]}`

**Ollama Web Fetch API:**
- Endpoint: `POST https://ollama.com/api/web_fetch`
- Auth: Bearer token
- Request: `{"url": "https://example.com"}`
- Response: `{"title": "...", "content": "...", "links": [...]}`

**Planned approach:**
1. Call Ollama Web Search API first with the user's query
2. Format search results as context text
3. Include context in LLM prompt: "Based on these search results, answer the user's question: [results]\n\nUser question: [query]"
4. Call Ollama Chat API with the augmented prompt
5. Single-pass avoids multi-turn tool calling which would exceed the 8-second timeout
6. Timing budget: search (~1-3s) + LLM call (~3-5s) = ~4-8s — tight but feasible with a fast model

**Considerations:**
- Not all questions need web search ("what is 2+2" doesn't need it)
- Could add a heuristic or fast tiny model to decide if search is needed
- Could make web search opt-in via a specific intent ("Alexa, ask AI chat to search for the latest news")
- Progressive Responses API could send "Let me check..." while searching

## Other Potential Improvements
- Add progressive responses ("Let me think about that...") while waiting for the LLM
- Cache frequent queries (e.g., news summary refreshed every 15 min)
- Add model switching via voice commands ("use the big model")
- Support multiple locales
- Better error messages with CloudWatch logging
