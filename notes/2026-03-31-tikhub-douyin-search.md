# TikHub 抖音搜索工具踩坑记录

日期：2026-03-31

## 背景

基于 TikHub API 实现抖音关键词搜索工具（`_search_douyin`），对接新版搜索端点。

## 坑 1：端点和请求方式搞错

**错误做法：** 沿用旧端点 `GET /api/v1/douyin/web/fetch_video_search_result`，params 用 query string 传。

**正确做法：** 新端点 `POST /api/v1/douyin/search/fetch_general_search_v2`，body 用 JSON 传。

```python
# 错误
resp = self._request("/api/v1/douyin/web/fetch_video_search_result", {
    "keyword": keyword, ...
})

# 正确
resp = self._request("/api/v1/douyin/search/fetch_general_search_v2",
                     method="POST", body={...})
```

## 坑 2：响应结构解析错误

**文档描述（不准确）：** `data.data[]` → 搜索结果列表

**实际响应结构：**
```json
{
  "data": {
    "business_data": [
      {
        "data_id": "0",
        "type": 1,
        "data": {
          "type": 1,
          "aweme_info": { ... }
        }
      }
    ]
  }
}
```

正确的取法：
```python
items = raw.get("business_data") or []
aweme = (item.get("data") or {}).get("aweme_info") or {}
```

## 根因

写解析代码之前没有拿到真实响应样本，完全依赖文档描述，而 TikHub 文档对响应结构的描述不够准确。

## 教训

**在写任何 API 响应解析代码之前，必须先拿到一个真实的响应样本。**

方法：
1. 用 `raw` action 直接调一次接口，打印完整响应
2. 或者让用户提供一个真实响应 JSON

不要靠文档猜结构，尤其是多层嵌套的响应，文档描述经常与实际不符。
