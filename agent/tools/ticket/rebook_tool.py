"""
Rebook execution tool for the Lulu ticket system.

Executes UPDATE operations across lulu_order, lulu_order_itinerary,
lulu_order_attachment, and lulu_ticket tables for order rebooking (改签).

Security constraints (enforced at tool level):
- Only UPDATE is allowed (no INSERT, DELETE, DDL)
- Only whitelisted tables and fields can be modified
- Each table requires a mandatory WHERE key field
- Uses a dedicated write-only MySQL user (mysql_write_user in config.json)

Config keys (in config.json):
    mysql_write_user      - Dedicated write MySQL user (UPDATE-only, must be configured)
    mysql_write_password  - Write user password
    mysql_host            - Reused from read config
    mysql_port            - Reused from read config
    mysql_database        - Reused from read config

IMPORTANT: This tool executes irreversible UPDATE operations.
The agent MUST show the full change summary to the operator and receive
explicit confirmation before calling this tool.
"""

from typing import Any, Dict, List, Tuple

from agent.tools.base_tool import BaseTool, ToolResult
from common.log import logger
from config import conf

# Whitelisted SET fields per table (only改签-related fields allowed)
_ALLOWED_FIELDS: Dict[str, set] = {
    "lulu_order": {
        "departure_time",
        "departure_province", "departure_city", "departure_district",
        "departure_addr", "departure_position", "departure_schedule_station_id",
        "arrive_province", "arrive_city", "arrive_district",
        "arrive_addr", "arrive_position", "arrive_schedule_station_id",
        "schedule_Id",
    },
    "lulu_order_itinerary": {
        "departure_time",
        "departure_province", "departure_city", "departure_district",
        "departure_addr", "departure_position", "departure_schedule_station_id",
        "arrive_province", "arrive_city", "arrive_district",
        "arrive_addr", "arrive_position", "arrive_schedule_station_id",
        "schedule_Id",
    },
    "lulu_order_attachment": {
        "departure_time",
        "departure_province", "departure_city", "departure_district",
        "departure_addr", "departure_position", "departure_schedule_station_id",
        "arrive_province", "arrive_city", "arrive_district",
        "arrive_addr", "arrive_position", "arrive_schedule_station_id",
        "schedule_Id",
    },
    "lulu_ticket": {
        "seat",
    },
}

# Each table requires this key field in WHERE (prevents full-table updates)
_MANDATORY_WHERE: Dict[str, str] = {
    "lulu_order": "order_no",
    "lulu_order_itinerary": "order_no",
    "lulu_order_attachment": "order_no",
    "lulu_ticket": "order_id",
}


class RebookExecuteTool(BaseTool):
    """Execute rebook (改签) UPDATE operations on ticket-related tables."""

    name: str = "rebook_execute"
    description: str = (
        "Execute rebook (改签) UPDATE operations on lulu_order, lulu_order_itinerary, "
        "lulu_order_attachment, and lulu_ticket tables. "
        "Supports changing departure time, departure/arrival location, and seat. "
        "ONLY call this after presenting the full change summary to the operator "
        "and receiving explicit confirmation. "
        "All updates in one call are executed in a single transaction."
    )
    params: dict = {
        "type": "object",
        "properties": {
            "updates": {
                "type": "array",
                "description": "List of UPDATE operations to execute in a single transaction",
                "items": {
                    "type": "object",
                    "properties": {
                        "table": {
                            "type": "string",
                            "enum": list(_ALLOWED_FIELDS.keys()),
                            "description": "Table to update"
                        },
                        "set": {
                            "type": "object",
                            "description": "Fields and new values to set (only whitelisted fields allowed)"
                        },
                        "where": {
                            "type": "object",
                            "description": (
                                "WHERE conditions. "
                                "lulu_order/lulu_order_itinerary/lulu_order_attachment: must include order_no. "
                                "lulu_ticket: must include order_id."
                            )
                        }
                    },
                    "required": ["table", "set", "where"]
                },
                "minItems": 1
            }
        },
        "required": ["updates"]
    }

    def execute(self, args: Dict[str, Any]) -> ToolResult:
        updates: List[dict] = args.get("updates", [])
        if not updates:
            return ToolResult.fail("Error: updates list cannot be empty")

        # Validate all operations before touching the database
        for i, op in enumerate(updates):
            err = self._validate(i, op)
            if err:
                return ToolResult.fail(err)

        try:
            import pymysql
            import pymysql.cursors
        except ImportError:
            return ToolResult.fail("Error: pymysql is not installed. Run: pip install pymysql")

        conn = None
        try:
            conn = self._connect()
            executed = []
            with conn.cursor() as cursor:
                for op in updates:
                    sql, params = self._build_sql(op)
                    logger.info(f"[RebookExecuteTool] SQL: {sql} | params: {params}")
                    cursor.execute(sql, params)
                    executed.append(f"  {op['table']}: {cursor.rowcount} row(s) updated")
            conn.commit()

            summary = "\n".join(executed)
            logger.info(f"[RebookExecuteTool] All updates committed:\n{summary}")
            return ToolResult.success(f"改签成功\n{summary}")

        except Exception as e:
            if conn:
                try:
                    conn.rollback()
                except Exception:
                    pass
            logger.error(f"[RebookExecuteTool] Error, rolled back: {e}")
            return ToolResult.fail(f"改签失败，已回滚: {str(e)}")
        finally:
            if conn:
                conn.close()

    def _validate(self, idx: int, op: dict) -> str:
        """Validate one update operation. Returns error string or empty string."""
        table = op.get("table", "")
        set_fields: dict = op.get("set", {})
        where_fields: dict = op.get("where", {})

        if table not in _ALLOWED_FIELDS:
            return (
                f"Error in updates[{idx}]: table '{table}' is not allowed. "
                f"Allowed: {sorted(_ALLOWED_FIELDS.keys())}"
            )
        if not set_fields:
            return f"Error in updates[{idx}]: 'set' cannot be empty"
        if not where_fields:
            return f"Error in updates[{idx}]: 'where' cannot be empty"

        # Field whitelist check (case-insensitive)
        allowed_lower = {f.lower() for f in _ALLOWED_FIELDS[table]}
        for field in set_fields:
            if field.lower() not in allowed_lower:
                return (
                    f"Error in updates[{idx}]: field '{field}' is not allowed on '{table}'. "
                    f"Allowed fields: {sorted(_ALLOWED_FIELDS[table])}"
                )

        # Mandatory WHERE key
        mandatory = _MANDATORY_WHERE[table]
        where_keys_lower = {k.lower() for k in where_fields}
        if mandatory.lower() not in where_keys_lower:
            return (
                f"Error in updates[{idx}]: WHERE clause for '{table}' must include '{mandatory}'"
            )

        return ""

    @staticmethod
    def _build_sql(op: dict) -> Tuple[str, list]:
        """Build a parameterized UPDATE SQL from an operation dict."""
        table = op["table"]
        set_fields: dict = op["set"]
        where_fields: dict = op["where"]

        set_clause = ", ".join(f"`{k}` = %s" for k in set_fields)
        where_clause = " AND ".join(f"`{k}` = %s" for k in where_fields)
        sql = f"UPDATE `{table}` SET {set_clause} WHERE {where_clause}"
        params = list(set_fields.values()) + list(where_fields.values())
        return sql, params

    def _connect(self):
        """Connect to MySQL using the dedicated write-only user."""
        import pymysql

        host = conf().get("mysql_host", "localhost")
        port = int(conf().get("mysql_port", 3306))
        database = conf().get("mysql_database", "")
        write_user = conf().get("mysql_write_user", "")
        write_password = conf().get("mysql_write_password", "")

        if not write_user:
            raise ValueError(
                "mysql_write_user is not configured in config.json. "
                "Create a dedicated MySQL user with UPDATE-only permission on the ticket tables."
            )

        return pymysql.connect(
            host=host,
            port=port,
            user=write_user,
            password=write_password,
            database=database or None,
            charset="utf8mb4",
            cursorclass=pymysql.cursors.Cursor,
            connect_timeout=10,
            autocommit=False,
        )
