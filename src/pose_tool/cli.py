"""命令行入口：pose render / diff / batch / index / schema。"""

from __future__ import annotations

import json
from pathlib import Path

import typer

from .batch import batch_render
from .diff import diff_poses, format_report
from .library import write_index
from .render import render_to_png
from .schema import export_json_schema, load_pose

app = typer.Typer(
    help="zzdzz-pose-tool：把姿态当作可版本管理的工程资产（MVP）",
    no_args_is_help=True,
)


@app.command("render")
def render_cmd(
    pose_path: Path = typer.Argument(..., exists=True, dir_okay=False, help="pose.json 路径"),
    output: Path = typer.Option(..., "--output", "-o", help="输出 PNG 路径"),
    person: int = typer.Option(0, "--person", help="渲染第几个人"),
) -> None:
    """把单个 pose.json 渲染成 ControlNet-OpenPose 风格骨架图。"""
    out = render_to_png(load_pose(pose_path), output, person_index=person)
    typer.echo(f"已渲染 → {out}")


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
