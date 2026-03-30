"""
Itinerary PDF generation tool for the Lulu ticket system.

Generates a travel itinerary document (行程单) as a PDF file, matching
the official 路禾出行 format, and returns the output file path for the
Send tool to deliver to the user.

Dependencies: reportlab (pip install reportlab)

Assets (place in agent/tools/ticket/assets/):
    logo.png     - 路禾出行 logo (icon + text)
    tagline.png  - 粤港澳交通出行平台
    qrcode.png   - Fixed QR code image

Config keys in config.json (optional overrides):
    itinerary_font_path   - Absolute path to a TTF/TTC Chinese font file
                            Falls back to common system font paths if not set.
    itinerary_output_dir  - Directory to save generated PDFs (default: /tmp)
"""

import os
import tempfile
import time
from typing import Any, Dict, List

from agent.tools.base_tool import BaseTool, ToolResult
from common.log import logger
from config import conf

# Assets directory: agent/tools/ticket/assets/
_ASSETS_DIR = os.path.join(os.path.dirname(__file__), "assets")
_LOGO_PATH = os.path.join(_ASSETS_DIR, "logo.png")
_TAGLINE_PATH = os.path.join(_ASSETS_DIR, "tagline.png")
_QR_PATH = os.path.join(_ASSETS_DIR, "qrcode.png")

# Common system Chinese font paths (tried in order)
_SYSTEM_FONT_CANDIDATES = [
    # macOS
    "/System/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/STHeiti Medium.ttc",
    "/System/Library/Fonts/STHeiti Light.ttc",
    "/Library/Fonts/Arial Unicode MS.ttf",
    # Linux (common distributions)
    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/arphic/uming.ttc",
]


def _find_chinese_font() -> str | None:
    """Find an available Chinese font from config or system paths."""
    configured = conf().get("itinerary_font_path", "")
    if configured and os.path.exists(configured):
        return configured
    for path in _SYSTEM_FONT_CANDIDATES:
        if os.path.exists(path):
            return path
    return None


class ItineraryPdfTool(BaseTool):
    """Generate a travel itinerary PDF (行程单) from order data."""

    name: str = "itinerary_pdf"
    description: str = (
        "Generate a travel itinerary PDF (行程单) from order data and return the file path. "
        "After calling this tool, use the send tool to deliver the PDF to the user. "
        "The rows parameter should contain one entry per ticket (one row per passenger per trip leg)."
    )
    params: dict = {
        "type": "object",
        "properties": {
            "phone": {
                "type": "string",
                "description": "User phone number, masked format e.g. '158****9960'"
            },
            "invoice_title": {
                "type": "string",
                "description": "Invoice title (发票抬头). Use '-' if not available."
            },
            "invoice_no": {
                "type": "string",
                "description": "Electronic invoice number (发票号). Use '-' if not available."
            },
            "rows": {
                "type": "array",
                "description": "List of itinerary rows, one per ticket",
                "items": {
                    "type": "object",
                    "properties": {
                        "order_no": {
                            "type": "string",
                            "description": "Order number (订单号)"
                        },
                        "passenger_name": {
                            "type": "string",
                            "description": "Passenger name (乘车人)"
                        },
                        "departure_time": {
                            "type": "string",
                            "description": "Departure time, e.g. '2026-08-31 07:40:00'"
                        },
                        "departure_station": {
                            "type": "string",
                            "description": "Boarding station name (上车站点)"
                        },
                        "arrival_station": {
                            "type": "string",
                            "description": "Alighting station name (下车站点)"
                        },
                        "amount": {
                            "type": "number",
                            "description": "Ticket price in yuan (订位金额)"
                        },
                        "remark": {
                            "type": "string",
                            "description": "Remark (备注). Use '-' if none."
                        }
                    },
                    "required": [
                        "order_no", "passenger_name", "departure_time",
                        "departure_station", "arrival_station", "amount"
                    ]
                },
                "minItems": 1
            }
        },
        "required": ["phone", "rows"]
    }

    def execute(self, args: Dict[str, Any]) -> ToolResult:
        phone = args.get("phone", "-")
        invoice_title = args.get("invoice_title") or "-"
        invoice_no = args.get("invoice_no") or "-"
        rows: List[dict] = args.get("rows", [])

        if not rows:
            return ToolResult.fail("Error: rows cannot be empty")

        try:
            from reportlab.lib import colors
            from reportlab.lib.pagesizes import A4
            from reportlab.lib.units import mm
            from reportlab.pdfbase import pdfmetrics
            from reportlab.pdfbase.ttfonts import TTFont
            from reportlab.platypus import (
                SimpleDocTemplate, Table, TableStyle, Paragraph,
                Spacer, HRFlowable, Image as RLImage
            )
            from reportlab.lib.styles import ParagraphStyle
            from reportlab.lib.enums import TA_LEFT, TA_CENTER
        except ImportError:
            return ToolResult.fail(
                "reportlab is not installed. Run: pip install reportlab"
            )

        # --- Font setup ---
        font_name = "Helvetica"  # fallback
        font_path = _find_chinese_font()
        if font_path:
            try:
                pdfmetrics.registerFont(TTFont("CJK", font_path))
                font_name = "CJK"
                logger.info(f"[ItineraryPdfTool] Using font: {font_path}")
            except Exception as e:
                logger.warning(f"[ItineraryPdfTool] Failed to load font {font_path}: {e}")
        else:
            logger.warning(
                "[ItineraryPdfTool] No Chinese font found. "
                "Set itinerary_font_path in config.json or install wqy-microhei."
            )

        # --- Output path ---
        output_dir = conf().get("itinerary_output_dir", tempfile.gettempdir())
        os.makedirs(output_dir, exist_ok=True)
        timestamp = int(time.time())
        output_path = os.path.join(output_dir, f"itinerary_{timestamp}.pdf")

        # --- Build PDF ---
        try:
            self._build_pdf(
                output_path=output_path,
                font_name=font_name,
                phone=phone,
                invoice_title=invoice_title,
                invoice_no=invoice_no,
                rows=rows,
            )
        except Exception as e:
            logger.error(f"[ItineraryPdfTool] PDF generation failed: {e}", exc_info=True)
            return ToolResult.fail(f"PDF 生成失败: {str(e)}")

        total = sum(r.get("amount", 0) for r in rows)
        logger.info(
            f"[ItineraryPdfTool] Generated itinerary PDF: {output_path} "
            f"({len(rows)} rows, total={total})"
        )
        return ToolResult.success({
            "path": output_path,
            "rows": len(rows),
            "total": round(total, 2),
            "message": f"行程单已生成，共 {len(rows)} 笔行程，合计 ¥{total:.2f} 元"
        })

    def _build_pdf(
        self,
        output_path: str,
        font_name: str,
        phone: str,
        invoice_title: str,
        invoice_no: str,
        rows: List[dict],
    ):
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import mm
        from reportlab.platypus import (
            SimpleDocTemplate, Table, TableStyle, Paragraph,
            Spacer, HRFlowable, Image as RLImage, KeepTogether
        )
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
        import datetime

        PAGE_W, PAGE_H = A4
        MARGIN = 20 * mm

        doc = SimpleDocTemplate(
            output_path,
            pagesize=A4,
            leftMargin=MARGIN,
            rightMargin=MARGIN,
            topMargin=15 * mm,
            bottomMargin=15 * mm,
        )

        # Color scheme matching the sample
        GREEN = colors.HexColor("#3DAA6E")
        DARK_GRAY = colors.HexColor("#333333")
        LIGHT_GRAY = colors.HexColor("#F5F5F5")
        MID_GRAY = colors.HexColor("#888888")
        TABLE_HEADER_BG = colors.HexColor("#4A4A4A")

        # Styles
        def style(name, **kw):
            defaults = dict(fontName=font_name, fontSize=10, leading=14,
                            textColor=DARK_GRAY)
            defaults.update(kw)
            return ParagraphStyle(name, **defaults)

        title_style = style("title", fontSize=28, leading=36, textColor=DARK_GRAY,
                            fontName=font_name)
        section_style = style("section", fontSize=28, leading=36, textColor=DARK_GRAY,
                              fontName=font_name)
        label_style = style("label", fontSize=10, leading=14, textColor=MID_GRAY)
        value_style = style("value", fontSize=10, leading=14, textColor=DARK_GRAY)
        summary_style = style("summary", fontSize=11, leading=16, textColor=DARK_GRAY)
        cell_style = style("cell", fontSize=9, leading=12, textColor=DARK_GRAY)
        footer_style = style("footer", fontSize=9, leading=12, textColor=MID_GRAY,
                             alignment=TA_CENTER)

        content_width = PAGE_W - 2 * MARGIN
        today = datetime.date.today().strftime("%Y-%m-%d")
        total = sum(r.get("amount", 0) for r in rows)

        story = []

        # ── Header: right-aligned [logo+tagline | QR] block ────────────────
        has_logo = os.path.exists(_LOGO_PATH)
        has_tagline = os.path.exists(_TAGLINE_PATH)
        has_qr = os.path.exists(_QR_PATH)

        # Dimensions
        logo_w, logo_h = 42 * mm, 14 * mm   # logo image
        tag_w, tag_h   = 38 * mm, 7 * mm    # tagline image
        qr_size        = 22 * mm             # QR code (square)
        right_block_w  = logo_w + qr_size + 2 * mm
        spacer_w       = content_width - right_block_w

        # Logo cell (or text fallback)
        if has_logo:
            logo_cell = RLImage(_LOGO_PATH, width=logo_w, height=logo_h,
                                kind="proportional")
        else:
            logo_cell = Paragraph(
                '<font color="#3DAA6E"><b>路禾出行</b></font>',
                style("logo_txt", fontSize=16, leading=20, textColor=GREEN)
            )

        # Tagline cell (or text fallback)
        if has_tagline:
            tag_cell = RLImage(_TAGLINE_PATH, width=tag_w, height=tag_h,
                               kind="proportional")
        else:
            tag_cell = Paragraph(
                '<font color="#888888">粤港澳交通出行平台</font>',
                style("tag_txt", fontSize=8, leading=10, textColor=MID_GRAY)
            )

        # QR code cell spanning both rows (or empty)
        qr_cell = RLImage(_QR_PATH, width=qr_size, height=qr_size) if has_qr else ""

        # Inner right block: [[logo, qr], [tagline, qr(span)]]
        inner = Table(
            [[logo_cell, qr_cell],
             [tag_cell,  ""]],
            colWidths=[logo_w + 2 * mm, qr_size],
        )
        inner.setStyle(TableStyle([
            ("SPAN",          (1, 0), (1, 1)),   # QR spans both rows
            ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
            ("ALIGN",         (1, 0), (1, -1), "RIGHT"),
            ("TOPPADDING",    (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ("LEFTPADDING",   (0, 0), (-1, -1), 0),
            ("RIGHTPADDING",  (0, 0), (-1, -1), 0),
        ]))

        # Outer header: [empty space | inner right block]
        header_table = Table(
            [["", inner]],
            colWidths=[spacer_w, right_block_w],
        )
        header_table.setStyle(TableStyle([
            ("VALIGN",        (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING",    (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ("LEFTPADDING",   (0, 0), (-1, -1), 0),
            ("RIGHTPADDING",  (0, 0), (-1, -1), 0),
        ]))
        story.append(header_table)
        story.append(Spacer(1, 3 * mm))

        # Horizontal divider (dashed)
        story.append(HRFlowable(width="100%", thickness=0.5, color=MID_GRAY,
                                dash=(3, 3)))
        story.append(Spacer(1, 6 * mm))

        # ── Title ───────────────────────────────────────────────────────────
        story.append(Paragraph("行程单", title_style))
        story.append(Spacer(1, 6 * mm))

        # ── Meta info (2-column layout) ─────────────────────────────────────
        meta_left = [
            [Paragraph(f'<font color="#3DAA6E">▍</font>开具日期：{today}', value_style)],
            [Paragraph(f'<font color="#3DAA6E">▍</font>发票抬头：{invoice_title}', value_style)],
        ]
        meta_right = [
            [Paragraph(f'<font color="#3DAA6E">▍</font>电话号码：{phone}', value_style)],
            [Paragraph(f'<font color="#3DAA6E">▍</font>发票号：{invoice_no}', value_style)],
        ]
        half = (content_width - 8 * mm) / 2
        meta_table = Table(
            [[meta_left[0][0], meta_right[0][0]],
             [meta_left[1][0], meta_right[1][0]]],
            colWidths=[half, half],
            spaceBefore=0,
        )
        meta_table.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ]))
        story.append(meta_table)
        story.append(Spacer(1, 4 * mm))

        # Summary line
        story.append(Paragraph(
            f'<font color="#3DAA6E">▍</font>共计 <b>{len(rows)}</b> 笔行程，'
            f'合计：<b>¥{total:.1f}元</b>',
            summary_style
        ))
        story.append(Spacer(1, 10 * mm))

        # ── Section: 行程记录 ────────────────────────────────────────────────
        story.append(Paragraph("行程记录", section_style))
        story.append(Spacer(1, 4 * mm))

        # Table headers
        headers = ["序\n号", "订单号", "乘车人", "上车时间", "上车站点", "下车站点",
                   "订位金额\n（元）", "备注"]

        def cell(text):
            return Paragraph(str(text), cell_style)

        table_data = [headers]
        for i, row in enumerate(rows, 1):
            table_data.append([
                cell(str(i)),
                cell(row.get("order_no", "")),
                cell(row.get("passenger_name", "")),
                cell(row.get("departure_time", "")),
                cell(row.get("departure_station", "")),
                cell(row.get("arrival_station", "")),
                cell(f"{row.get('amount', 0):.1f}"),
                cell(row.get("remark") or "-"),
            ])

        # Table indented 5mm each side
        TABLE_INDENT = 5 * mm
        table_w = content_width - 2 * TABLE_INDENT

        col_widths_pts = [
            8 * mm,   # 序号
            28 * mm,  # 订单号
            14 * mm,  # 乘车人
            22 * mm,  # 上车时间
            28 * mm,  # 上车站点
            28 * mm,  # 下车站点
            16 * mm,  # 订位金额
            table_w - (8 + 28 + 14 + 22 + 28 + 28 + 16) * mm,  # 备注（剩余）
        ]

        rows_table = Table(table_data, colWidths=col_widths_pts, repeatRows=1,
                           hAlign="CENTER")
        rows_table.setStyle(TableStyle([
            # Header row
            ("BACKGROUND", (0, 0), (-1, 0), TABLE_HEADER_BG),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), font_name),
            ("FONTSIZE", (0, 0), (-1, 0), 9),
            ("ALIGN", (0, 0), (-1, 0), "CENTER"),
            ("VALIGN", (0, 0), (-1, 0), "MIDDLE"),
            # Alternating row colors
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT_GRAY]),
            # Borders
            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#CCCCCC")),
            ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#DDDDDD")),
            # Padding
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LEFTPADDING", (0, 0), (-1, -1), 3),
            ("RIGHTPADDING", (0, 0), (-1, -1), 3),
            # Alignment
            ("ALIGN", (0, 1), (0, -1), "CENTER"),   # 序号
            ("ALIGN", (6, 1), (6, -1), "CENTER"),   # 金额
            ("VALIGN", (0, 1), (-1, -1), "MIDDLE"),
        ]))
        story.append(rows_table)

        story.append(Spacer(1, 12 * mm))

        # ── Footer ──────────────────────────────────────────────────────────
        story.append(HRFlowable(width="100%", thickness=0.5, color=MID_GRAY,
                                dash=(3, 3)))
        story.append(Spacer(1, 3 * mm))
        if has_tagline:
            # Center the tagline image
            from reportlab.platypus import KeepInFrame
            tbl = Table([[RLImage(_TAGLINE_PATH, width=50 * mm, height=6 * mm,
                                  kind="proportional")]],
                        colWidths=[content_width])
            tbl.setStyle(TableStyle([("ALIGN", (0, 0), (-1, -1), "CENTER")]))
            story.append(tbl)
        else:
            story.append(Paragraph("粤港澳交通出行平台", footer_style))

        doc.build(story)
