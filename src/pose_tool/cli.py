"""命令行入口：pose render / diff / batch / index / schema。"""

from __future__ import annotations

import json
from pathlib import Path

import typer

from .angles import compute_joint_angles, format_angles
from .batch import batch_render
from .bvh import export_bvh_to_file
from .depth import render_depth_to_png
from .diff import diff_poses, format_report
from .library import write_index
from .recognize import DEFAULT_CONFIG_PATH, load_recognize_config, recognize_image
from .render import render_to_png
from .schema import export_json_schema, load_pose


@app.command("pose-detect")
def pose_detect_cmd(
    image: Path = typer.Argument(..., exists=True, dir_okay=False, help="动作图片（jpg/png）"),
    output: Path = typer.Option(..., "--output", "-o", help="输出 pose.json 路径"),
    model_dir: Path = typer.Option(None, "--model-dir", help="DWPose ONNX 模型目录"),
) -> None:
    """用 DWPose 本地识别动作图片 → pose.json（2D 资产，无 3D/朝向）。"""
    from .dwpose import detect_to_pose_dict

    data = detect_to_pose_dict(image, model_dir)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    typer.echo(f"已识别 → {output}")

app = typer.Typer(
    help="zzdzz-pose-tool：把姿态当作可版本管理的工程资产（MVP）",
    no_args_is_help=True,
)


@app.command("render")
def render_cmd(
    pose_path: Path = typer.Argument(..., exists=True, dir_okay=False, help="pose.json 路径"),
    output: Path = typer.Option(..., "--output", "-o", help="输出 PNG 路径"),
    person: int = typer.Option(0, "--person", help="渲染第几个人"),
    depth: bool = typer.Option(False, "--depth", help="渲染深度图（需 pose_keypoints_3d）而非骨架图"),
) -> None:
    """把单个 pose.json 渲染成 ControlNet 控制图（骨架图或深度图）。"""
    pose = load_pose(pose_path)
    if depth:
        out = render_depth_to_png(pose, output, person_index=person)
    else:
        out = render_to_png(pose, output, person_index=person)
    typer.echo(f"已渲染 → {out}")


@app.command("export-bvh")
def export_bvh_cmd(
    pose_path: Path = typer.Argument(..., exists=True, dir_okay=False, help="pose.json 路径"),
    output: Path = typer.Option(..., "--output", "-o", help="输出 BVH 路径"),
    person: int = typer.Option(0, "--person", help="导出第几个人"),
) -> None:
    """把 pose.json 的 3D 关节导出为 BVH（Blender/Unity 等可直接导入）。"""
    out = export_bvh_to_file(load_pose(pose_path), output, person_index=person)
    typer.echo(f"已导出 → {out}")


@app.command("diff")
def diff_cmd(
    pose_a: Path = typer.Argument(..., exists=True, dir_okay=False, help="基准姿态"),
    pose_b: Path = typer.Argument(..., exists=True, dir_okay=False, help="对比姿态"),
    threshold: float = typer.Option(2.0, "--threshold", "-t", help="判定“移动”的像素阈值"),
    json_output: bool = typer.Option(False, "--json", help="以 JSON 输出报告"),
) -> None:
    """对比两个姿态，输出人可读的语义变化报告。"""
    report = diff_poses(load_pose(pose_a), load_pose(pose_b), threshold_px=threshold)
    if json_output:
        typer.echo(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        typer.echo(format_report(report))


@app.command("batch")
def batch_cmd(
    poses_dir: Path = typer.Argument(..., exists=True, file_okay=False, help="姿态库目录"),
    output_dir: Path = typer.Option(Path("renders"), "--output-dir", "-o", help="PNG 输出目录"),
) -> None:
    """批量渲染姿态库中的全部姿态。"""
    outputs = batch_render(poses_dir, output_dir)
    typer.echo(f"共渲染 {len(outputs)} 个姿态 → {output_dir}")


@app.command("index")
def index_cmd(
    poses_dir: Path = typer.Argument(..., exists=True, file_okay=False, help="姿态库目录"),
) -> None:
    """扫描姿态库并重建 index.yaml。"""
    out = write_index(poses_dir)
    typer.echo(f"索引已更新 → {out}")


@app.command("angles")
def angles_cmd(
    pose_path: Path = typer.Argument(..., exists=True, dir_okay=False, help="pose.json 路径"),
    person: int = typer.Option(0, "--person", help="计算第几个人"),
    json_output: bool = typer.Option(False, "--json", help="以 JSON 输出"),
) -> None:
    """计算姿态的关节角度（骨骼角度）表。"""
    angles = compute_joint_angles(load_pose(pose_path), person_index=person)
    if json_output:
        typer.echo(json.dumps(angles, ensure_ascii=False, indent=2))
    else:
        typer.echo(format_angles(angles))


@app.command("recognize")
def recognize_cmd(
    image: Path = typer.Argument(..., exists=True, dir_okay=False, help="输入图片（照片或骨架图）"),
    output: Path = typer.Option(..., "--output", "-o", help="输出的 pose.json 路径"),
    config_path: Path = typer.Option(
        Path(DEFAULT_CONFIG_PATH), "--config", help="识别配置文件（含 API 密钥，不入库）"
    ),
    angles_out: Path = typer.Option(None, "--angles-out", help="可选：骨骼角度 JSON 输出路径"),
    swap_sides: bool = typer.Option(
        False, "--swap-left-right", help="识别后互换左右标签（修正 MLLM 的左右颠倒）"
    ),
) -> None:
    """AI 识图：视觉模型识别图片中的姿态，导出 pose.json 与骨骼角度。"""
    config = load_recognize_config(config_path)
    typer.echo(f"使用模型 {config['model']} 分析图片 {image} ...")
    pose = recognize_image(image, config, swap_sides=swap_sides)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(pose.model_dump_json(indent=2), encoding="utf-8")
    typer.echo(f"识别结果已保存 → {output}")
    typer.echo("识别到的关节角度：")
    typer.echo(format_angles(compute_joint_angles(pose)))
    if angles_out:
        angles_out.parent.mkdir(parents=True, exist_ok=True)
        angles_out.write_text(
            json.dumps(compute_joint_angles(pose), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        typer.echo(f"角度数据已保存 → {angles_out}")


@app.command("import")
def import_cmd(
    file: Path = typer.Argument(..., exists=True, dir_okay=False, help="openpose/COCO JSON 或 Collada (.dae)"),
    output: Path = typer.Option(None, "--output", "-o", help="输出的 pose.json 路径（默认 <原名>.pose.json）"),
    frame: int = typer.Option(0, "--frame", "-f", help="Collada 动画的帧号（0=第 0 关键帧，负数从末尾数）"),
) -> None:
    """导入外部姿态数据（JSON / .dae），归一化为本项目的 pose.json 格式。"""
    import json as _json

    from .importers import detect_and_parse

    if file.suffix.lower() == ".dae":
        from .collada_import import parse_collada

        pose, warnings, total = parse_collada(file, frame=frame)
        for w in warnings:
            typer.echo(f"⚠ {w}")
    else:
        try:
            data = _json.loads(file.read_text(encoding="utf-8"))
        except _json.JSONDecodeError as e:
            typer.echo(f"❌ 不是有效 JSON（{e}）。注意：不支持带 // 注释的 JSON 文件")
            raise typer.Exit(1)
        pose, fmt, warnings = detect_and_parse(data)
        for w in warnings:
            typer.echo(f"⚠ {w}")

    target = output or file.with_suffix(".pose.json")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(pose.model_dump_json(indent=2), encoding="utf-8")
    typer.echo(f"已导出 → {target}")


@app.command("web")
def web_cmd(
    host: str = typer.Option("127.0.0.1", "--host", help="监听地址，默认仅本机"),
    port: int = typer.Option(7860, "--port", help="监听端口"),
) -> None:
    """启动 Web 界面（姿态库 / 画布编辑器 / AI 识图 / 对比）。"""
    import uvicorn

    from .webapp import create_app

    typer.echo(f"zzdzz-pose-tool Web 界面 → http://{host}:{port}")
    uvicorn.run(create_app(), host=host, port=port, log_level="warning")


@app.command("schema")
def schema_cmd(
    output: Path = typer.Option(Path("schemas/pose.schema.json"), "--output", "-o"),
) -> None:
    """从 pydantic 模型导出 JSON Schema（单一事实来源）。"""
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(export_json_schema(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    typer.echo(f"JSON Schema 已导出 → {output}")


if __name__ == "__main__":
    app()
