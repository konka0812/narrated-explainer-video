# 口播科普动画 Skill

把口播稿、旁白和字幕转化为有分镜、有解释性动作、可以继续修改的科普动画视频。

这个 Skill 为 AI 助手提供从内容理解、视觉设计到动画制作、预览修改和交付的工作流程，适用于知识讲解、原理演示、流程说明和观点评论。不限定主题、画幅、视觉风格或发布平台。

## 它能做什么

- 从选题、口播稿、最终音频字幕或已有工程开始，按当前进度继续。
- 以用户指定的最终版本建立时间轴，检查字幕重叠、空白和超出音频等问题。
- 用对象、动作和状态变化解释口播，让每句话都有视觉承接，无需机械地逐句切镜头。
- 结合已有素材确定视觉方向，处理文字大小、素材重复、字体加载和字幕安全区等问题。
- 使用 Remotion 制作、预览和迭代；已有合适的其他工具链也可沿用。
- 按需导出视频，并制作封面、发布标题与文案。发布素材由用户决定如何发布。

## 与 Remotion Skill 的关系

本 Skill 负责科普视频的内容表达、分镜和制作流程；官方 [`remotion-best-practices`](https://github.com/remotion-dev/skills) 负责 Remotion 的具体实现与渲染指导。使用 Remotion 制作时，两者应安装到同一个 AI 助手和安装范围中。

Skills CLI 不会因本 Skill 提到了另一个 Skill，就自动解析并安装它。下面的联合安装脚本会明确执行两次安装；单独安装本 Skill 时，需要自行补装或复用已有的官方 Skill。

安装 Skill 也不会安装 Node.js、Remotion 工程、渲染浏览器或 Python。进入制作阶段后，助手会按 [环境准备流程](references/environment.md) 检查并补齐实际需要的环境。

## 安装

安装器需要 Node.js、`npx` 和网络连接。先检查仓库中的 [`scripts/install.sh`](scripts/install.sh)，再执行。

### Codex 用户级安装

将两个 Skill 安装到 Codex 的用户级环境，方便多个视频项目复用：

```bash
git clone https://github.com/konka0812/narrated-explainer-video.git
cd narrated-explainer-video
bash scripts/install.sh --agent codex --global
```

脚本把相同的参数传给两次安装。可追加 `--yes` 跳过安装器确认；使用其他支持 Skills 的助手时，将 `codex` 替换为对应助手名称。已有同名 Skill 或本地修改时，先查看安装器提示，避免覆盖需要保留的内容。

### 项目级安装

项目级安装的位置由**执行命令时的当前工作目录**决定。先进入目标视频工程，再使用安装脚本的绝对路径，不传 `--global`：

```bash
cd "/path/to/video-project"
bash "/path/to/narrated-explainer-video/scripts/install.sh" --agent codex
```

将示例路径替换为实际位置。如果在本仓库目录直接执行无 `--global` 的命令，Skill 会安装到本仓库，而非另一个视频工程。

### 手动安装与 Windows PowerShell

`install.sh` 需要 Bash；Windows 可使用 Git Bash / WSL，也可以在 PowerShell 中分别执行以下两条命令：

```powershell
npx skills add konka0812/narrated-explainer-video --skill narrated-explainer-video --agent codex --global
npx skills add remotion-dev/skills --skill remotion-best-practices --agent codex --global
```

项目级安装时，在目标视频工程目录中执行，并同时移除两条命令的 `--global`。两次安装选择相同的助手和范围。安装器的更多选项见 [Skills CLI 文档](https://skills.sh/docs/cli)，官方依赖的使用方式见 [Remotion Agent Skills 文档](https://www.remotion.dev/docs/ai/skills)。

## 开始使用

在支持 Skills 的 AI 助手中，可以这样描述需求：

> 使用 `$narrated-explainer-video` 和 Remotion Skill，根据我的口播稿、音频和 SRT 字幕制作科普动画。先分析内容和时间轴，给我几个关键画面的设计方案，等我确认后再制作。

已有工程可以直接提出修改：

> 使用 `$narrated-explainer-video`，根据新的旁白和字幕更新视频。开头标题太小，部分素材重复，帮我调整排版、动画和同步，然后提供预览。

可提供主题与受众、口播稿、最终音频、SRT 字幕、目标平台与画幅、风格参考和已有工程。不必一次准备齐全；没有最终音频时，分镜时长只能估算。已确定的风格与交付要求可以直接沿用，无需每次重新选择。

## 制作方式

助手会先了解当前材料和交付要求，再组织逐句分镜。动画重点表现因果、过程、对比、累积和反馈；画面文字负责强调，字幕负责帮助观众跟上口播。

已有素材会参与视觉设计，但不限制所有镜头采用同一种背景或布局。需要时检查透明边缘、裁切、角色状态与字体加载；字幕和平台界面留出合理空间，具体位置与尺寸按画幅和内容确定。相关方法见 [素材准备](references/assets.md)、[环境与字体](references/environment.md) 和 [分镜与语义动画](references/storyboard.md)。

进入工程制作时，已有 Remotion 项目优先按原包管理器和锁文件恢复依赖；没有工程时再创建。先验证 Studio 预览和测试帧，再制作整片。仅讨论稿子或方案时无需安装完整环境。

交付前区分静帧检查、连续播放和文件检查：它们分别验证构图与可读性、节奏与同步、编码与完整性。检查范围会如实记录。封面和发布文案按需制作，不自动扩展交付范围。

## 字幕时间轴检查

仓库附带 Python 工具，使用标准库解析 SRT，保留字幕原文与绝对时间，并输出帧时间轴和警告。从仓库根目录可以执行：

```bash
python3 scripts/inspect_media.py \
  --srt "/path/to/captions.srt" \
  --audio "/path/to/narration.mp3" \
  --fps 30 \
  --output "/path/to/timeline.json"
```

在 Windows 中可使用本机可用的 `python` 或 `py` 命令，并按 PowerShell 语法换行，或将命令写成一行。示例路径替换为实际位置，输出文件的父目录需要存在。

`--audio` 与 `--output` 可省略；不指定输出文件时，JSON 写入标准输出。分数帧率可写为 `--fps 30000/1001`。传入 `--audio` 时，系统 `PATH` 中需要有 `ffprobe`；Remotion 提供的媒体工具不会自动被这个 Python 脚本调用。

工具检查时间结构，不进行语音识别，也不能证明字幕文字与发音一致。最终同步和观看体验仍需要实际预览。详见 [实现与同步](references/production.md)。

## 仓库结构

```text
SKILL.md                       面向 AI 助手的工作流程入口
README.md                      面向使用者的安装与使用说明
LICENSE                        MIT 许可证
agents/
  openai.yaml                  Skill 界面元数据
references/
  environment.md               环境检查与首次搭建
  storyboard.md                分镜与语义动画
  assets.md                    素材准备与复用
  production.md                工程实现与时间同步
  review-delivery.md            预览、检查与交付
scripts/
  install.sh                   联合安装本 Skill 与官方 Remotion Skill
  inspect_media.py             SRT 与音频时间轴检查工具
```

本仓库只发布一个 Skill，`SKILL.md` 和配套文件直接放在根目录。`scripts/install.sh` 是联合安装入口，`scripts/inspect_media.py` 是制作时使用的时间轴工具。安装过程中从官方来源获取 Remotion Skill，本仓库不内置其副本。

## 许可证

本仓库代码和文档采用 [MIT 许可证](LICENSE)。Remotion 官方 Skill 独立维护，其许可与使用条件以官方仓库为准。
