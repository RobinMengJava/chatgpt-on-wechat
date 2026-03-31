---
name: social-digest
description: 搜索小红书、抖音上的内容并按需推送。支持：关键词搜索内容、查看博主最新动态和数据、获取平台热榜、设置定时推送到群。当用户提到"帮我搜"、"最近有没有"、"热门内容"、"博主"、"每天推送"、"定时发送"等社媒相关需求时触发。
---

# 社媒内容搜索与推送

使用 `tikhub` 工具访问小红书和抖音数据。工具支持五种 action，根据用户意图选择对应场景。

---

## 场景一：关键词搜索

**触发**：用户想了解某个话题在社媒上的内容。

```
tikhub(action="search", platform="xiaohongshu", keyword="...", sort_by="hot", time_range="week", limit=5)
tikhub(action="search", platform="douyin", keyword="...", sort_by="hot", time_range="week", limit=5)
```

参数说明：
- `sort_by`：hot（最热）/ recent（最新）
- `time_range`：day（一天）/ week（一周）/ half_year（半年）

**结果格式**：
```
📱 社媒搜索｜{关键词}

🔴 小红书
① {标题} — {作者} 👍{点赞} ⭐{收藏}
   {链接}

🎵 抖音
① {标题} — {作者} 👍{点赞} ▶{播放}
   {链接}
```

---

## 场景二：博主追踪

**触发**：用户想看某个博主最近发了什么，或想了解博主的粉丝、数据。

**第一步：获取博主基本信息**
```
tikhub(action="user_info", platform="xiaohongshu", user_id="{sec_user_id}")
tikhub(action="user_info", platform="douyin", user_id="{sec_uid}")
```

**第二步：获取博主最新内容**
```
tikhub(action="user_posts", platform="xiaohongshu", user_id="{sec_user_id}", limit=5)
tikhub(action="user_posts", platform="douyin", user_id="{sec_uid}", limit=5)
```

> 注意：user_id 是平台内部 ID（非昵称）。若用户提供的是昵称或主页链接，先告知用户需要 sec_user_id / sec_uid，或用 `search` 搜索用户名找到对应 ID。

**结果格式**：
```
👤 {昵称}｜{平台}
粉丝：{数量}  获赞：{数量}
简介：{desc}

最新内容：
① {标题} 👍{点赞}  {链接}
② ...
```

---

## 场景三：热榜查询

**触发**：用户想知道今天平台上什么最火。

```
tikhub(action="hot_list", platform="xiaohongshu", limit=10)
tikhub(action="hot_list", platform="douyin", limit=10)
```

**结果格式**：
```
🔥 今日热榜｜{平台}｜{日期}

① {标题}  热度：{heat}
② ...
```

---

## 场景四：定时推送

**触发**：用户说"每天X点帮我推送..."、"设置定时发送"等。

**步骤**：
1. 理解用户想推送的内容（关键词 / 博主 / 热榜）
2. 确认推送时间，未指定默认每天 09:00
3. 调用 `scheduler` 工具创建任务：

```
scheduler(
    action="create",
    name="每日社媒热点",
    ai_task="搜索小红书和抖音上关于'{用户指定话题}'的最热内容（近一周，各取5条），汇总后发送到本群",
    schedule_type="cron",
    schedule_value="0 9 * * *"
)
```

- `ai_task` 里直接写清楚用户的具体需求，不要写泛化描述
- 发送目标自动取当前群，无需手动指定

---

## 场景五：高级用法（raw）

当上述四个场景不满足需求时，可直接调用 TikHub 的任意端点。

**常用端点参考**：

| 功能 | 端点 |
|------|------|
| 小红书笔记评论 | `/api/v1/xiaohongshu/web/fetch_note_comments` |
| 小红书用户粉丝列表 | `/api/v1/xiaohongshu/web/fetch_follower_list` |
| 小红书热门商品 | `/api/v1/xiaohongshu/web/fetch_hot_products` |
| 抖音视频详情 | `/api/v1/douyin/web/fetch_one_video` |
| 抖音视频评论 | `/api/v1/douyin/web/fetch_comment` |
| 抖音视频榜单 | `/api/v1/douyin/billboard/fetch_video_billboard` |
| 抖音音乐榜单 | `/api/v1/douyin/billboard/fetch_music_billboard` |
| 抖音城市热榜 | `/api/v1/douyin/billboard/fetch_city_hot_list` |
| 抖音挑战热榜 | `/api/v1/douyin/billboard/fetch_hot_challenge_list` |
| 星图达人基本信息 | `/api/v1/douyin/xingtu/get_kol_base_info_v1` |
| 星图达人粉丝画像 | `/api/v1/douyin/xingtu/get_kol_fans_portrait_v1` |
| 星图达人涨粉趋势 | `/api/v1/douyin/xingtu/get_kol_daily_fans_v1` |

**调用示例**：
```
tikhub(
    action="raw",
    platform="douyin",
    endpoint="/api/v1/douyin/billboard/fetch_video_billboard",
    params={"count": 10}
)
```

完整端点文档：https://docs.tikhub.io

---

## 注意事项

- 若工具报错"未配置 tikhub_api_key"，提示用户在 `config.json` 中添加 `"tikhub_api_key": "your_key"`
- 每次调用消耗约 $0.001，50次免费额度可用于初期测试
- 抖音搜索接口偶发失败，工具内部已自动重试3次
