"""
Query WeChat payment order tool.

Queries real-time WeChat Pay order status by merchant order number (out_trade_no).

API: GET /web/bus/luluOrder/queryWxOrder?outTradeNo={out_trade_no}
"""

from typing import Any, Dict

from agent.tools.base_tool import BaseTool, ToolResult
from agent.tools.ticket.client import TicketApiClient
from common.log import logger

QUERY_WX_ORDER_PATH = "/web/bus/luluOrder/queryWxOrder"


class QueryWxOrderTool(BaseTool):
    """Query WeChat Pay order status by merchant order number."""

    name: str = "query_wx_order"
    description: str = (
        "Query real-time WeChat Pay order status by merchant order number (out_trade_no / 商户订单号). "
        "The out_trade_no is lulu_order.order_no (our system's order number). "
        "Use this to verify whether a payment was actually received by WeChat, "
        "or to check the current trade state of an order."
    )
    params: dict = {
        "type": "object",
        "properties": {
            "out_trade_no": {
                "type": "string",
                "description": "商户订单号，即 lulu_order.order_no，如 GZ2026030623363200126"
            }
        },
        "required": ["out_trade_no"]
    }

    def execute(self, args: Dict[str, Any]) -> ToolResult:
        out_trade_no = args.get("out_trade_no", "").strip()
        if not out_trade_no:
            return ToolResult.fail("Error: out_trade_no is required")

        logger.info(f"[QueryWxOrderTool] Querying WeChat order: out_trade_no={out_trade_no}")

        try:
            client = TicketApiClient()
            result = client.get(QUERY_WX_ORDER_PATH, params={"outTradeNo": out_trade_no})
        except Exception as e:
            logger.error(f"[QueryWxOrderTool] API call failed: {e}")
            return ToolResult.fail(f"查询微信支付单失败: {str(e)}")

        logger.info(f"[QueryWxOrderTool] Response: {result}")

        if result.get("success") or result.get("code") == 200:
            data = result.get("result")
            return ToolResult.success(f"微信支付单查询结果：\n{data}")
        else:
            msg = result.get("message") or result.get("msg", str(result))
            return ToolResult.fail(f"查询失败: {msg}")
