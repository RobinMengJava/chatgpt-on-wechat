---
name: query-schedule
description: 查询班次信息，包括国内班次和跨境班次。当用户询问"有没有班次"、"最晚几点"、"几点的车"、"经过哪些站"、"还有余票吗"、"哪班车"等时触发。
---

# 查询班次

## 第一步：判断是国内还是跨境班次

- **国内班次**：出发地和目的地均在中国大陆，例如"广州到深圳"、"珠海到湛江"
- **跨境班次**：涉及香港、澳门，例如"广州到香港"、"珠海到澳门"，目前跨境供应商固定为 companyId=2

如果无法判断，询问用户："请问是国内班次还是跨境班次（涉及港澳）？"

---

## 【国内班次查询】

### 第一步：确认出发地、目的地、日期

从用户描述中提取：
- 出发省市（boardingProvince、boardingCity）
- 目的省市（terminalProvince、terminalCity）
- 班次日期（scheduleDate，格式 yyyy-MM-dd）

**处理相对日期：**
- "今天" → 当天日期
- "明天" → 明天日期
- "后天" → 后天日期

如果信息不完整，询问用户补充。

> 省份写全称，如"广东省"；市写全称，如"广州市"、"深圳市"。
> 如果用户只说城市名（如"广州"），自动补全为省份+市，例如 province="广东省", city="广州市"。

### 第二步：调用国内班次接口

调用 `ticket_api` tool：

```
method: post
path: /wap/schedule/getDateSchedule
body: {
  "scheduleDate": "{yyyy-MM-dd}",
  "boardingProvince": "{出发省份}",
  "boardingCity": "{出发城市}",
  "boardingDistrict": "{出发区县，可选}",
  "terminalProvince": "{目的省份}",
  "terminalCity": "{目的城市}",
  "terminalDistrict": "{目的区县，可选}"
}
```

### 第三步：处理结果

**无班次：** 告知"该日期 {出发城市}→{目的城市} 暂无可用班次"

**有班次：** 根据用户的具体问题筛选和展示：

| 用户问题 | 展示策略 |
|---------|---------|
| 最晚的班次 | 取 earliestDepartureTime 最大的一条 |
| 最早的班次 | 取 earliestDepartureTime 最小的一条 |
| X点的班次 | 筛选 earliestDepartureTime 接近该时间的班次 |
| 是否经过XX站 | 检查 boardingStations 或 terminalStations 的 stationName |
| 还有余票吗 | 显示 canSaleSeat，isScheduleAvailable=false 表示不可售 |
| 列出所有班次 | 按 earliestDepartureTime 排序全部展示 |

**班次展示格式：**

```
{出发城市} → {目的城市}  {scheduleDate}

班次 {序号}：{earliestDepartureTime} 出发
  余票：{canSaleSeat} 座  {isScheduleAvailable ? "可购" : "⚠️ 不可购"}
  票价：{bottomPreferPrice > 0 ? bottomPreferPrice+"元起（优惠价）" : bottomPrice+"元起"}
  上车点：
    - {stationName} {departureTime} {isStationAvailable ? "" : "（已截止）"}
  下车点：
    - {stationName}
```

如果只有一条班次，直接展示详情不加序号。

---

## 【跨境班次查询】

### 第一步：确认出发站点、目的站点、日期

从用户描述中提取出发地名称和目的地名称，以及日期。

### 第二步：查询站点 ID

根据站点名称从数据库查询 `open_station_id`（跨境供应商 company_id=2 的站点）：

```sql
SELECT open_station_id, name, city, district
FROM lulu_station
WHERE company_id = 2
  AND del_flag = 0
  AND name LIKE '%{站点关键词}%'
```

- 如果查到多个匹配站点，展示给用户选择
- 如果查不到，告知用户"未找到匹配的站点，请确认站点名称"

### 第三步：调用跨境班次接口

调用 `ticket_api` tool：

```
method: post
path: /wap/schedule/getCrossBorderDateSchedule
body: {
  "scheduleDate": "{yyyy-MM-dd}",
  "originId": "{出发站点 open_station_id}",
  "originName": "{出发站点名称}",
  "destinationId": "{目的站点 open_station_id}",
  "destinationName": "{目的站点名称}",
  "isRoundTrip": false,
  "companyId": 2
}
```

### 第四步：处理结果

**无班次：** 告知"该日期 {出发站点}→{目的站点} 暂无可用跨境班次"

**有班次：** 同样根据用户问题筛选展示：

```
{出发站点} → {目的站点}  {scheduleDate}  [跨境]

班次 {序号}：{departureTime} 出发
  票价：
    - {pricesType}：{pricesStr} 元
  上车点：{boardingStations[].stationName}
  下车点：{terminalStations[].stationName}
```

---

## 【查询可用城市】

当用户询问"从哪里可以出发"、"有哪些出发城市"时：

调用 `ticket_api` tool：
```
method: get
path: /wap/schedule/getDeparture
```

返回的是省→市→区的三级结构，整理后列出给用户。

当用户询问"从{城市}可以去哪里"时：

调用 `ticket_api` tool：
```
method: post
path: /wap/schedule/getDestination
body: {
  "province": "{省份}",
  "city": "{城市}",
  "district": "{区县，可选}"
}
```
