from mcp.server.fastmcp import FastMCP

import tools

mcp = FastMCP("reg-ops")


@mcp.tool()
def query_submissions(region: str, max_rows: int = 50) -> dict:
    """Fetch regulatory submissions for APAC, EMEA, or AMER."""
    return tools.query_submissions({
        "region": region,
        "max_rows": max_rows,
    })


@mcp.tool()
def search_policies(question: str, k: int = 4) -> dict:
    """Search regulatory policies and return passages with sources."""
    return tools.search_policies({
        "question": question,
        "k": k,
    })


if __name__ == "__main__":
    mcp.run()