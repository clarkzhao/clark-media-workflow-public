# Clark media workflow

旅行视频项目共享的本地工具与运行库。Git 管理组件清单、使用说明、个人技能和维护脚本；GitHub 仓库为 [clarkzhao/clark-media-workflow](https://github.com/clarkzhao/clark-media-workflow)。模型、软件二进制和 Python 环境不随仓库分发。

## 个人技能

- [clark-video-editing](skills/clark-video-editing/SKILL.md)：素材精选、导演稿、增量审片、画质、科普动画和多比例封面，附参考文档、提示词与封面交付脚本。
- [clark-spoken-delivery](skills/clark-spoken-delivery/SKILL.md)：口播表达、本地本人音色推理、逐句回改与试听，附通用配音脚本和已有 CPU 检查。

`skills/` 是两个技能的维护源。安装时可将技能目录联接到本地技能发现位置，让两处入口读取同一份源码；迁移前先核对并备份已有安装。

技能中的私人封面参考图保留在本地 `skills/clark-video-editing/assets/cover-style/`，已由 Git 忽略。模型、参考声音及配音产物也不入库；迁移源码不代表重新生成或验收媒体。

## 可复用制作方法

- [本地模型配音工作流](docs/local-voice-workflow.md)：VoxCPM2 与 Qwen3-TTS 的调用入口；技能、脚本与模型配置、逐句生成与回改、试听验收和剪辑交接。通用脚本由技能维护，私有声音与大型环境不入库。
- [本地模型插画与科普动画](docs/local-science-animation.md)：石灰岩示例的选图、提示词、科普过程设计、ComfyUI 执行与 UTF-8 排错、透明合成、4K 重绘。附实际 API 图、离线准备脚本和固定石灰岩案例的逐帧绘制器。

## 本地布局

| 路径 | 用途 |
| --- | --- |
| `nvencc_9.37/NVEncC64.exe` | NVEncC 9.37 编码与已验收方案的 RTX VSR 处理 |
| `shotcut/Shotcut/ffmpeg.exe`、`ffprobe.exe` | 媒体处理和属性检查；保留 Shotcut 的完整依赖树 |
| `photo_python/` | pillow-heif 1.8.0，CPython 3.13、Windows AMD64 扩展库 |
| `photo_wheels/` | 对应照片解码库的本地 wheel |
| `editing_env/Scripts/python.exe` | Python 3.12 剪辑辅助环境，包含 comtypes、pymediainfo、uiautomation |
| `components.json` | 相对路径、版本、关键文件 SHA256、运行条件 |
| `scripts/check_components.py` | 检查本地组件身份，可选执行版本命令 |

`photo_python` 是扩展库目录，不是 Python 解释器，不能注入 Python 3.12 环境。运行 HEIF 处理时使用本机现有的 CPython 3.13 AMD64 及 Pillow；`editing_env` 的基础解释器路径见其 `pyvenv.cfg`。移动虚拟环境后必须复核激活脚本与 console 入口，不能仅判断 `python.exe` 是否存在。

## 使用与验证

从当前项目定位同级共享目录，例如 Python 中使用 `project_root.parent / 'clark-media-workflow'`，再按 `components.json` 读取需要的入口。素材、项目配置、私人参考声音和产出继续放在各自项目中。

验证脚本需要 Python 3.11+；这里可直接使用共享环境：

```powershell
& './editing_env/Scripts/python.exe' './scripts/check_components.py' --versions
```

此检查只核对注册表列出的关键文件并运行版本命令，不证明完整渲染、画质或声音验收。完整迁移记录和运行日志留在本地。

## 历史项目兼容

迁移已有工具时，可在旧目录保留指向共享位置的 Windows 目录联接，以兼容历史脚本；新脚本使用共享路径。不要把联接当作第二份备份，也不要递归清理联接目标。只有核实不再存在旧依赖后才移除兼容入口。

工具下载包、运行环境、模型权重、私人声音及项目记录留在本地。只将实际可用且已核查的组件登记到清单中。

## 版本控制与迁移机器

仅明确添加说明、组件清单、`skills/` 内的通用技能资源和维护源码。不要 `git add -f` 软件目录、环境、模型或私人媒体。两个个人技能在本仓库维护，用户技能目录只保留联接；不要再复制一份独立修改。

新机器克隆后，将两个 `skills/<技能名>` 目录安装到该机的技能发现位置，或在 Windows 用目录联接指向克隆路径。安装前检查目标：已存在的目录先核对和备份，不覆盖；没有旧目录时可用 `New-Item -ItemType Junction -Path '<用户技能目录>/<技能名>' -Target '<仓库绝对路径>/skills/<技能名>'`。跨机器须重核本机路径、外部依赖技能及 Python/模型环境；私人封面参考图如需沿用，从本地备份恢复，不把缺图当成已查看。应用发现状态以新会话实际加载为准。

Git 克隆不会包含可执行工具。新机器先按清单核查平台、Python ABI 与已有工具，实际安装或更新时再核来源与许可。模型和大型运行库下载不走 VPN，优先国内官方源；只调整下载子进程并核查真实域名、重定向/CDN 路由，不能确认时停止该下载，不改全局代理或 VPN。

本机绝对路径与历史参考写入被忽略的 `local.paths.json` 或技能 `references/local-machine.private.md`。`.env`、私钥、私有说明和媒体不入库；提交前仍需检查暂存内容，忽略规则不能保护已跟踪文件。
