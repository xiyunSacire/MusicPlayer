# 音乐播放器 MusicPlayer

一个 Windows 桌面音乐播放器，PyQt5 实现，界面清爽、支持本地曲库、歌词同步与桌面歌词。

## 功能

- 本地音乐库：拖入文件夹即可加载，自动读取音频标签与专辑封面
- 播放控制：播放/暂停、上一首/下一首、进度条拖动、音量、顺序/循环/单曲/随机
- 歌词显示：LRC 逐行同步高亮、点击歌词跳转到对应时间点
- 双语歌词：同一时间戳的原文与译文成对显示（译文小一号、更淡）
- 桌面歌词：独立悬浮窗，置顶显示、可拖动，双击锁定后鼠标穿透，支持字号与颜色调整
- 歌词制作工具：打点标注、时间轴微调、逐句试听、翻译录入、导入/导出 LRC
- 网络取词：从网易云音乐搜索并获取歌词（含翻译），带分阶段状态提示
- 歌词缓存：统一保存在 `src/resources/lyrics/`，按 `歌手 - 歌名.lrc` 命名

## 环境要求

- Windows 10/11
- Python 3.10+（开发环境为 3.12）
- 依赖见 `requirements.txt`

```bash
pip install -r requirements.txt
```

## 运行

```bash
python main.py
```

首次启动会在项目根目录生成 `config.json` 保存窗口位置、音量、播放模式与桌面歌词设置。

## 目录结构

```
main.py                     程序入口（设置应用图标与应用标识）
src/player.py               播放器封装：跳转状态机、进度时钟
src/audio_utils.py          音频标签与封面读取
src/lyrics_service.py       歌词读取、网络获取、翻译合并、本地缓存
src/gui/main_ui.py          主窗口与各组件编排
src/gui/ui_controls.py      底部播放控制栏
src/gui/ui_widget.py        播放列表
src/gui/lyrics_widget.py    歌词显示、专辑封面、频谱
src/gui/lyrics_editor.py    LRC 制作与微调工具
src/gui/desktop_lyrics.py   桌面歌词悬浮窗
src/resources/icons/        界面图标与应用图标（app.ico 为多尺寸）
src/resources/lyrics/       歌词缓存目录
```

## 已知问题

在 Windows Media Foundation 后端下，部分时间点的跳转（拖动进度条或点击歌词）不会被底层接受，
表现为"回吐目标位置后时钟从头累加"，界面上看起来像歌词与进度闪回开头。
当前版本已能检测到并在约 1 秒内回落到真实位置，保证界面与声音一致，
但跳转本身不生效的问题需更换或增强播放后端后解决，计划在后续版本处理。

## 调试开关

| 环境变量 | 作用 |
|---|---|
| `MP_SEEK_DEBUG=1` | 输出跳转状态机日志到 `debug/seek.log` |
| `MP_UI_DEBUG=1` | 输出界面事件与心跳日志到 `debug/ui_trace.log`（排查卡顿） |

## 许可

仅用于学习与个人使用。内置歌词与封面由用户本地导入，版权归原作者所有。
