"""
MySQL Query tool

Allows agents to execute SQL queries against a MySQL database.
Read-only by default (SELECT/SHOW/DESCRIBE/EXPLAIN).
Write operations require `mysql_allow_write: true` in config.json.

Config keys (in config.json):
    mysql_host          - MySQL host (default: localhost)
    mysql_port          - MySQL port (default: 3306)
    mysql_user          - MySQL user
    mysql_password      - MySQL password
    mysql_database      - Default database
    mysql_allow_write   - Allow INSERT/UPDATE/DELETE/DDL (default: false)
    mysql_max_rows      - Max rows returned per query (default: 50)
"""

import json
from typing import Any, Dict

from agent.tools.base_tool import BaseTool, ToolResult
from common.log import logger
from config import conf

# SQL statement types that are considered read-only
_READ_ONLY_PREFIXES = ("select", "show", "describe", "desc", "explain")

# Max rows cap to prevent context overflow
_HARD_MAX_ROWS = 500


class MySQLQuery(BaseTool):
    """Tool for executing SQL queries against a MySQL database"""

    name: str = "mysql_query"
    description: str = (
        "Execute SQL queries against MySQL database. "
        "Use for data lookup, statistics, and business queries. "
        "SELECT/SHOW/DESCRIBE/EXPLAIN are always allowed. "
        "INSERT/UPDATE/DELETE require explicit permission."
    )
    params: dict = {
        "type": "object",
        "properties": {
            "sql": {
                "type": "string",
                "description": "SQL statement to execute"
            },
            "max_rows": {
                "type": "integer",
                "description": "Maximum number of rows to return (default: 50, max: 500)"
            }
        },
        "required": ["sql"]
    }

    def execute(self, args: Dict[str, Any]) -> ToolResult:
        sql = args.get("sql", "").strip()
        if not sql:
            return ToolResult.fail("Error: 'sql' parameter is required")

        max_rows = args.get("max_rows", conf().get("mysql_max_rows", 50))
        max_rows = min(int(max_rows), _HARD_MAX_ROWS)

        # Safety check: block write operations unless explicitly allowed
        if not self._is_read_only(sql):
            allow_write = conf().get("mysql_allow_write", False)
            if not allow_write:
                return ToolResult.fail(
                    "Error: Write operations are disabled. "
                    "Set 'mysql_allow_write: true' in config.json to enable INSERT/UPDATE/DELETE."
                )

        try:
            import pymysql
            import pymysql.cursors
        except ImportError:
            return ToolResult.fail(
                "Error: pymysql is not installed. Run: pip install pymysql"
            )

        conn = None
        try:
            conn = self._connect()
            with conn.cursor() as cursor:
                cursor.execute(sql)

                # For SELECT-like queries, fetch results
                if cursor.description:
                    columns = [col[0] for col in cursor.description]
                    rows = cursor.fetchmany(max_rows)
                    total_fetched = len(rows)

                    result = {
                        "columns": columns,
                        "rows": [list(row) for row in rows],
                        "row_count": total_fetched,
                        "truncated": total_fetched == max_rows
                    }

                    output = self._format_table(columns, result["rows"])
                    if result["truncated"]:
                        output += f"\n(showing first {max_rows} rows, result may be truncated)"

                    return ToolResult.success(output)
                else:
                    # DML: commit and return affected rows
                    conn.commit()
                    return ToolResult.success(
                        f"Query OK, {cursor.rowcount} row(s) affected"
                    )

        except Exception as e:
            logger.error(f"[MySQLQuery] Error executing SQL: {e}")
            return ToolResult.fail(f"Error: {str(e)}")
        finally:
            if conn:
                conn.close()

    def _connect(self):
        """Create a MySQL connection from config"""
        import pymysql

        host = conf().get("mysql_host", "localhost")
        port = int(conf().get("mysql_port", 3306))
        user = conf().get("mysql_user", "")
        password = conf().get("mysql_password", "")
        database = conf().get("mysql_database", "")

        if not user:
            raise ValueError("mysql_user is not configured in config.json")

        return pymysql.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            database=database or None,
            charset="utf8mb4",
            cursorclass=pymysql.cursors.Cursor,
            connect_timeout=10,
        )

    @staticmethod
    def _is_read_only(sql: str) -> bool:
        """Check if SQL is a read-only statement"""
        first_word = sql.lower().split()[0] if sql.split() else ""
        return first_word in _READ_ONLY_PREFIXES

    @staticmethod
    def _format_table(columns: list, rows: list) -> str:
        """Format query results as a plain-text table"""
        if not rows:
            return "Query returned 0 rows"

        # Compute column widths
        widths = [len(str(col)) for col in columns]
        for row in rows:
            for i, val in enumerate(row):
                widths[i] = max(widths[i], len(str(val) if val is not None else "NULL"))

        def fmt_row(values):
            return " | ".join(str(v if v is not None else "NULL").ljust(widths[i]) for i, v in enumerate(values))

        separator = "-+-".join("-" * w for w in widths)
        lines = [fmt_row(columns), separator]
        for row in rows:
            lines.append(fmt_row(row))

        lines.append(f"\n({len(rows)} row{'s' if len(rows) != 1 else ''})")
        return "\n".join(lines)
