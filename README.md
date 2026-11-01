# 口播科普动画 Skill

把一份口播稿、旁白和字幕，变成有分镜、有解释性动作、可以继续修改的科普动画视频。

这个 Skill 将创作经验整理成 AI 助手可执行的工作流程：从理解内容、确定风格，到逐句设计画面、制作预览、根据反馈调整，最后按需导出视频。适用于知识讲解、原理演示、流程说明、观点评论等主题，不限定视频画幅、视觉风格或发布平台。

## 它能做什么

- 从选题、口播稿、已有音频字幕或现有视频工程开始，按当前进度继续。
- 以用户指定的最终音频和 SRT 字幕为时间依据，检查字幕时间、重叠和超出音频等问题。
- 将口播拆成分镜，用对象、动作和状态变化解释内容，让每句话都有视觉承接，而不是机械地每句换镜头。
- 设计适合内容的配色、字体、镜头和画面节奏；根据反馈修改小字、留白过多、素材重复等问题。
- 在工程实现阶段检查环境，使用 Remotion 或合适的现有工具制作、预览和迭代。
- 按需导出成片，制作封面、发布标题与文案；制作发布素材不代表自动发布。

## 安装

本 Skill 与 [Remotion 官方 Skills](https://www.remotion.dev/docs/ai/skills) 配合使用：前者负责科普视频的内容、分镜和制作流程，后者提供 Remotion 实现与渲染指导。使用 Remotion 制作时，请将两者安装到同一个 AI 助手使用的环境。

可以先克隆仓库，审阅 `scripts/install.sh`，再运行安装脚本：

```bash
git clone https://github.com/konka0812/narrated-explainer-video.git narrated-explainer-video
cd narrated-explainer-video
bash scripts/install.sh
```

脚本依次调用 Skills CLI 安装本 Skill 与官方 `remotion-best-practices`。根据提示为两次安装选择相同的 AI 助手与安装范围；也可以传入相同参数避免两次交互，例如 `bash scripts/install.sh --agent codex --global --yes`。脚本会访问网络，Node.js 与 `npx` 需事先可用。

也可以手动在终端依次安装：

```bash
npx skills add https://github.com/konka0812/narrated-explainer-video.git
npx skills add remotion-dev/skills --skill remotion-best-practices
```

按照安装器提示选择你的 AI 助手及安装范围。以上是两次独立安装：单独安装本 Skill **不会自动安装** Remotion 官方 Skills，也不会自动安装 Node.js、Remotion 工程或渲染所需环境。安装前可查阅 [Skills CLI 文档](https://skills.sh/docs/cli) 和 [Remotion 官方文档](https://www.remotion.dev/docs/)。

如果当前环境已有 Remotion 官方 Skills，可直接复用；若不使用 Remotion，已有合适的制作工具也可以用于相应任务。

## 开始使用

在支持 Skills 的 AI 助手中，可以这样描述需求：

> 使用 `$narrated-explainer-video` 和 Remotion Skills，根据我的口播稿、音频和 SRT 字幕制作一条科普动画。先分析字幕与时间轴，给我几个关键画面的设计方案，等我确认后再制作。

也可以直接针对已有工程提出修改：

> 使用 `$narrated-explainer-video`，根据新的旁白和字幕更新视频。开头标题太小，部分画面重复，帮我调整排版、动画和时间同步，然后提供预览。

可提供的材料包括主题与受众、口播稿、最终旁白、SRT 字幕、目标画幅、风格参考和已有工程。不必一次准备齐全；如果没有最终音频，分镜时长仅能估算。

## Remotion 环境

**Skill 是给 AI 助手的指导文件，Remotion 工程才是实际运行和渲染视频的项目。**

进入制作阶段时，助手应先检查本机环境。已有工程优先按原有包管理器和锁文件恢复依赖；没有工程时再准备 Node.js、包管理器和兼容的系统环境，创建新工程，准备渲染浏览器，并检查 Studio 预览和测试帧。仅讨论选题或方案时，不需要先安装完整环境。

详见 [环境检查与首次搭建](skills/narrated-explainer-video/references/environment.md) 和 [Remotion 官方创建项目文档](https://www.remotion.dev/docs/)。

## 字幕时间轴检查

项目附有 `scripts/inspect_media.py`，使用 Python 3 标准库解析 SRT，保留字幕原文和绝对时间，并生成帧时间轴及警告：

```bash
python3 /path/to/narrated-explainer-video/scripts/inspect_media.py \
  --srt /path/to/captions.srt \
  --audio /path/to/narration.mp3 \
  --fps 30 \
  --output /path/to/timeline.json
```

把路径替换为实际安装位置和输入文件。`--audio` 与 `--output` 可省略；不指定输出文件时，JSON 写入标准输出。分数帧率可写为 `--fps 30000/1001`。脚本传入 `--audio` 时需要系统 `PATH` 中有 `ffprobe`；Remotion 自带的媒体工具不会自动被这个脚本调用。

脚本用于检查时间结构，并不进行语音识别，也不能判断字幕文字是否与口播一致；音画同步和观看体验仍需要实际预览。

## 目录

```text
scripts/install.sh                              两个 Skill 的安装入口
skills/narrated-explainer-video/
  SKILL.md                                      Skill 入口与整体工作流程
  references/environment.md                     环境检查与首次搭建
  references/storyboard.md                      分镜与语义动画
  references/production.md                      工程实现与时间同步
  references/review-delivery.md                 预览、检查与交付
  scripts/inspect_media.py                      SRT 与音频时间轴检查工具
  agents/openai.yaml                            Skill 界面元数据
```

## 创作原则

动画的作用是帮助理解：把因果、过程、对比、累积和反馈变成观众看得见的变化。画面文字要简洁、清楚，不能为了填满屏幕而堆砌装饰；新闻截图和数据要保留真实来源与上下文。静帧检查、连续播放和导出文件检查各有作用，不能相互替代。

## 许可证

本仓库代码和文档采用 [MIT 许可证](LICENSE)。Remotion 官方 Skill 独立维护，其许可与使用条件以其官方仓库为准。
