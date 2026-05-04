import json
import logging
import urllib.error
import urllib.request

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Timeout for API calls (seconds) - must stay well under Alexa's 8-second limit
API_TIMEOUT = 7
# Timeout for web search calls (seconds) - search is fast (~1s), keep tight
SEARCH_TIMEOUT = 3


class LLMClient:
    def __init__(self, url: str, api_key: str, model: str, search_url: str = ""):
        self.url = url
        self.api_key = api_key
        self.model = model
        self.search_url = search_url

    def api_request(self, prompt: str, question: str) -> dict:
        """Send a request to the Ollama Cloud API and return the response."""
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": prompt},
                {"role": "user", "content": question},
            ],
            "stream": False,
        }

        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self.url,
            data=data,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=API_TIMEOUT) as resp:
                body = json.loads(resp.read().decode("utf-8"))
                # Ollama native API returns: {"message": {"role": "assistant", "content": "..."}}
                content = body.get("message", {}).get("content", "")
                if not content:
                    # Fallback: try OpenAI-compatible response format
                    choices = body.get("choices", [])
                    if choices:
                        content = choices[0].get("message", {}).get("content", "")
                return {"message": content}

        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8", errors="replace")
            logger.error(f"Ollama API HTTP error {e.code}: {error_body}")
            return {
                "message": "Sorry, the AI service returned an error. Please try again."
            }
        except urllib.error.URLError as e:
            logger.error(f"Ollama API connection error: {e.reason}")
            return {
                "message": "Sorry, I couldn't reach the AI service. Please try again."
            }
        except Exception as e:
            logger.error(f"Unexpected error calling Ollama API: {e}")
            return {"message": "Sorry, something went wrong. Please try again."}

    def webhook_request(self, question: str, context: dict) -> dict:
        """Send a request to a webhook endpoint (unchanged from original)."""
        local_payload = {
            "token": self.api_key,
            "question": question,
        }

        payload = {**context, **local_payload}
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self.url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=API_TIMEOUT) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            logger.error(f"Webhook request failed: {e}")
            return {"message": "Sorry, I encountered an error processing your request."}

    def _api_headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def web_search(self, query: str, max_results: int = 5) -> list:
        """Search the web via Ollama API. Returns list of result dicts or empty list on failure."""
        if not self.search_url:
            logger.info("No search_url configured, skipping web search")
            return []

        payload = {
            "query": query,
            "max_results": max_results,
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self.search_url,
            data=data,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=SEARCH_TIMEOUT) as resp:
                body = json.loads(resp.read().decode("utf-8"))
                results = body.get("results", [])
                logger.info(f"Web search returned {len(results)} results for: {query}")
                return results
        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8", errors="replace")
            logger.error(f"Web search HTTP error {e.code}: {error_body}")
            return []
        except urllib.error.URLError as e:
            logger.error(f"Web search connection error: {e.reason}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error during web search: {e}")
            return []

    def api_request_with_messages(self, prompt: str, messages: list) -> dict:
        """Send a request with full conversation history to the Ollama Cloud API."""
        # Build the full messages list with system prompt
        full_messages = [{"role": "system", "content": prompt}] + messages

        payload = {
            "model": self.model,
            "messages": full_messages,
            "stream": False,
        }

        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self.url,
            data=data,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=API_TIMEOUT) as resp:
                body = json.loads(resp.read().decode("utf-8"))
                content = body.get("message", {}).get("content", "")
                if not content:
                    choices = body.get("choices", [])
                    if choices:
                        content = choices[0].get("message", {}).get("content", "")
                return {"message": content}

        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8", errors="replace")
            logger.error(f"Ollama API HTTP error {e.code}: {error_body}")
            return {
                "message": "Sorry, the AI service returned an error. Please try again."
            }
        except urllib.error.URLError as e:
            logger.error(f"Ollama API connection error: {e.reason}")
            return {
                "message": "Sorry, I couldn't reach the AI service. Please try again."
            }
        except Exception as e:
            logger.error(f"Unexpected error calling Ollama API: {e}")
            return {"message": "Sorry, something went wrong. Please try again."}
