import tempfile
import unittest
from unittest.mock import MagicMock, patch

from agent.tools.base_tool import ToolResult
from agent.tools.scheduler.integration import (
    _ensure_gz_station_monitor_task,
    _execute_tool_call,
)
from agent.tools.scheduler.scheduler_tool import SchedulerTool
from agent.tools.scheduler.task_store import TaskStore
from bridge.context import Context, ContextType


class SchedulerDirectToolTaskTest(unittest.TestCase):
    def test_monitor_task_is_auto_registered_once_config_is_complete(self):
        config = {
            "gz_old_api_base": "https://example.test/",
            "gz_old_api_username": "user",
            "gz_old_api_password": "password",
            "gz_station_monitor_wecom_webhook": "https://wecom.test/webhook",
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            store = TaskStore(f"{temp_dir}/tasks.json")

            self.assertTrue(_ensure_gz_station_monitor_task(store, config))
            self.assertFalse(_ensure_gz_station_monitor_task(store, config))

            tasks = store.list_tasks()
            self.assertEqual(len(tasks), 1)
            self.assertEqual(tasks[0]["id"], "gz-station-monitor")
            self.assertEqual(tasks[0]["schedule"]["expression"], "0 9 * * *")
            self.assertFalse(tasks[0]["action"]["deliver_result"])

    def test_monitor_task_is_not_registered_without_secrets(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = TaskStore(f"{temp_dir}/tasks.json")
            self.assertFalse(_ensure_gz_station_monitor_task(store, {}))
            self.assertEqual(store.list_tasks(), [])

    def test_create_persists_direct_tool_action(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            scheduler = SchedulerTool(config={"channel_type": "web"})
            scheduler.task_store = TaskStore(f"{temp_dir}/tasks.json")
            context = Context(ContextType.TEXT, "create task", kwargs={})
            context["receiver"] = "session-1"
            context["isgroup"] = False
            scheduler.current_context = context

            result = scheduler.execute(
                {
                    "action": "create",
                    "name": "冠中巴士旧版站点每日监控",
                    "tool_name": "gz_station_monitor",
                    "tool_params": {},
                    "deliver_result": False,
                    "schedule_type": "cron",
                    "schedule_value": "0 9 * * *",
                }
            )

            self.assertEqual(result.status, "success")
            tasks = scheduler.task_store.list_tasks()
            self.assertEqual(len(tasks), 1)
            action = tasks[0]["action"]
            self.assertEqual(action["type"], "tool_call")
            self.assertEqual(action["tool_name"], "gz_station_monitor")
            self.assertFalse(action["deliver_result"])
            self.assertEqual(tasks[0]["schedule"]["expression"], "0 9 * * *")

    def test_create_requires_exactly_one_action_type(self):
        scheduler = SchedulerTool()
        scheduler.task_store = MagicMock()
        scheduler.current_context = Context(ContextType.TEXT, "", kwargs={})

        result = scheduler.execute(
            {
                "action": "create",
                "name": "invalid",
                "message": "hello",
                "tool_name": "gz_station_monitor",
                "schedule_type": "cron",
                "schedule_value": "0 9 * * *",
            }
        )

        self.assertEqual(result.status, "success")
        self.assertIn("必须且只能提供一个", result.result)
        scheduler.task_store.add_task.assert_not_called()

    def test_delivery_disabled_executes_tool_without_creating_channel(self):
        fake_tool = MagicMock()
        fake_tool.execute.return_value = ToolResult.success("completed")
        task = {
            "id": "gz-test",
            "action": {
                "type": "tool_call",
                "tool_name": "gz_station_monitor",
                "tool_params": {},
                "deliver_result": False,
                "channel_type": "web",
            },
        }

        with patch(
            "agent.tools.tool_manager.ToolManager.create_tool",
            return_value=fake_tool,
        ), patch("channel.channel_factory.create_channel") as create_channel:
            _execute_tool_call(task, agent_bridge=None)

        fake_tool.execute.assert_called_once_with({})
        create_channel.assert_not_called()


if __name__ == "__main__":
    unittest.main()
