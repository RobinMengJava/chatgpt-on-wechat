import hashlib
import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from agent.tools.gz_station_monitor.client import (
    GzOldApiClient,
    GzOldApiError,
)
from agent.tools.gz_station_monitor.monitor import GzStationMonitorTool
from config import drag_sensitive


class FakeClient:
    def __init__(self, locations=None, error=None, **kwargs):
        self.locations = locations or {}
        self.error = error

    def fetch_all_locations(self):
        if self.error:
            raise self.error
        return self.locations


class RecordingNotifier:
    def __init__(self, messages, error=None, *args, **kwargs):
        self.messages = messages
        self.error = error

    def send(self, content):
        if self.error:
            raise self.error
        self.messages.append(content)


def station(station_id, name="站点", address="地址", route_id="1", on="true"):
    return {
        "id": station_id,
        "name": name,
        "address": address,
        "lat": "22.1",
        "lon": "113.1",
        "routeId": route_id,
        "on": on,
    }


class GzOldApiClientTest(unittest.TestCase):
    def test_signed_url_uses_legacy_signature_and_parameter_name(self):
        client = GzOldApiClient(
            "https://example.test/base/",
            "user",
            "password",
        )
        url = client.build_url("locations", {"routeId": "84"}, timestamp=123456)
        query = parse_qs(urlparse(url).query)
        expected = hashlib.md5(
            b"userName=user&psw=password&timestamp=123456"
        ).hexdigest()

        self.assertEqual(query["userName"], ["user"])
        self.assertEqual(query["timestamp"], ["123456"])
        self.assertEqual(query["signture"], [expected])
        self.assertEqual(query["format"], ["json"])
        self.assertEqual(query["routeId"], ["84"])

    def test_route_ids_are_expanded_and_deduplicated(self):
        routes = [
            {"routeId": "1", "routeIdStr": "1,2,10"},
            {"routeId": "2", "routeIdStr": "2,3,"},
            {"routeId": "4", "routeIdStr": ""},
        ]
        self.assertEqual(
            GzOldApiClient.expand_route_ids(routes),
            ["1", "2", "3", "4", "10"],
        )

    def test_missing_locations_is_a_complete_dataset_failure(self):
        class Response:
            def raise_for_status(self):
                return None

            def json(self):
                return {}

        client = GzOldApiClient(
            "https://example.test/",
            "user",
            "password",
            retries=0,
            request_get=lambda *args, **kwargs: Response(),
        )
        with self.assertRaises(GzOldApiError):
            client.fetch_locations("84")

    def test_request_retries_once(self):
        calls = []

        class Response:
            def raise_for_status(self):
                return None

            def json(self):
                return {"route": [{"routeId": "1"}]}

        def request_get(*args, **kwargs):
            calls.append(1)
            if len(calls) == 1:
                raise RuntimeError("temporary network error")
            return Response()

        client = GzOldApiClient(
            "https://example.test/",
            "user",
            "password",
            retries=1,
            request_get=request_get,
        )
        self.assertEqual(len(client.fetch_routes()), 1)
        self.assertEqual(len(calls), 2)


class GzStationMonitorTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.messages = []
        self.config = {
            "agent_workspace": self.temp_dir.name,
            "gz_old_api_base": "https://example.test/",
            "gz_old_api_username": "user",
            "gz_old_api_password": "password",
            "gz_station_monitor_wecom_webhook": "https://wecom.test/webhook",
        }

    def tearDown(self):
        self.temp_dir.cleanup()

    def make_tool(self, when, locations=None, client_error=None, notify_error=None):
        messages = self.messages

        def client_factory(**kwargs):
            return FakeClient(locations=locations, error=client_error)

        def notifier_factory(*args, **kwargs):
            return RecordingNotifier(messages, error=notify_error)

        return GzStationMonitorTool(
            config_provider=lambda: self.config,
            client_factory=client_factory,
            notifier_factory=notifier_factory,
            now_provider=lambda: when,
        )

    def snapshot_path(self, day):
        return (
            Path(self.temp_dir.name)
            / "state"
            / "gz_station_monitor"
            / f"{day}.json"
        )

    def test_first_run_creates_silent_baseline(self):
        tool = self.make_tool(
            datetime(2026, 7, 23, 9),
            {"1": [station("1", "福田站")]},
        )
        result = tool.execute({})

        self.assertEqual(result.status, "success")
        self.assertEqual(self.messages, [])
        self.assertTrue(self.snapshot_path("2026-07-23").exists())

    def test_route_order_duplicates_and_relationship_fields_are_ignored(self):
        day_one = {
            "1": [
                station("1", "福田站", "地址A", "1", "true"),
                station("1", "福田站", "地址B", "1", "true"),
            ],
            "2": [station("2", "机场站", "机场", "2", "false")],
        }
        self.make_tool(datetime(2026, 7, 23, 9), day_one).execute({})

        day_two = {
            "99": [
                station("2", "机场站", "机场", "99", "true"),
                station("1", "福田站", "地址B", "99", "false"),
                station("1", "福田站", "地址A", "99", "false"),
                station("1", "福田站", "地址A", "99", "false"),
            ]
        }
        result = self.make_tool(datetime(2026, 7, 24, 9), day_two).execute({})

        self.assertEqual(result.status, "success")
        self.assertIn("无变化", result.result)
        self.assertEqual(self.messages, [])

    def test_added_removed_and_modified_stations_notify_once(self):
        original = {
            "1": [
                station("1", "旧站", "旧地址"),
                station("2", "删除站", "地址"),
            ]
        }
        self.make_tool(datetime(2026, 7, 23, 9), original).execute({})
        changed = {
            "1": [
                station("1", "旧站", "新地址"),
                station("3", "新增站", "地址"),
            ]
        }

        first = self.make_tool(datetime(2026, 7, 24, 9), changed).execute({})
        second = self.make_tool(datetime(2026, 7, 24, 9, 5), changed).execute({})

        self.assertEqual(first.status, "success")
        self.assertEqual(second.status, "success")
        self.assertEqual(len(self.messages), 1)
        message = self.messages[0]
        self.assertIn("新增：1", message)
        self.assertIn("删除：1", message)
        self.assertIn("修改：1", message)
        self.assertIn("address", message)

    def test_api_failure_alerts_without_writing_today_snapshot(self):
        baseline = {"1": [station("1")]}
        self.make_tool(datetime(2026, 7, 23, 9), baseline).execute({})

        result = self.make_tool(
            datetime(2026, 7, 24, 9),
            client_error=GzOldApiError("route 84 timeout"),
        ).execute({})

        self.assertEqual(result.status, "error")
        self.assertEqual(len(self.messages), 1)
        self.assertIn("监控失败", self.messages[0])
        self.assertFalse(self.snapshot_path("2026-07-24").exists())
        self.assertTrue(self.snapshot_path("2026-07-23").exists())

    def test_missing_yesterday_baseline_alerts_and_saves_new_baseline(self):
        initial = {"1": [station("1")]}
        self.make_tool(datetime(2026, 7, 21, 9), initial).execute({})

        result = self.make_tool(datetime(2026, 7, 23, 9), initial).execute({})

        self.assertEqual(result.status, "success")
        self.assertEqual(len(self.messages), 1)
        self.assertIn("缺少昨日基线", self.messages[0])
        self.assertTrue(self.snapshot_path("2026-07-23").exists())

    def test_notification_failure_does_not_commit_changed_snapshot(self):
        original = {"1": [station("1", address="旧")]}
        self.make_tool(datetime(2026, 7, 23, 9), original).execute({})
        changed = {"1": [station("1", address="新")]}

        result = self.make_tool(
            datetime(2026, 7, 24, 9),
            changed,
            notify_error=RuntimeError("webhook unavailable"),
        ).execute({})

        self.assertEqual(result.status, "error")
        self.assertFalse(self.snapshot_path("2026-07-24").exists())

    def test_canonicalization_preserves_all_field_variants(self):
        normalized = GzStationMonitorTool.canonicalize_stations(
            {
                "1": [
                    station("1", address="地址B"),
                    station("1", address="地址A"),
                ],
                "2": [station("1", address="地址A", route_id="2", on="false")],
            }
        )

        self.assertEqual(normalized["1"]["address"], ["地址A", "地址B"])
        self.assertNotIn("routeId", normalized["1"])
        self.assertNotIn("on", normalized["1"])

    def test_snapshot_retention_keeps_latest_31_days(self):
        state_dir = Path(self.temp_dir.name)
        old_path = state_dir / "2026-06-22.json"
        cutoff_path = state_dir / "2026-06-23.json"
        current_path = state_dir / "2026-07-23.json"
        for path in (old_path, cutoff_path, current_path):
            path.write_text("{}", encoding="utf-8")

        GzStationMonitorTool._prune_snapshots(
            state_dir,
            date(2026, 7, 23),
        )

        self.assertFalse(old_path.exists())
        self.assertTrue(cutoff_path.exists())
        self.assertTrue(current_path.exists())

    def test_new_secrets_are_masked_in_config_logs(self):
        masked = drag_sensitive(
            {
                "gz_old_api_password": "top-secret-password",
                "gz_station_monitor_wecom_webhook": "https://wecom.test/secret",
            }
        )
        self.assertNotEqual(masked["gz_old_api_password"], "top-secret-password")
        self.assertNotEqual(
            masked["gz_station_monitor_wecom_webhook"],
            "https://wecom.test/secret",
        )


if __name__ == "__main__":
    unittest.main()
