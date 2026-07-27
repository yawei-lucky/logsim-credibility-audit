#!/usr/bin/env /usr/bin/python3
"""Create a one-slide editable PPTX for the CF-G→CF-I roadshow summary."""

from __future__ import annotations

import argparse
import shutil
import socket
import subprocess
import tempfile
import time
from pathlib import Path

import uno


SLIDE_W_MM = 338.667
SLIDE_H_MM = 190.5
FONT = "Noto Sans CJK SC"
FILL_NONE = uno.Enum("com.sun.star.drawing.FillStyle", "NONE")
FILL_SOLID = uno.Enum("com.sun.star.drawing.FillStyle", "SOLID")
LINE_NONE = uno.Enum("com.sun.star.drawing.LineStyle", "NONE")
LINE_SOLID = uno.Enum("com.sun.star.drawing.LineStyle", "SOLID")
LINE_DASH = uno.Enum("com.sun.star.drawing.LineStyle", "DASH")
VALIGN_TOP = uno.Enum("com.sun.star.drawing.TextVerticalAdjust", "TOP")
VALIGN_CENTER = uno.Enum("com.sun.star.drawing.TextVerticalAdjust", "CENTER")
VALIGN_BOTTOM = uno.Enum("com.sun.star.drawing.TextVerticalAdjust", "BOTTOM")
ALIGN_LEFT = uno.Enum("com.sun.star.style.ParagraphAdjust", "LEFT")
ALIGN_CENTER = uno.Enum("com.sun.star.style.ParagraphAdjust", "CENTER")
ALIGN_RIGHT = uno.Enum("com.sun.star.style.ParagraphAdjust", "RIGHT")
FONT_NORMAL = 100.0
FONT_BOLD = 150.0


def mm(value: float) -> int:
    return int(round(value * 100))


def color(value: str) -> int:
    return int(value.lstrip("#"), 16)


def point(x: float, y: float):
    item = uno.createUnoStruct("com.sun.star.awt.Point")
    item.X = mm(x)
    item.Y = mm(y)
    return item


def make_size(w: float, h: float):
    item = uno.createUnoStruct("com.sun.star.awt.Size")
    item.Width = mm(w)
    item.Height = mm(h)
    return item


def prop(name: str, value):
    item = uno.createUnoStruct("com.sun.star.beans.PropertyValue")
    item.Name = name
    item.Value = value
    return item


def wait_for_office(port: int, timeout: float = 18.0):
    local_ctx = uno.getComponentContext()
    resolver = local_ctx.ServiceManager.createInstanceWithContext(
        "com.sun.star.bridge.UnoUrlResolver", local_ctx
    )
    deadline = time.time() + timeout
    last_error = None
    while time.time() < deadline:
        try:
            return resolver.resolve(
                f"uno:socket,host=127.0.0.1,port={port};urp;"
                "StarOffice.ComponentContext"
            )
        except Exception as exc:  # LibreOffice may need a few seconds to start.
            last_error = exc
            time.sleep(0.25)
    raise RuntimeError(f"Could not connect to LibreOffice: {last_error}")


def add_rect(
    doc,
    page,
    x: float,
    y: float,
    w: float,
    h: float,
    fill: str,
    line: str | None = None,
    radius: float = 2.0,
    shadow: bool = False,
):
    shape = doc.createInstance("com.sun.star.drawing.RectangleShape")
    shape.Position = point(x, y)
    shape.Size = make_size(w, h)
    shape.FillStyle = FILL_SOLID
    shape.FillColor = color(fill)
    if line:
        shape.LineStyle = LINE_SOLID
        shape.LineColor = color(line)
        shape.LineWidth = mm(0.18)
    else:
        shape.LineStyle = LINE_NONE
    shape.CornerRadius = mm(radius)
    if shadow:
        shape.Shadow = True
        shape.ShadowColor = color("#CBD5E1")
        shape.ShadowTransparence = 72
        shape.ShadowXDistance = mm(0.7)
        shape.ShadowYDistance = mm(0.8)
    page.add(shape)
    return shape


def add_text(
    doc,
    page,
    text: str,
    x: float,
    y: float,
    w: float,
    h: float,
    *,
    size: float = 10.0,
    text_color: str = "#0F172A",
    bold: bool = False,
    align: str = "left",
    valign: str = "top",
    margin: float = 0.0,
):
    shape = doc.createInstance("com.sun.star.drawing.TextShape")
    shape.Position = point(x, y)
    shape.Size = make_size(w, h)
    shape.FillStyle = FILL_NONE
    shape.LineStyle = LINE_NONE
    shape.TextLeftDistance = mm(margin)
    shape.TextRightDistance = mm(margin)
    shape.TextUpperDistance = mm(margin)
    shape.TextLowerDistance = mm(margin)
    shape.TextAutoGrowHeight = False
    shape.TextAutoGrowWidth = False
    shape.TextVerticalAdjust = {
        "top": VALIGN_TOP,
        "center": VALIGN_CENTER,
        "bottom": VALIGN_BOTTOM,
    }[valign]
    page.add(shape)
    shape.String = text
    cursor = shape.createTextCursor()
    cursor.gotoEnd(True)
    cursor.CharFontName = FONT
    cursor.CharFontNameAsian = FONT
    cursor.CharHeight = size
    cursor.CharHeightAsian = size
    cursor.CharColor = color(text_color)
    cursor.CharWeight = FONT_BOLD if bold else FONT_NORMAL
    cursor.CharWeightAsian = FONT_BOLD if bold else FONT_NORMAL
    cursor.ParaAdjust = {
        "left": ALIGN_LEFT,
        "center": ALIGN_CENTER,
        "right": ALIGN_RIGHT,
    }[align]
    return shape


def add_line(
    doc,
    page,
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    *,
    line_color: str = "#94A3B8",
    width: float = 0.25,
    dashed: bool = False,
):
    shape = doc.createInstance("com.sun.star.drawing.LineShape")
    shape.Position = point(x1, y1)
    shape.Size = make_size(x2 - x1, y2 - y1)
    shape.LineColor = color(line_color)
    shape.LineWidth = mm(width)
    shape.LineStyle = LINE_DASH if dashed else LINE_SOLID
    page.add(shape)
    return shape


def add_card(
    doc,
    page,
    x: float,
    y: float,
    w: float,
    h: float,
    *,
    code: str,
    title: str,
    accent: str,
    intervention: str,
    observation: str,
    finding: str,
):
    add_rect(doc, page, x, y, w, h, "#FFFFFF", "#D9E2EC", 3.0, shadow=True)
    add_rect(doc, page, x, y, w, 3.2, accent, None, 3.0)
    add_rect(doc, page, x + 5, y + 7, 15.5, 7.8, accent, None, 3.8)
    add_text(
        doc,
        page,
        code,
        x + 5,
        y + 7,
        15.5,
        7.8,
        size=9.2,
        text_color="#FFFFFF",
        bold=True,
        align="center",
        valign="center",
    )
    add_text(
        doc,
        page,
        title,
        x + 24,
        y + 6.4,
        w - 29,
        9,
        size=14.2,
        text_color="#0F2744",
        bold=True,
        valign="center",
    )
    add_line(doc, page, x + 5, y + 18, x + w - 5, y + 18, line_color="#E2E8F0")

    sections = [
        ("受控干预", intervention, y + 21.5, 13.5),
        ("主要观察", observation, y + 39.5, 14.0),
        ("定性发现", finding, y + 58.0, 15.0),
    ]
    for label, body, sy, body_h in sections:
        add_text(
            doc,
            page,
            label,
            x + 5,
            sy,
            w - 10,
            5.2,
            size=8.5,
            text_color=accent,
            bold=True,
            valign="center",
        )
        add_text(
            doc,
            page,
            body,
            x + 5,
            sy + 5.1,
            w - 10,
            body_h,
            size=9.4,
            text_color="#334155",
            valign="top",
        )


def add_flow_node(
    doc,
    page,
    x: float,
    y: float,
    w: float,
    title: str,
    subtitle: str,
    *,
    fill: str,
    line: str,
):
    add_rect(doc, page, x, y, w, 20.0, fill, line, 2.8)
    add_text(
        doc,
        page,
        title,
        x + 2,
        y + 2.5,
        w - 4,
        6.2,
        size=9.0,
        text_color="#0F2744",
        bold=True,
        align="center",
        valign="center",
    )
    add_text(
        doc,
        page,
        subtitle,
        x + 2,
        y + 9,
        w - 4,
        8.0,
        size=7.8,
        text_color="#475569",
        align="center",
        valign="center",
    )


def create_slide(doc):
    pages = doc.getDrawPages()
    page = pages.getByIndex(0)
    while page.getCount():
        page.remove(page.getByIndex(0))
    page.Width = mm(SLIDE_W_MM)
    page.Height = mm(SLIDE_H_MM)

    add_rect(doc, page, 0, 0, SLIDE_W_MM, SLIDE_H_MM, "#F7F9FC", None, 0)
    add_rect(doc, page, 0, 0, 5.0, SLIDE_H_MM, "#2563EB", None, 0)

    add_text(
        doc,
        page,
        "阶段进展：从 CF-G 到 CF-I 建立反事实可信指标骨架",
        12,
        8,
        260,
        13,
        size=23.0,
        text_color="#0F2744",
        bold=True,
        valign="center",
    )
    add_rect(doc, page, 281, 10.2, 44.5, 8.5, "#E8F0FF", None, 4.0)
    add_text(
        doc,
        page,
        "第一阶段 · 定性结论",
        281,
        10.2,
        44.5,
        8.5,
        size=9.0,
        text_color="#1D4ED8",
        bold=True,
        align="center",
        valign="center",
    )
    add_text(
        doc,
        page,
        "实验对象：HUGSIM 重建场景中的动态 actor、运动/交互机制及六相机观测　｜　"
        "实验方法：保持其余条件基本不变，逐项施加可控干预并设置负对照",
        12,
        23.5,
        313,
        8.5,
        size=10.0,
        text_color="#475569",
        valign="center",
    )

    card_y = 36.0
    card_h = 76.5
    gap = 5.0
    card_w = (313.0 - gap * 3) / 4
    card_data = [
        (
            "CF-G",
            "几何一致性",
            "#2563EB",
            "同一 actor 纵向或横向移动",
            "世界坐标、深度、车道关系与相机投影",
            "测试范围内，几何关系和投影变化方向一致",
        ),
        (
            "CF-M",
            "运动一致性",
            "#0F6CBD",
            "同一路径改变初速度或加速过程",
            "位姿—速度—时间、轨迹连续性与冲突时序",
            "运动演化符合基本连续性和方向规律",
        ),
        (
            "CF-O",
            "可见性一致性",
            "#6D5BD0",
            "固定目标，只改变遮挡位置或强度",
            "深度顺序、目标可见信息与多相机支持",
            "明显遮挡增强时，目标可见信息按预期下降",
        ),
        (
            "CF-I",
            "交互因果一致性",
            "#B45309",
            "加入汇入/横穿 actor，改变到达顺序",
            "因果先后、身份连续性与交互响应",
            "形成有限因果证据；不代表现实行为分布",
        ),
    ]
    for idx, data in enumerate(card_data):
        x = 12 + idx * (card_w + gap)
        add_card(
            doc,
            page,
            x,
            card_y,
            card_w,
            card_h,
            code=data[0],
            title=data[1],
            accent=data[2],
            intervention=data[3],
            observation=data[4],
            finding=data[5],
        )
        if idx < 3:
            add_text(
                doc,
                page,
                "→",
                x + card_w,
                card_y + 31,
                gap,
                10,
                size=13.5,
                text_color="#64748B",
                bold=True,
                align="center",
                valign="center",
            )

    add_text(
        doc,
        page,
        "验证套路：从反事实规律到范围化可信声明",
        12,
        117.5,
        220,
        8,
        size=11.5,
        text_color="#0F2744",
        bold=True,
        valign="center",
    )
    add_text(
        doc,
        page,
        "当前指标骨架",
        278,
        117.5,
        47,
        8,
        size=8.8,
        text_color="#64748B",
        align="right",
        valign="center",
    )

    flow_y = 128.0
    node_widths = [44.0, 42.0, 45.0, 44.0, 50.0, 57.0]
    node_data = [
        ("受控干预", "CF-G · CF-M · CF-O · CF-I", "#E8F0FF", "#93B4E8"),
        ("有效性门", "时间 · 坐标 · 几何", "#F1F5F9", "#CBD5E1"),
        ("任务规律", "硬约束 · 单调关系 · 因果", "#F1F5F9", "#CBD5E1"),
        ("同一 AD 接收方", "感知 · 规划 · 控制", "#EDF6FF", "#A7C7E8"),
        ("稳健性审计", "效应 vs 重复误差 / 域差", "#FFF6E8", "#E8C790"),
        ("范围化可信声明", "等级＋范围＋误差＋反例", "#EAF7F0", "#9CCDB2"),
    ]
    xs = []
    x = 12.0
    flow_gap = 6.4
    for idx, (title, subtitle, fill, line) in enumerate(node_data):
        xs.append(x)
        add_flow_node(
            doc,
            page,
            x,
            flow_y,
            node_widths[idx],
            title,
            subtitle,
            fill=fill,
            line=line,
        )
        if idx < len(node_data) - 1:
            add_text(
                doc,
                page,
                "→",
                x + node_widths[idx],
                flow_y + 4.7,
                flow_gap,
                10,
                size=13.5,
                text_color="#64748B",
                bold=True,
                align="center",
                valign="center",
            )
        x += node_widths[idx] + flow_gap

    add_rect(doc, page, 61, 153.0, 43, 9.5, "#FDECEC", "#E7B6B6", 4.0)
    add_text(
        doc,
        page,
        "负对照 / 已知反例",
        61,
        153.0,
        43,
        9.5,
        size=8.3,
        text_color="#9F2D2D",
        bold=True,
        align="center",
        valign="center",
    )
    add_line(
        doc,
        page,
        82.5,
        153.0,
        xs[1] + node_widths[1] / 2,
        flow_y + 20.0,
        line_color="#C97979",
        width=0.22,
        dashed=True,
    )

    add_rect(doc, page, 237, 153.0, 46, 9.5, "#FFF2D9", "#E6C47A", 4.0)
    add_text(
        doc,
        page,
        "真实数据 / 独立参考",
        237,
        153.0,
        46,
        9.5,
        size=8.3,
        text_color="#8A5A00",
        bold=True,
        align="center",
        valign="center",
    )
    add_line(
        doc,
        page,
        260.0,
        153.0,
        xs[4] + node_widths[4] / 2,
        flow_y + 20.0,
        line_color="#C69A43",
        width=0.22,
        dashed=True,
    )

    add_rect(doc, page, 12, 169.5, 313, 12.5, "#0F2744", None, 3.0)
    add_text(
        doc,
        page,
        "阶段结论｜已形成“几何—运动—可见性—交互”的指标骨架；"
        "当前支持有限机制一致性，不代表现实等效。闭环结果仍为定性证据。",
        17,
        169.5,
        303,
        12.5,
        size=10.1,
        text_color="#FFFFFF",
        bold=True,
        align="center",
        valign="center",
    )
    return page


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path("artifacts/roadshow/cf-g-to-cf-i-slide-run001"),
    )
    args = parser.parse_args()
    out_dir = args.out_dir.resolve()
    if out_dir.exists():
        raise SystemExit(f"Refusing to overwrite existing output directory: {out_dir}")
    out_dir.mkdir(parents=True)

    pptx_path = out_dir / "cf_g_to_cf_i_credibility_progress.pptx"
    pdf_path = out_dir / "cf_g_to_cf_i_credibility_progress.pdf"
    preview_base = out_dir / "cf_g_to_cf_i_credibility_progress_preview"

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]

    office_profile = Path(tempfile.mkdtemp(prefix="codex-lo-profile-"))
    office_log = (out_dir / "libreoffice.log").open("w", encoding="utf-8")
    office = subprocess.Popen(
        [
            "soffice",
            "--headless",
            "--nologo",
            "--nodefault",
            "--nolockcheck",
            "--norestore",
            "--nofirststartwizard",
            f"-env:UserInstallation=file://{office_profile}",
            f"--accept=socket,host=127.0.0.1,port={port};urp;StarOffice.ServiceManager",
        ],
        stdout=office_log,
        stderr=subprocess.STDOUT,
    )

    doc = None
    try:
        ctx = wait_for_office(port)
        smgr = ctx.ServiceManager
        desktop = smgr.createInstanceWithContext("com.sun.star.frame.Desktop", ctx)
        doc = desktop.loadComponentFromURL(
            "private:factory/simpress",
            "_blank",
            0,
            (prop("Hidden", True),),
        )
        create_slide(doc)
        doc.storeAsURL(
            uno.systemPathToFileUrl(str(pptx_path)),
            (
                prop("FilterName", "Impress MS PowerPoint 2007 XML"),
                prop("Overwrite", False),
            ),
        )
        doc.storeToURL(
            uno.systemPathToFileUrl(str(pdf_path)),
            (
                prop("FilterName", "impress_pdf_Export"),
                prop("Overwrite", False),
            ),
        )
        doc.close(True)
        doc = None
    finally:
        if doc is not None:
            try:
                doc.close(True)
            except Exception:
                pass
        office.terminate()
        try:
            office.wait(timeout=5)
        except subprocess.TimeoutExpired:
            office.kill()
        office_log.close()
        shutil.rmtree(office_profile, ignore_errors=True)

    subprocess.run(
        [
            "pdftoppm",
            "-png",
            "-singlefile",
            "-r",
            "160",
            str(pdf_path),
            str(preview_base),
        ],
        check=True,
    )
    print(pptx_path)
    print(pdf_path)
    print(preview_base.with_suffix(".png"))


if __name__ == "__main__":
    main()
