"""Daily monitor for station data returned by the legacy Guan Zhong API."""

import hashlib
import json
import os
import tempfile
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Callable, Dict, Iterable, Optional

import requests

from agent.tools.base_tool import BaseTool, ToolResult
from common.log import logger
from common.utils import expand_path
from config import conf

from .client import GzOldApiClient, GzOldApiError


IGNORED_LOCATION_FIELDS = {"routeId", "on"}
SNAPSHOT_RETENTION_DAYS = 31
MAX_CHANGE_DETAILS = 20
MAX_MESSAGE_CHARS = 1800


class WecomWebhookNotifier:
    """Send text messages through a WeCom group robot webhook."""

    def __init__(self, webhook_url: str, timeout: int = 10, request_post=None):
        self.webhook_url = webhook_url
        self.timeout = timeout
        self._request_post = request_post or requests.post

    def send(self, content: str) -> None:
        response = self._request_post(
            self.webhook_url,
            json={"msgtype": "text", "text": {"content": content}},
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict) or payload.get("errcode") != 0:
            raise RuntimeError(
                f"企微机器人返回异常: {payload.get('errmsg', 'invalid response')}"
            )


class GzStationMonitorTool(BaseTool):
    """Fetch, normalize, compare and notify on Guan Zhong station changes."""

    name = "gz_station_monitor"
    description = (
        "检查冠中巴士旧版 routes/locations 接口的全量站点资料，"
        "与昨日快照比较，并在变化或失败时通知已配置的企微群。"
    )
    params = {
        "type": "object",
        "properties": {},
        "required": [],
    }

    def __init__(
        self,
        config_provider: Callable[[], dict] = conf,
        client_factory: Callable[..., GzOldApiClient] = GzOldApiClient,
        notifier_factory: Callable[..., WecomWebhookNotifier] = WecomWebhookNotifier,
        now_provider: Callable[[], datetime] = datetime.now,
    ):
        super().__init__()
        self._config_provider = config_provider
        self._client_factory = client_factory
        self._notifier_factory = notifier_factory
        self._now_provider = now_provider

    def execute(self, params: dict) -> ToolResult:
        config = self._config_provider()
        missing = [
            key
            for key in (
                "gz_old_api_base",
                "gz_old_api_username",
                "gz_old_api_password",
                "gz_station_monitor_wecom_webhook",
            )
            if not config.get(key)
        ]
        if missing:
            return ToolResult.fail(f"缺少配置: {', '.join(missing)}")

        current_time = self._now_provider()
        run_date = current_time.date()
        state_dir = self._state_dir(config)
        notifier = self._notifier_factory(
            config["gz_station_monitor_wecom_webhook"]
        )
        client = self._client_factory(
            base_url=config["gz_old_api_base"],
            username=config["gz_old_api_username"],
            password=config["gz_old_api_password"],
            timeout=30,
            retries=1,
            max_workers=4,
        )

        try:
            locations_by_route = client.fetch_all_locations()
            stations = self.canonicalize_stations(locations_by_route)
            if not stations:
                raise GzOldApiError("旧接口未返回任何有效站点")
            snapshot = self._build_snapshot(run_date, current_time, stations)
        except Exception as exc:
            return self._handle_failure(notifier, run_date, f"获取站点数据失败：{exc}")

        today_path = self._snapshot_path(state_dir, run_date)
        try:
            existing_today = self._read_snapshot(today_path)
        except Exception as exc:
            return self._handle_failure(
                notifier, run_date, f"读取今日快照失败：{exc}"
            )
        if existing_today and existing_today.get("content_hash") == snapshot["content_hash"]:
            return ToolResult.success(
                f"冠中站点监控今日已处理，站点数 {snapshot['station_count']}"
            )

        yesterday = run_date - timedelta(days=1)
        yesterday_path = self._snapshot_path(state_dir, yesterday)
        try:
            previous = self._read_snapshot(yesterday_path)
        except Exception as exc:
            return self._handle_failure(
                notifier, run_date, f"读取昨日快照失败：{exc}"
            )

        if previous is None:
            has_history = any(state_dir.glob("????-??-??.json"))
            if has_history:
                try:
                    notifier.send(
                        self._failure_message(
                            run_date,
                            f"缺少昨日基线快照：{yesterday.isoformat()}，"
                            "将以今日数据重建基线",
                        )
                    )
                except Exception as exc:
                    logger.error(
                        "[GzStationMonitor] Failed to send missing-baseline alert: %s",
                        exc,
                    )
                    return ToolResult.fail(f"发送企微告警失败: {exc}")
            try:
                self._commit_snapshot(state_dir, today_path, run_date, snapshot)
            except Exception as exc:
                return self._handle_failure(
                    notifier, run_date, f"保存今日基线失败：{exc}"
                )
            return ToolResult.success(
                f"已建立冠中站点基线，站点数 {snapshot['station_count']}"
            )

        changes = self.diff_stations(
            previous.get("stations", {}),
            snapshot["stations"],
        )
        if not any(changes.values()):
            try:
                self._commit_snapshot(state_dir, today_path, run_date, snapshot)
            except Exception as exc:
                return self._handle_failure(
                    notifier, run_date, f"保存今日快照失败：{exc}"
                )
            return ToolResult.success(
                f"冠中站点资料无变化，站点数 {snapshot['station_count']}"
            )

        message = self._change_message(run_date, changes, previous, snapshot)
        try:
            notifier.send(message)
        except Exception as exc:
            logger.error("[GzStationMonitor] Failed to send change alert: %s", exc)
            return ToolResult.fail(f"发送企微变更通知失败: {exc}")

        try:
            self._commit_snapshot(state_dir, today_path, run_date, snapshot)
        except Exception as exc:
            return self._handle_failure(
                notifier, run_date, f"变更已通知，但保存今日快照失败：{exc}"
            )
        return ToolResult.success(
            "冠中站点资料发生变化，"
            f"新增 {len(changes['added'])}、删除 {len(changes['removed'])}、"
            f"修改 {len(changes['modified'])}"
        )

    @staticmethod
    def canonicalize_stations(
        locations_by_route: Dict[str, Iterable[dict]]
    ) -> Dict[str, dict]:
        """Aggregate every non-route field into a stable unique value list."""
        aggregate = defaultdict(lambda: defaultdict(dict))
        for locations in locations_by_route.values():
            for location in locations:
                station_id = location.get("id")
                if station_id is None or str(station_id).strip() == "":
                    raise GzOldApiError("locations 中存在缺少 id 的站点")
                station_id = str(station_id)
                for field, value in location.items():
                    if field == "id" or field in IGNORED_LOCATION_FIELDS:
                        continue
                    serialized = json.dumps(
                        value,
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    )
                    aggregate[station_id][field][serialized] = value

        stations = {}
        for station_id in sorted(aggregate, key=lambda value: (len(value), value)):
            fields = {}
            for field in sorted(aggregate[station_id]):
                values = aggregate[station_id][field]
                fields[field] = [values[key] for key in sorted(values)]
            stations[station_id] = fields
        return stations

    @staticmethod
    def diff_stations(previous: dict, current: dict) -> dict:
        previous_ids = set(previous)
        current_ids = set(current)
        modified = {}
        for station_id in sorted(
            previous_ids & current_ids, key=lambda value: (len(value), value)
        ):
            if previous[station_id] == current[station_id]:
                continue
            fields = {}
            for field in sorted(set(previous[station_id]) | set(current[station_id])):
                old_value = previous[station_id].get(field)
                new_value = current[station_id].get(field)
                if old_value != new_value:
                    fields[field] = {"old": old_value, "new": new_value}
            modified[station_id] = fields
        return {
            "added": sorted(current_ids - previous_ids, key=lambda x: (len(x), x)),
            "removed": sorted(previous_ids - current_ids, key=lambda x: (len(x), x)),
            "modified": modified,
        }

    @staticmethod
    def _build_snapshot(run_date: date, fetched_at: datetime, stations: dict) -> dict:
        canonical = json.dumps(
            stations,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return {
            "snapshot_date": run_date.isoformat(),
            "fetched_at": fetched_at.isoformat(),
            "station_count": len(stations),
            "content_hash": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
            "stations": stations,
        }

    @staticmethod
    def _state_dir(config: dict) -> Path:
        workspace = expand_path(config.get("agent_workspace", "~/cow"))
        state_dir = Path(workspace) / "state" / "gz_station_monitor"
        state_dir.mkdir(parents=True, exist_ok=True)
        return state_dir

    @staticmethod
    def _snapshot_path(state_dir: Path, snapshot_date: date) -> Path:
        return state_dir / f"{snapshot_date.isoformat()}.json"

    @staticmethod
    def _read_snapshot(path: Path) -> Optional[dict]:
        if not path.exists():
            return None
        try:
            with path.open("r", encoding="utf-8") as file:
                payload = json.load(file)
            if not isinstance(payload, dict) or not isinstance(
                payload.get("stations"), dict
            ):
                raise ValueError("invalid snapshot structure")
            return payload
        except Exception as exc:
            raise GzOldApiError(f"快照读取失败 {path.name}: {exc}") from exc

    @staticmethod
    def _write_snapshot(path: Path, snapshot: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_path = tempfile.mkstemp(
            prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent)
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as file:
                json.dump(snapshot, file, ensure_ascii=False, indent=2)
                file.flush()
                os.fsync(file.fileno())
            os.replace(temp_path, path)
        except Exception:
            try:
                os.unlink(temp_path)
            except OSError:
                pass
            raise

    @classmethod
    def _commit_snapshot(
        cls, state_dir: Path, path: Path, run_date: date, snapshot: dict
    ) -> None:
        cls._write_snapshot(path, snapshot)
        cls._prune_snapshots(state_dir, run_date)

    @staticmethod
    def _prune_snapshots(state_dir: Path, run_date: date) -> None:
        cutoff = run_date - timedelta(days=SNAPSHOT_RETENTION_DAYS - 1)
        for path in state_dir.glob("????-??-??.json"):
            try:
                snapshot_date = date.fromisoformat(path.stem)
            except ValueError:
                continue
            if snapshot_date < cutoff:
                try:
                    path.unlink()
                except OSError as exc:
                    logger.warning(
                        "[GzStationMonitor] Failed to prune snapshot %s: %s",
                        path,
                        exc,
                    )

    def _handle_failure(
        self, notifier: WecomWebhookNotifier, run_date: date, reason: str
    ) -> ToolResult:
        logger.error("[GzStationMonitor] %s", reason)
        try:
            notifier.send(self._failure_message(run_date, reason))
        except Exception as notify_exc:
            logger.error(
                "[GzStationMonitor] Failed to send failure alert: %s", notify_exc
            )
            return ToolResult.fail(f"{reason}；企微告警发送失败：{notify_exc}")
        return ToolResult.fail(reason)

    @staticmethod
    def _failure_message(run_date: date, reason: str) -> str:
        return (
            "【冠中巴士站点监控失败】\n"
            f"检测日期：{run_date.isoformat()}\n"
            f"原因：{reason}"
        )

    def _change_message(
        self, run_date: date, changes: dict, previous: dict, current: dict
    ) -> str:
        lines = [
            "【冠中巴士站点资料变更】",
            f"检测日期：{run_date.isoformat()}",
            (
                f"站点总数：{previous.get('station_count', len(previous['stations']))}"
                f" → {current['station_count']}"
            ),
            (
                f"新增：{len(changes['added'])}，"
                f"删除：{len(changes['removed'])}，"
                f"修改：{len(changes['modified'])}"
            ),
            "",
            "变更明细：",
        ]
        details = []
        for station_id in changes["added"]:
            station = current["stations"][station_id]
            details.append(f"+ [{station_id}] {self._station_name(station)}")
        for station_id in changes["removed"]:
            station = previous["stations"][station_id]
            details.append(f"- [{station_id}] {self._station_name(station)}")
        for station_id, fields in changes["modified"].items():
            station = current["stations"][station_id]
            field_changes = []
            for field, values in list(fields.items())[:3]:
                old_value = self._short_value(values["old"])
                new_value = self._short_value(values["new"])
                field_changes.append(f"{field}: {old_value} → {new_value}")
            if len(fields) > 3:
                field_changes.append(f"另有 {len(fields) - 3} 个字段")
            details.append(
                f"* [{station_id}] {self._station_name(station)}："
                + "；".join(field_changes)
            )

        lines.extend(details[:MAX_CHANGE_DETAILS])
        if len(details) > MAX_CHANGE_DETAILS:
            lines.append(f"……另有 {len(details) - MAX_CHANGE_DETAILS} 个站点变化")
        message = "\n".join(lines)
        if len(message) > MAX_MESSAGE_CHARS:
            message = message[: MAX_MESSAGE_CHARS - 12] + "\n……明细过长已截断"
        return message

    @staticmethod
    def _short_value(value) -> str:
        rendered = json.dumps(value, ensure_ascii=False, sort_keys=True)
        return rendered if len(rendered) <= 60 else rendered[:57] + "..."

    @staticmethod
    def _station_name(station: dict) -> str:
        for field in ("name", "cname", "ename"):
            values = station.get(field)
            if values:
                return str(values[0])
        return "未命名站点"
