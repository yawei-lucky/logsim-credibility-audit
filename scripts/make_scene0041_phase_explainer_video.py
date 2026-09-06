#!/usr/bin/env python3
"""Build an honest explainer video from the four formal scene-0041 samples.

The source experiment rendered only frames 30, 36, 42 and 48 for the fixed
SparseDrive history.  This script deliberately holds those observations on
screen; it does not interpolate images or imply that they form a dense video.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


FRAME_SPECS = (
    (30, 2.5474770069122314),
    (36, 3.0473530292510986),
    (42, 3.5477938652038574),
    (48, 4.0488080978393555),
)

CONDITIONS = (
    {
        "id": "separated",
        "title": "separated  c = +0.50 s",
        "actor_interval": (0.11, 4.30),
        "explanation": "对方车先离开 C，0.50 s 后自车才进入",
    },
    {
        "id": "boundary",
        "title": "boundary  c = 0.00 s",
        "actor_interval": (0.61, 4.80),
        "explanation": "对方车离开 C 的同时，自车进入 C",
    },
    {
        "id": "overlap",
        "title": "overlap  c = -1.00 s",
        "actor_interval": (1.61, 5.80),
        "explanation": "两车在 C 内同时占用 1.00 s",
    },
)

EGO_INTERVAL = (4.80, 6.97)
FONT_REGULAR = Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc")
FONT_MEDIUM = Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Medium.ttc")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input-root",
        type=Path,
        default=Path("artifacts/hugsim_scene0041_opposing_path_dynamic"),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(
            "artifacts/hugsim_scene0041_opposing_path_dynamic/"
            "presentation-video-run001"
        ),
    )
    parser.add_argument("--fps", type=int, default=12)
    return parser.parse_args()


def font(size: int, medium: bool = False) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONT_MEDIUM if medium else FONT_REGULAR), size)


def text_center(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    value: str,
    selected_font: ImageFont.FreeTypeFont,
    fill: tuple[int, int, int],
) -> None:
    box = draw.textbbox((0, 0), value, font=selected_font)
    width = box[2] - box[0]
    draw.text((xy[0] - width / 2, xy[1]), value, font=selected_font, fill=fill)


def fit_image(path: Path, size: tuple[int, int]) -> Image.Image:
    source = Image.open(path).convert("RGB")
    target_ratio = size[0] / size[1]
    source_ratio = source.width / source.height
    if source_ratio > target_ratio:
        crop_width = int(source.height * target_ratio)
        left = (source.width - crop_width) // 2
        source = source.crop((left, 0, left + crop_width, source.height))
    elif source_ratio < target_ratio:
        crop_height = int(source.width / target_ratio)
        top = (source.height - crop_height) // 2
        source = source.crop((0, top, source.width, top + crop_height))
    return source.resize(size, Image.Resampling.LANCZOS)


def draw_timeline(
    canvas: Image.Image,
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    width: int,
    condition: dict[str, object],
    timestamp_s: float,
) -> None:
    axis_left = x + 46
    axis_right = x + width - 12
    t_max = 7.2

    def px(t: float) -> int:
        return int(axis_left + (axis_right - axis_left) * t / t_max)

    actor_start, actor_end = condition["actor_interval"]
    ego_start, ego_end = EGO_INTERVAL
    label_font = font(17)
    tick_font = font(14)
    draw.text((x + 2, y + 23), "对方", font=label_font, fill=(184, 92, 33))
    draw.text((x + 2, y + 62), "自车", font=label_font, fill=(36, 99, 166))
    draw.rounded_rectangle(
        (px(float(actor_start)), y + 20, px(float(actor_end)), y + 43),
        radius=5,
        fill=(223, 127, 63),
    )
    draw.rounded_rectangle(
        (px(ego_start), y + 59, px(ego_end), y + 82),
        radius=5,
        fill=(66, 133, 205),
    )
    overlap_left = max(float(actor_start), ego_start)
    overlap_right = min(float(actor_end), ego_end)
    if overlap_right > overlap_left:
        draw.rectangle(
            (px(overlap_left), y + 17, px(overlap_right), y + 85),
            fill=(194, 49, 49, 70),
        )
        draw.rounded_rectangle(
            (px(float(actor_start)), y + 20, px(float(actor_end)), y + 43),
            radius=5,
            fill=(223, 127, 63),
        )
        draw.rounded_rectangle(
            (px(ego_start), y + 59, px(ego_end), y + 82),
            radius=5,
            fill=(66, 133, 205),
        )

    for tick in (0, 2, 4, 6):
        tick_x = px(float(tick))
        draw.line((tick_x, y + 88, tick_x, y + 94), fill=(120, 126, 135), width=1)
        text_center(draw, (tick_x, y + 96), str(tick), tick_font, (100, 106, 115))
    now_x = px(timestamp_s)
    draw.line((now_x, y + 10, now_x, y + 88), fill=(30, 30, 33), width=3)
    text_center(draw, (now_x, y - 11), "当前", tick_font, (30, 30, 33))
    draw.line((axis_left, y + 88, axis_right, y + 88), fill=(100, 106, 115), width=1)
    draw.text((axis_right - 22, y + 96), "s", font=tick_font, fill=(100, 106, 115))


def sample_frame(input_root: Path, frame_index: int, timestamp_s: float) -> Image.Image:
    canvas = Image.new("RGB", (1600, 1000), (244, 246, 249))
    draw = ImageDraw.Draw(canvas, "RGBA")
    title_font = font(34, medium=True)
    sub_font = font(22)
    condition_font = font(24, medium=True)
    camera_font = font(16)
    explanation_font = font(18)
    dark = (26, 30, 36)
    muted = (92, 99, 110)

    text_center(
        draw,
        (800, 18),
        f"scene-0041 对向路径相位实验｜正式输入 frame {frame_index}，t={timestamp_s:.3f} s",
        title_font,
        dark,
    )
    text_center(
        draw,
        (800, 63),
        "银色车是唯一被改变的对象；三档速度相同，只改变它到达公共冲突区域 C 的时刻",
        sub_font,
        muted,
    )

    panel_width = 500
    image_size = (480, 270)
    x_values = (30, 550, 1070)
    for x, condition in zip(x_values, CONDITIONS):
        centre_x = x + panel_width // 2
        text_center(draw, (centre_x, 98), str(condition["title"]), condition_font, dark)
        frame_dir = input_root / f"formal-render-frame{frame_index:03d}-run001"
        front_left = fit_image(
            frame_dir / str(condition["id"]) / "CAM_FRONT_LEFT.png", image_size
        )
        front = fit_image(
            frame_dir / str(condition["id"]) / "CAM_FRONT.png", image_size
        )
        canvas.paste(front_left, (x + 10, 140))
        canvas.paste(front, (x + 10, 447))
        text_center(draw, (centre_x, 118), "左前相机", camera_font, muted)
        text_center(draw, (centre_x, 425), "前相机", camera_font, muted)
        draw_timeline(canvas, draw, x + 10, 754, 480, condition, timestamp_s)
        text_center(
            draw,
            (centre_x, 881),
            str(condition["explanation"]),
            explanation_font,
            dark,
        )

    text_center(
        draw,
        (800, 950),
        "黑线是当前采样时刻；彩色横条是车辆未来占用冲突区域 C 的时间段",
        sub_font,
        dark,
    )
    text_center(
        draw,
        (800, 978),
        "仅使用 4 个真实渲染采样并停帧展示；没有生成或插值中间画面",
        font(16),
        muted,
    )
    return canvas


def title_frame() -> Image.Image:
    canvas = Image.new("RGB", (1600, 1000), (244, 246, 249))
    draw = ImageDraw.Draw(canvas)
    dark = (26, 30, 36)
    muted = (92, 99, 110)
    text_center(draw, (800, 215), "scene-0041：三个 c 到底表示什么", font(52, True), dark)
    lines = (
        "场景：自车沿日志轨迹左转；银色对向车沿固定直线以 4 m/s 行驶。",
        "两条车身走廊的交集定义为公共冲突区域 C。",
        "c = 后进入 C 的时刻 − 先离开 C 的时刻。",
        "正数：错开；零：时间边界相接；负数：同时占用。",
    )
    for index, line in enumerate(lines):
        text_center(draw, (800, 360 + index * 72), line, font(28), dark)
    text_center(
        draw,
        (800, 735),
        "注意：c=0 只是本实验的几何边界，不是现实中的安全阈值。",
        font(24),
        muted,
    )
    return canvas


def ending_frame() -> Image.Image:
    canvas = Image.new("RGB", (1600, 1000), (244, 246, 249))
    draw = ImageDraw.Draw(canvas)
    dark = (26, 30, 36)
    muted = (92, 99, 110)
    text_center(draw, (800, 195), "看视频时最容易误解的一点", font(48, True), dark)
    lines = (
        "最后一个输入帧里，separated 的车反而最大、看起来最近，",
        "因为它更早经过了冲突区；overlap 的车较远，但未来与自车同占 C。",
        "所以 c 测的是未来路径的时间关系，不是当前画面中的像素距离。",
    )
    for index, line in enumerate(lines):
        text_center(draw, (800, 350 + index * 78), line, font(30), dark)
    text_center(
        draw,
        (800, 700),
        "本实验只能说明设计的相位变化进入了 HUGSIM RGB，并引起 SparseDrive 可分辨响应；",
        font(24),
        muted,
    )
    text_center(
        draw,
        (800, 743),
        "由于 3 s 计划窗口被冲突区截断，不能据此裁决 AD 是否正确化解冲突。",
        font(24),
        muted,
    )
    return canvas


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=False)
    frame_dir = args.output_dir / "frames"
    frame_dir.mkdir()
    source_files: list[Path] = []
    rendered: list[tuple[Image.Image, int]] = [
        (title_frame(), 3 * args.fps),
    ]
    for frame_index, timestamp_s in FRAME_SPECS:
        rendered.append((sample_frame(args.input_root, frame_index, timestamp_s), 2 * args.fps))
        for condition in CONDITIONS:
            for camera in ("CAM_FRONT_LEFT", "CAM_FRONT"):
                source_files.append(
                    args.input_root
                    / f"formal-render-frame{frame_index:03d}-run001"
                    / str(condition["id"])
                    / f"{camera}.png"
                )
    rendered.append((ending_frame(), 4 * args.fps))

    frame_number = 0
    cover_path = args.output_dir / "scene0041_phase_explainer_cover.png"
    for image, repeat in rendered:
        if frame_number == 3 * args.fps + 6 * args.fps:
            image.save(cover_path)
        for _ in range(repeat):
            image.save(frame_dir / f"frame_{frame_number:04d}.png")
            frame_number += 1

    video_path = args.output_dir / "scene0041_phase_explainer.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-framerate",
            str(args.fps),
            "-i",
            str(frame_dir / "frame_%04d.png"),
            "-c:v",
            "libx264",
            "-preset",
            "medium",
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
        "fps": args.fps,
        "duration_s": frame_number / args.fps,
        "source_samples": [
            {"frame_index": index, "timestamp_s": timestamp}
            for index, timestamp in FRAME_SPECS
        ],
        "source_policy": "exact formal samples held on screen; no interpolated images",
        "source_sha256": {
            str(path.resolve()): sha256(path) for path in source_files
        },
        "condition_intervals_s": {
            str(condition["id"]): {
                "actor": condition["actor_interval"],
                "ego": EGO_INTERVAL,
            }
            for condition in CONDITIONS
        },
    }
    manifest_path = args.output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    print(video_path.resolve())


if __name__ == "__main__":
    main()
