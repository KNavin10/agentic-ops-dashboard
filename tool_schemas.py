SENSITIVE = {
    "export_report",
    "email_summary",
}

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "query_submissions",
            "description": (
                "Fetch submissions for one region. "
                "Returns id, region, days_late, and status."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "region": {
                        "type": "string",
                        "description": "Return if the queries region by user exactly matches the enum, dont loosely try to match by guessing or nearby location.",
                        "enum": ["APAC", "EMEA", "AMER"],
                    },
                    "max_rows": {
                        "type": "integer",
                        "description": "Return exactly the number of rows requested by the user. Use maximum only when no number is given by user",
                        "minimum": 1,
                        "maximum": 200,
                    },
                },
                "required": ["region"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_breach_reasons",
            "description": (
                "Find why one submission breached its SLA. "
                "Use this after query_submissions returns an id. "
                "Returns the breach reason and days late."
                "The user can give single id or multiple id's. If no id is provided then dont call any tool, just prompt user for specific id"
                "The input to tool call will be array of integers"
            ),
            "parameters": {
                "type": "object",
                "properties": {                   
                    "ids": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "IDs to look up"
                    }
                },
                "required": ["ids"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "aggregate_by_month",
            "description": (
                "Summarize submission volume and SLA breaches by month "
                "for one region. Use this for trends and charts. "
                "Use query_submissions for individual records."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "region": {
                        "type": "string",
                        "description": "Return if the queries region by user exactly matches the enum, dont loosely try to match by guessing or nearby location.",
                        "enum": ["APAC", "EMEA", "AMER"],
                    },
                },
                "required": ["region"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "export_report",
            "description": (
                "Writes a local CSV file in output folder output/.csv format."
                "Use this tool when user gives approval to export a report for any specific region. Prompt user back if no region given."
                "Use query_submissions for individual records."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "region": {
                        "type": "string",
                        "description": "Return if the queries region by user exactly matches the enum, dont loosely try to match by guessing or nearby location.",
                        "enum": ["APAC", "EMEA", "AMER"],
                    },
                },
                "required": ["region"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "email_summary",
            "description": (
                "Prepare an email summary as a local JSON file in outbox/. "
                "Show the recipient, subject, and body and ask the user for approval "
                "before writing the file. Do not send an email."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "recipient": {
                        "type": "string",
                        "description": "Email address that should receive the summary."
                    },
                    "subject": {
                        "type": "string",
                        "description": "Subject of the email."
                    },
                    "body": {
                        "type": "string",
                        "description": "Summary text for the email."
                    },
                },
                "required": ["recipient", "subject", "body"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_policies",
            "description": (
                "Search regulatory policy documents. Returns passages with source references."
                "Use this for rules, deadlines, and definitions."
                "Do not use it for submission counts; use query_submissions instead."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {
                        "type": "string",
                        "description": "Email address that should receive the summary."
                    },
                    "k": {
                        "type": "integer",
                        "description": "Subject of the email.",
                        "maximum": 8
                    },
                },
                "required": ["question"],
            },
        },
    },
]
