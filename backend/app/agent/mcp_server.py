from fastmcp import FastMCP

from app.agent import tools
from app.agent.vectors import search_similar_checkins

mcp = FastMCP("meddi-navigator")

for function in (tools.get_patient_context, tools.get_recent_checkins, tools.get_trend, tools.search_guidance,
                 tools.get_contact, tools.ask_followup, tools.escalate):
    mcp.tool(function)


@mcp.tool
def find_similar_checkins(query: str, patient_id: str) -> list[dict]:
    """Similar past check-in messages of other patients (wording examples only, never used for the level)."""
    return search_similar_checkins(query, exclude_patient_id=patient_id)


if __name__ == "__main__":
    mcp.run(transport="streamable-http", host="127.0.0.1", port=8101)
