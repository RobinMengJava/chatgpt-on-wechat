"""
Invoice task resend tool for the Lulu ticket system.

Calls the /fpapi/resend-task API to retry a failed or interrupted
invoice task (creation or red-offset).

Use this when:
  - lulu_invoice.fp_task_state = -1 or -2  (invoice creation failed/interrupted)
  - lulu_invoice.fp_offset_task_state = -1 or -2  (red-offset failed/interrupted)

Config keys (in config.json):
    ticket_api_base      - API base URL (default: https://wap.luluroad.com)
    ticket_api_user      - Login username
    ticket_api_password  - Login password
"""

from typing import Any, Dict

from agent.tools.base_tool import BaseTool, ToolResult
from agent.tools.ticket.client import TicketApiClient
from common.log import logger

RESEND_TASK_PATH = "/fpapi/resend-task"


class InvoiceResendTool(BaseTool):
    """Resend a failed or interrupted invoice task."""

    name: str = "invoice_resend"
    description: str = (
        "Resend a failed or interrupted invoice task. "
        "Use when fp_task_state = -1 or -2 (invoice creation) "
        "or fp_offset_task_state = -1 or -2 (red-offset). "
        "Requires the task_id from lulu_invoice (fp_task_id for creation, "
        "fp_offset_invoice_task_id for red-offset)."
    )
    params: dict = {
        "type": "object",
        "properties": {
            "task_id": {
                "type": "string",
                "description": (
                    "Task ID to resend: use fp_task_id for invoice creation, "
                    "fp_offset_invoice_task_id for red-offset"
                )
            }
        },
        "required": ["task_id"]
    }

    def execute(self, args: Dict[str, Any]) -> ToolResult:
        task_id = args.get("task_id", "").strip()
        if not task_id:
            return ToolResult.fail("Error: task_id is required")

        body = {"taskId": task_id}

        logger.info(f"[InvoiceResendTool] Resending task: task_id={task_id}")

        try:
            client = TicketApiClient()
            result = client.post(RESEND_TASK_PATH, body)
        except Exception as e:
            logger.error(f"[InvoiceResendTool] API call failed: {e}")
            return ToolResult.fail(f"重发任务失败: {str(e)}")

        success = result.get("success", False)
        msg = result.get("message") or result.get("msg", "")

        if success:
            logger.info(f"[InvoiceResendTool] Task resent successfully: task_id={task_id}")
            return ToolResult.success(
                f"任务重发成功\n"
                f"任务ID：{task_id}\n"
                f"请稍等片刻后再次查询发票状态。"
            )
        else:
            logger.warning(f"[InvoiceResendTool] Task resend failed: {result}")
            return ToolResult.fail(f"任务重发失败: {msg or str(result)}")
