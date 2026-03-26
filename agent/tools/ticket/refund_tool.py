"""
Refund execution tool for the Lulu ticket system.

Calls the customAmtRefund API to execute a refund with custom amounts.
Requires ticket_api_user and ticket_api_password in config.json.

IMPORTANT: This tool executes an irreversible financial operation.
The agent MUST present a refund summary to the operator and receive
explicit confirmation before calling this tool.
"""

from typing import Any, Dict

from agent.tools.base_tool import BaseTool, ToolResult
from agent.tools.ticket.client import TicketApiClient
from common.log import logger

REFUND_API_PATH = "/web/bus/luluOrder/customAmtRefund"


class RefundExecuteTool(BaseTool):
    """Execute a refund for a Lulu ticket order."""

    name: str = "refund_execute"
    description: str = (
        "Execute a refund for a ticket order. "
        "ONLY call this after presenting the full refund breakdown to the operator "
        "and receiving explicit confirmation. "
        "Requires order_id, total_refund_amt, total_fee, and ticket_list."
    )
    params: dict = {
        "type": "object",
        "properties": {
            "order_id": {
                "type": "integer",
                "description": "Order ID (lulu_order.id, bigint)"
            },
            "total_refund_amt": {
                "type": "number",
                "description": "Total refund amount (after deducting fee)"
            },
            "total_fee": {
                "type": "number",
                "description": "Total service fee amount"
            },
            "ticket_list": {
                "type": "array",
                "description": "List of tickets to refund",
                "items": {
                    "type": "object",
                    "properties": {
                        "ticket_id": {
                            "type": "integer",
                            "description": "Ticket ID (lulu_ticket.id)"
                        },
                        "refund_amt": {
                            "type": "number",
                            "description": "Refund amount for this ticket"
                        },
                        "fee": {
                            "type": "number",
                            "description": "Service fee for this ticket"
                        }
                    },
                    "required": ["ticket_id", "refund_amt", "fee"]
                }
            }
        },
        "required": ["order_id", "total_refund_amt", "total_fee", "ticket_list"]
    }

    def execute(self, args: Dict[str, Any]) -> ToolResult:
        order_id = args.get("order_id")
        total_refund_amt = args.get("total_refund_amt")
        total_fee = args.get("total_fee")
        ticket_list = args.get("ticket_list", [])

        # Basic validation
        if order_id is None:
            return ToolResult.fail("Error: order_id is required")
        if total_refund_amt is None or total_fee is None:
            return ToolResult.fail("Error: total_refund_amt and total_fee are required")
        if not ticket_list:
            return ToolResult.fail("Error: ticket_list cannot be empty")

        # Build request body matching the API spec
        body = {
            "orderId": int(order_id),
            "totalRefundAmt": float(total_refund_amt),
            "totalFee": float(total_fee),
            "ticketList": [
                {
                    "ticketId": int(t["ticket_id"]),
                    "refundAmt": float(t["refund_amt"]),
                    "fee": float(t["fee"]),
                }
                for t in ticket_list
            ],
        }

        logger.info(
            f"[RefundExecuteTool] Executing refund: order_id={order_id}, "
            f"total_refund={total_refund_amt}, total_fee={total_fee}, "
            f"tickets={len(ticket_list)}"
        )

        try:
            client = TicketApiClient()
            result = client.post(REFUND_API_PATH, body)
        except Exception as e:
            logger.error(f"[RefundExecuteTool] API call failed: {e}")
            return ToolResult.fail(f"退款请求失败: {str(e)}")

        # API returns {"msg":"退款成功"} on success; anything else is failure
        msg = result.get("msg", "")
        if msg == "退款成功":
            logger.info(f"[RefundExecuteTool] Refund succeeded for order {order_id}")
            return ToolResult.success(
                f"退款成功\n"
                f"订单ID：{order_id}\n"
                f"退款金额：{total_refund_amt} 元\n"
                f"手续费：{total_fee} 元"
            )
        else:
            logger.warning(f"[RefundExecuteTool] Refund failed: {result}")
            return ToolResult.fail(f"退款失败: {msg or str(result)}")
