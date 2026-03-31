---
name: invoice-order
description: 处理订单发票相关操作，包含两种场景：(1) 开票：为已支付订单开具电子发票；(2) 红冲：对已开具发票执行冲红。当运营人员提到"开票"、"开发票"、"发票"、"红冲"、"冲红"时触发。用户提供订单号，invoice_id 和 task_id 始终通过数据库查询获得，不由用户提供。
---

# 订单发票相关操作

## 第一步：判断操作类型

根据用户描述判断场景：

- **开票**：说"开票"、"开发票"、"帮我开票" → 执行[开票流程]
- **红冲**：说"红冲"、"冲红"、"撤销发票" → 执行[红冲流程]

无法判断时询问："请问您需要：(1) 开票 (2) 红冲（撤销已开发票）？"

---

## 【开票流程】

### 第一步：查询订单和发票信息

用户提供订单号，先查该订单关联的 `invoice_id`：

```sql
SELECT
    o.order_no,
    o.invoice_id,
    i.id              AS invoice_id,
    i.invoice_title,
    i.taxation_number,
    i.invoice_type,
    i.invoice_amount,
    i.email,
    i.fp_task_id,
    i.fp_task_state,
    i.fp_create_invoice_status,
    i.fp_message
FROM lulu_order o
JOIN lulu_invoice i ON i.id = o.invoice_id
WHERE o.order_no = '{订单号}'
  AND o.del_flag = 0
  AND i.del_flag = 0
```

**异常情况处理：**
- 查不到记录 → 提示"该订单未关联发票信息，无法开票"
- `fp_create_invoice_status = 1` → 提示"该发票已开具成功（发票号：{fp_electronic_invoice_no}），无需重复开票"
- `fp_task_state = 2` → 提示"开票任务正在执行中，请稍后查询状态"

### 第二步：查询同一发票关联的所有订单

一张发票可能关联多个订单，用查到的 `invoice_id` 查出所有关联订单：

```sql
SELECT order_no
FROM lulu_order
WHERE invoice_id = {invoice_id}
  AND del_flag = 0
ORDER BY id
```

若关联订单数量 > 1，展示给运营确认：

```
该发票关联了以下 {N} 个订单：
- {order_no_1}
- {order_no_2}
- ...
本次开票将覆盖以上所有订单，确认继续？
```

若只有 1 个订单，直接进入下一步。

### 第三步：展示发票信息，获得确认

```
待开票信息
──────────────────
发票抬头：{invoice_title}
税号：{taxation_number}（个人发票无税号）
发票金额：{invoice_amount} 元
发票类型：{1=企业, 2=个人/非企业}
接收邮箱：{email}
商品：旅游服务*代租车费（税率 1%）
──────────────────
确认开票？
```

### 第四步：调用开票接口

确认后，调用 `invoice_create` tool：
- 参数：`invoice_id`（从第一步查到的 `i.id`）

### 第五步：设置自动状态监听

`invoice_create` 调用成功后，立即用 `scheduler` tool 创建轮询任务，然后告知运营。

**创建轮询任务：**

```
action: create
name: invoice_poll_{invoice_id}
schedule_type: interval
schedule_value: "60"
ai_task: |
  【开票状态轮询】invoice_id={invoice_id}，开票提交时间={当前ISO时间}

  执行步骤：
  1. 查询数据库：
     SELECT fp_task_state, fp_electronic_invoice_no, fp_message
     FROM lulu_invoice
     WHERE id = {invoice_id}

  2. 根据 fp_task_state 处理：

     终态——在通知内容末尾加上 [TASK_DONE] 标记，系统会自动停止轮询：
     - 1（成功）→ 回复"✅ 发票开具成功！发票号：{fp_electronic_invoice_no} [TASK_DONE]"
     - 3（等待验证码）→ 回复"⚠️ 开票平台需要短信验证码，请提供验证码后回复 [TASK_DONE]"
     - -1（执行错误）→ 回复"❌ 开票失败：{fp_message}。如需重试请发送"重发发票 {invoice_id}" [TASK_DONE]"
     - -2（任务中断）→ 回复"❌ 开票任务中断。如需重试请发送"重发发票 {invoice_id}" [TASK_DONE]"

     超时——通知用户后停止轮询：
     - fp_task_state 为 null 或 2，且当前时间距开票提交时间超过 10 分钟 →
       回复"⏰ 开票任务已超过10分钟仍未完成，请到后台手动检查发票 ID {invoice_id} 的状态 [TASK_DONE]"

     继续等待——静默，不发送任何消息：
     - fp_task_state 为 null 或 2，且未超时 → 仅回复 [SILENT]，不输出任何其他内容
```

**告知运营：**

```
✅ 开票任务已提交。系统将持续监听开票结果，有更新时会主动通知您（最多等待10分钟）。
```

---

## 【红冲流程】

### 第一步：查询发票信息

用户提供订单号，查询关联的发票记录：

```sql
SELECT
    o.order_no,
    i.id              AS invoice_id,
    i.invoice_title,
    i.invoice_amount,
    i.fp_create_invoice_status,
    i.fp_electronic_invoice_no,
    i.fp_draw_date,
    i.fp_offset_invoice_task_id,
    i.fp_offset_task_state,
    i.fp_offset_invoice_status
FROM lulu_order o
JOIN lulu_invoice i ON i.id = o.invoice_id
WHERE o.order_no = '{订单号}'
  AND o.del_flag = 0
  AND i.del_flag = 0
```

**异常情况处理：**
- 查不到记录 → 提示"该订单未关联发票信息"
- `fp_create_invoice_status != 1` → 提示"该发票尚未成功开具，无法红冲"
- `fp_offset_invoice_status = 1` → 提示"该发票已红冲成功，无需重复操作"
- `fp_offset_task_state = 2` → 提示"红冲任务正在执行中，请稍后查询状态"

### 第二步：展示发票信息，获得确认

```
待红冲发票信息
──────────────────
发票抬头：{invoice_title}
发票金额：{invoice_amount} 元
电子发票号：{fp_electronic_invoice_no}
开具日期：{fp_draw_date}
──────────────────
确认红冲该发票？红冲后不可撤销。
```

### 第三步：调用红冲接口

确认后，调用 `invoice_offsetting` tool：
- 参数：`invoice_id`

### 第四步：设置自动状态监听

`invoice_offsetting` 调用成功后，立即用 `scheduler` tool 创建轮询任务，然后告知运营。

**创建轮询任务：**

```
action: create
name: offset_poll_{invoice_id}
schedule_type: interval
schedule_value: "60"
ai_task: |
  【红冲状态轮询】invoice_id={invoice_id}，红冲提交时间={当前ISO时间}

  执行步骤：
  1. 查询数据库：
     SELECT fp_offset_task_state, fp_offset_invoice_status, fp_message
     FROM lulu_invoice
     WHERE id = {invoice_id}

  2. 根据 fp_offset_task_state 处理：

     终态——在通知内容末尾加上 [TASK_DONE] 标记，系统会自动停止轮询：
     - 1（成功）→ 回复"✅ 红冲成功！ [TASK_DONE]"
     - 3（等待验证码）→ 回复"⚠️ 开票平台需要短信验证码，请提供验证码后回复 [TASK_DONE]"
     - -1（执行错误）→ 回复"❌ 红冲失败：{fp_message}。如需重试请发送"重发红冲 {invoice_id}" [TASK_DONE]"
     - -2（任务中断）→ 回复"❌ 红冲任务中断。如需重试请发送"重发红冲 {invoice_id}" [TASK_DONE]"

     超时——通知用户后停止轮询：
     - fp_offset_task_state 为 null 或 2，且当前时间距红冲提交时间超过 10 分钟 →
       回复"⏰ 红冲任务已超过10分钟仍未完成，请到后台手动检查发票 ID {invoice_id} 的状态 [TASK_DONE]"

     继续等待——静默，不发送任何消息：
     - fp_offset_task_state 为 null 或 2，且未超时 → 仅回复 [SILENT]，不输出任何其他内容
```

**告知运营：**

```
✅ 红冲任务已提交。系统将持续监听红冲结果，有更新时会主动通知您（最多等待10分钟）。
```

---

## 【验证码处理】

当 `fp_task_state = 3`（开票）或 `fp_offset_task_state = 3`（红冲）时：

1. 提示运营：
   ```
   开票平台需要短信验证码验证，请提供您收到的验证码。
   ```

2. 收到验证码后，调用 `invoice_captcha` tool：
   - 开票场景：`task_id` = `fp_task_id`
   - 红冲场景：`task_id` = `fp_offset_invoice_task_id`
   - `captcha` = 用户提供的验证码

3. 提交成功后，提示"验证码已提交，请稍后查询状态"，再次执行对应流程的状态查询步骤。

---

## 【任务失败处理】

当 `fp_task_state = -1 或 -2`（开票）或 `fp_offset_task_state = -1 或 -2`（红冲）时：

1. 展示失败信息：
   ```
   任务执行失败
   ──────────────────
   状态：{-1=执行错误, -2=任务中断}
   错误信息：{fp_message}（如有）
   ──────────────────
   可以尝试重发任务，是否重发？
   ```

2. 运营确认重发后，调用 `invoice_resend` tool：
   - 开票场景：`task_id` = `fp_task_id`
   - 红冲场景：`task_id` = `fp_offset_invoice_task_id`

3. 重发成功后，提示"任务已重发，请稍后查询状态"，再次执行对应流程的状态查询步骤。

4. 若重发后仍然失败，告知运营"任务重发后仍失败，请联系技术人员排查，错误信息：{fp_message}"。
