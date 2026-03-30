"""
Invoice captcha submission tool for the Lulu ticket system.

Calls the /fpapi/submit-captcha API to upload a verification code
required by the FP platform during invoice creation or red-offset.

Use this when lulu_invoice.fp_task_state = 3 (invoice creation)
or lulu_invoice.fp_offset_task_state = 3 (red-offset).

Config keys (in config.json):
    ticket_api_base      - API base URL (default: https://wap.luluroad.com)
    ticket_api_user      - Login username
    ticket_api_password  - Login password
"""

from typing import Any, Dict

from agent.tools.base_tool import BaseTool, ToolResult
from agent.tools.ticket.client import TicketApiClient
from common.log import logger

SUBMIT_CAPTCHA_PATH = "/fpapi/submit-captcha"


class InvoiceCaptchaTool(BaseTool):
    """Submit a verification code for an in-progress invoice or red-offset task."""

    name: str = "invoice_captcha"
    description: str = (
        "Submit a verification code for an invoice task that requires captcha. "
        "Use when fp_task_state = 3 (invoice creation) or fp_offset_task_state = 3 (red-offset). "
        "Requires the task_id from lulu_invoice (fp_task_id for creation, "
        "fp_offset_invoice_task_id for red-offset) and the captcha code provided by the operator."
    )
    params: dict = {
        "type": "object",
        "properties": {
            "task_id": {
                "type": "string",
                "description": (
                    "Task ID: use fp_task_id for invoice creation, "
                    "fp_offset_invoice_task_id for red-offset"
                )
            },
            "captcha": {
                "type": "string",
                "description": "Verification code provided by the operator"
            }
        },
        "required": ["task_id", "captcha"]
    }

    def execute(self, args: Dict[str, Any]) -> ToolResult:
        task_id = args.get("task_id", "").strip()
        captcha = args.get("captcha", "").strip()

        if not task_id:
            return ToolResult.fail("Error: task_id is required")
        if not captcha:
            return ToolResult.fail("Error: captcha is required")

        body = {"taskId": task_id, "captcha": captcha}

        logger.info(f"[InvoiceCaptchaTool] Submitting captcha for task_id={task_id}")

        try:
            client = TicketApiClient()
            result = client.post(SUBMIT_CAPTCHA_PATH, body)
        except Exception as e:
            logger.error(f"[InvoiceCaptchaTool] API call failed: {e}")
            return ToolResult.fail(f"验证码提交失败: {str(e)}")

        success = result.get("success", False)
        msg = result.get("message") or result.get("msg", "")

        if success:
            logger.info(f"[InvoiceCaptchaTool] Captcha submitted successfully: task_id={task_id}")
            return ToolResult.success(
                f"验证码提交成功\n"
                f"任务ID：{task_id}\n"
                f"请稍等片刻后再次查询发票状态。"
            )
        else:
            logger.warning(f"[InvoiceCaptchaTool] Captcha submission failed: {result}")
            return ToolResult.fail(f"验证码提交失败: {msg or str(result)}")
