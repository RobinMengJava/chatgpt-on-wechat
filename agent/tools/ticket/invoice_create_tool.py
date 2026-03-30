"""
Invoice creation tool for the Lulu ticket system.

Calls the /fpapi/invoice/create API to submit an invoice creation task.
Goods name and tax rate are fixed: "旅游服务*代租车费" at 1%.

The API is asynchronous — it returns immediately after creating a task.
After calling this tool, query lulu_invoice.fp_task_state to check progress:
  1  → success
  2  → still processing
  3  → waiting for captcha (call invoice_captcha tool)
  -1 → execution error (can resend task)
  -2 → task interrupted (can resend task)

Config keys (in config.json):
    ticket_api_base      - API base URL (default: https://wap.luluroad.com)
    ticket_api_user      - Login username
    ticket_api_password  - Login password

IMPORTANT: This tool triggers an irreversible financial operation.
The agent MUST show the invoice details to the operator and receive
explicit confirmation before calling this tool.
"""

from typing import Any, Dict

from agent.tools.base_tool import BaseTool, ToolResult
from agent.tools.ticket.client import TicketApiClient
from common.log import logger

INVOICE_CREATE_PATH = "/fpapi/invoice/create"

_GOODS_NAME = "*旅游服务*代租车费"
_TAX_RATE = 0.01


class InvoiceCreateTool(BaseTool):
    """Submit an invoice creation task for a lulu_invoice record."""

    name: str = "invoice_create"
    description: str = (
        "Submit an invoice creation task for a given invoice_id. "
        "Goods name and tax rate are fixed (旅游服务*代租车费, 1%). "
        "The operation is asynchronous — after calling this, query lulu_invoice.fp_task_state "
        "to check the result. "
        "ONLY call this after presenting the invoice details to the operator "
        "and receiving explicit confirmation."
    )
    params: dict = {
        "type": "object",
        "properties": {
            "invoice_id": {
                "type": "integer",
                "description": "lulu_invoice.id (bigint)"
            }
        },
        "required": ["invoice_id"]
    }

    def execute(self, args: Dict[str, Any]) -> ToolResult:
        invoice_id = args.get("invoice_id")
        if invoice_id is None:
            return ToolResult.fail("Error: invoice_id is required")

        body = {
            "invoices": [
                {
                    "invoiceId": str(invoice_id),
                    "mark": "",
                    "goods": [
                        {
                            "goodsName": _GOODS_NAME,
                            "taxRate": _TAX_RATE,
                        }
                    ],
                }
            ]
        }

        logger.info(f"[InvoiceCreateTool] Submitting invoice creation task: invoice_id={invoice_id}")

        try:
            client = TicketApiClient()
            result = client.post(INVOICE_CREATE_PATH, body)
        except Exception as e:
            logger.error(f"[InvoiceCreateTool] API call failed: {e}")
            return ToolResult.fail(f"开票请求失败: {str(e)}")

        logger.info(f"[InvoiceCreateTool] API response: {result}")
        success = result.get("success", False)
        msg = result.get("message") or result.get("msg", "")

        if success:
            logger.info(f"[InvoiceCreateTool] Invoice task submitted: invoice_id={invoice_id}")
            return ToolResult.success(
                f"开票任务已提交\n"
                f"发票ID：{invoice_id}\n"
                f"请稍等片刻后查询 lulu_invoice.fp_task_state 确认状态。\n"
                f"状态说明：1=成功，2=执行中，3=等待验证码，-1=执行错误，-2=任务中断"
            )
        else:
            logger.warning(f"[InvoiceCreateTool] Invoice creation failed: {result}")
            return ToolResult.fail(f"开票失败: {msg or str(result)}")
