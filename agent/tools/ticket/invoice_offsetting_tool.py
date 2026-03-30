"""
Invoice offsetting (红冲) tool for the Lulu ticket system.

Calls the /fpapi/invoice/offsetting API to submit a red-offset task
for an already-issued invoice.

The API is asynchronous — it returns immediately after creating a task.
After calling this tool, query lulu_invoice.fp_offset_task_state to check progress:
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
The agent MUST verify the invoice has been successfully issued
(fp_create_invoice_status = 1) and receive explicit operator confirmation
before calling this tool.
"""

from typing import Any, Dict

from agent.tools.base_tool import BaseTool, ToolResult
from agent.tools.ticket.client import TicketApiClient
from common.log import logger

INVOICE_OFFSETTING_PATH = "/fpapi/invoice/offsetting"


class InvoiceOffsettingTool(BaseTool):
    """Submit a red-offset (红冲) task for an issued invoice."""

    name: str = "invoice_offsetting"
    description: str = (
        "Submit a red-offset (红冲) task for an already-issued invoice. "
        "The invoice must have fp_create_invoice_status = 1 (successfully issued). "
        "The operation is asynchronous — after calling this, query lulu_invoice.fp_offset_task_state "
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

        body = {"invoiceId": int(invoice_id)}

        logger.info(f"[InvoiceOffsettingTool] Submitting red-offset task: invoice_id={invoice_id}")

        try:
            client = TicketApiClient()
            result = client.post(INVOICE_OFFSETTING_PATH, body)
        except Exception as e:
            logger.error(f"[InvoiceOffsettingTool] API call failed: {e}")
            return ToolResult.fail(f"红冲请求失败: {str(e)}")

        success = result.get("success", False)
        msg = result.get("message") or result.get("msg", "")

        if success:
            logger.info(f"[InvoiceOffsettingTool] Red-offset task submitted: invoice_id={invoice_id}")
            return ToolResult.success(
                f"红冲任务已提交\n"
                f"发票ID：{invoice_id}\n"
                f"请稍等片刻后查询 lulu_invoice.fp_offset_task_state 确认状态。\n"
                f"状态说明：1=成功，2=执行中，3=等待验证码，-1=执行错误，-2=任务中断"
            )
        else:
            logger.warning(f"[InvoiceOffsettingTool] Red-offset failed: {result}")
            return ToolResult.fail(f"红冲失败: {msg or str(result)}")
