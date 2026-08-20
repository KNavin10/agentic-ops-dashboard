import os
from groq import Groq
from dotenv import load_dotenv
from tool_schemas import TOOLS


load_dotenv()
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

client = Groq(api_key=os.environ["GROQ_API_KEY"])
def ask_model(messages: list[dict]) -> dict:
    response = client.chat.completions.create(
        model="openai/gpt-oss-120b",
        max_tokens=500,
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
