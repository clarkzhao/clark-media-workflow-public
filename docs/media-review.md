# 媒体修订检查

从项目已有 STATE、时间线或 delivery manifest 导出一次只读快照，检查过期依赖、数值绑定、批注应用和必需动作。不会修改原素材、自动重渲染、配音或推断用户验收；快照是检查输入，不是另一个需要手工维护的当前入口。

Python 3.11+；核心只用标准库。可选运动检查使用已安装的 PyAV、OpenCV 和 numpy，无自动下载。已验证组合为 PyAV 18.1.0 / OpenCV 5.0.0 / numpy 2.5.2；其他版本以同一组编码回归测试验证。源码不附媒体或运行库。

## 运行一个无私人素材的例子

从仓库根目录执行，`python` 替换为已核查的解释器。输出目录必须是新目录：

```sh
python examples/media_review/demo.py --out outputs/review-demo
python scripts/media_review.py outputs/review-demo/revision.json --report outputs/review-demo/check-1.json
python -m unittest discover -s tests -p 'test_media_review.py' -v
python -m unittest discover -s tests -p 'test_motion_probe.py' -v
```

例子只有合成测试数字、SVG、字幕文本和预览页，不代表任何实验结论。自动检查通过时，四类人工/外部检查覆盖仍为 `unknown`。修改 `synthetic-results.json` 的数字而不重建图与字幕，再运行检查，会看到两个产物及其下游预览失效。

运动测试在临时目录生成并编码极短视频，比较真实局部运动、静图、缩放、字幕变化和无法配准的画面。没有可选依赖时显式 `skipped`，不算运动验证通过。CI 的运动任务先检查依赖存在，再执行这些测试。

## 小 Interface 与实际 Seam

`scripts/media_review.py` 的 Interface 为 `review(manifest, root, motion_probe=None) -> report`。它在“版本快照进入交付检查”的 Seam 上集中处理依赖传播、事实换算、当前批注和检查覆盖。`scripts/motion_probe.py` 是实际解码的 Adapter；测试可传入故障 Adapter 验证缺能力时不会误判通过，编码集成测试则使用真实解码。

保留已有渲染器，不新建通用渲染框架或包装每个历史版本。后续有真实第二个调用者时再提炼场景渲染与构建计划。当前模块检查显式声明，不能发现未登记的输入或代替模型正确性证明。

## 快照字段

参见 `examples/media_review/demo.py` 生成的 `revision.json`。相对路径以该 JSON 所在目录为基准，也允许本地绝对路径；私人项目快照不入公开仓库。

- `schema_version: 1`、`revision`：版本身份。
- `inputs`：`ID -> {path, sha256}`。包括实际读取的数据、代码、参数、媒体和样式配置；SHA256 使用小写十六进制。
- `artifacts`：`ID -> {path, sha256, depends_on: {上游ID: 构建时读取的哈希}}`。上游可为 input 或 artifact，不允许循环。输入与产物 ID 不重复。
- `experiments`：`ID -> {input, kind, metric, population, conditions, method, unit, display_unit, decimals}`。`kind` 为 `sample`、`expectation_estimate`、`analytic`、`observation`；期望估计还需 `replicates >= 2`、`sampling`、`uncertainty`。这些元数据要求保留出处，不代表工具已验证其真实性。
- `facts`：`ID -> {experiment, pointer}`。`pointer` 为 JSON Pointer，例如 `/result/mean` 或 `/runs/0/value`；支持 `~0`、`~1` 转义。从已核对哈希的结果读取有限数值，不再手填第二份数字。
- `bindings`：`[{artifact, fact, value, unit}]`。渲染器/导出器记录实际使用的显示值，`value` 为字符串，例如 `"1.5"`。同组实验共用显示单位与精度；输出 `display_facts` 可直接供各语言文本和图表生成使用。支持秒/分钟互换或单位不变，使用 decimal 半入舍入；百分比应在结果中按未舍入数据计算，不从显示值反算。
- `decisions`：当前有效的 `[{id, instruction, scope, targets, applied}]`；`targets` 为受影响产物 ID，`applied` 为 `产物ID -> 应用该批注后的内容哈希`。被替代决定保留在项目历史，不同时导出为有效指令。工具核对已声明覆盖，影响范围仍由 agent 根据批注判断。
- `scenes`：`[{id, artifact, media_kind, motion_required, ...}]`。媒体类型为 `still`、`video`、`svg_animation`、`blender_sequence`；类型说明实际用于该场景的媒体。必须有动作时不能声明为静图；需补 `action` 和 `motion`。有意静止则写 `static_reason`。
- `reviews`：`[{artifact, sha256, category, status, reviewer, reference, scope}]`。四类为 `technical`、`semantic`、`playback`、`acceptance`；状态为 `passed`、`failed`、`partial`，仅 `scope: whole_artifact` 可声明整件通过。局部观看保存区间及引用，状态仍是 `partial`；需要更细覆盖时按已有镜头导出独立产物。每个产物/类别仅导出当前一条记录，旧记录留历史。
- `review_targets`：可选的 `类别 -> [产物ID]`，指定该类检查对象，例如只对最终影片记录连续看听，不要求每份字幕文件重新审片。缺省检查所有登记产物。
- `required_reviews`：本轮已有要求的类别列表，缺省为空。按当前授权和阶段决定，不能为了让工具变绿自动新增审批或伪造验收。

依赖哈希在构建时记录，**不能在检查前批量重算依赖和批注完成哈希来消除失败**。源内容变了，即使源节点的新哈希正确，仍需重建或证明下游可复用；失效沿依赖图传播。只改发布文案则不应把它错误登记成影片输入。

## 动作检查

对最终编码视频运行 `--motion`。场景的 `motion` 示例（数值仅为示例，需用项目坏/好样例校准）：

```json
{
  "window_s": [1.0, 3.0],
  "roi": [0.1, 0.15, 0.9, 0.8],
  "samples": 5,
  "pixel_delta": 12,
  "min_changed_fraction": 0.015,
  "min_pairs": 2,
  "min_alignment_correlation": 0.65
}
```

时间相对编码文件首帧；ROI 为归一化 `x0,y0,x1,y1`，避开字幕及无关运动，最短边至少 64 像素。均匀采样后补偿整体仿射变换，统计有效重叠区域的变化比例；足够多的相邻样本超过阈值才通过筛查。不运行探测、缺依赖、采样越界、重复取到同一帧或配准不可靠都保持未知。

此方法能发现本次回归类型，不能验证动作语义、证明整段没有卡顿、识别所有跳帧或判断美感。纯刚体位移可能被补偿掉；画面切换、阴影或闪烁可能产生残差。应选物体动作及稳定背景区域，并结合事件记录与实际连续播放；不能把筛查分数当成影片质量评分。

## 输出与退出状态

- `automated_status`：`passed` / `failed` / `incomplete`，只针对本快照的自动检查。
- `invalidated`：依赖或文件已经失效的产物；不包含所有需要创意修改的产物。
- `display_facts`：统一换算后的值、单位、证据类型；不是 OCR 或听写结果。
- `coverage`、`uncovered`：四类当前记录及未覆盖对象；结果未覆盖不自动表示用户尚未授权制作。
- `required_uncovered`：本轮已声明需要、但未通过或未覆盖的类别。

退出码 `0` 表示声明的自动检查及所需记录满足，`1` 表示检测失败，`2` 表示动作能力或所需评审未覆盖。没有设为必需的验收可以继续为未知；不得将退出 `0` 表述为用户已验收。报告写到新路径，拒绝覆盖已有文件。

文件哈希不证明内容正确，绑定元数据不证明最终画面读得清或真实音轨念得对；对最终编码画面和音频仍按技能执行检查。未知输入、漏登记镜头和遗漏批注必须由制作流程发现。
