# PaddleOCR-VL-1.6 接口文档

## 服务概览

| 端口 | 容器 | 协议 | 适用场景 |
|---|---|---|---|
| `30008` | paddleocr-vl-api | PaddleX 专有 | 版面检测 + OCR + 结构化 JSON / Markdown |
| `30009` | paddleocr-vlm-server | OpenAI 兼容 | VLM 直连，自定义 prompt |

> 两容器均由 `docker-compose-baidu.yml` 启动。30009 为标准 vLLM OpenAI 实现，支持 `/v1/*` 端点。

## 接口选择

| | `30008 /layout-parsing` | `30009 /v1/chat/completions` |
|---|---|---|
| PDF | ✅ 原生支持 | ❌ 需先转图片 |
| 图片 | ✅ URL / Base64 | ✅ URL / Base64 |
| 版面分析 | ✅ PP-DocLayoutV3 | ❌ |
| 输出 | 结构化 JSON + Markdown | 纯文本 |
| 自定义 prompt | ❌ | ✅ |
| 典型场景 | 文档归档、坐标提取 | 自定义 OCR、问答 |

---

## 公共说明

所有接口通过 JSON body 传文件（不支持 multipart）。本地文件需 Base64 编码：

```bash
# Linux
FILE_B64=$(base64 -w 0 /path/to/image.png)
PDF_B64=$(base64 -w 0 /path/to/document.pdf)

# macOS（base64 无 -w，用 -i）
FILE_B64=$(base64 -i /path/to/image.png)
```

---

## 接口一：`POST /layout-parsing`（30008）

文档版面解析 + OCR 全流程，支持图片和 PDF。

```
POST /layout-parsing
Content-Type: application/json
```

### 健康检查

```bash
curl http://127.0.0.1:30008/health
```

### 请求参数

请求体为 JSON。除 `file` 外均为可选；不传时使用服务默认配置。传 `null` 表示沿用配置文件默认值。

#### 输入

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `file` | string | ✅ | — | 待解析文件。支持：**Base64 编码**的文件内容，或**可访问的 URL**（图片/PDF）。默认 PDF 超过 10 页仅处理前 10 页；解除限制需在产线配置中设 `Serving.extra.max_num_input_imgs: null` |
| `fileType` | integer \| null | | 自动推断 | 文件类型：`0`=PDF，`1`=图片。不传时根据 URL 后缀推断；Base64 时建议显式指定 |

#### 文档预处理

| 参数 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `useDocOrientationClassify` | boolean \| null | `false` | 启用**文档方向分类**，自动纠正 0°/90°/180°/270° 旋转的扫描件 |
| `useDocUnwarping` | boolean \| null | `false` | 启用**文档畸变矫正**（UVDoc），修正拍照/扫描产生的弯曲、透视变形 |

> ✅ **当前部署已启用文档预处理**（产线配置 `use_doc_preprocessor: True`，含方向矫正 + 畸变矫正）。扫描件场景可直接传 `useDocOrientationClassify: true` / `useDocUnwarping: true`，或不传参数（默认即开启）。

> 两者同时开启时，先方向矫正再畸变矫正。适合手机拍照、扫描仪文档；正常截图也可开启，对已是正向的水平文档影响较小。

#### 版面检测

| 参数 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `useLayoutDetection` | boolean \| null | `true` | 启用**版面区域检测与排序**（PP-DocLayoutV3）。关闭后不做版面切分，整图直接送 VLM |
| `useChartRecognition` | boolean \| null | `false` | 启用**图表解析**，对 chart 类型区域做专门识别 |
| `layoutThreshold` | number \| object \| null | 各类别默认阈值 | 版面检测**置信度阈值**。可传全局浮点数（0~1），或按类别 ID 传对象，如 `{"22": 0.5, "21": 0.4}`。阈值越高漏检越多、误检越少 |
| `layoutNms` | boolean \| null | `true` | 是否对检测框做 **NMS** 去重 |
| `layoutUnclipRatio` | number \| array \| object \| null | `[1.0, 1.0]` | 检测框**扩张系数**，扩大裁剪区域避免切掉边缘文字。可传单个数、二元组或按类别对象 |
| `layoutMergeBboxesMode` | string \| object \| null | 按类别配置 | 同类检测框的**合并策略**，如 `"union"`（取并集）、`"large"`（保留大框）等，可按类别分别设置 |
| `mergeLayoutBlocks` | boolean \| null | `true` | 是否合并**跨栏、上下交错分栏**的版面框，避免多栏报纸/论文被拆碎 |

> `useLayoutDetection=false` 时跳过版面检测，需配合 `promptLabel` 指定 VLM 任务类型。

#### VLM 识别

| 参数 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `promptLabel` | string \| null | — | VLM 任务类型，**仅 `useLayoutDetection=false` 时生效**。可选：`ocr`（通用 OCR）、`formula`（公式）、`table`（表格）、`chart`（图表） |
| `formatBlockContent` | boolean \| null | `false` | 是否将 `block_content` 格式化为 Markdown（表格、公式等结构化渲染） |
| `repetitionPenalty` | number \| null | 模型默认 | VLM 采样**重复惩罚**，越大越抑制重复输出 |
| `temperature` | number \| null | 模型默认 | VLM 采样**温度**，越低输出越确定，OCR 场景建议偏低 |
| `topP` | number \| null | 模型默认 | VLM **nucleus sampling** 参数 |
| `minPixels` | number \| null | 模型默认 | VLM 预处理图像**最小像素数**，过小图会被放大 |
| `maxPixels` | number \| null | 模型默认 | VLM 预处理图像**最大像素数**，过大图会被缩小 |
| `maxNewTokens` | number \| null | 模型默认 | VLM **最大生成 token 数**，影响长文档/大表格的输出长度上限 |

#### Markdown 输出

| 参数 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `markdownIgnoreLabels` | array \| null | 见下方 | 生成 Markdown 时**忽略的版面类型**。默认忽略：`number`、`footnote`、`header`、`header_image`、`footer`、`footer_image`、`aside_text` |
| `prettifyMarkdown` | boolean | `true` | 是否**美化 Markdown**（如图表居中），渲染后更美观 |
| `showFormulaNumber` | boolean | `false` | Markdown 中是否**保留公式编号** |

#### 响应控制

| 参数 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `visualize` | boolean \| null | `true` | 是否返回可视化图像。`true` 时响应含 `outputImages.layout_det_res`（版面标注图）和 `inputImage`（原图 Base64 JPEG）；`false` 时不返回，响应体从 ~2.6 MB 降至 ~50 KB，**生产环境建议关闭** |

### 调用示例

**图片 URL**

```bash
curl -X POST "http://127.0.0.1:30008/layout-parsing" \
  -H "Content-Type: application/json" \
  -d '{
    "file": "https://paddle-model-ecology.bj.bcebos.com/paddlex/imgs/demo_image/paddleocr_vl_demo.png",
    "fileType": 1,
    "visualize": false
  }'
```

**本地图片 / PDF（Base64）**

```bash
curl -X POST "http://127.0.0.1:30008/layout-parsing" \
  -H "Content-Type: application/json" \
  -d "{\"file\": \"${FILE_B64}\", \"fileType\": 1}"

curl -X POST "http://127.0.0.1:30008/layout-parsing" \
  -H "Content-Type: application/json" \
  -d "{\"file\": \"${PDF_B64}\", \"fileType\": 0}"
```

**扫描件（方向矫正 + 畸变矫正 + 格式化）**

```bash
curl -X POST "http://127.0.0.1:30008/layout-parsing" \
  -H "Content-Type: application/json" \
  -d '{
    "file": "https://example.com/scan.jpg",
    "fileType": 1,
    "useDocOrientationClassify": true,
    "useDocUnwarping": true,
    "formatBlockContent": true,
    "visualize": false
  }'
```

**普通文档（仅格式化）**

```bash
curl -X POST "http://127.0.0.1:30008/layout-parsing" \
  -H "Content-Type: application/json" \
  -d '{
    "file": "https://paddle-model-ecology.bj.bcebos.com/paddlex/imgs/demo_image/paddleocr_vl_demo.png",
    "fileType": 1,
    "formatBlockContent": true,
    "visualize": false
  }'
```

### 响应结构

成功时 HTTP `200`，`errorCode=0`。每个 `layoutParsingResults` 元素对应一页（PDF 多页时数组有多项）。

```
响应
├── logId, errorCode, errorMsg
└── result
    ├── dataInfo          输入宽高、type（image/pdf）
    └── layoutParsingResults[]
        ├── prunedResult  结构化数据（最常用）
        │   ├── width, height, page_count
        │   ├── model_settings
        │   ├── parsing_res_list[]   合并后的版面块（按阅读顺序）
        │   └── layout_det_res.boxes[]  原始检测框（含 score）
        ├── markdown        { text, images }
        ├── outputImages    visualize=true 时有 layout_det_res（Base64 JPEG）
        └── inputImage      visualize=true 时有原图 Base64
```

**取数对照**

| 需求 | 字段 |
|---|---|
| Markdown 全文 | `layoutParsingResults[i].markdown.text` |
| 坐标 + 类型 + 文本 | `prunedResult.parsing_res_list` |
| 检测置信度 | `prunedResult.layout_det_res.boxes` |
| 可视化调试 | `outputImages.layout_det_res` |

### 响应字段说明

#### 坐标说明

> 参考：[PaddleOCR-VL 官方文档](https://www.paddleocr.ai/latest/version3.x/pipeline_usage/PaddleOCR-VL.html)（`layout_shape_mode`、`block_bbox` 字段说明）及 PaddleX 源码 [`processors.py`](https://github.com/PaddlePaddle/PaddleX/blob/develop/paddlex/inference/models/layout_analysis/processors.py)。

所有坐标均基于**原始输入图像**（与 `dataInfo.width/height`、`prunedResult.width/height` 一致），单位为**像素（px）**。

**官方 `layout_shape_mode` 与坐标形态**

| 模式 | 官方说明 | 对应字段 |
|---|---|---|
| `rect` | 水平正向边界框，**包含 x1, y1, x2, y2** | `block_bbox` / `coordinate` |
| `quad` | 由**四个顶点**组成的任意四边形（倾斜/透视） | `block_polygon_points`（4 点） |
| `poly` | 由**多个坐标点**组成的闭合轮廓 | `block_polygon_points`（>4 点） |
| `auto` | 按区域复杂度自动选择上述形态 | 默认模式 |

**坐标系**

```
(0,0) ──────────────→ x（宽，最大 = width）
  │
  │    (x1,y1)┌──────────────┐
  │           │   版面区域    │
  │           └──────────────┘(x2,y2)
  ↓
  y（高，最大 = height）
```

- 原点 `(0, 0)` 在图像**左上角**
- `x` 轴向右递增，范围 `[0, width]`
- `y` 轴向下递增，范围 `[0, height]`

**矩形框 `[x1, y1, x2, y2]`**

> 官方文档：`block_bbox` 为「版面区域的边界框」；`layout_shape_mode=rect` 时格式为 **x1, y1, x2, y2**（PaddleX 源码记为 `[xmin, ymin, xmax, ymax]`）。

**不是**四个角按顺序排列，而是 **2 个对角点**：

| 字段 | 格式 | 出现位置 | 含义 |
|---|---|---|---|
| `block_bbox` | `[x1, y1, x2, y2]` | `parsing_res_list[]` | 合并后的版面块外接矩形 |
| `coordinate` | `[x1, y1, x2, y2]` | `layout_det_res.boxes[]` | 原始检测框外接矩形（与 `block_bbox` 格式相同） |

| 数组项 | 官方含义 | 角点 |
|---|---|---|
| `x1, y1` | xmin, ymin | **左上角** |
| `x2, y2` | xmax, ymax | **右下角** |

```
(x1,y1) 左上角 ─────────── (x2,y1) 右上角
    │                          │
    │        矩形区域           │
    │                          │
(x1,y2) 左下角 ─────────── (x2,y2) 右下角
```

- `[x1, y1, x2, y2]` 中**只给出** `(x1,y1)` 左上角 和 `(x2,y2)` 右下角
- 右上 `(x2,y1)`、左下 `(x1,y2)` **不在数组中**，由上述两点推导
- 区域宽度 = `x2 - x1`，高度 = `y2 - y1`
- 坐标可为浮点数（检测模型输出），使用时通常取整

**示例**：`block_bbox: [130, 35, 1384, 127]`

| 角点 | 坐标 | 来源 |
|---|---|---|
| 左上 | `(130, 35)` | 数组第 1、2 项 |
| 右下 | `(1384, 127)` | 数组第 3、4 项 |
| 右上 | `(1384, 35)` | 推导：`x=x2, y=y1` |
| 左下 | `(130, 127)` | 推导：`x=x1, y=y2` |

**多边形顶点 `block_polygon_points`**

| 字段 | 格式 | 出现位置 | 含义 |
|---|---|---|---|
| `block_polygon_points` | `[[x, y], ...]` | `parsing_res_list[]` | 版面块实际轮廓（4 点=矩形，>4 点=不规则区域） |
| `polygon_points` | `[[x, y], ...]` | `layout_det_res.boxes[]` | 检测框轮廓，格式同上 |

> 官方文档未逐字段描述 `block_polygon_points`，但 PaddleX 源码 `_rect_from_box()` 和 `convert_polygon_to_quad()` 明确：**从左上角开始，顺时针排列**（clockwise from top-left）。

**水平矩形（4 个点，`layout_shape_mode=rect`）**

官方源码 `_rect_from_box()` 生成的顺序：

**`[0]` 左上 → `[1]` 右上 → `[2]` 右下 → `[3]` 左下 → 闭合回 `[0]`**

```python
# PaddleX processors.py — _rect_from_box()
[[x_min, y_min], [x_max, y_min], [x_max, y_max], [x_min, y_max]]
#  左上           右上            右下            左下
```

```
遍历顺序（非数组下标位置图）：

  [0]左上 ──────→ [1]右上
    ↑               │
    │               ↓
  [3]左下 ←────── [2]右下
```

**示例**：`block_polygon_points: [[130,35], [1384,35], [1384,127], [130,127]]`

| 索引 | 角点 | 坐标 |
|---|---|---|
| `[0]` | 左上 | `(130, 35)` |
| `[1]` | 右上 | `(1384, 35)` |
| `[2]` | 右下 | `(1384, 127)` |
| `[3]` | 左下 | `(130, 127)` |

**不规则区域（`layout_shape_mode=poly`，>4 个点）**

官方说明：「多个坐标点组成的**闭合轮廓**」。顶点沿检测轮廓依次排列，无固定角点命名；`vision_footnote` 等不规则块由 PP-DocLayoutV3 分割 mask 提取。

**示例**（`vision_footnote`，7 个点）：

```json
"block_polygon_points": [
  [809, 702],   // [0] 靠左上起点
  [809, 736],   // [1] 沿左边界向下
  [817, 743],   // [2] 轮廓转折
  [1485, 749],  // [3] 靠右下
  [1485, 723],  // [4] 沿右边界向上
  [1478, 716],  // [5] 轮廓转折
  [1455, 702]   // [6] 回到上方，闭合至 [0]
]
```

- 相邻索引 `[i]` 与 `[i+1]` 之间连线；最后一项 `[n-1]` 连回 `[0]`
- 水平矩形时，4 角点与 `block_bbox` 描述同一区域，只是表达方式不同

**三组坐标的关系**

| 对比 | `layout_det_res.boxes` | `parsing_res_list` |
|---|---|---|
| 来源 | 版面检测模型原始输出 | 检测框合并 + OCR 后的最终结果 |
| 矩形字段 | `coordinate` | `block_bbox` |
| 多边形字段 | `polygon_points` | `block_polygon_points` |
| 数量 | 较多（本例 33 个） | 较少（本例 31 个，合并后减少） |
| 额外信息 | 含 `score` 置信度 | 含 `block_content` 识别文本 |

**本例实测（1524×1368 图像）**

| 块类型 | 字段 | 值 | 解读 |
|---|---|---|---|
| `doc_title` | `block_bbox` | `[130, 35, 1384, 127]` | 顶部横跨全宽的标题，高 92px |
| `text` | `block_bbox` | `[582, 157, 930, 183]` | 标题下方居中作者行，宽 348px、高 26px |
| `image` | `block_bbox` | `[777, 201, 1502, 685]` | 右侧图片区，宽 725px、高 484px |
| `vision_footnote` | `block_polygon_points` | 7 个顶点 | 图注区域不规则，7 点多边形比矩形更精确 |

> `markdown.images` 的键名也嵌入了坐标，如 `imgs/img_in_image_box_777_201_1502_685.jpg` 对应 `image` 块的 `block_bbox`。

**常见用途**

| 用途 | 用法 |
|---|---|
| 裁剪区域内容 | 按 `block_bbox` 从原图截取：`img[y1:y2, x1:x2]` |
| 前端高亮标注 | 在 `width×height` 画布上按坐标画框 |
| 坐标归一化 | `x_norm = x / width`，便于不同分辨率间复用 |
| 判断空间关系 | 比较 `y1` 判断上下位置，比较 `x1` 判断左右栏 |

---

**`parsing_res_list` 单块**

| 字段 | 类型 | 含义 |
|---|---|---|
| `block_label` | string | 版面类型（见下表） |
| `block_content` | string | 识别文本；`image` 块通常为空 |
| `block_bbox` | `[x1,y1,x2,y2]` | 版面块外接矩形，见[坐标说明](#坐标说明) |
| `block_polygon_points` | `[[x,y], ...]` | 版面块轮廓多边形，倾斜区域比 bbox 更准 |
| `block_id` | int | 块索引 |
| `block_order` | int \| null | 阅读顺序；图片/图注等为 `null` |
| `group_id` | int | 逻辑分组 ID |

**`layout_det_res.boxes` 单框**

| 字段 | 含义 |
|---|---|
| `cls_id`, `label` | 类别 ID / 名称（同 `block_label`） |
| `score` | 检测置信度 0~1 |
| `coordinate` | 检测框外接矩形 `[x1,y1,x2,y2]`，见[坐标说明](#坐标说明) |
| `order` | 阅读顺序 |
| `polygon_points` | 检测框轮廓多边形 |

**`markdown`**

| 字段 | 含义 |
|---|---|
| `text` | 排版后的 Markdown（标题、正文、`<img>` 引用等） |
| `images` | 键为 `text` 中 `src` 路径，值为 Base64 图片 |
| `isStart` / `isEnd` | PDF 多页时段落起止标记 |

**`block_label` 版面类型**

| 标签 | 含义 | 标签 | 含义 |
|---|---|---|---|
| `doc_title` | 文档标题 | `paragraph_title` | 小节标题 |
| `text` | 正文 | `image` | 图片区域 |
| `vision_footnote` | 图注 | `table` | 表格 |
| `chart` | 图表 | `display_formula` / `inline_formula` | 行间/行内公式 |
| `header` / `footer` | 页眉/页脚 | `footnote` | 脚注 |
| `number` | 页码 | `seal` | 印章 |
| `abstract` | 摘要 | `reference` / `reference_content` | 参考文献 |
| `aside_text` | 旁注 | 其他 | 见 [官方文档](https://www.paddleocr.ai/latest/en/version3.x/pipeline_usage/PaddleOCR-VL.html) |

### 详细返回示例

以下基于 `127.0.0.1:30008` 对官方 demo 图片的实际调用（`visualize: false`）。完整响应约 **50 KB**；若 `visualize: true` 还会额外返回 ~2.5 MB 的 Base64 图像。

**对应请求**

```bash
curl -X POST "http://127.0.0.1:30008/layout-parsing" \
  -H "Content-Type: application/json" \
  -d '{
    "file": "https://paddle-model-ecology.bj.bcebos.com/paddlex/imgs/demo_image/paddleocr_vl_demo.png",
    "fileType": 1,
    "visualize": false
  }'
```

**本例统计**

| 指标 | 值 |
|---|---|
| 输入尺寸 | 1524 × 1368 px |
| `layoutParsingResults` 长度 | 1（单张图片） |
| `parsing_res_list` 块数 | 31 |
| `layout_det_res.boxes` 框数 | 33 |
| 类型分布 | `text×25`, `paragraph_title×3`, `doc_title×1`, `image×1`, `vision_footnote×1` |
| `markdown.text` 长度 | 2696 字符 |
| `markdown.images` 数量 | 1 张 |

**完整返回 JSON（数组已截断，其余 block 结构相同）**

```json
{
  "logId": "bbb70540-6250-496c-9071-7eba7ab93948",
  "errorCode": 0,
  "errorMsg": "Success",
  "result": {
    "dataInfo": {
      "width": 1524,
      "height": 1368,
      "type": "image"
    },
    "layoutParsingResults": [
      {
        "prunedResult": {
          "width": 1524,
          "height": 1368,
          "page_count": null,
          "model_settings": {
            "use_doc_preprocessor": false,
            "use_layout_detection": true,
            "use_chart_recognition": false,
            "use_seal_recognition": false,
            "use_ocr_for_image_block": false,
            "format_block_content": false,
            "merge_layout_blocks": true,
            "markdown_ignore_labels": [
              "number", "footnote", "header", "header_image",
              "footer", "footer_image", "aside_text"
            ],
            "return_layout_polygon_points": true
          },
          "parsing_res_list": [
            {
              "block_label": "doc_title",
              "block_content": "助力双方交往 搭建友谊桥梁",
              "block_bbox": [130, 35, 1384, 127],
              "block_id": 0,
              "block_order": 1,
              "group_id": 0,
              "block_polygon_points": [[130, 35], [1384, 35], [1384, 127], [130, 127]]
            },
            {
              "block_label": "text",
              "block_content": "本报记者 沈小晓 任彦 黄培昭",
              "block_bbox": [582, 157, 930, 183],
              "block_id": 1,
              "block_order": 2,
              "group_id": 1,
              "block_polygon_points": [[582, 157], [930, 157], [930, 183], [582, 183]]
            },
            {
              "block_label": "image",
              "block_content": "",
              "block_bbox": [777, 201, 1502, 685],
              "block_id": 2,
              "block_order": null,
              "group_id": 2,
              "block_polygon_points": [[777, 201], [1502, 201], [1502, 685], [777, 685]]
            },
            {
              "block_label": "vision_footnote",
              "block_content": "在厄立特里亚不久前举办的第六届中国风筝文化节上，当地小学生体验风筝制作。\n中国驻厄立特里亚大使馆供图",
              "block_bbox": [809, 702, 1486, 750],
              "block_id": 3,
              "block_order": null,
              "group_id": 3,
              "block_polygon_points": [[809, 702], [809, 736], [817, 743], [1485, 749], [1485, 723], [1478, 716], [1455, 702]]
            },
            {
              "block_label": "text",
              "block_content": "身着中国传统民族服装的厄立特里亚青年依次登台表演中国民族舞、现代舞、扇子舞等，曼妙的舞姿赢得现场观众阵阵掌声。这是日前厄立特里亚高等教育与研究院孔子学院（以下简称「厄特孔院」）举办「喜迎新年」中国歌舞比赛的场景。",
              "block_bbox": [9, 199, 361, 342],
              "block_id": 4,
              "block_order": 3,
              "group_id": 4,
              "block_polygon_points": [[9, 199], [361, 199], [361, 342], [9, 342]]
            },
            {
              "block_label": "paragraph_title",
              "block_content": "“学好中文，我们的未来不是梦”",
              "block_bbox": [27, 455, 341, 520],
              "block_id": 6,
              "block_order": 5,
              "group_id": 6,
              "block_polygon_points": [[27, 455], [341, 455], [341, 520], [27, 520]]
            }
          ],
          "layout_det_res": {
            "boxes": [
              {
                "cls_id": 6,
                "label": "doc_title",
                "score": 0.9300883412361145,
                "coordinate": [130, 35, 1384, 127],
                "order": 1,
                "polygon_points": [[130, 35], [1384, 35], [1384, 127], [130, 127]]
              },
              {
                "cls_id": 22,
                "label": "text",
                "score": 0.848341703414917,
                "coordinate": [582, 157, 930, 183],
                "order": 2,
                "polygon_points": [[582, 157], [930, 157], [930, 183], [582, 183]]
              }
            ]
          }
        },
        "markdown": {
          "text": "# 助力双方交往 搭建友谊桥梁\n\n本报记者 沈小晓 任彦 黄培昭\n\n<div style=\"text-align: center;\"><img src=\"imgs/img_in_image_box_777_201_1502_685.jpg\" alt=\"Image\" width=\"47%\" /></div>\n\n\n在厄立特里亚不久前举办的第六届中国风筝文化节上，当地小学生体验风筝制作。\n\n中国驻厄立特里亚大使馆供图\n\n身着中国传统民族服装的厄立特里亚青年依次登台表演中国民族舞、现代舞、扇子舞等，曼妙的舞姿赢得现场观众阵阵掌声。……\n\n## "学好中文，我们的未来不是梦"\n\n"鲜花曾告诉我你怎样走过，大地知道你心中的每一个角落……"……",
          "images": {
            "imgs/img_in_image_box_777_201_1502_685.jpg": "/9j/4AAQSkZJRgABAQAA……（Base64 JPEG，约 140 KB）"
          }
        },
        "outputImages": null,
        "inputImage": ""
      }
    ]
  }
}
```

> `parsing_res_list` 实际共 **31** 项、`layout_det_res.boxes` 共 **33** 项，上例各展示 6 / 2 项。PDF 输入时 `layoutParsingResults` 数组长度等于处理页数，每页结构相同。

**各层字段对照**

| 路径 | 本例实际值 | 说明 |
|---|---|---|
| `logId` | `"bbb70540-6250-496c-9071-7eba7ab93948"` | 请求 UUID，排查问题时提供 |
| `errorCode` / `errorMsg` | `0` / `"Success"` | 成功固定值；失败时 `errorCode` 为非零 |
| `result.dataInfo.type` | `"image"` | PDF 时为 `"pdf"` |
| `result.dataInfo.width/height` | `1524` / `1368` | 坐标基准尺寸，所有 bbox 均相对此画布 |
| `prunedResult.page_count` | `null` | 单图无意义；PDF 时为总页数 |
| `prunedResult.model_settings` | 见 JSON | 本次推理实际生效的配置快照 |
| `parsing_res_list[].block_bbox` | 如 `[130,35,1384,127]` | 左上角 `(130,35)` + 右下角 `(1384,127)`，单位 px |
| `parsing_res_list[].block_polygon_points` | 如 4 或 7 个 `[x,y]` | 不规则区域（如图注）顶点数 > 4 |
| `parsing_res_list[].block_order` | `1, 2, null, null, 3, 5, …` | 有值=阅读顺序；`null`=不参与排序 |
| `parsing_res_list[].block_content` | 见 JSON | `image` 块为空；正文块含 OCR 文本 |
| `layout_det_res.boxes[].coordinate` | 如 `[130,35,1384,127]` | 与对应 `block_bbox` 格式相同，为检测阶段原始框 |
| `layout_det_res.boxes[].score` | `0.93`, `0.85`, … | 版面检测置信度，非 OCR 置信度 |
| `markdown.text` | 2696 字符 | 标题转 `#`/`##`，图片转 `<img>` 标签 |
| `markdown.images` | 1 个键值对 | 键名 = `text` 中 `src` 路径 |
| `outputImages` | `null` | `visualize=true` 时为 `{"layout_det_res": "<Base64>"}` |
| `inputImage` | `""` | `visualize=true` 时为原图 Base64 JPEG（~1.3 MB） |

**`visualize=true` 时的额外字段**

```json
{
  "outputImages": {
    "layout_det_res": "/9j/4AAQSkZJRg……（Base64 JPEG，约 1.2 MB，版面区域标注图）"
  },
  "inputImage": "/9j/4AAQSkZJRg……（Base64 JPEG，约 1.3 MB，输入原图）"
}
```

**`markdown.text` 实际渲染效果（节选）**

```markdown
# 助力双方交往 搭建友谊桥梁

本报记者 沈小晓 任彦 黄培昭

<div style="text-align: center;"><img src="imgs/img_in_image_box_777_201_1502_685.jpg" alt="Image" width="47%" /></div>

在厄立特里亚不久前举办的第六届中国风筝文化节上，当地小学生体验风筝制作。

中国驻厄立特里亚大使馆供图

身着中国传统民族服装的厄立特里亚青年依次登台表演中国民族舞、现代舞、扇子舞等，……

## "学好中文，我们的未来不是梦"

"鲜花曾告诉我你怎样走过，大地知道你心中的每一个角落……"……
```

**注意事项**

| 现象 | 处理建议 |
|---|---|
| `image` 块 `block_content` 为空 | 图片内容在 `markdown.images`；坐标用 `block_bbox` |
| 部分 `text` 块 `block_content` 为空 | 多栏拆框导致，优先用 `markdown.text` |
| `block_order` 为 `null` | 图片/图注不参与排序，勿按 null 排序 |
| `parsing_res_list` 少于 `boxes` | 检测框合并后的正常结果 |
| 响应体过大 | 生产环境设 `"visualize": false` |
| 单图 `page_count` 为 `null` | 用 `len(layoutParsingResults)` 判断页数 |

---

## 接口二：`POST /v1/chat/completions`（30009）

vLLM OpenAI 兼容接口，仅支持图片，不支持 PDF。

### 健康检查

```bash
curl http://127.0.0.1:30009/health
curl http://127.0.0.1:30009/v1/models
```

### 任务提示词

| 任务 | `text` 值 |
|---|---|
| 通用 OCR | `"OCR:"` |
| 表格 | `"Table Recognition:"` |
| 公式 | `"Formula Recognition:"` |
| 图表 | `"Chart Recognition:"` |
| 自由问答 | 任意自然语言 |

### 调用示例

```bash
curl -X POST "http://127.0.0.1:30009/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "PaddleOCR-VL-1.6-0.9B",
    "messages": [{
      "role": "user",
      "content": [
        {"type": "image_url", "image_url": {"url": "https://example.com/img.png"}},
        {"type": "text", "text": "OCR:"}
      ]
    }],
    "temperature": 0.0,
    "max_tokens": 2048
  }'
```

本地图片将 URL 换为 `data:image/png;base64,${FILE_B64}`。PDF 请优先用 `30008 /layout-parsing`。

---

## 参考链接

- [PaddleOCR-VL 官方文档](https://www.paddleocr.ai/latest/en/version3.x/pipeline_usage/PaddleOCR-VL.html)
- [部署说明](./readme.md)
