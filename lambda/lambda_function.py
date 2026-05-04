# -*- coding: utf-8 -*-

import logging

from ask_sdk_core import utils as ask_utils
from ask_sdk_core.dispatch_components import (
    AbstractExceptionHandler,
    AbstractRequestHandler,
)
from ask_sdk_core.handler_input import HandlerInput
from ask_sdk_core.skill_builder import SkillBuilder
from ask_sdk_model import Response
from llm_intent.llm_client import LLMClient
from llm_intent.utils import CannedResponse, load_config

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

config = load_config()
canned_response = CannedResponse("en-GB")

LLM_URL = config["llm_url"]
LLM_KEY = config["llm_key"]
LLM_MODEL = config["llm_model"]
LLM_SYSTEM_PROMPT = config.get(
    "llm_system_prompt",
    "You are Ollama, a friendly voice assistant speaking through an Alexa device. Follow these rules strictly: Speak as if you're talking to someone in the same room. Use natural, casual language. Keep every answer under 3 sentences. If there's more to say, end with 'Want to know more?' Never use formatting that only makes sense on screen — no bullet points, numbered lists, markdown, headers, or special characters. Never say 'As an AI' or 'I'm an AI' — you're just Ollama. If you're not sure about something, say so honestly rather than making things up. For yes or no questions, start with yes or no, then give a brief explanation. For how-to questions, give the simplest version, not every possible method. Round numbers — say 'about 50' not '47.3'.",
)

WEB_SEARCH_URL = config.get("web_search_url", "https://ollama.com/api/web_search")

llm_client = LLMClient(LLM_URL, LLM_KEY, LLM_MODEL, WEB_SEARCH_URL)

# Keywords that suggest a question needs current/real-time information
NEEDS_SEARCH_KEYWORDS = [
    "latest",
    "news",
    "today",
    "current",
    "recent",
    "now",
    "this week",
    "this month",
    "this year",
    "happening",
    "update",
    "score",
    "weather",
    "price",
    "stock",
    "election",
    "result",
    "live",
    "tonight",
    "yesterday",
    "online",
    "internet",
    "search",
    "look up",
    "look it up",
    "find",
    "check",
    "google",
    "lookup",
]

# Max conversation turns to keep in history (to stay within token limits)
MAX_HISTORY = 10


def get_conversation_history(handler_input):
    """Get conversation history from session attributes."""
    session_attr = handler_input.attributes_manager.session_attributes
    return session_attr.get("conversation_history", [])


def save_to_conversation_history(handler_input, role, content):
    """Add a message to conversation history and trim old ones."""
    session_attr = handler_input.attributes_manager.session_attributes
    history = session_attr.get("conversation_history", [])
    history.append({"role": role, "content": content})
    # Keep only the last MAX_HISTORY messages (plus system prompt)
    if len(history) > MAX_HISTORY:
        history = history[-MAX_HISTORY:]
    session_attr["conversation_history"] = history


def needs_web_search(query: str) -> bool:
    """Check if a query likely needs web search for current information."""
    query_lower = query.lower()
    return any(kw in query_lower for kw in NEEDS_SEARCH_KEYWORDS)


def format_search_results(results: list) -> str:
    """Format search results into context text for the LLM."""
    if not results:
        return ""
    # Limit to 3 results, truncate each to 500 chars for better context
    MAX_RESULTS = 3
    MAX_CONTENT_LEN = 500
    parts = []
    for r in results[:MAX_RESULTS]:
        title = r.get("title", "")
        content = r.get("content", "")[:MAX_CONTENT_LEN]
        if content:
            parts.append(f"{title}: {content}" if title else content)
    return "\n".join(parts)


def ask_ollama(handler_input, user_message, search_context=None):
    """Send a message to Ollama with conversation history and return the response."""
    history = get_conversation_history(handler_input)

    # If we have search results, augment the user message
    if search_context:
        augmented_message = (
            f"IMPORTANT: Use the search results below as your primary source of information. "
            f"They contain current, up-to-date facts that may differ from your training data. "
            f"Always trust the search results over your training data.\n\n"
            f"Search results:\n{search_context}\n\n"
            f"User question: {user_message}"
        )
    else:
        augmented_message = user_message

    # Build the messages list
    messages = []
    for msg in history:
        messages.append({"role": msg["role"], "content": msg["content"]})
    messages.append({"role": "user", "content": augmented_message})

    # Save the user message to history
    save_to_conversation_history(handler_input, "user", user_message)

    # Call Ollama
    response = llm_client.api_request_with_messages(LLM_SYSTEM_PROMPT, messages)

    # Save the assistant response to history
    assistant_message = response.get("message", "")
    if assistant_message:
        save_to_conversation_history(handler_input, "assistant", assistant_message)

    return response


class LaunchRequestHandler(AbstractRequestHandler):
    """Handler for Skill Launch."""

    def can_handle(self, handler_input: HandlerInput) -> bool:
        return ask_utils.is_request_type("LaunchRequest")(handler_input)

    def handle(self, handler_input: HandlerInput) -> Response:
        speak_output = "AI chat ready. What would you like to know?"
        return (
            handler_input.response_builder.speak(speak_output)
            .ask(speak_output)
            .response
        )


class QuestionIntentHandler(AbstractRequestHandler):
    """Main handler for question/answer flow."""

    def can_handle(self, handler_input: HandlerInput) -> bool:
        return ask_utils.is_intent_name("QuestionIntent")(handler_input)

    def handle(self, handler_input: HandlerInput) -> Response:
        slots = handler_input.request_envelope.request.intent.slots

        if slots is None or "searchQuery" not in slots:
            speak_output = "I didn't catch your question. Could you try again?"
            return (
                handler_input.response_builder.speak(speak_output)
                .ask(speak_output)
                .response
            )

        voice_prompt = slots["searchQuery"].value

        if voice_prompt is None:
            speak_output = "I didn't catch that. Could you try again?"
            return (
                handler_input.response_builder.speak(speak_output)
                .ask(speak_output)
                .response
            )

        logger.info("User asks: " + voice_prompt)

        # Check for existing search context from a previous question in this session.
        # Reusing context on follow-ups avoids re-searching (saves time) and preserves
        # context so "tell me more about the crew" stays on topic.
        search_context = handler_input.attributes_manager.session_attributes.get(
            "last_search_context"
        )
        if search_context:
            logger.info("Reusing existing search context for follow-up question")
        else:
            # No existing context — search for fresh results.
            # Always search because carrier phrases are stripped by AMAZON.SearchQuery.
            logger.info("Attempting web search for: " + voice_prompt)
            search_results = llm_client.web_search(voice_prompt)
            logger.info("Search results count: " + str(len(search_results)))
            search_context = format_search_results(search_results)
            if search_context:
                logger.info(
                    "Search context length: " + str(len(search_context)) + " chars"
                )
                handler_input.attributes_manager.session_attributes[
                    "last_search_context"
                ] = search_context
            else:
                logger.info("No search context generated")
                search_context = None

        response = ask_ollama(
            handler_input, voice_prompt, search_context=search_context
        )

        logger.info("LLM Response: " + response.get("message", "")[:200])

        speak_output = response.get("message", canned_response.get_no_message_phrase())
        return (
            handler_input.response_builder.speak(speak_output)
            .ask("Anything else?")
            .response
        )


class YesIntentHandler(AbstractRequestHandler):
    """Handler for 'yes' - treats it as a continuation request."""

    def can_handle(self, handler_input: HandlerInput) -> bool:
        return ask_utils.is_intent_name("AMAZON.YesIntent")(handler_input)

    def handle(self, handler_input: HandlerInput) -> Response:
        logger.info("User says yes - continuing conversation")
        # Re-use search context from the previous question if available
        search_context = handler_input.attributes_manager.session_attributes.get(
            "last_search_context"
        )
        response = ask_ollama(
            handler_input, "Yes, please tell me more.", search_context=search_context
        )

        speak_output = response.get("message", canned_response.get_no_message_phrase())
        return (
            handler_input.response_builder.speak(speak_output)
            .ask("Anything else?")
            .response
        )


class NoIntentHandler(AbstractRequestHandler):
    """Handler for 'no' - ends the session."""

    def can_handle(self, handler_input: HandlerInput) -> bool:
        return ask_utils.is_intent_name("AMAZON.NoIntent")(handler_input)

    def handle(self, handler_input: HandlerInput) -> Response:
        speak_output = "Alright, goodbye!"
        return handler_input.response_builder.speak(speak_output).response


class HelpIntentHandler(AbstractRequestHandler):
    """Handler for Help Intent."""

    def can_handle(self, handler_input: HandlerInput) -> bool:
        return ask_utils.is_intent_name("AMAZON.HelpIntent")(handler_input)

    def handle(self, handler_input: HandlerInput) -> Response:
        speak_output = "You can ask me anything. Try saying tell me about, what is, or who is, followed by your topic."
        return (
            handler_input.response_builder.speak(speak_output)
            .ask(speak_output)
            .response
        )


class CancelOrStopIntentHandler(AbstractRequestHandler):
    """Handler for Cancel and Stop Intent."""

    def can_handle(self, handler_input: HandlerInput) -> bool:
        return ask_utils.is_intent_name("AMAZON.CancelIntent")(
            handler_input
        ) or ask_utils.is_intent_name("AMAZON.StopIntent")(handler_input)

    def handle(self, handler_input: HandlerInput) -> Response:
        speak_output = canned_response.get_goodbye_phrase()
        return handler_input.response_builder.speak(speak_output).response


class FallbackIntentHandler(AbstractRequestHandler):
    """Handler for Fallback Intent."""

    def can_handle(self, handler_input: HandlerInput) -> bool:
        return ask_utils.is_intent_name("AMAZON.FallbackIntent")(handler_input)

    def handle(self, handler_input: HandlerInput) -> Response:
        logger.info("In FallbackIntentHandler")
        speak_output = (
            "I didn't catch that. Try starting with tell me about, what is, or who is."
        )
        reprompt = "What would you like to know?"
        return handler_input.response_builder.speak(speak_output).ask(reprompt).response


class SessionEndedRequestHandler(AbstractRequestHandler):
    """Handler for Session End."""

    def can_handle(self, handler_input: HandlerInput) -> bool:
        return ask_utils.is_request_type("SessionEndedRequest")(handler_input)

    def handle(self, handler_input: HandlerInput) -> Response:
        return handler_input.response_builder.response


class IntentReflectorHandler(AbstractRequestHandler):
    """Reflects the intent name back for debugging."""

    def can_handle(self, handler_input: HandlerInput) -> bool:
        return ask_utils.is_request_type("IntentRequest")(handler_input)

    def handle(self, handler_input: HandlerInput) -> Response:
        intent_name = ask_utils.get_intent_name(handler_input)
        speak_output = "You just triggered " + intent_name + "."
        return (
            handler_input.response_builder.speak(speak_output)
            .ask(canned_response.get_reprompt_phrase())
            .response
        )


class CatchAllExceptionHandler(AbstractExceptionHandler):
    """Generic error handler."""

    def can_handle(self, handler_input: HandlerInput, exception: Exception) -> bool:
        return True

    def handle(self, handler_input: HandlerInput, exception: Exception) -> Response:
        logger.error(exception, exc_info=True)
        speak_output = "Sorry, something went wrong. Please try again."
        return handler_input.response_builder.speak(speak_output).response


sb = SkillBuilder()
sb.add_request_handler(LaunchRequestHandler())
sb.add_request_handler(QuestionIntentHandler())
sb.add_request_handler(YesIntentHandler())
sb.add_request_handler(NoIntentHandler())
sb.add_request_handler(HelpIntentHandler())
sb.add_request_handler(CancelOrStopIntentHandler())
sb.add_request_handler(FallbackIntentHandler())
sb.add_request_handler(SessionEndedRequestHandler())
sb.add_request_handler(IntentReflectorHandler())
sb.add_exception_handler(CatchAllExceptionHandler())

lambda_handler = sb.lambda_handler()
