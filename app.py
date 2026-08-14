import os
import json

from groq import Groq
from dotenv import load_dotenv
from tool_schemas import TOOLS
from tools import TOOL_REGISTRY


load_dotenv()

client = Groq(api_key=os.environ["GROQ_API_KEY"])
response = client.chat.completions.create(
    model="openai/gpt-oss-120b",
    max_tokens=500,
    temperature=0,
    tools=TOOLS,
    messages=[
        {
        "role": "system",
        "content": "You are a regulatory operations assistant.",
      },
        # {"role": "user", "content": "Which emirates submissions were late? Show only 5 rows of data"}
        # {"role": "user", "content": "What is the breach reason"}
        {"role": "user", "content": "What is the monthly trend for  APAC?"}
    ],
)
message = response.choices[0].message
if message.tool_calls:
    print("Tool called")
    tool_request = message.tool_calls[0]
    function = TOOL_REGISTRY[tool_request.function.name]
    arguments = json.loads(tool_request.function.arguments)
    result = function(arguments)
    print("LLM resp:",message)
    print("Tool:", tool_request)
    print("Args:",arguments)
    print(result)
else:
    print(message.content)
