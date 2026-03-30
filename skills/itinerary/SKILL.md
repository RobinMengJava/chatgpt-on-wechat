---
name: itinerary
description: 为用户生成行程单 PDF（路禾出行格式），并通过企微机器人发送文件。当运营人员提到"行程单"、"开行程单"、"出行记录"时触发。用户提供订单号，存在往返程时需询问用户选择去程还是返程（或全部）。
---

# 行程单开具

## 第一步：获取订单号

若用户未提供订单号，询问：
> "请提供需要开具行程单的订单号"

---

## 第二步：查询订单和行程信息

对用户提供的订单号执行以下 SQL（以 `lulu_order_itinerary` 为主，join `lulu_ticket` 取乘车人姓名）：

```sql
SELECT
    o.id          AS order_id,
    o.order_no,
    o.invoice_id,
    o.user_id,
    oi.id         AS itinerary_id,
    oi.itinerary,
    oi.departure_time,
    oi.departure_addr,
    oi.arrive_addr,
    oi.actual_amt,
    oi.refund_fee_amt,
    t.name        AS passenger_name,
    t.pay_amt,
    t.state       AS ticket_state
FROM lulu_order o
JOIN lulu_order_itinerary oi ON oi.order_id = o.id AND oi.del_flag = 0
JOIN lulu_ticket t ON t.order_itinerary_id = oi.id AND t.del_flag = 0
WHERE o.order_no = '{订单号}'
  AND o.del_flag = 0
ORDER BY oi.itinerary, oi.id, t.id
```

字段说明：
- `oi.itinerary`：行程类型，**1=去程，2=返程**
- 每条 `lulu_order_itinerary` 记录对应一段行程，每段行程可能有多张票（多名乘客）
- 每行 = 每条 itinerary + 每张 ticket 的组合

**异常处理：**
- 查不到记录 → 提示"该订单号不存在或已删除"

---

## 第三步：查询同一发票关联的所有订单

若该订单有 `invoice_id`，查出所有绑定到同一发票的订单：

```sql
SELECT order_no
FROM lulu_order
WHERE invoice_id = {invoice_id}
  AND del_flag = 0
ORDER BY id
```

**若关联订单数量 > 1**，询问运营：

```
该发票关联了以下 {N} 个订单：
- {order_no_1}（您提供的）
- {order_no_2}
- ...
请问需要：
(1) 将所有订单开到同一张行程单
(2) 仅开具您提供的订单 {order_no}
```

- 选择 (1)：对所有关联订单逐一执行第二步 SQL，合并所有数据
- 选择 (2)：仅使用用户提供订单的数据

**若只有 1 个订单**，直接进入下一步。

---

## 第四步：处理往返程选择

检查已确认订单数据中的 `oi.itinerary` 值：

- **只有 1 种值**（只有去程或只有返程）→ 直接进入第五步

- **同时有 1（去程）和 2（返程）** → 询问：
  > "该订单包含去程和返程，请问需要开哪段的行程单？
  > (1) 去程  (2) 返程  (3) 全部"

  根据选择过滤数据：
  - 去程：仅保留 `oi.itinerary = 1` 的行
  - 返程：仅保留 `oi.itinerary = 2` 的行
  - 全部：保留所有行

---

## 第五步：查询用户手机号和发票信息

### 查询手机号

```sql
SELECT phone FROM lulu_user WHERE id = {user_id} LIMIT 1
```

脱敏规则：保留前 3 位和后 4 位，中间替换为 `****`（如 `158****9960`）。
查不到则使用 `"-"`。

### 查询发票信息（若有 invoice_id）

```sql
SELECT invoice_title, fp_electronic_invoice_no
FROM lulu_invoice
WHERE id = {invoice_id} AND del_flag = 0
LIMIT 1
```

无 invoice_id 或查不到时，`invoice_title` 和 `invoice_no` 均填 `"-"`。

---

## 第六步：展示待生成信息，请求确认

```
待生成行程单
──────────────────
包含订单：{order_no_1}、{order_no_2}...
电话号码：{masked_phone}
发票抬头：{invoice_title}
发票号：{invoice_no}
行程段：{去程 / 返程 / 全部}
行程条数：{N} 笔
乘客：{passenger_name1}、{passenger_name2}...
──────────────────
确认生成？
```

---

## 第七步：组装数据并生成 PDF

调用 `itinerary_pdf` tool：

**组装规则：**
- 每行 = 一条 `lulu_order_itinerary` + 一张 `lulu_ticket` 的组合
- `departure_station` = `oi.departure_addr`
- `arrival_station` = `oi.arrive_addr`
- `departure_time` = `oi.departure_time`（格式：`YYYY-MM-DD HH:mm:ss`）
- `passenger_name` = `t.name`
- `amount` = `t.pay_amt`
- `remark`：
  - 若 `oi.refund_fee_amt` 不为 null 且 > 0 → `"退票手续费"`
  - 否则 → `"-"`
- 多个订单合并后按 `oi.departure_time` 升序排列

```json
{
  "phone": "158****9960",
  "invoice_title": "...",
  "invoice_no": "...",
  "rows": [
    {
      "order_no": "CYW...",
      "passenger_name": "张三",
      "departure_time": "2026-08-31 07:40:00",
      "departure_station": "蛤地地铁站B口公交站",
      "arrival_station": "拱北口岸（拱北通大汽车站）",
      "amount": 8.8,
      "remark": "-"
    }
  ]
}
```

---

## 第八步：发送 PDF

`itinerary_pdf` tool 返回文件路径后，调用 `send` tool：

```json
{
  "path": "{返回的 path}",
  "message": "行程单已生成，共 {N} 笔行程，合计 ¥{total} 元"
}
```
