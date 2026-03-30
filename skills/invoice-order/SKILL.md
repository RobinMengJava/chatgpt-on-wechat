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

### 第五步：查询任务状态

调用成功后，提示"开票任务已提交，正在处理..."，然后查询状态：

```sql
SELECT
    fp_task_id,
    fp_task_state,
    fp_create_invoice_status,
    fp_electronic_invoice_no,
    fp_message
FROM lulu_invoice
WHERE id = {invoice_id}
```

根据 `fp_task_state` 处理：

| 状态 | 含义 | 处理方式 |
|------|------|----------|
| `1` | 成功 | 告知运营"开票成功，发票号：{fp_electronic_invoice_no}" |
| `2` | 执行中 | 告知运营"任务执行中，请稍后再次查询" |
| `3` | 等待验证码 | → 跳转[验证码处理] |
| `-1` | 执行错误 | → 跳转[任务失败处理]，提示 fp_message |
| `-2` | 任务中断 | → 跳转[任务失败处理] |
| `null` | 尚未更新 | 告知运营"任务刚提交，请稍等后重新查询" |

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

### 第四步：查询任务状态

调用成功后，提示"红冲任务已提交，正在处理..."，然后查询状态：

```sql
SELECT
    fp_offset_invoice_task_id,
    fp_offset_task_state,
    fp_offset_invoice_status
FROM lulu_invoice
WHERE id = {invoice_id}
```

根据 `fp_offset_task_state` 处理：

| 状态 | 含义 | 处理方式 |
|------|------|----------|
| `1` | 成功 | 告知运营"红冲成功" |
| `2` | 执行中 | 告知运营"任务执行中，请稍后再次查询" |
| `3` | 等待验证码 | → 跳转[验证码处理]，task_id 使用 fp_offset_invoice_task_id |
| `-1` | 执行错误 | → 跳转[任务失败处理] |
| `-2` | 任务中断 | → 跳转[任务失败处理] |
| `null` | 尚未更新 | 告知运营"任务刚提交，请稍等后重新查询" |

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
