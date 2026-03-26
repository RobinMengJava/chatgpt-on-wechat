---
name: refund-order
description: 处理订单退款相关操作，包含三种场景：(1) 退款：实际退钱给用户；(2) 仅取消：改变订单状态为退款中但不退钱；(3) 恢复行程：撤销"仅取消"操作，恢复订单到原始状态。当运营人员提到"退款"、"退票"、"取消订单"、"恢复行程"时触发。用户会提供订单号、外部订单号或车票号，ticket_id 始终通过数据库查询获得，不由用户提供。
---

# 订单退款相关操作

## 第一步：判断操作类型

根据用户描述判断场景：

- **退款**：说"退款"、"退钱"、"退票" → 执行[退款流程]
- **仅取消**：说"取消订单"、"不退钱"、"只取消" → 执行[仅取消流程]
- **恢复行程**：说"恢复"、"撤销取消"、"后悔了" → 执行[恢复行程流程]

无法判断时询问："请问您需要：(1) 退款（实际退钱）(2) 仅取消订单（不退钱）(3) 恢复行程？"

---

## 【公共】查询订单信息

所有流程都需要先执行此步骤，根据用户提供的标识符类型选择对应 SQL。

### 标识符识别规则

| 用户提供的内容 | 类型 | 使用字段 |
|---|---|---|
| 系统内部订单号（如 `2024XXXXXX`） | 内部订单号 | `lulu_order.order_no` |
| 外部/第三方订单号（如来自微信、OTA等） | 外部订单号 | `lulu_order.open_order_no` |
| 短票号（通常10位以内，如 `T00123`） | 票号 | `lulu_ticket.ticket_no` |
| 取票码 | 取票码 | `lulu_ticket.take_ticket_no` |

如果无法判断类型，优先尝试 `order_no`，查不到再尝试 `open_order_no`。

### 按内部订单号查询

```sql
SELECT
    o.id          AS order_id,
    o.order_no,
    o.open_order_no,
    o.actual_amt,
    o.state       AS order_state,
    t.id          AS ticket_id,
    t.ticket_no,
    t.name        AS passenger_name,
    t.pay_amt,
    t.state       AS ticket_state
FROM lulu_order o
JOIN lulu_ticket t ON t.order_id = o.id
WHERE o.order_no = '{值}'
  AND o.del_flag = 0
  AND t.del_flag = 0
```

### 按外部订单号查询

```sql
SELECT
    o.id          AS order_id,
    o.order_no,
    o.open_order_no,
    o.actual_amt,
    o.state       AS order_state,
    t.id          AS ticket_id,
    t.ticket_no,
    t.name        AS passenger_name,
    t.pay_amt,
    t.state       AS ticket_state
FROM lulu_order o
JOIN lulu_ticket t ON t.order_id = o.id
WHERE o.open_order_no = '{值}'
  AND o.del_flag = 0
  AND t.del_flag = 0
```

### 按票号查询

票号对应单张车票，查到票后取其 order_id，再查出该订单下所有车票：

```sql
SELECT
    o.id          AS order_id,
    o.order_no,
    o.open_order_no,
    o.actual_amt,
    o.state       AS order_state,
    t.id          AS ticket_id,
    t.ticket_no,
    t.name        AS passenger_name,
    t.pay_amt,
    t.state       AS ticket_state
FROM lulu_ticket t
JOIN lulu_order o ON o.id = t.order_id
WHERE t.ticket_no = '{值}'
  AND o.del_flag = 0
  AND t.del_flag = 0
```

> 注意：按票号查出来的可能只有一张票，但该订单下可能有多张票（如跨境往返程，itinerary=1 去程，itinerary=2 返程）。
> 查到票后，额外查出该订单下所有车票的状态（ticket.state）：
>
> - **所有票均未使用**（state ≤ 200，即 WAIT_TRAVEL 或更早）→ 默认退整单，无需询问用户
> - **部分票已使用**（某张票 state = 300 FINISHED）→ 询问用户：
>   "检测到该订单有去程和返程，其中 {已完成的程} 已出行。请问需要退整单，还是仅退未使用的 {未完成的程}？"
>   根据用户选择决定 ticket_list 的范围

### 查询异常处理

- 查询结果为空：告知"未找到该订单，请确认提供的信息是否正确"
- 订单 state=500（已退款）或 state=400（已取消）：告知"该订单已退款/已取消，无法重复操作"
- 订单 state=350（已完成有退款）：提示用户该订单已有过退款记录，确认是否继续

---

## 退款流程

### 1. 查询订单（见上方公共步骤）

### 2. 确认手续费

**用户已提供手续费**（如"收10%"、"不收手续费"、"手续费20元"）→ 直接跳到第3步。

**否则**询问：
> "请问此次退款收取多少手续费？（如"收10%"、"收20元"或"不收手续费"）"

### 3. 展示退款明细并确认

计算规则：
- 百分比：`fee = actual_amt × 费率`，`refund = actual_amt - fee`
- 固定金额：`fee = 固定金额`，`refund = actual_amt - fee`
- 不收手续费：`fee = 0`，`refund = actual_amt`
- 多张车票按 `pay_amt / actual_amt` 比例各自分摊退款额和手续费，**金额精确到分（保留2位小数）**

展示：
```
退款明细确认
--------------
订单号：{order_no}
乘客：{passenger_name(s)}
订单金额：{actual_amt} 元
手续费：{fee} 元
实际退款：{refund} 元

请确认是否执行退款？（回复"确认"或"取消"）
```

### 4. 执行退款

用户确认后调用 **refund_execute** 工具，传入：
- `order_id`
- `total_refund_amt`、`total_fee`
- `ticket_list`：每张票的 `ticket_id`（来自数据库查询结果）、`refund_amt`、`fee`

用户取消则告知"已取消退款操作"。

---

## 仅取消流程

### 1. 查询订单（见上方公共步骤）

### 2. 展示并确认

```
仅取消确认（不退款）
--------------
订单号：{order_no}
乘客：{passenger_name(s)}
操作：仅修改订单状态为退款中，不执行实际退款

请确认是否执行？（回复"确认"或"取消"）
```

### 3. 执行取消

用户确认后调用 **cancel_ticket** 工具，传入 `ticket_id_list`（来自数据库查询结果）。

---

## 恢复行程流程

### 1. 查询订单（见上方公共步骤）

检查订单状态：若为 500（已退款）则告知"该订单已完成退款，无法恢复行程"，终止流程。

### 2. 展示并确认

```
恢复行程确认
--------------
订单号：{order_no}
乘客：{passenger_name(s)}
操作：将订单状态恢复到原始状态

请确认是否恢复？（回复"确认"或"取消"）
```

### 3. 执行恢复

用户确认后调用 **restore_ticket** 工具，传入 `ticket_id_list`（来自数据库查询结果）。
