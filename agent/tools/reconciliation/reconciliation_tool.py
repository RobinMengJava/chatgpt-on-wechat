"""
Reconciliation tool for supplier Excel statement verification.

Supports two suppliers:
- 路禾出行 (supplier_1): Order-level reconciliation
  - Detect:    header contains "供应商账号"
  - Match key: 订单ID (col 0) → lulu_order.open_order_no
  - Compare:   票数 → COUNT(lulu_ticket)
               总金额 → lulu_order.actual_amt
               退款金额 → lulu_order.refund_amt
               订单状态 → lulu_order.state

- 路路出行/车盈网 (supplier_2): Ticket-level reconciliation
  - Detect:    header contains "车盈网条码"
  - Match key: 车盈网条码 (col 36) → lulu_ticket.open_ticket_no
  - Compare:   支付金额 (col 61) → lulu_ticket.pay_amt
               车票状态 (col 17) → lulu_ticket.state
"""

import json
import os
from typing import Any, Dict, List, Tuple

from agent.tools.base_tool import BaseTool, ToolResult
from common.log import logger
from config import conf

# ── Supplier detection ───────────────────────────────────────────────────────

_SUPPLIER_1_MARKER = "供应商账号"   # unique column in 路禾出行
_SUPPLIER_2_MARKER = "车盈网条码"   # unique column in 路路出行/车盈网

# ── Supplier 1 column indices (0-based) ─────────────────────────────────────

S1_COL_ORDER_ID   = 0
S1_COL_TICKET_CNT = 5
S1_COL_CHILD_CNT  = 6   # 儿童票数，计入总票数
S1_COL_TOTAL_AMT  = 14
S1_COL_REFUND_AMT = 15
S1_COL_STATUS     = 18

# supplier status → expected lulu_order.state values
S1_STATUS_MAP: Dict[str, set] = {
    "普通":   {100, 200, 210, 260, 300},
    "已取消": {400, 450, 500},
}

# ── Supplier 2 column indices (0-based) ─────────────────────────────────────

S2_COL_STATUS  = 17
S2_COL_PAY_AMT = 61
S2_COL_BARCODE = 36   # 车盈网条码 → lulu_ticket.open_ticket_no
S2_COL_ORDER_NO = 27  # 订单号，用于报告展示
S2_COL_PASSENGER = 32 # 乘车人姓名，用于报告展示

# supplier status labels
S2_VALID_STATUSES  = {"已检", "已售", "混检"}
S2_REFUND_STATUSES = {"已退"}

# expected lulu_ticket.state values
S2_STATUS_MAP: Dict[str, set] = {
    "valid":  {200, 300},
    "refund": {0, 400, 500},
}

# ── Misc ─────────────────────────────────────────────────────────────────────

_BATCH = 200        # DB IN-clause batch size
_AMT_TOLERANCE = 0.01  # float comparison tolerance


class ReconciliationTool(BaseTool):
    """对账供应商Excel账单，逐行比对订单/票据状态和金额是否与系统一致。"""

    name: str = "reconciliation"
    description: str = (
        "对账供应商Excel账单，逐行比对订单状态和金额是否与系统一致。"
        "支持路禾出行（订单级）和路路出行/车盈网（票级）两种账单格式，自动识别。"
        "传入文件路径，返回差异明细和汇总统计。"
    )
    params: dict = {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "供应商Excel账单的本地文件路径（.xlsx 或 .xls）"
            }
        },
        "required": ["file_path"]
    }

    def execute(self, args: Dict[str, Any]) -> ToolResult:
        file_path = args.get("file_path", "").strip()
        if not file_path:
            return ToolResult.fail("Error: file_path is required")

        if not os.path.exists(file_path):
            return ToolResult.fail(f"Error: 文件不存在: {file_path}")

        try:
            rows, headers = self._read_excel(file_path)
        except ImportError:
            return ToolResult.fail(
                "Error: openpyxl 未安装，请执行: pip install openpyxl"
            )
        except Exception as e:
            return ToolResult.fail(f"Error: 读取 Excel 失败: {e}")

        if not rows:
            return ToolResult.fail("Error: Excel 文件为空或无数据行")

        header_set = {str(h).strip() for h in headers if h}
        if _SUPPLIER_1_MARKER in header_set:
            return self._reconcile_supplier1(rows)
        elif _SUPPLIER_2_MARKER in header_set:
            return self._reconcile_supplier2(rows)
        else:
            return ToolResult.fail(
                "无法识别供应商格式，请确认是路禾出行或路路出行/车盈网的账单。"
            )

    # ── Excel reader ─────────────────────────────────────────────────────────

    @staticmethod
    def _read_excel(file_path: str) -> Tuple[List[tuple], tuple]:
        import openpyxl
        wb = openpyxl.load_workbook(file_path, read_only=True, data_only=True)
        ws = wb.active
        all_rows = list(ws.iter_rows(values_only=True))
        wb.close()
        if not all_rows:
            return [], ()
        headers = all_rows[0]
        data_rows = [r for r in all_rows[1:] if any(c is not None for c in r)]
        return data_rows, headers

    # ── DB connection ─────────────────────────────────────────────────────────

    @staticmethod
    def _connect():
        import pymysql
        import pymysql.cursors
        return pymysql.connect(
            host=conf().get("mysql_host", "localhost"),
            port=int(conf().get("mysql_port", 3306)),
            user=conf().get("mysql_user", ""),
            password=conf().get("mysql_password", ""),
            database=conf().get("mysql_database", "") or None,
            charset="utf8mb4",
            cursorclass=pymysql.cursors.DictCursor,
            connect_timeout=10,
        )

    # ── Supplier 1：路禾出行（订单级） ────────────────────────────────────────

    def _reconcile_supplier1(self, rows: List[tuple]) -> ToolResult:
        order_ids = [
            str(r[S1_COL_ORDER_ID]).strip()
            for r in rows
            if r[S1_COL_ORDER_ID]
        ]
        if not order_ids:
            return ToolResult.fail("账单中未找到有效的订单ID")

        db_orders = self._query_orders_batch(order_ids)
        db_ticket_counts = self._query_ticket_counts_batch(order_ids)

        issues = []
        not_found = []
        matched = 0

        for row in rows:
            oid = str(row[S1_COL_ORDER_ID]).strip() if row[S1_COL_ORDER_ID] else None
            if not oid:
                continue

            if oid not in db_orders:
                not_found.append(oid)
                continue

            db = db_orders[oid]
            row_issues = []

            # 票数（成人票 + 儿童票）
            supplier_cnt = int(row[S1_COL_TICKET_CNT] or 0) + int(row[S1_COL_CHILD_CNT] or 0)
            db_cnt = db_ticket_counts.get(oid, 0)
            if supplier_cnt != db_cnt:
                row_issues.append({
                    "field": "票数",
                    "supplier": supplier_cnt,
                    "db": db_cnt,
                })

            # 总金额 → actual_amt
            supplier_amt = float(row[S1_COL_TOTAL_AMT] or 0)
            db_amt = float(db["actual_amt"] or 0)
            if abs(supplier_amt - db_amt) > _AMT_TOLERANCE:
                row_issues.append({
                    "field": "总金额",
                    "supplier": supplier_amt,
                    "db": db_amt,
                })

            # 退款金额 → refund_amt
            supplier_refund = float(row[S1_COL_REFUND_AMT] or 0)
            db_refund = float(db["refund_amt"] or 0)
            if abs(supplier_refund - db_refund) > _AMT_TOLERANCE:
                row_issues.append({
                    "field": "退款金额",
                    "supplier": supplier_refund,
                    "db": db_refund,
                })

            # 订单状态
            supplier_status = str(row[S1_COL_STATUS] or "").strip()
            db_state = int(db["state"] or 0)
            expected = S1_STATUS_MAP.get(supplier_status)
            if expected is not None and db_state not in expected:
                row_issues.append({
                    "field": "订单状态",
                    "supplier": supplier_status,
                    "db": db_state,
                })

            if row_issues:
                issues.append({"order_no": oid, "issues": row_issues})
            else:
                matched += 1

        return self._build_result("路禾出行", len(order_ids), matched, issues, not_found)

    # ── Supplier 2：路路出行/车盈网（票级） ───────────────────────────────────

    def _reconcile_supplier2(self, rows: List[tuple]) -> ToolResult:
        barcodes = [
            str(r[S2_COL_BARCODE]).strip()
            for r in rows
            if r[S2_COL_BARCODE]
        ]
        if not barcodes:
            return ToolResult.fail("账单中未找到有效的车盈网条码")

        db_tickets = self._query_tickets_batch(barcodes)

        issues = []
        not_found = []
        matched = 0

        for row in rows:
            bc = str(row[S2_COL_BARCODE]).strip() if row[S2_COL_BARCODE] else None
            if not bc:
                continue

            if bc not in db_tickets:
                not_found.append(bc)
                continue

            db = db_tickets[bc]
            row_issues = []

            # 支付金额 → pay_amt
            supplier_amt = float(row[S2_COL_PAY_AMT] or 0)
            db_amt = float(db["pay_amt"] or 0)
            if abs(supplier_amt - db_amt) > _AMT_TOLERANCE:
                row_issues.append({
                    "field": "支付金额",
                    "supplier": supplier_amt,
                    "db": db_amt,
                })

            # 车票状态 → lulu_ticket.state
            supplier_status = str(row[S2_COL_STATUS] or "").strip()
            db_state = int(db["state"] or 0)
            if supplier_status in S2_VALID_STATUSES:
                expected = S2_STATUS_MAP["valid"]
            elif supplier_status in S2_REFUND_STATUSES:
                expected = S2_STATUS_MAP["refund"]
            else:
                expected = None  # 未知状态跳过

            if expected is not None and db_state not in expected:
                row_issues.append({
                    "field": "车票状态",
                    "supplier": supplier_status,
                    "db": db_state,
                })

            if row_issues:
                issues.append({
                    "order_no": str(row[S2_COL_ORDER_NO] or bc),
                    "barcode": bc,
                    "passenger": str(row[S2_COL_PASSENGER] or ""),
                    "issues": row_issues,
                })
            else:
                matched += 1

        return self._build_result("路路出行/车盈网", len(barcodes), matched, issues, not_found)

    # ── DB queries ────────────────────────────────────────────────────────────

    def _query_orders_batch(self, order_ids: List[str]) -> Dict[str, dict]:
        result: Dict[str, dict] = {}
        conn = None
        try:
            conn = self._connect()
            with conn.cursor() as cur:
                for i in range(0, len(order_ids), _BATCH):
                    batch = order_ids[i:i + _BATCH]
                    ph = ",".join(["%s"] * len(batch))
                    cur.execute(
                        f"SELECT open_order_no, actual_amt, refund_amt, state "
                        f"FROM lulu_order "
                        f"WHERE open_order_no IN ({ph}) AND del_flag=0",
                        batch,
                    )
                    for row in cur.fetchall():
                        result[row["open_order_no"]] = row
        except Exception as e:
            logger.error(f"[ReconciliationTool] Query orders failed: {e}")
        finally:
            if conn:
                conn.close()
        return result

    def _query_ticket_counts_batch(self, order_ids: List[str]) -> Dict[str, int]:
        result: Dict[str, int] = {}
        conn = None
        try:
            conn = self._connect()
            with conn.cursor() as cur:
                for i in range(0, len(order_ids), _BATCH):
                    batch = order_ids[i:i + _BATCH]
                    ph = ",".join(["%s"] * len(batch))
                    cur.execute(
                        f"SELECT open_order_no, COUNT(*) AS cnt "
                        f"FROM lulu_ticket "
                        f"WHERE open_order_no IN ({ph}) AND del_flag=0 "
                        f"GROUP BY open_order_no",
                        batch,
                    )
                    for row in cur.fetchall():
                        result[row["open_order_no"]] = int(row["cnt"])
        except Exception as e:
            logger.error(f"[ReconciliationTool] Query ticket counts failed: {e}")
        finally:
            if conn:
                conn.close()
        return result

    def _query_tickets_batch(self, barcodes: List[str]) -> Dict[str, dict]:
        result: Dict[str, dict] = {}
        conn = None
        try:
            conn = self._connect()
            with conn.cursor() as cur:
                for i in range(0, len(barcodes), _BATCH):
                    batch = barcodes[i:i + _BATCH]
                    ph = ",".join(["%s"] * len(batch))
                    cur.execute(
                        f"SELECT open_ticket_no, pay_amt, state "
                        f"FROM lulu_ticket "
                        f"WHERE open_ticket_no IN ({ph}) AND del_flag=0",
                        batch,
                    )
                    for row in cur.fetchall():
                        result[row["open_ticket_no"]] = row
        except Exception as e:
            logger.error(f"[ReconciliationTool] Query tickets failed: {e}")
        finally:
            if conn:
                conn.close()
        return result

    # ── Result builder ────────────────────────────────────────────────────────

    @staticmethod
    def _build_result(
        supplier: str,
        total: int,
        matched: int,
        issues: List[dict],
        not_found: List[str],
    ) -> ToolResult:
        result = {
            "supplier": supplier,
            "total": total,
            "matched": matched,
            "issue_count": len(issues),
            "not_found_count": len(not_found),
            "issues": issues,
            "not_found": not_found[:50],  # 防止 token 溢出
        }
        logger.info(
            f"[ReconciliationTool] {supplier}: total={total}, matched={matched}, "
            f"issues={len(issues)}, not_found={len(not_found)}"
        )
        return ToolResult.success(json.dumps(result, ensure_ascii=False, indent=2))
