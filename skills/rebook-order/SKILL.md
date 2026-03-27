---
name: rebook-order
description: 处理订单改签操作，支持修改出发时间、出发地点、到达地点、座位号，可单独或组合修改。当运营人员提到"改签"、"改时间"、"改班次"、"改站点"、"改座位"时触发。用户会提供订单号、外部订单号或车票号，ticket_id 和 itinerary_id 始终通过数据库查询获得，不由用户提供。
---

# 订单改签操作

## 第一步：查询订单信息

根据用户提供的标识符，使用下方 SQL 查询订单及行程。

### 标识符识别（同退款 SKILL）

| 用户提供的内容 | 类型 | 查询方式 |
|---|---|---|
| GZ/CYW/BBZ/CBS/CXBS/YXQC 开头 | 内部订单号 | `lulu_order.order_no` |
| 其他格式 | 外部订单号 | `lulu_order.open_order_no` |
| 短票号（如 T00123） | 票号 | `lulu_ticket.ticket_no` |
| 取票码 | 取票码 | `lulu_ticket.take_ticket_no` |

### 查询订单 + 行程（按内部订单号）

```sql
SELECT
    o.id          AS order_id,
    o.order_no,
    o.open_order_no,
    o.order_type,
    o.state       AS order_state,
    o.attachment_id,
    oi.id         AS itinerary_id,
    oi.itinerary,
    oi.state      AS itinerary_state,
    oi.departure_time,
    oi.departure_province,
    oi.departure_city,
    oi.departure_district,
    oi.departure_addr,
    oi.departure_position,
    oi.departure_schedule_station_id,
    oi.arrive_province,
    oi.arrive_city,
    oi.arrive_district,
    oi.arrive_addr,
    oi.arrive_position,
    oi.arrive_schedule_station_id
FROM lulu_order o
JOIN lulu_order_itinerary oi ON oi.order_id = o.id AND oi.del_flag = 0
WHERE o.order_no = '{值}'
  AND o.del_flag = 0
ORDER BY oi.itinerary
```

> 外部订单号时将 `o.order_no` 改为 `o.open_order_no`。
> 按票号/取票码时先查出 order_id，再用上方 SQL 按 `o.id = {order_id}` 查询。

### 查询该订单的车票

```sql
SELECT
    id          AS ticket_id,
    itinerary,
    seat,
    name        AS passenger_name,
    state       AS ticket_state
FROM lulu_ticket
WHERE order_id = {order_id}
  AND del_flag = 0
ORDER BY itinerary
```

### 查询异常处理

- 查询结果为空：告知"未找到该订单，请确认提供的信息是否正确"
- 订单 state=400/500：告知"该订单已取消/已退款，无法改签"

---

## 第二步：判断改签哪一程

### 单程（order_type=1）

直接进入 **第三步**，无需询问。

### 双程（order_type=2）

查询结果会有 itinerary=1（去程）和 itinerary=2（返程）两条行程记录。

**智能判断规则（优先判断，无需询问用户）：**

| 去程 itinerary_state | 判断结果 |
|---|---|
| 260（已验票）或 300（已完成） | 默认改签**返程**，向用户说明："检测到去程已出行，默认改签返程（{返程出发地} → {返程到达地}，{返程出发时间}），请确认。" |
| 其他 | 询问用户："该订单有去程和返程，请问需要改签哪一程？(1) 去程（{去程出发地}→{去程到达地}，{去程时间}）(2) 返程（{返程出发地}→{返程到达地}，{返程时间}）" |

---

## 第三步：确认改签内容

根据用户提供的改签信息，判断本次改签类型（可组合）：

- **仅改时间**：用户提供新出发时间 → 执行[时间改签]
- **改出发站点**：用户说改上车站点 → 执行[出发站点改签]
- **改到达站点**：用户说改下车站点 → 执行[到达站点改签]
- **改座位**：用户提供新座位号 → 执行[座位改签]
- **组合改签**：以上任意组合，分别收集信息后一并执行

---

## 【时间改签】

**信息收集：**

若用户已提供新时间（如"改到明天9点"），直接使用。否则询问："请提供新的出发时间（如 2026-03-28 09:00）。"

**涉及字段：** `departure_time`

**无需查参考数据**，直接进入第四步。

---

## 【出发站点改签】

**信息收集：**

若用户已提供站点名（如"改到广州南站"），直接使用。否则询问："请提供新的上车站点名称。"

**查参考地址数据：**

根据改签的是哪一程，选择对应的查询方式：

- **改去程出发站**：在 `lulu_order` 中查
- **改返程出发站**：在 `lulu_order_itinerary` 中查

```sql
-- 改去程出发站：在 lulu_order 中找
SELECT
    departure_province, departure_city, departure_district,
    departure_addr, departure_position, departure_schedule_station_id
FROM lulu_order
WHERE departure_addr LIKE '%{站点名}%'
  AND del_flag = 0
  AND departure_province IS NOT NULL
  AND departure_addr IS NOT NULL
LIMIT 1

-- 改返程出发站：在 lulu_order_itinerary 中找（itinerary=2）
SELECT
    departure_province, departure_city, departure_district,
    departure_addr, departure_position, departure_schedule_station_id
FROM lulu_order_itinerary
WHERE departure_addr LIKE '%{站点名}%'
  AND itinerary = 2
  AND del_flag = 0
  AND departure_province IS NOT NULL
  AND departure_addr IS NOT NULL
LIMIT 1
```

若查不到结果（该站点在系统中没有历史记录），告知用户："未找到站点"{站点名}"的参考数据，请提供完整地址信息：省份、城市、区域、详细地址、经纬度（格式：经度,纬度）。"

**涉及字段：** `departure_province`、`departure_city`、`departure_district`、`departure_addr`、`departure_position`、`departure_schedule_station_id`

---

## 【到达站点改签】

同出发站点改签，但查询和更新 `arrive_*` 字段：

```sql
-- 改去程到达站：在 lulu_order 中找
SELECT
    arrive_province, arrive_city, arrive_district,
    arrive_addr, arrive_position, arrive_schedule_station_id
FROM lulu_order
WHERE arrive_addr LIKE '%{站点名}%'
  AND del_flag = 0
  AND arrive_province IS NOT NULL
  AND arrive_addr IS NOT NULL
LIMIT 1

-- 改返程到达站：在 lulu_order_itinerary 中找（itinerary=2）
SELECT
    arrive_province, arrive_city, arrive_district,
    arrive_addr, arrive_position, arrive_schedule_station_id
FROM lulu_order_itinerary
WHERE arrive_addr LIKE '%{站点名}%'
  AND itinerary = 2
  AND del_flag = 0
  AND arrive_province IS NOT NULL
  AND arrive_addr IS NOT NULL
LIMIT 1
```

**涉及字段：** `arrive_province`、`arrive_city`、`arrive_district`、`arrive_addr`、`arrive_position`、`arrive_schedule_station_id`

---

## 【座位改签】

**信息收集：**

若用户已提供新座位号，直接使用。否则询问："请提供新的座位号。"

**涉及表：** 仅 `lulu_ticket`，无需查参考数据。

---

## 第四步：展示变更明细并确认

整理所有待更新的字段，展示变更前后对比，请用户确认：

```
改签明细确认
--------------
订单号：{order_no}
改签程次：去程 / 返程 / 单程

【变更内容】
出发时间：{旧值} → {新值}         （仅时间改签时显示）
上车站点：{旧 departure_addr} → {新 departure_addr}  （仅出发站点改签时显示）
下车站点：{旧 arrive_addr} → {新 arrive_addr}        （仅到达站点改签时显示）
座位号：{旧 seat} → {新 seat}     （仅座位改签时显示）

【涉及更新的表】
- {表名1}（WHERE ...）
- {表名2}（WHERE ...）
...

请确认是否执行改签？（回复"确认"或"取消"）
```

> 若有多名乘客（多张票），座位变更需逐一列出每张票的变更情况。

用户取消则告知"已取消改签操作"。

---

## 第五步：执行改签

用户确认后，调用 **rebook_execute** 工具。

根据改签程次，决定更新哪些表：

### 改签去程（itinerary=1）或单程

```json
{
  "updates": [
    {
      "table": "lulu_order",
      "set": { /* 本次涉及的字段 */ },
      "where": { "order_no": "{order_no}" }
    },
    {
      "table": "lulu_order_itinerary",
      "set": { /* 本次涉及的字段 */ },
      "where": { "order_no": "{order_no}", "itinerary": 1 }
    },
    {
      "table": "lulu_ticket",
      "set": { "seat": "{新座位}" },
      "where": { "order_id": {order_id}, "itinerary": 1 }
    }
  ]
}
```

> 若本次不涉及座位变更，省略 `lulu_ticket` 的 update 项。
> 若本次不涉及时间/地点变更，省略 `lulu_order` 和 `lulu_order_itinerary` 的 update 项。

### 改签返程（itinerary=2）

```json
{
  "updates": [
    {
      "table": "lulu_order_itinerary",
      "set": { /* 本次涉及的字段 */ },
      "where": { "order_no": "{order_no}", "itinerary": 2 }
    },
    {
      "table": "lulu_order_attachment",
      "set": { /* 本次涉及的字段（同 itinerary 的变更内容）*/ },
      "where": { "order_no": "{order_no}" }
    },
    {
      "table": "lulu_ticket",
      "set": { "seat": "{新座位}" },
      "where": { "order_id": {order_id}, "itinerary": 2 }
    }
  ]
}
```

> 改签返程时，`lulu_order_itinerary`（itinerary=2）和 `lulu_order_attachment` 更新相同的字段内容。
> 若本次不涉及座位变更，省略 `lulu_ticket` 的 update 项。

### 多张票的座位变更

若订单有多名乘客（多张 itinerary 相同的票），每张票各发一条 `lulu_ticket` update，每条 WHERE 中额外加 `ticket_id`（但 `order_id` 仍为必须）：

```json
{
  "table": "lulu_ticket",
  "set": { "seat": "{乘客A的新座位}" },
  "where": { "order_id": {order_id}, "id": {ticket_id_A} }
}
```

---

## 执行结果

- 成功：告知"改签成功，已更新{涉及的表}共{N}条记录。"
- 失败：告知具体错误信息，提示"改签未执行，数据库已回滚，请检查后重试。"
