#!/usr/bin/env python3
"""
OCR 打码工具 — Python 版本

功能与 RedactMain.java 一致：
1. 读取本地 PNG 图片
2. 调用 PaddleOCR layout-parsing 服务获取文本块坐标
3. 在图片上画红框标记，可切换为黑色填充打码

注意：
  产线默认开启文档预处理（方向/畸变矫正）时，返回的 block_bbox
  相对的是矫正后图像，直接画在原图上会整体偏移。
  本脚本默认关闭预处理，保证坐标与原图像素对齐。

用法：
    python ocr_redact.py                          # 默认：关预处理 + 红框
    python ocr_redact.py --fill                   # 黑框打码模式
    python ocr_redact.py --with-preprocess        # 启用服务端预处理（坐标可能不准）
    python ocr_redact.py --offset-y 80            # 手动追加 Y 轴偏移（像素）
    python ocr_redact.py --raw                    # 打印 OCR 原始响应 JSON
"""

import argparse
import base64
import json
import sys
from pathlib import Path

import requests
from PIL import Image, ImageDraw


# ---------- 配置 ----------
OCR_URL = "http://127.0.0.1:30008/layout-parsing"
INPUT_FILE = Path("20260811-111613.png")
OUTPUT_FILE = Path("abc.png")
REDACT_PADDING_PX = 3
RED_BORDER_WIDTH = 2


def call_ocr(
    image_bytes: bytes,
    *,
    url: str,
    use_preprocess: bool = False,
) -> dict:
    """调用 PaddleOCR layout-parsing 服务，返回完整 JSON 响应。"""
    # 打码场景画在原图上：必须显式关闭预处理，否则 bbox 落在矫正图坐标系里
    payload: dict = {
        "file": base64.b64encode(image_bytes).decode("ascii"),
        "fileType": 1,
        "visualize": False,
        "useDocOrientationClassify": use_preprocess,
        "useDocUnwarping": use_preprocess,
    }

    print(f"[OCR] 请求 {url} ...")
    print(f"[OCR] 文档预处理: {'开启' if use_preprocess else '关闭（坐标对齐原图）'}")
    resp = requests.post(url, json=payload, timeout=120)
    print(f"[OCR] 状态码: {resp.status_code}")
    resp.raise_for_status()
    data = resp.json()
    if data.get("errorCode") != 0:
        print(f"[OCR] 服务端错误: {data.get('errorMsg')} (logId={data.get('logId')})")
        sys.exit(1)
    return data


def extract_boxes(data: dict, img_w: int, img_h: int) -> list[dict]:
    """从 OCR 响应中提取所有文本块的 bbox 信息。"""
    boxes = []
    for lp_result in data["result"]["layoutParsingResults"]:
        pruned = lp_result["prunedResult"]
        svc_w = pruned.get("width")
        svc_h = pruned.get("height")
        print(f"[OCR] 服务返回尺寸: {svc_w} x {svc_h}")
        print(f"[图像] 原图尺寸: {img_w} x {img_h}")
        if svc_w and svc_h and (svc_w != img_w or svc_h != img_h):
            print(
                f"[警告] 尺寸不一致，按比例缩放坐标 "
                f"(sx={img_w / svc_w:.4f}, sy={img_h / svc_h:.4f})"
            )
            sx, sy = img_w / svc_w, img_h / svc_h
        else:
            sx = sy = 1.0

        ms = pruned.get("model_settings") or {}
        if ms.get("use_doc_preprocessor"):
            print(
                "[警告] 服务端仍启用了文档预处理，bbox 可能相对矫正图，"
                "画在原图上会偏移。请确认请求已传 useDocUnwarping=false"
            )

        for item in pruned.get("parsing_res_list") or []:
            bbox = item.get("block_bbox")
            if not bbox or len(bbox) < 4:
                continue
            x1 = int(bbox[0] * sx)
            y1 = int(bbox[1] * sy)
            x2 = int(bbox[2] * sx)
            y2 = int(bbox[3] * sy)
            boxes.append({
                "label": item.get("block_label", ""),
                "content": item.get("block_content", ""),
                "x": x1,
                "y": y1,
                "w": x2 - x1,
                "h": y2 - y1,
            })
    return boxes


def draw_boxes(
    image_path: Path,
    output_path: Path,
    boxes: list[dict],
    *,
    fill: bool = False,
    offset_y: int = 0,
) -> None:
    """在图片上绘制 bbox，支持红框模式或黑框填充模式。"""
    img = Image.open(image_path).convert("RGB")
    draw = ImageDraw.Draw(img)

    for i, box in enumerate(boxes):
        x = box["x"]
        y = box["y"] + offset_y
        w = box["w"]
        h = box["h"]

        if fill:
            # 黑框打码（带 padding）
            x_fill = max(0, x - REDACT_PADDING_PX)
            y_fill = max(0, y - REDACT_PADDING_PX)
            w_fill = w + 2 * REDACT_PADDING_PX
            h_fill = h + 2 * REDACT_PADDING_PX
            if x_fill + w_fill > img.width:
                w_fill = img.width - x_fill
            if y_fill + h_fill > img.height:
                h_fill = img.height - y_fill
            draw.rectangle(
                [x_fill, y_fill, x_fill + w_fill - 1, y_fill + h_fill - 1],
                fill="black",
            )
        else:
            # 红框标记（仅边框，不填充）
            for offset in range(RED_BORDER_WIDTH):
                draw.rectangle(
                    [x - offset, y - offset, x + w + offset, y + h + offset],
                    outline="red",
                )

        # 打印前几条
        if i < 5:
            content_preview = box["content"][:60] if box["content"] else "(empty)"
            print(f"  [{i}] label={box['label']} content=[{content_preview}] "
                  f"x={x} y={y} w={w} h={h}")

    img.save(output_path, "PNG")
    mode = "黑框打码" if fill else "红框标记"
    print(f"[输出] {output_path} ({mode}, total={len(boxes)} blocks)")


def main() -> None:
    parser = argparse.ArgumentParser(description="OCR 打码工具")
    parser.add_argument("--fill", action="store_true", help="黑框打码模式（默认仅画红框）")
    parser.add_argument("--offset-y", type=int, default=0, help="手动追加 Y 轴偏移量（像素）")
    parser.add_argument(
        "--with-preprocess",
        action="store_true",
        help="启用服务端文档预处理（默认关闭；开启后坐标常与原图不对齐）",
    )
    parser.add_argument(
        "--no-unwarp",
        action="store_true",
        help="兼容旧参数：关闭预处理（现为默认行为，可省略）",
    )
    parser.add_argument("--raw", action="store_true", help="打印 OCR 原始响应 JSON")
    parser.add_argument("--input", type=str, default=str(INPUT_FILE), help="输入图片路径")
    parser.add_argument("--output", type=str, default=str(OUTPUT_FILE), help="输出图片路径")
    parser.add_argument("--url", type=str, default=OCR_URL, help="layout-parsing 服务地址")
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"[错误] 文件不存在: {input_path}")
        sys.exit(1)

    # 1. 读取原始文件字节（跳过 Pillow 重新编码）
    image_bytes = input_path.read_bytes()
    with Image.open(input_path) as im:
        img_w, img_h = im.size

    # 2. 调用 OCR（默认关预处理，保证 bbox 对齐原图）
    use_preprocess = args.with_preprocess and not args.no_unwarp
    data = call_ocr(image_bytes, url=args.url, use_preprocess=use_preprocess)

    if args.raw:
        print("--- OCR 原始响应 ---")
        print(json.dumps(data, ensure_ascii=False, indent=2)[:4000])
        print("--- OCR 原始响应结束 ---")

    # 3. 提取坐标
    boxes = extract_boxes(data, img_w, img_h)
    if not boxes:
        print("[OCR] 未检测到任何文本块")
        sys.exit(0)

    # 4. 画框输出
    draw_boxes(
        input_path,
        Path(args.output),
        boxes,
        fill=args.fill,
        offset_y=args.offset_y,
    )


if __name__ == "__main__":
    main()
