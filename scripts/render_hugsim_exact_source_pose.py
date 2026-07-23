#!/usr/bin/env python3
"""Render an official HUGSIM source frame at explicitly selected metadata poses."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
import sys
from datetime import date
from pathlib import Path, PurePosixPath
from typing import Any

import numpy as np


CAMERAS = (
    "CAM_BACK",
    "CAM_BACK_LEFT",
    "CAM_BACK_RIGHT",
    "CAM_FRONT",
    "CAM_FRONT_LEFT",
    "CAM_FRONT_RIGHT",
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def frame_camera(frame: dict[str, Any]) -> str:
    return PurePosixPath(frame["rgb_path"]).parent.name


def select_camera_records(
    metadata: dict[str, Any], frame_index: int
) -> dict[str, dict[str, Any]]:
    records = {}
    for frame in metadata.get("frames", []):
        path = PurePosixPath(frame["rgb_path"])
        if int(path.stem) != frame_index:
            continue
        camera = frame_camera(frame)
        if camera in records:
            raise ValueError(f"duplicate {camera} record for frame {frame_index}")
        records[camera] = frame
    if set(records) != set(CAMERAS):
        missing = sorted(set(CAMERAS) - set(records))
        extra = sorted(set(records) - set(CAMERAS))
        raise ValueError(
            f"frame {frame_index} is not a six-camera group; "
            f"missing={missing}, extra={extra}"
        )
    timestamps = {float(frame["timestamp"]) for frame in records.values()}
    if len(timestamps) != 1:
        raise ValueError(f"frame {frame_index} has inconsistent timestamps")
    return records


def image_metrics(real: np.ndarray, rendered: np.ndarray) -> dict[str, float]:
    real_float = np.asarray(real, dtype=np.float64) / 255.0
    rendered_float = np.asarray(rendered, dtype=np.float64) / 255.0
    if real_float.shape != rendered_float.shape:
        raise ValueError(
            f"image shape mismatch: {real_float.shape} != {rendered_float.shape}"
        )
    delta = rendered_float - real_float
    mse = float(np.mean(delta * delta))
    mae = float(np.mean(np.abs(delta)))
    psnr = math.inf if mse == 0 else float(-10.0 * math.log10(mse))
    result = {"mae": mae, "mse": mse, "psnr_db": psnr}
    try:
        from skimage.metrics import structural_similarity

        result["ssim"] = float(
            structural_similarity(
                real_float, rendered_float, channel_axis=-1, data_range=1.0
            )
        )
    except ImportError:
        result["ssim"] = None
    return result


def parse_metadata_specs(specs: list[str]) -> dict[str, Path]:
    parsed = {}
    for spec in specs:
        if "=" not in spec:
            raise ValueError("--metadata must use LABEL=PATH")
        label, raw_path = spec.split("=", 1)
        if not label or label in parsed:
            raise ValueError(f"invalid or duplicate metadata label: {label!r}")
        parsed[label] = Path(raw_path).resolve()
    if not parsed:
        raise ValueError("at least one --metadata LABEL=PATH is required")
    return parsed


def git_commit(repo: Path) -> str | None:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else None


def render_variants(args: argparse.Namespace) -> dict[str, Any]:
    import imageio.v2 as imageio
    import matplotlib.pyplot as plt
    import torch
    from omegaconf import OmegaConf

    sys.path.insert(0, str(args.hugsim_repo))
    from gaussian_renderer import GaussianModel, render
    from scene.cameras import Camera
    from scene.obj_model import ObjModel

    metadata_paths = parse_metadata_specs(args.metadata)
    metadata_by_label = {}
    records_by_label = {}
    for label, path in metadata_paths.items():
        with path.open("r", encoding="utf-8") as stream:
            metadata = json.load(stream)
        metadata_by_label[label] = metadata
        records_by_label[label] = select_camera_records(
            metadata, args.frame_index
        )

    reference_label = next(iter(records_by_label))
    reference_records = records_by_label[reference_label]
    for label, records in records_by_label.items():
        for camera in CAMERAS:
            reference = reference_records[camera]
            candidate = records[camera]
            if candidate["rgb_path"] != reference["rgb_path"]:
                raise ValueError(f"{label}/{camera} RGB path does not match reference")
            if float(candidate["timestamp"]) != float(reference["timestamp"]):
                raise ValueError(f"{label}/{camera} timestamp does not match reference")
            if np.asarray(candidate["intrinsics"]).shape not in ((3, 3), (4, 4)):
                raise ValueError(f"{label}/{camera} has invalid intrinsics")

    output = args.output.resolve()
    if output.exists():
        raise FileExistsError(f"refusing to overwrite existing output: {output}")
    output.mkdir(parents=True)

    cfg = OmegaConf.load(args.model_dir / "cfg.yaml")
    torch.manual_seed(0)
    torch.cuda.manual_seed_all(0)
    gaussians = GaussianModel(cfg.model.sh_degree, affine=cfg.affine)
    model_params, model_iteration = torch.load(
        args.model_dir / "scene.pth", map_location="cuda", weights_only=False
    )
    gaussians.restore(model_params, None)

    dynamic_ids = sorted(
        {
            dynamic_id
            for records in records_by_label.values()
            for frame in records.values()
            for dynamic_id in frame.get("dynamics", {})
        }
    )
    dynamic_gaussians = {}
    for dynamic_id in dynamic_ids:
        path = args.model_dir / f"dynamic_{dynamic_id}.pth"
        dynamic = ObjModel(cfg.model.sh_degree, feat_mutable=False)
        dynamic_params, _ = torch.load(
            path, map_location="cuda", weights_only=False
        )
        dynamic.restore(dynamic_params, None)
        dynamic_gaussians[dynamic_id] = dynamic

    bg_color = [1.0, 1.0, 1.0] if cfg.model.white_background else [0.0, 0.0, 0.0]
    background = torch.tensor(bg_color, dtype=torch.float32, device="cuda")
    real_images = {}
    real_paths = {}
    for camera, frame in reference_records.items():
        path = args.real_root / frame["rgb_path"].removeprefix("./")
        image = imageio.imread(path)
        if image.ndim != 3 or image.shape[2] < 3:
            raise ValueError(f"invalid RGB image: {path}")
        image = image[:, :, :3]
        declared_shape = (int(frame["height"]), int(frame["width"]))
        if image.shape[:2] != declared_shape:
            raise ValueError(
                f"{camera} image shape {image.shape[:2]} != {declared_shape}"
            )
        real_images[camera] = image
        real_paths[camera] = path

    variants = {}
    render_arrays: dict[str, dict[str, np.ndarray]] = {}
    for label, records in records_by_label.items():
        variant_dir = output / label
        variant_dir.mkdir()
        camera_results = {}
        render_arrays[label] = {}
        for camera in CAMERAS:
            frame = records[camera]
            real_image = real_images[camera]
            intrinsics = np.asarray(frame["intrinsics"], dtype=np.float64)
            camtoworld = np.asarray(frame["camtoworld"], dtype=np.float64)
            dynamics = {
                dynamic_id: torch.tensor(
                    matrix, dtype=torch.float32, device="cuda"
                )
                for dynamic_id, matrix in frame.get("dynamics", {}).items()
            }
            viewpoint = Camera(
                width=int(frame["width"]),
                height=int(frame["height"]),
                image=real_image.astype(np.float32) / 255.0,
                K=intrinsics,
                c2w=camtoworld,
                image_name=f"{camera}_{args.frame_index:05d}",
                data_device="cuda",
                timestamp=float(frame["timestamp"]),
                dynamics=dynamics,
            )
            with torch.no_grad():
                package = render(
                    viewpoint=viewpoint,
                    prev_viewpoint=None,
                    pc=gaussians,
                    dynamic_gaussians=dynamic_gaussians,
                    unicycles=None,
                    bg_color=background,
                    render_optical=False,
                )
            rendered_tensor = package["render"].detach()
            if not bool(torch.isfinite(rendered_tensor).all()):
                raise ValueError(f"non-finite render for {label}/{camera}")
            rendered = (
                rendered_tensor.clamp(0, 1).permute(1, 2, 0).cpu().numpy() * 255.0
            ).round().astype(np.uint8)
            render_arrays[label][camera] = rendered
            render_path = variant_dir / f"{camera}.png"
            imageio.imwrite(render_path, rendered)
            camera_results[camera] = {
                "render_path": str(render_path),
                "render_sha256": sha256_file(render_path),
                "real_path": str(real_paths[camera]),
                "real_sha256": sha256_file(real_paths[camera]),
                "width": int(frame["width"]),
                "height": int(frame["height"]),
                "timestamp_s": float(frame["timestamp"]),
                "native_dynamic_ids": sorted(frame.get("dynamics", {})),
                "metrics": image_metrics(real_image, rendered),
            }
        finite_psnr = [
            result["metrics"]["psnr_db"] for result in camera_results.values()
        ]
        variants[label] = {
            "metadata_path": str(metadata_paths[label]),
            "metadata_sha256": sha256_file(metadata_paths[label]),
            "camera_results": camera_results,
            "mean_metrics": {
                "mae": float(
                    np.mean(
                        [result["metrics"]["mae"] for result in camera_results.values()]
                    )
                ),
                "mse": float(
                    np.mean(
                        [result["metrics"]["mse"] for result in camera_results.values()]
                    )
                ),
                "psnr_db": float(np.mean(finite_psnr)),
                "ssim": float(
                    np.mean(
                        [
                            result["metrics"]["ssim"]
                            for result in camera_results.values()
                            if result["metrics"]["ssim"] is not None
                        ]
                    )
                )
                if all(
                    result["metrics"]["ssim"] is not None
                    for result in camera_results.values()
                )
                else None,
            },
        }

    figure, axes = plt.subplots(
        len(CAMERAS),
        1 + len(render_arrays),
        figsize=(5.2 * (1 + len(render_arrays)), 2.6 * len(CAMERAS)),
        squeeze=False,
    )
    labels = list(render_arrays)
    for row, camera in enumerate(CAMERAS):
        axes[row, 0].imshow(real_images[camera])
        axes[row, 0].set_title(f"{camera} — official sample RGB")
        axes[row, 0].axis("off")
        for column, label in enumerate(labels, start=1):
            axes[row, column].imshow(render_arrays[label][camera])
            score = variants[label]["camera_results"][camera]["metrics"]["psnr_db"]
            axes[row, column].set_title(f"{label} render — PSNR {score:.2f} dB")
            axes[row, column].axis("off")
    figure.tight_layout()
    comparison_path = output / "real_vs_pose_variants.png"
    figure.savefig(comparison_path, dpi=140)
    plt.close(figure)

    manifest_path = (
        args.source_archive_manifest.resolve()
        if args.source_archive_manifest is not None
        else None
    )
    result = {
        "audit_id": "hugsim_exact_source_pose_render",
        "date": date.today().isoformat(),
        "frame_index": args.frame_index,
        "timestamp_s": float(
            next(iter(reference_records.values()))["timestamp"]
        ),
        "camera_order": list(CAMERAS),
        "hugsim": {
            "repo": str(args.hugsim_repo),
            "commit": git_commit(args.hugsim_repo),
            "model_dir": str(args.model_dir),
            "scene_checkpoint_sha256": sha256_file(args.model_dir / "scene.pth"),
            "model_iteration": int(model_iteration),
            "cfg_sha256": sha256_file(args.model_dir / "cfg.yaml"),
            "dynamic_checkpoint_sha256": {
                dynamic_id: sha256_file(
                    args.model_dir / f"dynamic_{dynamic_id}.pth"
                )
                for dynamic_id in dynamic_ids
            },
        },
        "source": {
            "real_root": str(args.real_root),
            "archive_manifest": str(manifest_path) if manifest_path else None,
            "archive_manifest_sha256": (
                sha256_file(manifest_path) if manifest_path else None
            ),
        },
        "script_sha256": sha256_file(Path(__file__).resolve()),
        "variants": variants,
        "comparison_path": str(comparison_path),
        "comparison_sha256": sha256_file(comparison_path),
        "claim_boundary": (
            "This run compares current-checkpoint rendering error under declared "
            "pose metadata variants. It does not by itself establish original "
            "nuScenes token provenance, sensor equivalence, or AD equivalence."
        ),
    }
    (output / "exact_pose_render.json").write_text(
        json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hugsim-repo", type=Path, required=True)
    parser.add_argument("--model-dir", type=Path, required=True)
    parser.add_argument("--real-root", type=Path, required=True)
    parser.add_argument("--metadata", action="append", required=True)
    parser.add_argument("--frame-index", type=int, required=True)
    parser.add_argument("--source-archive-manifest", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    args.hugsim_repo = args.hugsim_repo.resolve()
    args.model_dir = args.model_dir.resolve()
    args.real_root = args.real_root.resolve()
    result = render_variants(args)
    print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
