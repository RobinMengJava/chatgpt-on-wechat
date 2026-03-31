"""
Generic Ticket API tool for the Lulu ticket system.

Wraps TicketApiClient so the agent can call any endpoint without a dedicated
per-endpoint tool. Authentication (login, token caching, 401 retry) is handled
automatically by the client.

Usage in SKILL.md:
  Call ticket_api tool with:
    method: "post" or "get"
    path:   "/web/bus/luluOrder/someAction"
    body:   { ... }        # for POST
    params: { ... }        # for GET (query string)

Config keys (in config.json):
    ticket_api_base      - API base URL (default: https://wap.luluroad.com)
    ticket_api_user      - Login username
    ticket_api_password  - Login password
"""

from typing import Any, Dict

from agent.tools.base_tool import BaseTool, ToolResult
from agent.tools.ticket.client import TicketApiClient
from common.log import logger


class TicketApiTool(BaseTool):
    """Generic tool for calling any Lulu ticket system API endpoint."""

    name: str = "ticket_api"
    description: str = (
        "Call any Lulu ticket system (luluroad) API endpoint. "
        "Authentication is handled automatically. "
        "Use method='post' with body={...} for POST requests, "
        "or method='get' with params={...} for GET requests."
    )
    params: dict = {
        "type": "object",
        "properties": {
            "method": {
                "type": "string",
                "enum": ["post", "get"],
                "description": "HTTP method: 'post' or 'get'"
            },
            "path": {
                "type": "string",
                "description": "API path, e.g. /web/bus/luluOrder/someAction"
            },
            "body": {
                "type": "object",
                "description": "Request body for POST requests"
            },
            "params": {
                "type": "object",
                "description": "Query string parameters for GET requests"
            }
        },
        "required": ["method", "path"]
    }

    def execute(self, args: Dict[str, Any]) -> ToolResult:
        method = (args.get("method") or "").lower().strip()
        path = (args.get("path") or "").strip()

        if not path:
            return ToolResult.fail("Error: path is required")
        if method not in ("post", "get"):
            return ToolResult.fail("Error: method must be 'post' or 'get'")

        logger.info(f"[TicketApiTool] {method.upper()} {path}")

        try:
            client = TicketApiClient()

            if method == "post":
                body = args.get("body") or {}
                result = client.post(path, body)
            else:
                params = args.get("params") or {}
                result = client.get(path, params)

        except Exception as e:
            logger.error(f"[TicketApiTool] Request failed: {e}")
            return ToolResult.fail(f"请求失败: {str(e)}")

        logger.info(f"[TicketApiTool] Response: {result}")
        return ToolResult.success(result)
