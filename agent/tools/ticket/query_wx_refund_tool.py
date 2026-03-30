"""
Query WeChat refund tool.

Queries real-time WeChat refund status by order number (order_no).
Since users typically provide an order number rather than a refund number,
this tool first looks up lulu_refund by order_no to get out_refund_no,
then queries the WeChat API for each refund record found.

API: GET /web/bus/luluOrder/queryWxRefund?outRefundNo={out_refund_no}

Config keys (in config.json):
    mysql_host / mysql_port / mysql_user / mysql_password / mysql_database
    ticket_api_base / ticket_api_user / ticket_api_password
"""

from typing import Any, Dict

from agent.tools.base_tool import BaseTool, ToolResult
from agent.tools.ticket.client import TicketApiClient
from common.log import logger
from config import conf

QUERY_WX_REFUND_PATH = "/web/bus/luluOrder/queryWxRefund"


def _get_refund_nos(order_no: str) -> list:
    """Query lulu_refund table and return list of (refund_no, refund_amt) tuples."""
    import pymysql

    conn = pymysql.connect(
        host=conf().get("mysql_host", "localhost"),
        port=int(conf().get("mysql_port", 3306)),
        user=conf().get("mysql_user", ""),
        password=conf().get("mysql_password", ""),
        database=conf().get("mysql_database") or None,
        charset="utf8mb4",
        connect_timeout=10,
    )
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT refund_no, refund_amt, state, create_time "
                "FROM lulu_refund "
                "WHERE order_no = %s AND del_flag = 0 "
                "ORDER BY create_time DESC",
                (order_no,)
            )
            return cursor.fetchall()
    finally:
        conn.close()


class QueryWxRefundTool(BaseTool):
    """Query WeChat refund status by order number."""

    name: str = "query_wx_refund"
    description: str = (
        "Query real-time WeChat refund status by order number (订单号). "
        "Automatically looks up the refund record(s) for the given order, "
        "then queries WeChat for each refund's current status. "
        "Use this to verify whether a refund was processed by WeChat."
    )
    params: dict = {
        "type": "object",
        "properties": {
            "order_no": {
                "type": "string",
                "description": "订单号 (lulu_order.order_no / lulu_refund.order_no)"
            }
        },
        "required": ["order_no"]
    }

    def execute(self, args: Dict[str, Any]) -> ToolResult:
        order_no = args.get("order_no", "").strip()
        if not order_no:
            return ToolResult.fail("Error: order_no is required")

        logger.info(f"[QueryWxRefundTool] Looking up refund records for order: {order_no}")

        try:
            rows = _get_refund_nos(order_no)
        except ImportError:
            return ToolResult.fail("pymysql is not installed. Run: pip install pymysql")
        except Exception as e:
            logger.error(f"[QueryWxRefundTool] DB query failed: {e}")
            return ToolResult.fail(f"查询退款记录失败: {str(e)}")

        if not rows:
            return ToolResult.fail(f"未找到订单 {order_no} 的退款记录")

        client = TicketApiClient()
        results = []

        for refund_no, refund_amt, state, create_time in rows:
            if not refund_no:
                results.append(f"退款记录（金额 {refund_amt}）：退款单号为空，无法查询")
                continue

            logger.info(f"[QueryWxRefundTool] Querying WeChat refund: out_refund_no={refund_no}")
            try:
                result = client.get(QUERY_WX_REFUND_PATH, params={"outRefundNo": refund_no})
                logger.info(f"[QueryWxRefundTool] Response for {refund_no}: {result}")

                if result.get("success") or result.get("code") == 200:
                    data = result.get("result")
                    results.append(f"退款单号 {refund_no}（金额 {refund_amt}）：\n{data}")
                else:
                    msg = result.get("message") or result.get("msg", str(result))
                    results.append(f"退款单号 {refund_no}（金额 {refund_amt}）查询失败: {msg}")
            except Exception as e:
                logger.error(f"[QueryWxRefundTool] API call failed for {refund_no}: {e}")
                results.append(f"退款单号 {refund_no} 请求失败: {str(e)}")

        return ToolResult.success("\n\n".join(results))
