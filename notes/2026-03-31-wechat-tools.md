# 微信支付查询工具开发笔记 (2026-03-31)

## 新增工具

- `QueryWxOrderTool`：根据商户订单号查询微信支付单状态
- `QueryWxRefundTool`：根据订单号查询微信退款状态（自动查 `lulu_refund` 表）

## 踩坑记录

### 1. 开票工具请求体字段错误

`invoice_create_tool.py` 初始请求体与前端实际发送的不一致，导致 API 返回 `success: True, result: null`，后台没有任何日志。

差异对比：

| 字段 | 错误值 | 正确值 |
|------|--------|--------|
| `remark` | `"旅游服务*代租车费"` | 字段名应为 `mark`，值为 `""` |
| `goodsName` | `"旅游服务*代租车费"` | `"*旅游服务*代租车费"`（前面多一个 `*`）|
| `taxRate` | `"1%"`（字符串）| `0.01`（数字）|

**教训：** 接口字段要以浏览器 DevTools 抓包为准，不要凭猜测写。

### 2. out_trade_no 的含义搞反了

微信视角：我们系统是商户方，`out_trade_no`（商户订单号）= 我们系统的 `lulu_order.order_no`。

不是 `open_order_no`（那是 OTA 平台的单号）。

初始版本 description 写错，导致 agent 多查了一次库去拿 `open_order_no`，行为错误。

**教训：** Tool 的 description 和参数说明要明确指出对应数据库的哪个字段，否则 agent 会自行推断，可能推断错误。

### 3. TicketApiClient 只有 post，新增了 get 方法

微信查询接口是 GET，原来的 client 只支持 POST，需要新增 `get()` 方法。

---

# 开票状态轮询 + Scheduler 踩坑记录 (2026-03-31)

## 背景

开票/红冲接口是异步的，提交后通过回调更新状态。设计了用 `scheduler` tool 每分钟轮询数据库状态、有结果后主动通知用户的方案。

---

## 踩坑 1：[SILENT] 过滤用精确匹配，agent 不严格遵守导致漏网

**现象：** agent 回复了 `"发票已处于成功终态...无需继续轮询。\n[SILENT]"`，消息被发送给用户。

**原因：** `integration.py` 里的过滤条件是 `reply.content.strip() == "[SILENT]"`，精确匹配。agent 有时会在 `[SILENT]` 前面加上自己的分析文字，导致条件不成立，消息照发。

**修复：** 改为从 content 中 strip 掉 `[SILENT]`，剩余为空则不发送；有内容则正常发送（去掉标记）。这样即使 agent 多写了内容也能正确处理。

---

## 踩坑 2：ai_task 里无法调用 scheduler tool 删除自己

**现象：** agent 报 "scheduler 接口需要认证，请手动到后台删除定时任务"，轮询任务无法自删。

**原因：** `agent_bridge.py` 里有意为之的逻辑：当 `context["is_scheduled_task"] == True` 时，scheduler tool 被从工具列表中排除，目的是防止 ai_task 递归创建新的定时任务。但这同时也让 ai_task 无法调用 scheduler 来删除自身。

**修复：** 引入 `[TASK_DONE]` 标记机制。ai_task 在终态回复末尾加 `[TASK_DONE]`，`integration.py` 检测到后直接调 `_task_store.delete_task(task_id)` 删任务，不需要 ai_task 自己调 scheduler tool。这样绕开了工具限制，也不需要改 agent_bridge 的排除逻辑。

---

## 踩坑 3：agent 创建了 once 任务而非 interval 任务

**现象：** 截图中定时任务显示为 `once` 类型，而 SKILL.md 里明确写的是 `interval`。

**原因：** agent 没有严格遵循 SKILL.md 的参数，自行决定用了 `once`。

**影响：** `once` 任务执行一次后自动删除，不会每分钟重复检查，轮询功能未生效。

**说明：** `once` 任务由 scheduler_service 在执行后自动删除，不会残留。`interval` 任务不会自动删除，依赖 `[TASK_DONE]` 机制清理。

---

## 最终方案总结

| 标记 | 含义 | integration.py 处理 |
|------|------|---------------------|
| `[TASK_DONE]` | 终态，停止轮询 | 删除任务，发送通知（去掉标记） |
| `[SILENT]` | 还在等待，无需通知 | 不发送消息 |
| 普通内容 | 正常回复 | 发送给用户 |
