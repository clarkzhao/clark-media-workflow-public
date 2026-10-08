# RTX VSR 命令行复现（Windows）

## 工具与实现

- NVEncC `9.37`；仓库相对入口 `nvencc_9.37/NVEncC64.exe`。需要支持 NGX VSR 的 NVIDIA GPU 与驱动。
- 同目录有 `nvngx_vsr.dll`，参考试样记录版本为 `1.8.3.0`。NVEncC 通过 NVIDIA NGX VSR 执行超分，不是 SeedVR2，也不是只在浏览器播放时开启的增强。
- FFmpeg：仓库相对入口 `shotcut/Shotcut/ffmpeg.exe`。
- 帧级验证可用已安装 PyAV 的 Python；从本机私有配置定位解释器。
- 这些二进制不随技能仓库分发。迁移机器需先核查工具版本、GPU/驱动和本地 DLL，不从推理流程自动下载。下载遵守主技能的非 VPN 路由要求。

```powershell
$toolRoot = '<仓库绝对路径>'
$nv = "$toolRoot/nvencc_9.37/NVEncC64.exe"
$ff = "$toolRoot/shotcut/Shotcut/ffmpeg.exe"
& $nv --version
& $nv --check-features
Get-FileHash "$toolRoot/nvencc_9.37/nvngx_vsr.dll" -Algorithm SHA256
Get-AuthenticodeSignature "$toolRoot/nvencc_9.37/nvngx_vsr.dll" | Select-Object Status
```

组件版本与相对入口见仓库 `components.json`；二进制和环境不随 Git 分发。当前素材、输出和可选项目适配器从本机配置定位。

## 输入先变成经核验的 SDR BT.709

以下命令仅用于**已确认 BT.709 SDR limited、横屏 16:9、无旋转的低分辨率素材**。full-range 输入须先验证范围转换；不要用于未知颜色、HLG/PQ 或随意拉伸竖屏。确认输出目录是新目录；所有命令检查退出码。

```powershell
$source = 'D:/media/source.mp4' # 改为实际源文件
$work = 'D:/media/vsr_trial01' # 改为新的本地输出目录
New-Item -ItemType Directory -Path $work -ErrorAction Stop | Out-Null
& $ff -n -ss 2 -i $source -an -vf 'setpts=PTS-STARTPTS,fps=30,setsar=1,format=yuv444p10le' -frames:v 210 -c:v libx264 -preset fast -qp 0 -pix_fmt yuv444p10le -color_primaries bt709 -color_trc bt709 -colorspace bt709 -color_range tv "$work/input_709_30.mp4"
if ($LASTEXITCODE -ne 0) { throw 'Input preparation failed' }
```

这里的 2 秒入点、210 帧为 7 秒示例；要核实原片区间足够长，不循环、不长时间补静帧。`fps=30` 是取/重复帧，不是光流插帧；原片 60→30 的流畅感变化与超分算法分开评估。标签不能执行 HDR→SDR 转换。

HLG/PQ 输入必须先验证实际 tone mapping，并记录 LUT 或转换参数及其身份；本技能不提供未经验证的通用 LUT。不能只更改标签。原生 4K 走原片路径，不进 VSR。

## 超分：实际采用的参数

单独启动的 PowerShell 进程内设置下列变量，进程退出即结束；不要改全局 VPN/代理。清除代理不能证明绕过系统 VPN。已有 NGX 缓存与 DLL 应足够运行，出现更新/联网需求时停止排查。

```powershell
Get-ChildItem Env: | Where-Object Name -Match 'proxy' | ForEach-Object { Remove-Item -LiteralPath "Env:$($_.Name)" }
$env:NO_PROXY = '*'
$env:__NGX_DISABLE_UPDATER = '1'
$env:__NGX_LOG_LEVEL = '1'
$env:__NGX_LOG_PATH_OVERRIDE = $work
if (Test-Path "$work/vsr_4k30.mp4") { throw 'Output already exists' }
& $nv --avsw -i "$work/input_709_30.mp4" -o "$work/vsr_4k30.mp4" --codec hevc --preset quality --cqp 12 --output-depth 10 --output-res 3840x2160 --vpp-resize 'algo=ngx-vsr,vsr-quality=4' --colormatrix bt709 --colorprim bt709 --transfer bt709 --colorrange limited --log-level debug 2> "$work/vsr.log"
if ($LASTEXITCODE -ne 0) { throw 'RTX VSR failed; inspect vsr.log' }
Select-String -Path "$work/vsr.log" -Pattern 'ngx-vsr|nvsdk-ngx'
```

`--avsw` 用软件解码，超分和 HEVC 编码仍由 NVIDIA 处理。Q4 为本次质量档位，CQP12 为高质量中间片，不是发布文件的固定码率。必须看日志确认实际启用了 `ngx-vsr`，不能仅以 4K 输出尺寸为证据。NGX 内部 RGBA8，Main10 编码不等于恢复原生 10-bit 细节。

竖屏或其他比例先计算保持比例的目标尺寸，匹配最终分屏单元，不直接套 3840×2160。中间片暂不带音轨；剪辑时仍从原片同一入点读取现场声，字幕和路牌等图文在增强后合成。

## 同条件基线与检查

```powershell
& $ff -n -i "$work/input_709_30.mp4" -an -vf 'scale=3840:2160:flags=lanczos,format=yuv420p10le' -c:v hevc_nvenc -preset p7 -qp 12 -color_primaries bt709 -color_trc bt709 -colorspace bt709 -color_range tv "$work/lanczos_4k30.mp4"
& $ff -v error -i "$work/vsr_4k30.mp4" -map 0:v:0 -f null -
```

两种编码器接口的相同 QP 不保证完全一致的编码行为；判断细微纹理时注意编码误差。正常速度比较同一帧率的片段，再单独比较原生帧率版本。检查尺寸、30fps、实际解码 210 帧、PTS 连续、BT.709 limited 标签、闪烁/拖影/假纹理。浏览器卡顿时先排查解码/码率，用审片代理辅助，不能直接判定模型不流畅。

## ComfyUI 是可选入口

可选本地适配器包装同一 NVEncC 流程，不是通用内置节点，也不随本仓库分发。先从本机私有配置确定节点名，读取服务 `/object_info/<节点名>` 核实节点及输入结构；不存在时使用上面的独立 CLI，不伪造节点。

先检查 `/queue` 避免占用他人 GPU 任务，再提交本任务已授权的 `/prompt`，按返回的 prompt_id 查询 `/history/{prompt_id}`。成功须同时核对 status、实际输出和日志；GUI 工作流不能直接当 API prompt 提交。历史验证脚本可能提交作业或复制文件，先读实现，不作为只读命令执行。

## 项目适配与故障边界

- 项目专用函数可能依赖素材索引、LUT、时间线和已确认的阶段授权；使用前核查实际依赖，不伪造审批记录使函数通过。
- 缓存绑定源内容、入点、帧数、颜色转换、工具/DLL 身份和参数。长期跨机复用记录 SHA256；图像或颜色参数改变应重建。
- NGX 缺文件、驱动不兼容、CUDA OOM：保留日志，检查本机版本/显存与 DLL；失败不默默回退普通放大后仍标 VSR。不自动启用 NGX updater 或下载模型。

## 验证范围

历史技术验证用已转换的 SDR 1080P30 短片运行上述 NVEncC 参数，日志确认 `ngx-vsr 1920x1080 -> 3840x2160`；PyAV 全解码核查输出尺寸、30fps、BT.709 limited 与连续 PTS。样片与日志仅保留本地。这证明对应环境的命令可运行，不替代人工画质验收，也不保证其他机器或素材兼容。
