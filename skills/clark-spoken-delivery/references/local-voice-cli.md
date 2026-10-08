# 本地代配音命令行复现（Windows）

这是本地参考音色推理的可复用配方。仅推理，不微调参数。参考录音、参考转写、待配稿、生成音频及收据全部放在仓库外的本地私有目录；仓库只收录通用脚本与文档。

## 参考环境与本机配置

- 参考版本：Python `3.12.14`；需要兼容的 NVIDIA GPU、驱动与足够显存。
- PyTorch `2.9.1+cu128` / CUDA runtime `12.8`；voxcpm `2.0.3`；qwen-tts `0.1.1`；transformers `4.57.3`；soundfile `0.14.0`；numpy `2.5.3`。
- Python：使用已安装语音环境的解释器，路径保存在本机私有配置中。
- 权重根目录包含所选引擎的 `VoxCPM2` 或 `Qwen3-TTS-12Hz-1.7B-Base`。复制技能不包含权重或环境。
- 上述版本是参考组合，不是完整锁文件。异机安装先按主技能检查下载路由、核实完整依赖和 GPU 兼容性，不盲目执行安装或下载。

```powershell
$py = '<语音环境>/Scripts/python.exe' # 替换为已核查的解释器
$repoRoot = '<仓库绝对路径>'
$ff = Join-Path $repoRoot 'shotcut/Shotcut/ffmpeg.exe'
& $py -c "import torch; print(torch.__version__, torch.version.cuda, torch.cuda.is_available()); print(torch.cuda.get_device_name(0))"
& $py -m pip check
```

历史验证使用过裁剪的推理环境，`pip check` 曾报告缺少 gradio，以及 VoxCPM 声明的 datasets、funasr、matplotlib、modelscope、spaces、wetext。不能声称完整依赖检查通过。下述禁用 denoiser/normalize、无 Web UI 的推理路径单独实测；训练、文本正规化或其他功能可能依赖这些包。不要为消除提示自动安装全部依赖，先判断调用路径并遵守下载约定。

## 准备输入

优先从当前项目清单读取已验收参考；若存在本地 `local-machine.private.md` 可按其入口查找，不把历史路径当作新项目默认值，不把参考声音或转写复制到技能仓库。

脚本要求单声道 WAV/FLAC、3–30 秒干净选段与逐字对应的 UTF-8 转写。这是本配方的工作边界，不是所有模型的固有限制。待配稿为 UTF-8 文本，单次最多 200 字；分段长度依实际语义。

需要从录音截取时，先人工确定入点和时长。示例数值必须按自己的选段修改；不覆盖原录音：

```powershell
& $ff -n -ss 12 -i 'D:/private-voice/recording.m4a' -t 12 -vn -ac 1 -ar 48000 -c:a pcm_s24le 'D:/private-voice/reference.wav'
```

`D:/private-voice` 是示例占位路径，先建立实际本地目录并填写 `reference.txt` 与 `line01.txt`，不要凭示例时间截取后沿用旧转写。

## 主用 VoxCPM2

```powershell
$env:PYTHONUTF8 = '1'
$cli = Join-Path $repoRoot 'skills/clark-spoken-delivery/scripts/local_voice.py'
$models = '<本机模型根目录>'
$private = 'D:/private-voice' # 改为本机已准备的私有目录
& $py $cli --engine voxcpm2 --model "$models/VoxCPM2" --reference "$private/reference.wav" --transcript "$private/reference.txt" --text "$private/line01.txt" --output "$private/line01_vox_raw.wav" --seed 10403 --cfg 2.0 --steps 10
if ($LASTEXITCODE -ne 0) { throw 'Voice inference failed' }
```

内部使用 `VoxCPM.from_pretrained(..., load_denoiser=False, optimize=False, local_files_only=True, device='cuda')`，`generate` 同时传 `prompt_wav_path`、`prompt_text`、`reference_wav_path`，并设 `normalize=False, denoise=False, retry_badcase=False`。这复用本项目配方，不声称所有输入的最优参数。

## 备选 Qwen3-TTS

```powershell
& $py $cli --engine qwen3 --model "$models/Qwen3-TTS-12Hz-1.7B-Base" --reference "$private/reference.wav" --transcript "$private/reference.txt" --text "$private/line01.txt" --output "$private/line01_qwen_raw.wav" --seed 10403
```

内部使用 BF16、`cuda:0`、`attn_implementation='sdpa'`，`generate_voice_clone(language='Chinese', ref_audio=(audio,sr), ref_text=prompt)`；不强装 FlashAttention。Vox 的 cfg/steps 参数不用于 Qwen。

## 后处理与交付

```powershell
& $ff -n -i "$private/line01_vox_raw.wav" -af 'atempo=1.0,loudnorm=I=-18:TP=-2:LRA=7' -ar 48000 -ac 1 -c:a pcm_s24le "$private/line01_vox_edit.wav"
```

这是本次使用的单遍响度与剪辑采样率配方，不保证严格达到目标综合响度，也不替代最终混音测量。速度与句间停顿依当前语义和听感调整。保留 raw；不要用速度处理挽救不自然的句子。

脚本拒绝覆盖既有 WAV 或 JSON；输出浮点 WAV 与同名 JSON，记录输入哈希、权重身份、版本、种子、参数、时长和显存峰值。仅预检公共依赖与选中引擎，不要求安装另一个引擎。种子相同不保证跨版本/硬件逐位一致；调用者检查收据后决定是否复用，脚本不自动命中缓存。

## 多句批量生成

将以下清单保存为私有目录中的 `jobs.json`，路径相对于清单所在目录，也支持绝对路径。待配稿文件需先准备好。

```json
[
  {"text": "line01.txt", "output": "batch/line01.wav"},
  {"text": "line02.txt", "output": "batch/line02.wav"}
]
```

```powershell
& $py $cli --engine voxcpm2 --model "$models/VoxCPM2" --reference "$private/reference.wav" --transcript "$private/reference.txt" --batch "$private/jobs.json" --seed 10403 --cfg 2.0 --steps 10
```

`--batch` 与单句 `--text/--output` 二选一；所有任务先检查输入、输出冲突与依赖，再加载一次模型、计算一次完整权重哈希。共享信息写入 `jobs.model.json`，每句收据引用其路径与哈希；共享记录和各句收据需一起保留在本地。每句独立重置随机种子，按顺序生成，不并发占用 GPU。

批量中途失败时，已经完成的句子保留；未完成任务另建清单重试，不覆盖旧结果。`setup_s` 是整批共享准备耗时，各句 `generation_s` 是各自生成耗时，不要把 setup 在逐句统计中重复相加。批量清单与收据均不入库。

## 隐私与故障边界

- 脚本设置 Hugging Face 离线变量，并拒绝 Python socket connect；这不是系统级防火墙，也不能证明原生库/子进程绝无联网。已安装环境应核实行为；缺依赖/权重时失败，不在推理中临时下载。
- CUDA 不可用时停止，不隐式回退 CPU。显存不足先检查占用，串行加载模型并按语义缩短句子；只结束本任务已确认可停止的 GPU 作业，不中断其他任务，不同时加载两个模型。
- 权重目录缺文件、版本不匹配或参数不兼容时对照上述版本检查，不能通过删除离线设置绕过错误。
- 内容靠本地 ASR 辅助核对；音色、英文词、语气及前后衔接需实际试听。JSON 默认 `human_listening_verified=false`。
- 继续旧工程前检查其批处理依赖和缓存键，不把固定历史计划或仅按文本命中的缓存作为新项目通用入口。

## 验证范围

修改推理脚本时先运行同目录的 `test_local_voice.py`（仅 CPU），检查单引擎依赖隔离、批量相对路径和输出冲突预检；纯文档修改只核查受影响内容。历史本地验证覆盖两条引擎的单句 CLI 与批量生成，音频和收据保存在私有项目，不随源码发布；这些记录不证明当前机器可用或听感合格。

Qwen 的历史直接生成路径使用 SDPA 成功完成，但曾出现 SoX 缺失、flash-attn 未安装和 pad token 提示。需要 SoX 的额外处理功能未验证；不要把提示隐藏成完整环境通过，也不必为成功的 SDPA 推理强装 FlashAttention。
