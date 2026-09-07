#!/usr/bin/env python3
"""Show scene-0041 formal camera history and SparseDrive plans together."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw

from make_scene0041_phase_explainer_video import (
    FRAME_SPECS,
    fit_image,
    font,
    sha256,
    text_center,
)


CONDITIONS = (
    ("factual", "无注入车辆", None, (84, 90, 99)),
    ("separated", "separated", "+0.50 s", (35, 139, 111)),
    ("boundary", "boundary", "0.00 s", (218, 104, 24)),
    ("overlap", "overlap", "−1.00 s", (112, 100, 178)),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input-root",
        type=Path,
        default=Path("artifacts/hugsim_scene0041_opposing_path_dynamic"),
    )
    parser.add_argument(
        "--receiver-json",
        type=Path,
        default=Path(
            "artifacts/hugsim_scene0041_opposing_path_dynamic/"
            "sparsedrive-sequences-run001/sparsedrive_exact_render_sequence.json"
        ),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(
            "artifacts/hugsim_scene0041_opposing_path_dynamic/"
            "presentation-video-run002"
        ),
    )
    parser.add_argument("--fps", type=int, default=12)
    return parser.parse_args()


def load_plans(path: Path) -> dict[str, list[list[float]]]:
    report = json.loads(path.read_text())
    return {
        condition: [[0.0, 0.0]]
        + report["runs"][condition]["replicate_1"]["frames"][-1]["native"][
            "final_planning_values"
        ]
        for condition, _, _, _ in CONDITIONS
    }


def base_canvas(frame_index: int, timestamp_s: float, input_root: Path) -> Image.Image:
    canvas = Image.new("RGB", (1600, 1000), (244, 246, 249))
    draw = ImageDraw.Draw(canvas)
    dark = (27, 31, 37)
    muted = (92, 99, 110)
    text_center(
        draw,
        (800, 14),
        "同一场景、同一SparseDrive：车辆相位变化如何改变3秒规划",
        font(35, True),
        dark,
    )
    text_center(
        draw,
        (800, 58),
        f"正式输入 frame {frame_index}｜t={timestamp_s:.3f} s｜下方轨迹将在四帧历史输入完成后显示",
        font(20),
        muted,
    )
    panel_width = 380
    image_size = (364, 205)
    for index, (condition, label, c_value, colour) in enumerate(CONDITIONS):
        x = 20 + index * 395
        title = label if c_value is None else f"{label}  c={c_value}"
        text_center(draw, (x + panel_width // 2, 91), title, font(21, True), colour)
        image_path = (
            input_root
            / f"formal-render-frame{frame_index:03d}-run001"
            / condition
            / "CAM_FRONT.png"
        )
        canvas.paste(fit_image(image_path, image_size), (x + 8, 126))
    draw.line((32, 356, 1568, 356), fill=(190, 195, 202), width=1)
    return canvas


def map_plan_point(
    point: list[float] | tuple[float, float], rect: tuple[int, int, int, int]
) -> tuple[int, int]:
    right_m, forward_m = point
    x_min, x_max = -7.5, 0.5
    y_min, y_max = 0.0, 15.5
    left, top, right, bottom = rect
    x = left + (float(right_m) - x_min) / (x_max - x_min) * (right - left)
    y = bottom - (float(forward_m) - y_min) / (y_max - y_min) * (bottom - top)
    return round(x), round(y)


def partial_plan(points: list[list[float]], progress: float) -> list[tuple[float, float]]:
    progress = max(0.0, min(progress, len(points) - 1))
    whole = int(progress)
    result = [tuple(point) for point in points[: whole + 1]]
    if whole < len(points) - 1 and progress > whole:
        fraction = progress - whole
        start = points[whole]
        end = points[whole + 1]
        result.append(
            (
                start[0] + fraction * (end[0] - start[0]),
                start[1] + fraction * (end[1] - start[1]),
            )
        )
    return result


def draw_plan_plot(
    canvas: Image.Image,
    plans: dict[str, list[list[float]]],
    reveal: float,
    show_summary: bool,
) -> None:
    draw = ImageDraw.Draw(canvas, "RGBA")
    dark = (27, 31, 37)
    muted = (92, 99, 110)
    plot = (95, 420, 940, 900)
    left, top, right, bottom = plot
    text_center(draw, ((left + right) // 2, 371), "SparseDrive原生3秒规划（统一坐标尺）", font(25, True), dark)

    for forward in (0, 3, 6, 9, 12, 15):
        y = map_plan_point((0, forward), plot)[1]
        draw.line((left, y, right, y), fill=(205, 209, 215), width=1)
        draw.text((left - 42, y - 11), str(forward), font=font(15), fill=muted)
    for right_m in (-7, -5, -3, -1, 0):
        x = map_plan_point((right_m, 0), plot)[0]
        draw.line((x, top, x, bottom), fill=(218, 221, 226), width=1)
        text_center(draw, (x, bottom + 7), str(right_m), font(15), muted)
    draw.rectangle(plot, outline=(145, 151, 160), width=1)
    draw.text((left - 78, top + 178), "前进 (m)", font=font(17), fill=dark)
    text_center(draw, ((left + right) // 2, bottom + 36), "横向：右为正、左为负 (m)", font(17), dark)

    for condition, label, c_value, colour in CONDITIONS:
        visible = partial_plan(plans[condition], reveal)
        pixels = [map_plan_point(point, plot) for point in visible]
        if len(pixels) > 1:
            draw.line(pixels, fill=colour, width=6, joint="curve")
        for point in pixels[1:]:
            draw.ellipse(
                (point[0] - 6, point[1] - 6, point[0] + 6, point[1] + 6),
                fill=colour,
            )
    origin_x, origin_y = map_plan_point((0.0, 0.0), plot)
    draw.ellipse(
        (origin_x - 8, origin_y - 8, origin_x + 8, origin_y + 8),
        fill=dark,
    )
    draw.text((origin_x - 74, origin_y - 30), "当前车位", font=font(16, True), fill=dark)

    side_x = 1000
    draw.text((side_x, 397), "3秒末端前进量", font=font(25, True), fill=dark)
    final_values = {
        condition: plans[condition][-1][1] for condition, _, _, _ in CONDITIONS
    }
    for index, (condition, label, c_value, colour) in enumerate(CONDITIONS):
        y = 450 + index * 57
        draw.text((side_x, y), label, font=font(20), fill=colour)
        draw.text(
            (1258, y),
            f"{final_values[condition]:.3f} m",
            font=font(20, True),
            fill=colour,
        )

    if show_summary:
        draw.line((side_x, 690, 1545, 690), fill=(190, 195, 202), width=1)
        draw.text((side_x, 716), "最明显的两层变化", font=font(24, True), fill=dark)
        draw.text(
            (side_x, 765),
            "① 有车条件比无车少前进 2.310–3.428 m",
            font=font(20),
            fill=dark,
        )
        draw.text(
            (side_x, 810),
            "② overlap反而比boundary多前进 1.118 m",
            font=font(20),
            fill=dark,
        )
        draw.text(
            (side_x, 855),
            "重复运行误差上限仅 0.0000305 m",
            font=font(19),
            fill=muted,
        )
        draw.text(
            (side_x, 900),
            "结论：响应真实可分辨，但不是简单的“越危险越减速”",
            font=font(19, True),
            fill=(166, 69, 36),
        )
    else:
        draw.text(
            (side_x, 735),
            "正在按0.5秒步长展开模型输出……",
            font=font(20),
            fill=muted,
        )

    text_center(
        draw,
        (800, 965),
        "轨迹是frame 48之后的SparseDrive预测规划，不是已经执行的闭环行驶轨迹",
        font(18),
        muted,
    )


def title_frame() -> Image.Image:
    canvas = Image.new("RGB", (1600, 1000), (244, 246, 249))
    draw = ImageDraw.Draw(canvas)
    dark = (27, 31, 37)
    muted = (92, 99, 110)
    text_center(draw, (800, 235), "最清楚的一段结果：画面变化＋规划响应", font(49, True), dark)
    text_center(
        draw,
        (800, 360),
        "先播放SparseDrive真正接收的4个相机采样，再在同一坐标尺上展开4条规划。",
        font(27),
        dark,
    )
    text_center(
        draw,
        (800, 435),
        "比较：无注入车辆、separated、boundary、overlap。",
        font(27),
        dark,
    )
    text_center(
        draw,
        (800, 570),
        "规划点间隔0.5秒，总时域3秒；所有条件使用同一模型和同一左转指令。",
        font(24),
        muted,
    )
    return canvas


def main() -> None:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=False)
    frames_dir = args.output_dir / "frames"
    frames_dir.mkdir()
    plans = load_plans(args.receiver_json)
    video_frames: list[Image.Image] = []

    video_frames.extend([title_frame()] * (2 * args.fps))
    for frame_index, timestamp_s in FRAME_SPECS:
        frame = base_canvas(frame_index, timestamp_s, args.input_root)
        draw = ImageDraw.Draw(frame)
        text_center(
            draw,
            (800, 620),
            "正在形成四帧历史输入……",
            font(29, True),
            (82, 89, 99),
        )
        video_frames.extend([frame] * args.fps)

    final_index, final_timestamp = FRAME_SPECS[-1]
    reveal_frames = 4 * args.fps
    for index in range(reveal_frames):
        frame = base_canvas(final_index, final_timestamp, args.input_root)
        reveal = 6.0 * (index + 1) / reveal_frames
        draw_plan_plot(frame, plans, reveal, show_summary=False)
        video_frames.append(frame)
    final_frame = base_canvas(final_index, final_timestamp, args.input_root)
    draw_plan_plot(final_frame, plans, 6.0, show_summary=True)
    video_frames.extend([final_frame] * (5 * args.fps))

    cover_path = args.output_dir / "scene0041_receiver_result_cover.png"
    final_frame.save(cover_path)
    for index, frame in enumerate(video_frames):
        frame.save(frames_dir / f"frame_{index:04d}.png")

    video_path = args.output_dir / "scene0041_receiver_result.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-framerate",
            str(args.fps),
            "-i",
            str(frames_dir / "frame_%04d.png"),
            "-c:v",
            "libx264",
            "-crf",
            "18",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(video_path),
        ],
        check=True,
    )
    manifest = {
        "artifact": str(video_path.resolve()),
        "artifact_sha256": sha256(video_path),
        "cover": str(cover_path.resolve()),
        "duration_s": len(video_frames) / args.fps,
        "fps": args.fps,
        "camera_samples": [
            {"frame_index": index, "timestamp_s": timestamp}
            for index, timestamp in FRAME_SPECS
        ],
        "camera_policy": "exact formal CAM_FRONT samples held on screen; no interpolation",
        "plan_source": str(args.receiver_json.resolve()),
        "plan_source_sha256": sha256(args.receiver_json),
        "plan_role": "SparseDrive 3 s prediction at frame 48; not executed closed-loop motion",
    }
    (args.output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n"
    )
    print(video_path.resolve())


if __name__ == "__main__":
    main()
