# 2026-03-26 工作笔记（下）：Ticket 退款工具开发

## 一、方案讨论：如何接入 Spring Boot 业务接口

### 核心结论

- **查询类**（只读）→ 直接用已有的 `MySQLQuery` tool，复用，零额外开发
- **写操作类**（退款、取消、恢复）→ 写 Python `BaseTool` 子类调 REST 接口，代码层保障参数校验和确认流程
- **流程编排**（多步对话）→ 用 `SKILL.md` 写指令，模型读指令、靠对话上下文维持多轮状态，不需要 Task

### Skill 机制澄清

CowAgent 的 Skill 不是多步状态机，而是 **Markdown 指令文件**，注入到 system prompt 里给模型看。多轮流程（如"先查订单→问手续费→确认→执行"）完全靠对话上下文维持，不需要代码层面的状态机。

条件逻辑（如"如果用户已提供手续费则跳过询问"）直接用自然语言写在 SKILL.md 里，模型天然理解。

### Skill 自进化

SKILL.md 是普通文件，agent 有 Read/Write/Edit 工具，可以直接修改自己的 skill 文件。跟 agent 说"哪里做得不好，帮我改"，它会自己更新 SKILL.md，下次对话生效。业务 skill 放在 `workspace/skills/`（custom），不放 `skills/`（builtin）。

---

## 二、鉴权方案：TicketApiClient

Spring Boot 用的是 JeecgBoot 框架（识别特征：`/sys/login` + `checkKey` 字段 + `X-Access-Token` 请求头）。

### 设计要点

- 登录接口：`POST /sys/login`，body 含 `checkKey`（当前毫秒时间戳）
- Token 缓存到 `~/.cow/ticket_token.json`，含 `expires_at` 字段
- JWT exp 字段通过 base64 解码获取（无需验证签名）
- 过期前 5 分钟主动刷新；收到 401 时清缓存重新登录，自动重试一次
- 所有 Tool 继承 `TicketApiClient`，鉴权对上层完全透明

### config.json 新增字段

```json
"ticket_api_base": "https://wap.luluroad.com",
"ticket_api_user": "mwl",
"ticket_api_password": "你的密码"
```

---

## 三、新增文件清单

```
agent/tools/ticket/
  client.py              # TicketApiClient：登录、token 缓存、401 自动重试
  refund_tool.py         # RefundExecuteTool：调 customAmtRefund 执行退款
  cancel_ticket_tool.py  # CancelTicketTool：仅取消订单，不退钱
  restore_ticket_tool.py # RestoreTicketTool：恢复已取消行程

skills/refund-order/
  SKILL.md               # 退款流程指引（三种场景）
```

---

## 四、退款 SKILL.md 设计要点

### 三种场景

| 场景 | 触发关键词 | 调用 Tool |
|---|---|---|
| 退款 | "退款"、"退钱"、"退票" | `refund_execute` |
| 仅取消 | "取消订单"、"只取消"、"不退钱" | `cancel_ticket` |
| 恢复行程 | "恢复"、"撤销取消"、"后悔了" | `restore_ticket` |

### 多种标识符支持

用户可提供以下任一标识符，ticket_id 始终由数据库查询获得：

| 用户提供 | 查询字段 |
|---|---|
| 内部订单号 | `lulu_order.order_no` |
| 外部订单号 | `lulu_order.open_order_no` |
| 票号（短，≤10位） | `lulu_ticket.ticket_no` |
| 取票码 | `lulu_ticket.take_ticket_no` |

### 往返程多票处理逻辑

按票号查询可能命中单张票，但订单下有去程+返程两张票（`itinerary=1/2`）：

- **所有票 state ≤ 200**（均未使用）→ 默认退整单，不询问
- **部分票 state = 300**（有一程已出行）→ 询问用户：退整单还是仅退未使用的那程

### 手续费确认逻辑

- 用户开头已提供手续费（如"收10%"、"不收手续费"）→ 跳过询问步骤
- 未提供 → 询问后继续
- 多张票按 `pay_amt / actual_amt` 比例分摊，精确到分

---

## 五、接口信息备忘

| 接口 | 路径 |
|---|---|
| 登录 | `POST /sys/login` |
| 退款 | `POST /web/bus/luluOrder/customAmtRefund` |
| 仅取消 | `POST /web/bus/luluOrder/cancelTicket` |
| 恢复行程 | `POST /web/bus/luluOrder/restoreTicket` |

退款成功响应：`{"msg":"退款成功"}`，其他均视为失败。
取消/恢复成功响应：`{"success": true, "code": 200, "message": "批量XX成功!"}`

---

## 六、待完成

- [ ] 服务器 config.json 补充 ticket_api_* 三个字段
- [ ] 测试登录接口，确认 `X-Access-Token` header 是否正确（JeecgBoot 标准，若不对改为 `Authorization: Bearer {token}`）
- [ ] 端到端测试退款流程
