import os

from dotenv import load_dotenv
from groq import Groq

from tool_schemas import TOOLS

load_dotenv()

_client = None


def _get_client():
    global _client

    if _client is None:
        _client = Groq(api_key=os.environ["GROQ_API_KEY"])

    return _client


SYSTEM = {
    "role": "system",
    "content": """You are a regulatory operations assistant.
                Use query_submissions for live database values.
                Use aggregate_by_month for trends.
                Use search_policies for policy rules, deadlines, and definitions.
                Answer document-based claims only from retrieved passages.
                Cite every policy claim using the returned source and chunk ID.
                If retrieval returns no relevant evidence, answer clearly with INSUFFICIENT_DATA.
                Do not invent a policy answer from general model knowledge.""",
}


def ask_model(messages: list[dict], client=None, model_fn=None) -> dict:
    if model_fn is None:
        active_client = client if client is not None else _get_client()
        model_fn = active_client.chat.completions.create

    response = model_fn(
        model="openai/gpt-oss-120b",
        max_completion_tokens=500,
        temperature=0,
        tools=TOOLS,
        messages=[SYSTEM, *messages],
    )

    message = response.choices[0].message
    tool_calls = message.tool_calls or []
    resp = {
        "text": message.content or "",
        "tool_calls": tool_calls,
        "input_tokens": response.usage.prompt_tokens,
        "output_tokens": response.usage.completion_tokens,
    }
    return resp
