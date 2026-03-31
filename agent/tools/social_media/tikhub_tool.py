"""
TikHub social media tool.

Supports Xiaohongshu (小红书) and Douyin (抖音) via TikHub API.
Requires TIKHUB_API_KEY in environment (auto-synced from config.json: tikhub_api_key).

Actions:
  search     - Keyword search for notes/videos
  user_info  - Get user profile (followers, likes, bio)
  user_posts - Get user's recent posts/videos
  hot_list   - Get platform trending/hot list
  raw        - Call any TikHub endpoint directly (for advanced use)

API docs: https://docs.tikhub.io
Base URL: https://api.tikhub.dev (mainland China, no proxy needed)
"""

import os
import time
from typing import Any, Dict, Optional

import requests

from agent.tools.base_tool import BaseTool, ToolResult
from common.log import logger

BASE_URL = "https://api.tikhub.dev"
DEFAULT_TIMEOUT = 30


class TikHubTool(BaseTool):
    """Access Xiaohongshu and Douyin content via TikHub API."""

    name: str = "tikhub"
    description: str = (
        "访问小红书（xiaohongshu）和抖音（douyin）的内容数据，支持以下操作：\n"
        "- search：关键词搜索笔记/视频\n"
        "- user_info：查询博主基本信息（粉丝数、获赞数、简介）\n"
        "- user_posts：获取博主最近发布的内容\n"
        "- hot_list：获取平台热榜/热搜榜\n"
        "- raw：直接调用任意 TikHub 端点（高级用法，需指定 endpoint 和 params）\n"
        "需要在 config.json 中配置 tikhub_api_key。"
    )
    params: dict = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["search", "user_info", "user_posts", "hot_list", "raw"],
                "description": "操作类型"
            },
            "platform": {
                "type": "string",
                "enum": ["xiaohongshu", "douyin"],
                "description": "平台：xiaohongshu 或 douyin"
            },
            "keyword": {
                "type": "string",
                "description": "[search] 搜索关键词"
            },
            "sort_by": {
                "type": "string",
                "enum": ["hot", "recent"],
                "description": "[search] 排序：hot（最热）或 recent（最新），默认 hot"
            },
            "time_range": {
                "type": "string",
                "enum": ["day", "week", "half_year"],
                "description": "[search] 时间范围：day（一天内）/ week（一周内）/ half_year（半年内），默认 week"
            },
            "user_id": {
                "type": "string",
                "description": "[user_info / user_posts] 用户ID（小红书：sec_user_id；抖音：sec_uid 或 unique_id）"
            },
            "limit": {
                "type": "integer",
                "description": "返回结果数量，默认 5，最多 20"
            },
            "endpoint": {
                "type": "string",
                "description": "[raw] TikHub API 端点路径，如 /api/v1/xiaohongshu/web/fetch_note_comments"
            },
            "params": {
                "type": "object",
                "description": "[raw] 请求参数（query string）"
            },
            "method": {
                "type": "string",
                "enum": ["GET", "POST"],
                "description": "[raw] HTTP 方法，默认 GET"
            }
        },
        "required": ["action", "platform"]
    }

    def __init__(self, config: dict = None):
        self.config = config or {}

    @staticmethod
    def is_available() -> bool:
        return bool(os.environ.get("TIKHUB_API_KEY"))

    def _get_headers(self) -> dict:
        return {
            "Authorization": f"Bearer {os.environ.get('TIKHUB_API_KEY', '')}",
            "Content-Type": "application/json"
        }

    def _check_auth(self) -> Optional[ToolResult]:
        if not self.is_available():
            return ToolResult.fail(
                "未配置 tikhub_api_key，请在 config.json 中添加：\"tikhub_api_key\": \"your_key\""
            )
        return None

    def _request(self, endpoint: str, params: dict = None, method: str = "GET", body: dict = None) -> requests.Response:
        url = f"{BASE_URL}{endpoint}"
        if method == "POST":
            return requests.post(url, headers=self._get_headers(), json=body or {}, timeout=DEFAULT_TIMEOUT)
        return requests.get(url, headers=self._get_headers(), params=params or {}, timeout=DEFAULT_TIMEOUT)

    def _check_response(self, resp: requests.Response) -> Optional[ToolResult]:
        if resp.status_code == 401:
            return ToolResult.fail("TIKHUB_API_KEY 无效，请检查 config.json 中的 tikhub_api_key")
        if resp.status_code == 402:
            return ToolResult.fail("TikHub 余额不足，请前往 https://tikhub.io 充值")
        if resp.status_code != 200:
            return ToolResult.fail(f"TikHub API 返回 HTTP {resp.status_code}")
        return None

    def execute(self, args: Dict[str, Any]) -> ToolResult:
        err = self._check_auth()
        if err:
            return err

        action = args.get("action", "").strip()
        platform = args.get("platform", "").strip()

        if platform not in ("xiaohongshu", "douyin"):
            return ToolResult.fail("platform 必须是 xiaohongshu 或 douyin")

        try:
            if action == "search":
                return self._search(args, platform)
            elif action == "user_info":
                return self._user_info(args, platform)
            elif action == "user_posts":
                return self._user_posts(args, platform)
            elif action == "hot_list":
                return self._hot_list(args, platform)
            elif action == "raw":
                return self._raw(args)
            else:
                return ToolResult.fail(f"未知 action: {action}")
        except requests.Timeout:
            return ToolResult.fail(f"请求超时（{DEFAULT_TIMEOUT}s）")
        except requests.ConnectionError:
            return ToolResult.fail("无法连接到 TikHub API，请检查网络")
        except Exception as e:
            logger.error(f"[TikHubTool] {e}", exc_info=True)
            return ToolResult.fail(str(e))

    # ------------------------------------------------------------------ #
    # action: search
    # ------------------------------------------------------------------ #

    def _search(self, args: dict, platform: str) -> ToolResult:
        keyword = (args.get("keyword") or "").strip()
        if not keyword:
            return ToolResult.fail("search 操作需要提供 keyword 参数")

        limit = min(int(args.get("limit") or 5), 20)
        sort_by = args.get("sort_by") or "hot"
        time_range = args.get("time_range") or "week"

        if platform == "xiaohongshu":
            return self._search_xhs(keyword, limit, sort_by, time_range)
        return self._search_douyin(keyword, limit, sort_by, time_range)

    def _search_xhs(self, keyword: str, limit: int, sort_by: str, time_range: str) -> ToolResult:
        sort_map = {"hot": "popularity_descending", "recent": "time_descending"}
        time_map = {"day": "一天内", "week": "一周内", "half_year": "半年内"}

        resp = self._request("/api/v1/xiaohongshu/app_v2/search_notes", {
            "keyword": keyword,
            "page": 1,
            "sort_type": sort_map.get(sort_by, "popularity_descending"),
            "time_filter": time_map.get(time_range, "一周内"),
            "note_type": "不限",
        })
        err = self._check_response(resp)
        if err:
            return err

        resp_json = resp.json()
        # 结构：resp_json["data"]["data"]["items"]
        outer = resp_json.get("data") or {}
        inner = outer.get("data") or outer
        items = inner.get("items") or inner.get("notes") or inner.get("list") or []

        results = []
        for item in items[:limit]:
            note = item.get("note") or item.get("note_card") or item
            note_id = note.get("id") or note.get("note_id") or ""
            user = note.get("user") or {}
            results.append({
                "title": note.get("title") or note.get("display_title") or note.get("desc") or "（无标题）",
                "author": user.get("nickname") or "未知作者",
                "likes": note.get("liked_count") or 0,
                "collects": note.get("collected_count") or 0,
                "link": f"https://www.xiaohongshu.com/explore/{note_id}" if note_id else "",
            })

        return ToolResult.success({"platform": "xiaohongshu", "action": "search",
                                   "keyword": keyword, "count": len(results), "results": results})

    def _search_douyin(self, keyword: str, limit: int, sort_by: str, time_range: str) -> ToolResult:
        sort_map = {"hot": "1", "recent": "2"}
        time_map = {"day": "1", "week": "7", "half_year": "180"}

        last_error = None
        for attempt in range(3):
            try:
                resp = self._request("/api/v1/douyin/web/fetch_video_search_result", {
                    "keyword": keyword,
                    "sort_type": sort_map.get(sort_by, "1"),
                    "publish_time": time_map.get(time_range, "7"),
                    "count": limit
                })
                err = self._check_response(resp)
                if err:
                    return err

                data = resp.json()
                raw = data.get("data") or {}
                items = (raw.get("data") or raw.get("aweme_list") or raw.get("list") or []) if isinstance(raw, dict) else raw

                results = []
                for item in items[:limit]:
                    aweme = item.get("aweme_info") or item.get("aweme") or item
                    aweme_id = aweme.get("aweme_id") or aweme.get("id") or ""
                    stats = aweme.get("statistics") or {}
                    author = aweme.get("author") or {}
                    results.append({
                        "title": aweme.get("desc") or aweme.get("title") or "（无标题）",
                        "author": author.get("nickname") or "未知作者",
                        "likes": stats.get("digg_count") or stats.get("like_count") or 0,
                        "plays": stats.get("play_count") or stats.get("view_count") or 0,
                        "link": f"https://www.douyin.com/video/{aweme_id}" if aweme_id else "",
                    })

                return ToolResult.success({"platform": "douyin", "action": "search",
                                           "keyword": keyword, "count": len(results), "results": results})
            except Exception as e:
                last_error = str(e)
            if attempt < 2:
                time.sleep(1)

        return ToolResult.fail(f"抖音搜索失败（重试3次）：{last_error}")

    # ------------------------------------------------------------------ #
    # action: user_info
    # ------------------------------------------------------------------ #

    def _user_info(self, args: dict, platform: str) -> ToolResult:
        user_id = (args.get("user_id") or "").strip()
        if not user_id:
            return ToolResult.fail("user_info 操作需要提供 user_id 参数")

        if platform == "xiaohongshu":
            resp = self._request("/api/v1/xiaohongshu/app_v2/get_user_info", {"user_id": user_id})
        else:
            resp = self._request("/api/v1/douyin/web/handler_user_profile_v3", {"sec_uid": user_id})

        err = self._check_response(resp)
        if err:
            return err

        data = resp.json().get("data") or {}
        if platform == "xiaohongshu":
            user = data.get("basicInfo") or data.get("user") or data
            interact = data.get("interactions") or []
            fans = next((i.get("count") for i in interact if i.get("type") == "fans"), 0)
            likes = next((i.get("count") for i in interact if i.get("type") == "liked"), 0)
            result = {
                "platform": "xiaohongshu", "user_id": user_id,
                "nickname": user.get("nickname", ""),
                "desc": user.get("desc", ""),
                "followers": fans,
                "likes": likes,
            }
        else:
            user = data.get("user") or data
            stats = user.get("statistics") or user.get("custom_verify") or {}
            result = {
                "platform": "douyin", "user_id": user_id,
                "nickname": user.get("nickname", ""),
                "signature": user.get("signature", ""),
                "followers": user.get("follower_count") or stats.get("follower_count") or 0,
                "likes": user.get("total_favorited") or 0,
                "video_count": user.get("aweme_count") or 0,
            }

        return ToolResult.success({"action": "user_info", **result})

    # ------------------------------------------------------------------ #
    # action: user_posts
    # ------------------------------------------------------------------ #

    def _user_posts(self, args: dict, platform: str) -> ToolResult:
        user_id = (args.get("user_id") or "").strip()
        if not user_id:
            return ToolResult.fail("user_posts 操作需要提供 user_id 参数")

        limit = min(int(args.get("limit") or 5), 20)

        if platform == "xiaohongshu":
            resp = self._request("/api/v1/xiaohongshu/app_v2/get_user_posted_notes",
                                 {"user_id": user_id, "cursor": ""})
        else:
            resp = self._request("/api/v1/douyin/app/v3/fetch_user_posted_videos",
                                 {"sec_uid": user_id, "count": limit})

        err = self._check_response(resp)
        if err:
            return err

        data = resp.json().get("data") or {}
        items = data.get("notes") or data.get("list") or data.get("aweme_list") or []

        results = []
        if platform == "xiaohongshu":
            for item in items[:limit]:
                note_id = item.get("note_id") or item.get("id", "")
                interact = item.get("interact_info") or {}
                results.append({
                    "title": item.get("display_title") or item.get("title") or item.get("desc") or "（无标题）",
                    "likes": interact.get("liked_count") or 0,
                    "link": f"https://www.xiaohongshu.com/explore/{note_id}" if note_id else "",
                })
        else:
            for item in items[:limit]:
                aweme = item.get("aweme_info") or item
                aweme_id = aweme.get("aweme_id") or ""
                stats = aweme.get("statistics") or {}
                results.append({
                    "title": aweme.get("desc") or "（无标题）",
                    "likes": stats.get("digg_count") or 0,
                    "plays": stats.get("play_count") or 0,
                    "link": f"https://www.douyin.com/video/{aweme_id}" if aweme_id else "",
                })

        return ToolResult.success({"platform": platform, "action": "user_posts",
                                   "user_id": user_id, "count": len(results), "results": results})

    # ------------------------------------------------------------------ #
    # action: hot_list
    # ------------------------------------------------------------------ #

    def _hot_list(self, args: dict, platform: str) -> ToolResult:
        limit = min(int(args.get("limit") or 10), 20)

        if platform == "xiaohongshu":
            resp = self._request("/api/v1/xiaohongshu/web_v2/fetch_hot_list")
        else:
            resp = self._request("/api/v1/douyin/app/v3/fetch_hot_search_list",
                                 {"board_type": "0", "board_sub_type": ""})

        err = self._check_response(resp)
        if err:
            return err

        data = resp.json().get("data") or {}
        items = data.get("items") or data.get("list") or data.get("word_list") or []

        results = []
        for item in items[:limit]:
            if platform == "xiaohongshu":
                results.append({
                    "title": item.get("title") or item.get("word") or "",
                    "heat": item.get("heat_score") or item.get("view_count") or 0,
                })
            else:
                results.append({
                    "title": item.get("word") or item.get("sentence_str") or "",
                    "heat": item.get("hot_value") or item.get("score") or 0,
                })

        return ToolResult.success({"platform": platform, "action": "hot_list",
                                   "count": len(results), "results": results})

    # ------------------------------------------------------------------ #
    # action: raw
    # ------------------------------------------------------------------ #

    def _raw(self, args: dict) -> ToolResult:
        endpoint = (args.get("endpoint") or "").strip()
        if not endpoint:
            return ToolResult.fail("raw 操作需要提供 endpoint 参数，如 /api/v1/xiaohongshu/web/fetch_note_comments")

        params = args.get("params") or {}
        method = (args.get("method") or "GET").upper()

        logger.info(f"[TikHubTool] raw {method} {endpoint} params={params}")

        if method == "POST":
            resp = self._request(endpoint, method="POST", body=params)
        else:
            resp = self._request(endpoint, params=params)

        err = self._check_response(resp)
        if err:
            return err

        return ToolResult.success({"endpoint": endpoint, "data": resp.json()})
