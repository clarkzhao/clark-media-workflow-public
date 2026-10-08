# 本地模型插画与科普动画

本例演示 **本地 FLUX 生成静态底图，再用 Python 绘制过程动画，最后合成实拍**；没有用视频模型生成地质过程，也不是物理模拟。模型权重、生成图、视频和私人声音保留在本地项目，仓库保存方法、提示词、API 图和绘制源码。

## 先说明一个过程，再打磨画面

画面精致不等于过程清楚。本例依次表现水流接触岩石、溶出物随水移动、条件合适时出现薄层沉积，用标签和动画解释因果。

- 每段先明确一个观众问题，用几个连续的因果步骤回答。文字、旁白和运动指向同一对象；少数邻近标签比满屏术语更易跟随。
- 底图承担空间关系和材质，箭头、粒子、描线、遮罩承担方向和变化，文字由程序排版。不要让模型直接生成中文、精确箭头或可靠的因果顺序。
- 对解释没有帮助的闪光、旋转和漂浮装饰先删。讲解中保持底图稳定，让标注与对象不漂移；镜头推进只在不破坏对应关系时采用。
- 模型名和制作说明不进入观众画面；用于解释内容的必要标签可以保留。具体文字、描线与重绘范围以当前项目已确认要求为准。

## 底图提示词与候选判断

模板和本次选中提示词见 [science-illustration.json](../prompts/science-illustration.json)，实际成功节点结构见 [FLUX API 图](../workflows/flux2-klein-science.api.json)。

提示词依次描述：主体与空间关系 → 可见材质 → 简单剖面 → 轮廓 → 视角与留边 → 光照和背景 → 无字底图。单次只调整少数变量，保留种子、参数和被否决原因。

本次前两张出现过于规整的厚方形石板，像人工水池。选中版强调自然侵蚀、不规则弧岸、低矮石基和全部边缘入画；透明水体、灰色岩层与浅色沉积区容易区分。这个材质方向适合本次场景，不是所有科普题材的固定画风。底图漂亮仍需检查它是否给动画留下可信的接触点、流向和标注位置。

历史成功参数：FLUX.2 Klein 9B NVFP4、Qwen 3 8B FP8 mixed 文本编码器、FLUX.2 VAE；1536×864、batch 1、Euler、4 steps、CFG 1、seed 2026100613。模型文件名保存在图中；这是已跑通配方，不保证其他模型、版本或硬件同样有效。官方 FLUX.2 pro/max 提示词指南的原则用于 Klein 属于本地试验，不能当作兼容保证。

用 Python 3.11+ 在仓库根目录准备新的 API 图：

```powershell
& './editing_env/Scripts/python.exe' './scripts/prepare_science_workflow.py' --prompt-file 'D:/current-project/research/illustration_prompt.txt' --seed 12345 --width 1536 --height 864 --prefix 'science_sample/run_01' --output 'D:/current-project/outputs/science/run_01_api.json'
```

示例路径须替换为当前项目。省略 `--prompt-file` 时使用已保存的石灰岩场景提示词。脚本只准备 JSON 和配方收据，拒绝覆盖；不启动服务、不提交 GPU 作业、不下载。尺寸会同时更新 latent 和 scheduler 两处。

## 本地生成的可靠执行方式

执行 ComfyUI 工作时使用当前 `comfyui` 技能；节点名、输入和模型选项以该机 `/object_info` 等实际返回为准。保存的图是 API 格式，不能冒充有布局的 GUI 工作流。

1. 先核已有服务、`/system_stats`、模型文件和节点结构，再看 `/queue`。已有任务时等待或协调，不清队列、不卸载别人的模型、不为一次任务重装环境。
2. 在本轮已授权范围内提交 batch 1 小样；保存 API 图、prompt_id 和收据。通过 WebSocket 或有限时的 `/history/{prompt_id}` 查询追踪自己的作业，失败读取 node_errors/status；超时先查询同一任务，不盲目重复提交。
3. 完成后核对实际输出图、尺寸和状态，保留原生 PNG 与哈希。接口成功不等于内容、科学性或画质通过。参数调整后只重做必要底图，动画及文字不必再次调用模型。

Windows 曾遇到重定向日志使用 GBK，SeedVR2 启动警告字符触发 `UnicodeEncodeError`，继而日志递归异常使 ComfyUI 未监听。该次修复只给现有 Python 启动增加 `-X utf8`，隐藏启动窗口，监听 `127.0.0.1`，分别保存 stdout/stderr；随后确认接口和一次小样成功。只有日志符合该成因才采用，不把所有服务失败都归因于编码。启动/重启前检查进程与队列，不结束无关作业，不修改审批策略、全局编码或代理。

## 过程动画：可控的语义层

本次时间、尺寸和科学边界见 [石灰岩示意配方](../examples/limestone-science.json)。[render_limestone_overlay.py](../scripts/render_limestone_overlay.py) 提取了原绘制逻辑，提供明确的 `make_renderer(image_path, font_path, scale)` 与逐帧函数，不再依赖读取旧项目脚本后动态执行。

这是 **固定八秒石灰岩案例绘制器**，不是任意题材的通用动画引擎。曲线位置、标签和阶段配合选中的底图；换图、换口播或换原理时必须重排，不能原样套用。时间以当前完整口播和画面锚点为准，本次 2.48、4.22 秒不是教学最佳时长。

- 第一阶段强调灰色岩石与水流；第二阶段用扁平暖色点表示溶出物随水移动；第三阶段让点抵达岸边，并沿原池缘逐渐出现浅色薄层。
- 蓝色箭头只表示水流方向，不解释湖水为何蓝；粒子是抽象符号，不是可见金属球、色素或真实尺度颗粒。
- 岩石与沉积层分开标注。沉积保留“条件合适时”的限定，不能画成水一碰石头就瞬间长高坝，也不能宣称所有海子都按同一机制形成。
- 科普图明确是“示意”，不伪装成实测剖面或当天实拍。缩略图、标签和口播中的限定要一致。

用现有含 Pillow、NumPy 的本地 Python 生成五张阶段检查图；`--image` 传入本项目模型生成的底图，`--font` 使用本机可用中文字体：

```powershell
& '<已有Pillow和NumPy的Python>' './scripts/render_limestone_overlay.py' --image '<当前项目底图.png>' --font 'C:/Windows/Fonts/msyhbd.ttc' --output '<当前项目>/outputs/science/stages' --scale 1
```

`--all-frames` 生成完整 240 帧；`--scale 2` 直接绘制 2160×1560 图层，适用于本例 4K 合成。既有输出目录拒绝覆盖。脚本不生成新配音，不自动重做模型底图。具体帧和阶段也可通过 `--frames 45 90 147 207 228` 选择。

需要透明视频交接时，从完整序列编码，保留 PNG 作为可重建来源：

```powershell
& './shotcut/Shotcut/ffmpeg.exe' -n -framerate 30 -i '<帧目录>/%04d.png' -frames:v 240 -c:v qtrle -pix_fmt argb '<项目输出>/science_overlay.mov'
```

本次抽取验证：五张 1080×780 阶段图与原版 RGBA 像素完全一致；2160×1560 阶段图、边界帧及 alpha 检查通过；API 图离线结构检查和参数同步、拒绝覆盖检查通过。没有重新推理、提交服务作业或完整重渲染八秒片段；这些检查不新增人工听看验收。

## 合成、颜色和 4K

本例在 1920×1080 实拍右上放 1080×780 图层，位置 (800,50)，给下方口播字幕留空间；4K 对应图层 2160×1560、位置 (1600,100)。新构图先核人物、主体和字幕安全区，不固定沿用这些数字。

透明 PNG / qtrle ARGB MOV 保存 alpha。把模型图与绘制图层按实际来源识别为 sRGB；本例合成到 SDR BT.709 时，先分离 alpha，只对颜色做一次显式转换，再合回 alpha。原本已是 SDR BT.709 的实拍不重复转换。示意滤镜如下，输入必须先核为对应色彩，不能照搬到 HDR：

```text
[overlay]split[oc][oa];[oa]alphaextract[a];
[oc]format=gbrp,zscale=primariesin=bt709:transferin=iec61966-2-1:matrixin=gbr:rangein=full:primaries=bt709:transfer=bt709:matrix=bt709:range=limited,format=yuv444p[c];
[c][a]alphamerge[o]
```

4K 从原实拍、原生底图和绘制参数重建。原模型底图仍是 1536×864，并不会因 4K 合成变成原生 4K 模型细节；文字、描线和粒子在目标网格重绘，而不是放大整条 1080P 特效。缓存同时绑定底图、绘制器、字体/参数、时间线和配方；字、时序或程序变化要使对应缓存失效。

检查阶段帧后，还要正常速度连着前后场景看：过程是否读懂、标签是否漂移、粒子是否传错意思、口播阶段是否同步、透明边是否异常。技术检查包含帧数/帧率、颜色与 alpha、完整解码；不得把静态图检查或解码通过写成人工完整审片。本轮沉淀只验证复用脚本，不重渲染已交付电影。

## 方法与科学参考

以下为方法与科学背景来源；迁移新主题时仍需核查相应原理，不将视觉图或提示词当作事实来源：

- [Mayer 与 Fiorella 的多媒体学习原则](https://www.cambridge.org/core/books/abs/cambridge-handbook-of-multimedia-learning/principles-for-reducing-extraneous-processing-in-multimedia-learning-coherence-signaling-redundancy-spatial-contiguity-and-temporal-contiguity-principles/CD5B7AE1279A9AB81F8EEBB53DBEC86E)：本次用于邻近标注、同步强调和减少冗余；八秒时长与配色是剪辑选择。
- [地学视频与动画实践](https://www.geosociety.org/gsa-today/june-2020/geoscience-videos-and-animations-how-to-make-them-with-your-students-and-how-to)：用过程故事解释不容易直接看见的变化。
- [USGS：钙华沉积溪流的化学演化](https://www.usgs.gov/publications/chemical-evolution-a-travertine-depositing-stream-geochemical-processes-and-mass)：这项研究不是九寨沟实测，不能套作每个湖的形成结论。
- [九寨沟官方讲解词](https://www.jiuzhai.com/news/scenic-news/10794-2025-11-19-01-23-43)、[景区科普](https://www.jiuzhai.com/tourism-product/popular-science)。
- [BFL FLUX.2 提示词指南](https://docs.bfl.ai/guides/prompting_guide_flux2)、[ComfyUI Klein 工作流](https://docs.comfy.org/tutorials/flux/flux-2-klein)。

生成图、任务收据、完整研究与用户评审记录保存在各项目的本地私有目录，不随仓库分发。公开示例不附个人项目路径或私人素材哈希。