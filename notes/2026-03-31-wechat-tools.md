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
