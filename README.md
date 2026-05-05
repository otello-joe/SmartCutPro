# 🎬 SmartCut Pro (V1.1 Pure White Edition)

![Python Version](https://img.shields.io/badge/python-3.10%2B-blue)
![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20Linux-lightgrey)
![Build Status](https://github.com/otello-joe/SmartCutPro/actions/workflows/build.yml/badge.svg)
![Release](https://img.shields.io/github/v/release/otello-joe/SmartCutPro)

**SmartCut Pro** 是一款专为高效内容创作者打造的现代化视频自动化处理工具。它集成了智能场景分割、分屏裁切、无损变速、水印添加与 BGM 混音等功能，拥有极简的纯白工业级 UI，并针对底层 I/O 和并发进行了深度优化。

---

## ✨ 核心特性 (Key Features)

### 🎞️ 视频与音频处理
- **智能场景分割**：基于 `scenedetect` 算法，自动识别视频转场并精准切片。
- **专业级无损变速**：底层调用 FFmpeg `atempo` 滤镜，**变速不变调**，彻底告别“花栗鼠”音效。
- **自动化合成**：一键添加全局水印（支持自适应缩放）与背景音乐（支持自动循环、音量调节与尾部渐出）。
- **分屏裁切**：一键将横屏/宽屏视频精准裁切为左、右两部分，适合短视频二次创作。

### ⚡ 性能与工程优化
- **内存级 I/O 加速**：在 Linux 系统下自动识别并使用 `/dev/shm`（内存盘）作为缓存，读写速度提升百倍，且零硬盘磨损。
- **智能并发队列**：根据系统 CPU 核心数动态分配线程，采用 `Queue` 消费者模型，拒绝卡顿与内存溢出。
- **显式内存回收**：深度优化 MoviePy 内存泄漏问题，每次渲染后强制 `gc.collect()`，坚如磐石。
- **底层环境隔离**：全局拦截 `subprocess`，彻底解决 PyInstaller 打包后 Linux 下的 `LD_LIBRARY_PATH` 环境变量污染问题。

### 🎨 工业级 UI / UX
- **纯白极简设计**：基于 `customtkinter` 打造的现代化界面，支持 Light/Dark 主题切换。
- **拖拽交互**：支持多文件一键拖拽导入，带有灵动的视觉反馈。
- **实时日志系统**：内嵌可视化日志窗口，渲染进度、报错信息一目了然。
- **布局记忆**：自动记忆用户的窗口大小、位置及分栏比例，下次打开完美还原。
- **系统级通知**：任务队列完成后，自动发送系统级桌面通知（支持 Linux `notify-send`）。

---

## 📥 下载与安装 (Installation)

### 方式一：下载免安装版 (推荐)
我们通过 GitHub Actions 提供了自动打包的开箱即用版本：
1. 前往本仓库的 [Releases 页面](https://github.com/otello-joe/SmartCutPro/releases)。
2. 下载对应系统的压缩包：
   - **Windows**: `SmartCutPro-Windows.zip`
   - **Linux**: `SmartCutPro-Linux.tar.gz`
3. 解压后，直接运行 `SmartCutPro` 可执行文件即可。

> **⚠️ 重要提示**：本软件底层依赖 FFmpeg。
> - **Linux 用户**：请确保系统已安装 FFmpeg (`sudo apt install ffmpeg` 或 `sudo pacman -S ffmpeg`)。
> - **Windows 用户**：请自行下载 `ffmpeg.exe`，并在软件的“系统设置”中配置好 FFmpeg 路径。

### 方式二：从源码运行
确保你的电脑已安装 Python 3.10 或更高版本。

# 1. 克隆仓库
git clone https://github.com/otello-joe/SmartCutPro.git
cd SmartCutPro

# 2. 安装依赖
pip install -r requirements.txt

# 3. 运行程序
python main.py

---

## 🚀 使用指南 (Usage)

- **导入视频**：点击 `+ 导入` 按钮，或直接将视频文件拖拽到左侧列表中。
- **选择模式**：
  - `智能分割`：根据画面变化自动切片。
  - `分屏裁切`：将视频从中间一分为二（左/右）。
  - `合成成品`：不剪切，仅添加水印、BGM和变速。
- **配置资源**：
  - 导入你的水印图片（`.png` / `.jpg`）。
  - 导入背景音乐（`.mp3` / `.wav`），可点击 `▶ 试听` 实时调节音量。
  - 拖动滑块设置视频倍速（0.5x - 2.0x）。
- **开启生产**：点击 `🚀 开启生产`，软件将自动开启多线程处理。处理完成后，点击 `📂 浏览输出` 即可查看成品。

---

## 🛠️ 二次开发与打包 (Development & Build)

本项目已配置完整的 GitHub Actions CI/CD 工作流。如果你想在本地手动打包，请执行以下命令：

# 安装打包工具
pip install pyinstaller

# 执行打包 (包含必要的元数据和依赖)
pyinstaller --noconfirm --onedir --windowed --name "SmartCutPro" \
  --collect-all customtkinter \
  --collect-all tkinterdnd2 \
  --copy-metadata imageio \
  --copy-metadata moviepy \
  main.py

打包完成后，可执行文件将生成在 `dist/SmartCutPro/` 目录下。

---

## 📄 开源协议 (License)

本项目采用 MIT License 开源协议。你可以自由地使用、修改和分发本软件，但请保留原作者的版权声明。
