# 2026-03-30 工作笔记：行程单 PDF 工具开发与部署踩坑

## 一、完成内容

```
agent/tools/ticket/itinerary_pdf_tool.py   # ItineraryPdfTool：生成行程单 PDF
agent/tools/ticket/assets/                 # logo.png、tagline.png、qrcode.png
skills/itinerary/SKILL.md                  # 行程单开具流程
```

同步新增/注册：
- `agent/tools/__init__.py`：注册 `ItineraryPdfTool`
- `requirements.txt`：新增 `reportlab`

---

## 二、部署踩坑

### 1. Python 3.6 兼容性问题

**现象**：服务器 Python 3.6.8，导入模块时报错

**原因**：代码中使用了 `str | None` 联合类型语法，这是 Python 3.10+ 特性

**修复**：
```python
# 改前
from typing import Any, Dict, List
def _find_chinese_font() -> str | None:

# 改后
from typing import Any, Dict, List, Optional
def _find_chinese_font() -> Optional[str]:
```

**后续**：计划将服务器 Python 升级到 3.9

---

### 2. reportlab 安装失败

**现象**：`pip install reportlab` 编译 C 扩展时出错

**修复**：使用预编译二进制包
```bash
pip install --only-binary=:all: reportlab
```

---

### 3. 中文字体路径不对

**现象**：代码内置候选路径在服务器上不存在，PDF 中文显示异常

**实际路径**（CentOS 服务器）：
```
/usr/share/fonts/wqy-microhei/wqy-microhei.ttc
```

**内置候选路径**（原来只有）：
```
/usr/share/fonts/truetype/wqy/wqy-microhei.ttc   # Ubuntu 路径，不存在
```

**修复**：`_SYSTEM_FONT_CANDIDATES` 中新增以下路径：
```python
"/usr/share/fonts/wqy-microhei/wqy-microhei.ttc",
"/usr/share/fonts/wqy-microhei/wqy-microhei.ttf",
"/usr/share/fonts/wqy-zenhei/wqy-zenhei.ttc",
```

**字体安装**：
```bash
# CentOS
yum install -y wqy-microhei-fonts
# Ubuntu
apt-get install -y fonts-wqy-microhei
```

**备选**：在 `config.json` 中显式指定：
```json
"itinerary_font_path": "/usr/share/fonts/wqy-microhei/wqy-microhei.ttc"
```

---

### 4. 透明 PNG 图片无法在 PDF 中显示

**现象**：logo、tagline、qrcode 三张图片均为透明背景 PNG，reportlab 渲染结果图片不显示

**原因**：reportlab 对带 alpha 通道的 PNG 处理不稳定

**修复**：新增 `_flatten_png()` 函数，用 Pillow 将透明 PNG 合成到白底后再传给 reportlab：
```python
def _flatten_png(src_path: str) -> str:
    from PIL import Image as PILImage
    img = PILImage.open(src_path).convert("RGBA")
    bg = PILImage.new("RGBA", img.size, (255, 255, 255, 255))
    bg.paste(img, mask=img.split()[3])
    flat = bg.convert("RGB")
    tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    flat.save(tmp.name, "PNG")
    return tmp.name
```

所有图片加载时均经过此函数处理。Pillow 已在 requirements.txt 中，无需额外安装。

---

## 三、PDF 布局调整记录

| 问题 | 修复方式 |
|------|----------|
| logo/tagline/QR 位置错乱 | header 改为 [空白 \| 右侧块]，右侧块内 QR 跨 2 行 |
| "行程记录"标题字号过小 | `section_style` fontSize 改为 28（与"行程单"标题一致） |
| 表格两侧无边距 | 增加 `TABLE_INDENT=5mm`，`hAlign="CENTER"` |
| "共计X笔"不与上方左对齐 | 移入 meta_table 第三行并 SPAN 全宽 |
| 订位金额列文字溢出 | 列宽从 16mm 增至 20mm |

---

## 四、关键业务逻辑备忘

- `lulu_order_itinerary.itinerary`：**1=去程，2=返程**
- 行程单每行 = 一条 `lulu_order_itinerary` × 一张 `lulu_ticket`（关联字段：`lulu_ticket.order_itinerary_id = lulu_order_itinerary.id`）
- `amount` 取 `lulu_ticket.pay_amt`
- 备注：`oi.refund_fee_amt > 0` → `"退票手续费"`，否则 `"-"`
- 手机号从 `lulu_user` 表取（**不是** `sys_user`）
- 一张发票可关联多个订单（通过 `lulu_order.invoice_id` FK）
