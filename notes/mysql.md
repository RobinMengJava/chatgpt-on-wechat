## LuLu 数据库表结构

> 数据库：lulu_prod
> 字符集：utf8mb4_general_ci
> 所有表均有公共字段：`create_time`、`update_time`、`create_by`、`update_by`、`del_flag`（0=有效，1=失效）

---

### 表索引

| 表名 | 说明 |
|------|------|
| [lulu_user](#lulu_user) | 用户 |
| [lulu_open_user](#lulu_open_user) | 第三方开放用户信息（微信等） |
| [lulu_riders](#lulu_riders) | 乘车人 |
| [lulu_company](#lulu_company) | 对接公司 |
| [lulu_station](#lulu_station) | 站点 |
| [lulu_route_station_relationship](#lulu_route_station_relationship) | 线路站点关系 |
| [lulu_gz_city](#lulu_gz_city) | 广州城市/区域 |
| [lulu_order](#lulu_order) | 主订单 |
| [lulu_order_itinerary](#lulu_order_itinerary) | 订单行程（去程/返程） |
| [lulu_ticket](#lulu_ticket) | 车票 |
| [lulu_pay](#lulu_pay) | 第三方支付 |
| [lulu_refund](#lulu_refund) | 退款 |
| [lulu_invoice](#lulu_invoice) | 发票 |

---

### lulu_user

用户表，存储注册用户基本信息。

| 字段 | 类型 | 可空 | 默认值 | 说明 |
|------|------|------|--------|------|
| id | bigint unsigned | NOT NULL | — | 主键 |
| phone | varchar(128) | YES | — | 手机号码 |
| password | varchar(255) | YES | — | 密码 |
| salt | varchar(45) | YES | — | md5密码盐 |
| channel | varchar(30) | YES | — | 来源渠道 |
| create_time | datetime | YES | CURRENT_TIMESTAMP | 创建时间 |
| update_time | datetime | YES | ON UPDATE | 更新时间 |
| create_by | int | YES | — | 创建人 |
| update_by | int | YES | — | 最后更新人 |
| del_flag | int | YES | 0 | 1=失效 0=有效 |

---

### lulu_open_user

第三方开放平台用户信息（如微信），与 `lulu_user` 关联。

| 字段 | 类型 | 可空 | 默认值 | 说明 |
|------|------|------|--------|------|
| id | bigint unsigned | NOT NULL | — | 主键 |
| user_id | bigint | YES | — | 关联 lulu_user.id |
| open_id | varchar(32) | YES | — | 第三方平台用户Id |
| client | varchar(20) | YES | — | 客户端：100=微信 |
| channel | varchar(32) | YES | — | 来源渠道 |
| create_time | datetime | YES | CURRENT_TIMESTAMP | 创建时间 |
| update_time | datetime | YES | ON UPDATE | 更新时间 |
| create_by | int | YES | — | 创建人 |
| update_by | int | YES | — | 最后更新人 |
| del_flag | tinyint(1) | YES | 0 | 1=失效 0=有效 |

---

### lulu_riders

乘车人信息，一个用户可有多个乘车人。

| 字段 | 类型 | 可空 | 默认值 | 说明 |
|------|------|------|--------|------|
| id | bigint unsigned | NOT NULL | — | 主键 |
| user_id | bigint | YES | — | 关联 lulu_user.id |
| name | varchar(100) | YES | — | 乘车人姓名 |
| id_card | varchar(20) | YES | — | 身份证号 |
| card_type | tinyint | YES | — | 证件类型：1=身份证，2=港澳通行证 |
| phone | varchar(11) | YES | — | 乘车人手机号 |
| riders_type | tinyint | YES | — | 乘车人类型：1=成年人，2=未成年 |
| default_user | tinyint | YES | 0 | 默认乘车人：1=是，0=否 |
| create_time | datetime | YES | CURRENT_TIMESTAMP | 创建时间 |
| update_time | datetime | YES | ON UPDATE | 更新时间 |
| create_by | bigint | YES | — | 创建人 |
| update_by | bigint | YES | — | 最后更新人 |
| del_flag | tinyint(1) | YES | 0 | 1=失效 0=有效 |

---

### lulu_company

对接的第三方公司信息。

| 字段 | 类型 | 可空 | 默认值 | 说明 |
|------|------|------|--------|------|
| id | bigint unsigned | NOT NULL | — | 主键 |
| name | varchar(255) | NOT NULL | — | 公司名称 |
| abbreviated | varchar(255) | YES | — | 公司简称 |
| create_time | datetime | YES | — | 创建时间 |
| update_time | datetime | YES | — | 修改时间 |
| create_by | bigint | YES | — | 创建人 |
| update_by | bigint | YES | — | 最后更新人 |
| del_flag | tinyint unsigned | YES | — | 1=失效 0=有效 |

---

### lulu_station

站点表，包含上下车点的地理信息。

| 字段 | 类型 | 可空 | 默认值 | 说明 |
|------|------|------|--------|------|
| id | bigint unsigned | NOT NULL | — | 主键 |
| open_station_id | varchar(50) | YES | — | 第三方站点Id（唯一） |
| name | varchar(255) | YES | — | 站点名称 |
| province | varchar(50) | YES | — | 省份/直辖市 |
| province_code | varchar(50) | YES | — | 省份编码 |
| city | varchar(50) | YES | — | 市/直辖市 |
| city_code | varchar(50) | YES | — | 城市编码 |
| district | varchar(50) | YES | — | 区/县 |
| district_code | varchar(50) | YES | — | 区县编码 |
| position | varchar(256) | YES | — | 经纬度 |
| picture_url | text | YES | — | 站点图片链接 |
| address | varchar(1024) | YES | — | 详情地址 |
| station_type | tinyint | YES | 0 | 1=上车站点，2=下车站点，3=两者都是 |
| company_id | bigint | YES | — | 所属企业Id |
| create_time | datetime | YES | CURRENT_TIMESTAMP | 创建时间 |
| update_time | datetime | YES | CURRENT_TIMESTAMP ON UPDATE | 修改时间 |
| create_by | varchar(50) | YES | — | 创建人 |
| update_by | varchar(50) | YES | — | 最后更新人 |
| del_flag | int | YES | 0 | 1=失效 0=有效 |

**索引：** `(province, city)`

---

### lulu_route_station_relationship

线路与站点的关联关系表。

| 字段 | 类型 | 可空 | 默认值 | 说明 |
|------|------|------|--------|------|
| id | bigint | NOT NULL | — | 主键 |
| station_id | bigint unsigned | NOT NULL | — | 关联 lulu_station.id |
| route_id | bigint unsigned | NOT NULL | — | 线路Id |
| boarding_terminal | tinyint unsigned | NOT NULL | — | 1=上车点，2=下车点 |
| seq | tinyint unsigned | NOT NULL | — | 上下车点序号 |
| create_time | datetime | YES | CURRENT_TIMESTAMP | 创建时间 |
| update_time | datetime | YES | — | 修改时间 |
| create_by | bigint | YES | — | 创建人 |
| update_by | bigint | YES | — | 最后更新人 |
| del_flag | tinyint unsigned | YES | — | 1=失效 0=有效 |

**索引：** `route_id`、`station_id`

---

### lulu_gz_city

广州城市/区域编码表，用于城市映射。

| 字段 | 类型 | 可空 | 默认值 | 说明 |
|------|------|------|--------|------|
| id | int unsigned | NOT NULL | AUTO_INCREMENT | 主键 |
| city_name | varchar(50) | NOT NULL | — | 城市名 |
| district | varchar(50) | YES | — | 区 |
| city_id | varchar(20) | NOT NULL | — | 城市Id |

---

### lulu_order

主订单表，记录用户下单信息（主要是订单金额相关信息，包含单程信息）。

**订单号区分**
内部订单号(查询时使用order_no)字段:
- GZ开头
- CYW开头
- BBZ开头
- CBS开头
- CXBS开头
- YXQC开头
其他均属于外部订单号(查询时使用open_order_no)字段

**订单状态（state）：**
- `0` = 待支付
- `100` = 出票中
- `200` = 待出行
- `210` = 待出行-车辆已出发
- `260` = 已验票
- `300` = 已完成
- `350` = 已完成有退款
- `400` = 已取消
- `450` = 退款中
- `400` = 已取消
- `500` = 已退款

**退款状态（refund_state）：**
- `0` = 正常，无退款
- `-1` = 退款失败
- `100` = 退款中
- `200` = 有退款
- `300` = 已退款

| 字段 | 类型 | 可空 | 默认值 | 说明 |
|------|------|------|--------|------|
| id | bigint unsigned | NOT NULL | — | 主键 |
| order_no | varchar(32) | YES | — | 订单编号，内部订单编号，规则见上方订单号区分 |
| attachment_id | bigint | YES | — | 返程行程Id（空=无返程） |
| schedule_Id | bigint | YES | — | 班次Id |
| user_id | bigint | YES | — | 购票人Id（关联 lulu_user.id） |
| open_id | varchar(255) | YES | — | 第三方用户Id |
| client | varchar(20) | YES | — | 客户端：100=微信小程序 |
| ticket_source | varchar(20) | YES | — | 车票来源 |
| company_id | bigint | YES | — | 第三方公司Id |
| state | int | YES | — | 订单状态（见上方枚举） |
| order_type | int | YES | — | 订单类型：1=单程，2=双程 |
| refund_state | int | YES | 0 | 退款状态 |
| open_order_no | varchar(36) | YES | — | 外部订单编号，规则见上方订单号区分|
| departure_time | datetime | YES | — | 上车时间 |
| departure_province | varchar(10) | YES | — | 上车点省份 |
| departure_city | varchar(10) | YES | — | 上车点城市 |
| departure_district | varchar(10) | YES | — | 上车点区域 |
| departure_addr | varchar(255) | YES | — | 上车地点 |
| departure_position | varchar(255) | YES | — | 上车点经纬度 |
| departure_schedule_station_id | bigint | YES | — | 上车班次站点Id |
| arrive_province | varchar(10) | YES | — | 下车点省份 |
| arrive_city | varchar(10) | YES | — | 下车点城市 |
| arrive_district | varchar(10) | YES | — | 下车点区域 |
| arrive_addr | varchar(255) | YES | — | 下车地点 |
| arrive_position | varchar(255) | YES | — | 下车点经纬度 |
| arrive_schedule_station_id | bigint | YES | — | 下车班次站点Id |
| open_port_id | varchar(32) | YES | — | 口岸Id |
| price | decimal(10,2) | YES | — | 票单价 |
| total_amt | decimal(10,2) | YES | — | 总价 |
| dis_amt | decimal(10,2) | YES | — | 折扣金额 |
| actual_amt | decimal(10,2) | YES | — | 实际支付金额 |
| refund_amt | decimal(10,2) | YES | — | 退款金额 |
| refund_fee_amt | decimal(10,2) | YES | 0.00 | 退款手续费 |
| balance_amt | decimal(10,2) | YES | — | 余额 |
| tel | varchar(100) | YES | — | 跟车联系电话 |
| notice_tel | varchar(20) | YES | — | 通知电话 |
| notice_state | tinyint | NOT NULL | 0 | 通知状态：-1=已接电话，其他=通知次数 |
| coupons_id | varchar(32) | YES | — | 优惠券Id |
| license_plate | varchar(255) | YES | — | 车牌号 |
| invoice_id | bigint | YES | — | 发票Id（关联 lulu_invoice.id） |
| invoice_state | tinyint | YES | — | 发票状态：0=失败，1=成功，2=处理中 |
| create_time | datetime | YES | CURRENT_TIMESTAMP | 创建时间 |
| update_time | datetime | YES | ON UPDATE | 更新时间 |
| create_by | varchar(64) | YES | — | 创建人 |
| update_by | varchar(64) | YES | — | 最后更新人 |
| del_flag | tinyint(1) | YES | 0 | 1=失效 0=有效 |

**索引：** `order_no`、`state`、`user_id`

---

### lulu_order_itinerary

订单行程表，双程订单会有去程和返程两条记录。

**状态枚举与 `lulu_order` 相同。**

| 字段 | 类型 | 可空 | 默认值 | 说明 |
|------|------|------|--------|------|
| id | bigint unsigned | NOT NULL | — | 主键 |
| order_id | bigint | YES | — | 关联 lulu_order.id |
| order_no | varchar(32) | YES | — | 订单编号 |
| schedule_Id | bigint | YES | — | 班次Id |
| user_id | bigint | YES | — | 购票人Id |
| company_id | bigint | YES | — | 第三方公司Id |
| state | int | YES | — | 行程状态 |
| refund_state | int | YES | 0 | 退款状态 |
| itinerary | tinyint(1) | YES | 0 | 票程：1=去程，2=返程 |
| open_order_no | varchar(36) | YES | — | 外部订单编号 |
| departure_time | datetime | YES | — | 上车时间 |
| departure_province | varchar(10) | YES | — | 上车点省份 |
| departure_city | varchar(10) | YES | — | 上车点城市 |
| departure_district | varchar(10) | YES | — | 上车点区域 |
| departure_addr | varchar(255) | YES | — | 上车地点 |
| departure_position | varchar(255) | YES | — | 上车点经纬度 |
| departure_schedule_station_id | bigint | YES | — | 上车班次站点Id |
| arrive_province | varchar(10) | YES | — | 下车点省份 |
| arrive_city | varchar(10) | YES | — | 下车点城市 |
| arrive_district | varchar(10) | YES | — | 下车点区域 |
| arrive_addr | varchar(255) | YES | — | 下车地点 |
| arrive_position | varchar(255) | YES | — | 下车点经纬度 |
| arrive_schedule_station_id | bigint | YES | — | 下车班次站点Id |
| open_port_id | varchar(32) | YES | — | 口岸Id |
| total_amt | decimal(10,2) | YES | — | 总价 |
| dis_amt | decimal(10,2) | YES | — | 折扣金额 |
| actual_amt | decimal(10,2) | YES | — | 实际金额 |
| refund_amt | decimal(10,2) | YES | — | 退款金额 |
| refund_fee_amt | decimal(10,2) | YES | 0.00 | 退款手续费 |
| balance_amt | decimal(10,2) | YES | — | 余额 |
| tel | varchar(100) | YES | — | 跟车联系电话 |
| first_tel | varchar(100) | YES | — | 班次联系电话 |
| node_tel | varchar(100) | YES | — | 站点电话 |
| customer_service_tel | varchar(100) | YES | — | 线路方客服电话 |
| follow_tel | varchar(100) | YES | — | 班次跟车电话 |
| notice_tel | varchar(20) | YES | — | 通知电话 |
| notice_state | tinyint | NOT NULL | 0 | 通知状态：-1=已接电话，其他=通知次数 |
| coupons_id | varchar(32) | YES | — | 优惠券Id |
| license_plate | varchar(255) | YES | — | 车牌号 |
| invoice_id | bigint | YES | — | 发票Id |
| invoice_state | tinyint | YES | — | 发票状态：0=失败，1=成功，2=处理中 |
| create_time | datetime | YES | CURRENT_TIMESTAMP | 创建时间 |
| update_time | datetime | YES | ON UPDATE | 更新时间 |
| create_by | varchar(64) | YES | — | 创建人 |
| update_by | varchar(64) | YES | — | 最后更新人 |
| del_flag | tinyint(1) | NOT NULL | 0 | 1=失效 0=有效 |

**索引：** `order_no`、`state`、`user_id`

---

### lulu_ticket

车票表，每个乘车人对应一张票，关联到订单行程。

**票状态（state）：**
- `0` = 待支付
- `100` = 出票中
- `200` = 待出行
- `300` = 已完成
- `400` = 已取消
- `500` = 已退款

| 字段 | 类型 | 可空 | 默认值 | 说明 |
|------|------|------|--------|------|
| id | bigint unsigned | NOT NULL | — | 主键 |
| user_id | bigint | YES | — | 用户Id |
| order_id | bigint | YES | — | 关联 lulu_order.id |
| order_itinerary_id | bigint | YES | — | 关联 lulu_order_itinerary.id |
| open_order_no | varchar(36) | YES | — | 外部订单编号 |
| riders_id | bigint | YES | — | 关联 lulu_riders.id |
| schedule_id | bigint | YES | — | 班次Id |
| name | varchar(100) | YES | — | 乘车人姓名 |
| id_card | varchar(20) | YES | — | 身份证号 |
| card_type | tinyint | YES | — | 证件类型：1=身份证，2=港澳通行证 |
| riders_type | tinyint | YES | — | 乘车人类型：1=成年人，2=未成年 |
| phone | varchar(11) | YES | — | 乘车人手机号 |
| ticket_no | varchar(10) | YES | — | 票号 |
| take_ticket_no | varchar(32) | YES | — | 取票码 |
| open_ticket_no | varchar(32) | YES | — | 第三方票号 |
| seat | varchar(10) | YES | — | 座位号 |
| tick_price_type | varchar(255) | YES | — | 车票类型：1=全票，2=半票，3=优惠票 |
| price | decimal(10,2) | YES | — | 原价 |
| pay_amt | decimal(10,2) | YES | — | 支付价格 |
| refund_fee_amt | decimal(10,2) | YES | — | 退款手续费 |
| state | int | YES | — | 票状态（见上方枚举） |
| refund_state | int | YES | 0 | 退款状态 |
| itinerary | int | YES | 1 | 票程：1=去程，2=返程 |
| create_time | datetime | YES | CURRENT_TIMESTAMP | 创建时间 |
| update_time | datetime | YES | ON UPDATE | 更新时间 |
| create_by | varchar(64) | YES | — | 创建人 |
| update_by | varchar(64) | YES | — | 最后更新人 |
| del_flag | tinyint(1) | YES | 0 | 1=失效 0=有效 |

**索引：** `order_id`、`riders_id`

---

### lulu_pay

第三方支付记录表，记录每笔支付流水。

**支付状态（pay_state）：**
- `-1` = 失效
- `0` = 待支付
- `100` = 已支付
- `150` = 部分退款
- `200` = 全部退款

**退款状态（refund_state）：**
- `0` = 正常（无退款）
- `-1` = 退款失败
- `100` = 退款中
- `200` = 有退款
- `300` = 已全部退款

| 字段 | 类型 | 可空 | 默认值 | 说明 |
|------|------|------|--------|------|
| id | bigint unsigned | NOT NULL | — | 主键 |
| order_id | bigint | YES | — | 关联 lulu_order.id |
| order_no | varchar(32) | YES | — | 订单编号 |
| platform | varchar(20) | YES | — | 支付平台：alipay、weChat |
| merchant_id | varchar(36) | YES | — | 商户Id |
| trade_id | varchar(36) | YES | — | 第三方平台交易Id |
| total_amt | decimal(10,2) | YES | — | 总金额 |
| balance | decimal(10,2) | YES | — | 余额 |
| pay_state | int | YES | — | 支付状态（见上方枚举） |
| refund_state | int | YES | — | 退款状态（见上方枚举） |
| create_time | datetime | YES | CURRENT_TIMESTAMP | 创建时间 |
| update_time | datetime | YES | ON UPDATE | 更新时间 |
| create_by | varchar(64) | YES | — | 创建人 |
| update_by | varchar(64) | YES | — | 最后更新人 |
| del_flag | tinyint(1) | YES | 0 | 1=失效 0=有效 |

---

### lulu_refund

退款记录表，记录每笔退款流水。

| 字段 | 类型 | 可空 | 默认值 | 说明 |
|------|------|------|--------|------|
| id | bigint unsigned | NOT NULL | — | 主键 |
| pay_id | bigint | YES | — | 关联 lulu_pay.id |
| refund_amt | decimal(10,2) | YES | — | 退款金额 |
| total_amt | decimal(10,2) | YES | — | 订单总金额 |
| refund_no | varchar(36) | YES | — | 第三方退款单号 |
| order_no | varchar(36) | YES | — | 订单编号 |
| state | int | YES | — | 退款状态 |
| ticket_list | varchar(255) | YES | — | 车票Id列表（逗号分割） |
| refund_reason | varchar(255) | YES | — | 退款原因 |
| create_time | datetime | YES | CURRENT_TIMESTAMP | 创建时间 |
| update_time | datetime | YES | ON UPDATE | 更新时间 |
| create_by | varchar(64) | YES | — | 创建人 |
| update_by | varchar(64) | YES | — | 最后更新人 |
| del_flag | tinyint(1) | YES | 0 | 1=失效 0=有效 |

---

### lulu_invoice

发票表，记录用户申请的发票信息。

**发票类型（invoice_type）：**
- `1` = 企业
- `2` = 个人/非企业性单位

| 字段 | 类型 | 可空 | 默认值 | 说明 |
|------|------|------|--------|------|
| id | bigint | NOT NULL | — | 主键 |
| user_id | bigint | YES | — | 关联 lulu_user.id |
| order_num | int | YES | — | 订单数量 |
| invoice_type | tinyint | NOT NULL | — | 发票类型（见上方枚举） |
| invoice_title | varchar(255) | NOT NULL | — | 发票抬头 |
| taxation_number | varchar(50) | YES | — | 税号 |
| company_addr | varchar(255) | YES | — | 企业地址 |
| company_phone | varchar(255) | YES | — | 企业电话 |
| bank_name | varchar(255) | YES | — | 开户银行 |
| bank_account | varchar(255) | YES | — | 银行账户 |
| email | varchar(255) | NOT NULL | — | 邮件地址 |
| phone | varchar(255) | YES | — | 联系电话 |
| invoice_amount | decimal(10,2) | YES | — | 发票金额 |
| create_time | datetime | YES | — | 创建时间 |
| update_time | datetime | YES | — | 修改时间 |
| create_by | bigint | YES | — | 创建人 |
| update_by | bigint | YES | — | 最后修改人 |
| del_flag | tinyint | YES | — | 1=失效 0=有效 |

---

### 表关联关系

```
lulu_user
  ├── lulu_open_user   (user_id → lulu_user.id)
  ├── lulu_riders      (user_id → lulu_user.id)
  ├── lulu_invoice     (user_id → lulu_user.id)
  └── lulu_order       (user_id → lulu_user.id)
        ├── lulu_order_itinerary  (order_id → lulu_order.id)
        │     └── lulu_ticket     (order_itinerary_id → lulu_order_itinerary.id)
        ├── lulu_pay              (order_id → lulu_order.id)
        │     └── lulu_refund     (pay_id → lulu_pay.id)
        └── lulu_invoice          (invoice_id → lulu_invoice.id)

lulu_station
  └── lulu_route_station_relationship (station_id → lulu_station.id)
```