"""Client for the legacy Guan Zhong bus routes/locations API."""

import hashlib
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, Dict, Iterable, List, Optional
from urllib.parse import urlencode

import requests


class GzOldApiError(RuntimeError):
    """Raised when the legacy Guan Zhong API cannot provide a complete dataset."""


class GzOldApiClient:
    """Fetch all station records from the legacy routes + locations API."""

    def __init__(
        self,
        base_url: str,
        username: str,
        password: str,
        timeout: int = 30,
        retries: int = 1,
        max_workers: int = 4,
        request_get: Optional[Callable] = None,
    ):
        if not base_url or not username or not password:
            raise ValueError("base_url, username and password are required")
        self.base_url = base_url.rstrip("/") + "/"
        self.username = username
        self.password = password
        self.timeout = timeout
        self.retries = retries
        self.max_workers = max(1, min(int(max_workers), 4))
        self._request_get = request_get or requests.get

    def build_url(
        self,
        method: str,
        params: Optional[Dict[str, object]] = None,
        timestamp: Optional[int] = None,
    ) -> str:
        """Build a signed legacy API URL."""
        timestamp = int(timestamp if timestamp is not None else time.time() * 1000)
        raw = (
            f"userName={self.username}"
            f"&psw={self.password}"
            f"&timestamp={timestamp}"
        )
        signature = hashlib.md5(raw.encode("utf-8")).hexdigest()
        query = {
            "userName": self.username,
            "timestamp": timestamp,
            # The upstream API intentionally uses this misspelled parameter.
            "signture": signature,
            "format": "json",
        }
        if params:
            query.update(params)
        return f"{self.base_url}{method}?{urlencode(query)}"

    def request(self, method: str, params: Optional[Dict[str, object]] = None) -> dict:
        """Call one API method, retrying once by default."""
        last_error = None
        for attempt in range(self.retries + 1):
            try:
                response = self._request_get(
                    self.build_url(method, params),
                    headers={"Accept": "*/*", "Connection": "keep-alive"},
                    timeout=self.timeout,
                )
                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload, dict):
                    raise GzOldApiError(f"{method} returned a non-object response")
                return payload
            except Exception as exc:
                last_error = exc
                if attempt < self.retries:
                    continue
        raise GzOldApiError(f"{method} request failed: {last_error}") from last_error

    @staticmethod
    def expand_route_ids(routes: Iterable[dict]) -> List[str]:
        """Expand routeIdStr values and return stable, unique route IDs."""
        route_ids = set()
        for route in routes:
            if not isinstance(route, dict):
                raise GzOldApiError("routes contains a non-object item")
            raw_ids = route.get("routeIdStr") or route.get("routeId") or ""
            for route_id in str(raw_ids).split(","):
                route_id = route_id.strip()
                if route_id:
                    route_ids.add(route_id)
        return sorted(route_ids, key=lambda value: (len(value), value))

    def fetch_routes(self) -> List[dict]:
        payload = self.request("routes")
        routes = payload.get("route")
        if not isinstance(routes, list):
            raise GzOldApiError("routes response is missing the route list")
        if not routes:
            raise GzOldApiError("routes response contains no routes")
        return routes

    def fetch_locations(self, route_id: str) -> List[dict]:
        payload = self.request("locations", {"routeId": route_id})
        if "locations" not in payload:
            raise GzOldApiError(
                f"locations response for route {route_id} is missing locations"
            )
        locations = payload.get("locations")
        if not isinstance(locations, list):
            raise GzOldApiError(
                f"locations response for route {route_id} is not a list"
            )
        if any(not isinstance(item, dict) for item in locations):
            raise GzOldApiError(
                f"locations response for route {route_id} contains a non-object item"
            )
        return locations

    def fetch_all_locations(self) -> Dict[str, List[dict]]:
        """Fetch a complete route-to-locations mapping."""
        route_ids = self.expand_route_ids(self.fetch_routes())
        if not route_ids:
            raise GzOldApiError("routes response contains no usable route IDs")

        result = {}
        failures = []
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {
                executor.submit(self.fetch_locations, route_id): route_id
                for route_id in route_ids
            }
            for future in as_completed(futures):
                route_id = futures[future]
                try:
                    result[route_id] = future.result()
                except Exception as exc:
                    failures.append(f"{route_id}: {exc}")

        if failures:
            preview = "; ".join(sorted(failures)[:5])
            suffix = f"; 另有 {len(failures) - 5} 个失败" if len(failures) > 5 else ""
            raise GzOldApiError(f"部分线路站点获取失败: {preview}{suffix}")
        return {route_id: result[route_id] for route_id in route_ids}
