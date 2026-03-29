---
name: reconciliation
description: 对账供应商账单。当运营提到"对账"、"核对账单"、"对一下账"、"帮我对下账"时触发。分两种情况：①用户上传了Excel文件 → 调用 reconciliation 工具；②用户说"对账XX公司X月账单"且没有文件 → 直接查数据库。
---

# 供应商账单对账

## 判断走哪条路径

| 情况 | 路径 |
|------|------|
| 消息中包含文件路径 `[文件: /path/to/file]` | → [Excel对账](#excel对账) |
| 没有文件，用户提到公司名称 + 账期 | → [系统对账](#系统对账) |
| 没有文件，也没有公司名称 | 回复：请发送账单文件，或告知公司名称和账期 |

---

## Excel对账

### 第一步：提取文件路径并立即调用工具

检查消息中是否包含文件路径（格式为 `[文件: /path/to/file]`）。

- **没有文件路径** → 回复：
  > 请先发送供应商账单文件（Excel 格式），再发送对账指令。

- **有文件路径** → **不要自己读取或预览文件内容**，立即回复：
  > 正在对账，请稍候……

  然后直接调用 **reconciliation** 工具，传入提取到的 `file_path`。

**严格禁止：**
- 禁止在调用工具前自行读取、分析、预览文件内容
- 禁止根据文件名或文件内容自行判断格式或是否支持
- 禁止在未调用工具的情况下对文件内容做任何结论

格式识别、数据校验全部由工具完成，Agent 只负责传路径、等结果、输出报告。

---

### 第三步：渐进式输出对账报告

拿到工具返回的 JSON 后，**按以下顺序逐段输出**，让用户边看边等：

#### 3.1 汇总（第一段，先输出）

```
📊 对账完成 — {supplier}
──────────────────────────
总计：{total} 条
✅ 匹配：{matched} 条
⚠️ 有差异：{issue_count} 条
❓ 系统未找到：{not_found_count} 条
```

#### 3.2 财务汇总（第二段）

**若是新国线账单**，输出：

```
💰 财务汇总
有效票数：{有效票数} 张
总金额：¥{总金额}
佣金比例：{佣金比例}
佣金：¥{佣金}
应结款：¥{应结款}
```

**若是车盈网账单**，分空港/非空港两块输出：

```
💰 财务汇总

【空港票源（佣金 {空港票源.佣金比例}）】
有效票金额：¥{空港票源.有效票金额}
退票金额：¥{空港票源.退票金额}
有效票数：{空港票源.有效票数} 张
佣金比例：{空港票源.佣金比例}
代售佣金：¥{空港票源.代售佣金}

【非空港票源（佣金 {非空港票源.佣金比例}）】
有效票金额：¥{非空港票源.有效票金额}
退票金额：¥{非空港票源.退票金额}
有效票数：{非空港票源.有效票数} 张
佣金比例：{非空港票源.佣金比例}
代售佣金：¥{非空港票源.代售佣金}
```

#### 3.3 差异明细（第三段）

若 `issue_count > 0`，逐条列出：

```
【差异明细】

1. 订单号：{order_no}
   {若是车盈网，附加：乘车人：{passenger}  条码：{barcode}}
   - {field}：供应商 {supplier_val} → 系统 {db_val}
   （同一条目有多个差异字段时逐行列出）

2. 订单号：...
   ...
```

若差异超过 20 条，前 20 条后补充：

```
…… 还有 {剩余数} 条差异，如需继续查看请告知。
```

#### 3.4 未找到（第四段，最后输出）

若 `not_found_count > 0`：

```
【系统中未找到的订单/条码】
{逐行列出，每行一个，最多显示 10 条}
{若超过 10 条：…… 共 {not_found_count} 条未找到}
```

#### 3.5 全部匹配时

若 `issue_count == 0` 且 `not_found_count == 0`：

```
✅ 全部匹配，账单数据与系统完全一致，无差异。
```

---

### 第四步：等待追问

报告输出后保持上下文，等待运营追问。常见场景：

- **"第X条详情"** / **"查一下这个订单"** → 用 `mysql_query` 查询 `lulu_order_itinerary` / `lulu_ticket` 详情展示
- **"为什么金额不一样"** → 查询行程详情后分析原因（优惠券、退款记录等）
- **"继续看差异"** → 输出第 21 条起的差异明细
- **"未找到的原因"** → 尝试用 `mysql_query` 查询该订单号是否存在于系统，反馈查询结果

---

## 系统对账

适用于系统内其他供应商（无Excel文件，直接查库）。

### 第一步：查公司 ID

```sql
SELECT id, name FROM lulu_company
WHERE name LIKE '%{供应商名称}%' AND del_flag = 0
```

若查到多条，列出让用户确认；若查不到，告知用户。

### 第二步：查财务汇总

账期默认按 `departure_time` 过滤，若未指定年份默认当前年份。

```sql
SELECT
  COUNT(*)                  AS 有效票数,
  ROUND(SUM(t.pay_amt), 2)  AS 总金额
FROM lulu_ticket t
JOIN lulu_order_itinerary oi ON t.order_itinerary_id = oi.id
WHERE oi.company_id = {company_id}
  AND t.state IN (200, 260, 300)
  AND oi.departure_time >= '{start_date}'
  AND oi.departure_time <  '{end_date}'
  AND t.del_flag  = 0
  AND oi.del_flag = 0
```

### 第三步：计算并输出财务汇总

拿到查询结果后在本地计算（**不要重新查库**），默认佣金比例 **10%**：

```
佣金   = ROUND(总金额 × 佣金比例, 2)
应结款 = ROUND(总金额 - 佣金, 2)
```

输出格式：

```
💰 财务汇总 — {供应商名称}（{账期}）
──────────────────────────
有效票数：{有效票数} 张
总金额：¥{总金额}
佣金比例：{佣金比例}%
佣金：¥{佣金}
应结款：¥{应结款}
```

### 第四步：等待追问

- **"佣金改成8%"** → 用已查到的总金额重新计算，无需重新查库
- **"导出明细"** / **"给我看看明细"** → 查询并展示订单明细：

```sql
SELECT
  oi.open_order_no     AS 订单号,
  t.name               AS 乘车人,
  oi.departure_time    AS 出发时间,
  oi.departure_addr    AS 上车地点,
  oi.arrive_addr       AS 下车地点,
  t.pay_amt            AS 支付金额,
  t.state              AS 票状态
FROM lulu_ticket t
JOIN lulu_order_itinerary oi ON t.order_itinerary_id = oi.id
WHERE oi.company_id = {company_id}
  AND t.state IN (200, 300)
  AND oi.departure_time >= '{start_date}'
  AND oi.departure_time <  '{end_date}'
  AND t.del_flag  = 0
  AND oi.del_flag = 0
ORDER BY oi.departure_time
```

- **"查某个订单"** → 用 `mysql_query` 查询该订单详情
