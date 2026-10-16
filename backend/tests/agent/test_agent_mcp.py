import asyncio
import json

from fastmcp import Client

from app.agent.mcp_server import mcp
from app.agent.tools import LOG_FILE


def test_mcp_lists_tools_and_searches_guidance():
    async def scenario():
        async with Client(mcp) as client:
            names = {tool.name for tool in await client.list_tools()}
            result = await client.call_tool("search_guidance", {"query": "horečka po chemoterapii", "lang": "cs"})
            context = await client.call_tool("get_patient_context", {"patient_id": "ONC-014", "as_of": "2026-09-09T20:00:00+02:00"})
            contact = await client.call_tool("get_contact", {"level": 4, "at": "2026-09-09T21:52:00+02:00"})
            return names, result, context, contact

    names, result, context, contact = asyncio.run(scenario())
    assert {"get_patient_context", "get_recent_checkins", "get_trend", "search_guidance", "get_contact", "ask_followup", "escalate"} <= names
    hits = json.loads(result.content[0].text)
    assert hits and all(hit["cite"].startswith("guide:") for hit in hits)
    patient = json.loads(context.content[0].text)
    assert "Ludmila" not in json.dumps(patient, ensure_ascii=False) and patient["palliative"] is True
    assert "724 590 848" in json.loads(contact.content[0].text)["contact"]
    assert '"tool": "search_guidance"' in LOG_FILE.read_text(encoding="utf-8")
