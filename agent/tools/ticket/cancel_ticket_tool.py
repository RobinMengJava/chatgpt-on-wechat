"""
Cancel ticket tool for the Lulu ticket system.

Cancels tickets and changes order status to "refunding" state,
WITHOUT executing an actual money refund. Corresponds to BatchCancelTicketBo.

API: POST /web/bus/luluOrder/cancelTicket
Body: {"ticketIdList": [ticketId1, ticketId2, ...]}
"""

from typing import Any, Dict, List

from agent.tools.base_tool import BaseTool, ToolResult
from agent.tools.ticket.client import TicketApiClient
from common.log import logger

CANCEL_TICKET_API_PATH = "/web/bus/luluOrder/cancelTicket"


class CancelTicketTool(BaseTool):
    """Cancel tickets without executing a real money refund."""

    name: str = "cancel_ticket"
    description: str = (
        "Cancel tickets and change order status to refunding state, WITHOUT actual money refund. "
        "Use when operator wants to cancel tickets only (no real refund). "
        "Requires a list of ticket IDs (lulu_ticket.id)."
    )
    params: dict = {
        "type": "object",
        "properties": {
            "ticket_id_list": {
                "type": "array",
                "description": "List of ticket IDs to cancel (lulu_ticket.id)",
                "items": {"type": "integer"}
            }
        },
        "required": ["ticket_id_list"]
    }

    def execute(self, args: Dict[str, Any]) -> ToolResult:
        ticket_id_list: List[int] = args.get("ticket_id_list", [])

        if not ticket_id_list:
            return ToolResult.fail("Error: ticket_id_list cannot be empty")

        body = {"ticketIdList": [int(tid) for tid in ticket_id_list]}

        logger.info(f"[CancelTicketTool] Cancelling tickets: {ticket_id_list}")

        try:
            client = TicketApiClient()
            result = client.post(CANCEL_TICKET_API_PATH, body)
        except Exception as e:
            logger.error(f"[CancelTicketTool] API call failed: {e}")
            return ToolResult.fail(f"取消车票请求失败: {str(e)}")

        if result.get("success") or result.get("code") == 200:
            msg = result.get("message", "批量取消车票成功")
            logger.info(f"[CancelTicketTool] Success: {msg}")
            return ToolResult.success(f"操作成功：{msg}\n已取消车票ID：{ticket_id_list}")
        else:
            msg = result.get("message", str(result))
            logger.warning(f"[CancelTicketTool] Failed: {result}")
            return ToolResult.fail(f"取消车票失败: {msg}")
