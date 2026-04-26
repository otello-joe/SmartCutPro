# SmartCut Pro V40 🎬

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python Version](https://img.shields.io/badge/python-3.9%2B-blue)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20Linux-lightgrey)](https://github.com/)

**SmartCut Pro** is a high-performance, AI-powered video automation tool designed for content creators. It enables rapid batch processing of videos, including intelligent scene splitting, split-screen cropping, and automated watermark/BGM compositing.

**SmartCut Pro** 是一款高性能、智能化的视频自动化处理工具，专为内容创作者设计。它支持通过 AI 场景检测进行快速批量处理，包括智能场景分割、同框分屏裁切以及自动化的水印与背景音乐合成。

---

## ✨ Key Features / 核心功能

- 🧠 **AI Scene Detection / 智能场景分割**: Uses `PySceneDetect` to automatically identify shot changes and split long videos into clips. (利用 AI 技术自动识别转场并分割视频)
- ✂️ **Split-Screen Cropping / 同框分屏裁切**: Quickly generate Left/Right split-screen videos for social media. (快速生成适合短视频平台的左右分屏视频)
- 🎨 **Batch Effect Compositing / 批量特效合成**: Automatically apply watermarks and background music (BGM) with volume control to entire batches. (批量添加水印和背景音乐，支持音量调节)
- 🚀 **High-Efficiency Engine / 高效处理引擎**: Supports "Fast Mode" (FFmpeg stream copy) and multi-threaded processing to maximize hardware utilization. (支持极速模式与多线程并行处理，榨干硬件性能)
- 🖥️ **Modern UI / 现代化界面**: A sleek, dark-themed interface built with `CustomTkinter`, featuring drag-and-drop support. (基于 CustomTkinter 开发的现代深色界面，支持文件拖拽)
- ⚙️ **Smart Settings / 智能配置**: Remembers your last used watermark, BGM, and bitrate settings. (自动记忆上次使用的水印、音乐及码率设置)

---

## 🛠️ Prerequisites / 环境准备

Before running SmartCut Pro, ensure you have the following installed:

1. **Python 3.9 or higher**
2. **FFmpeg** (Crucial: Must be added to your system PATH)
   - [Download FFmpeg](https://ffmpeg.org/download.html)
3. **Git** (Optional, for cloning)

在运行 SmartCut Pro 之前，请确保已安装以下环境：
1. **Python 3.9 或更高版本**
2. **FFmpeg** (至关重要：必须添加到系统环境变量 PATH 中)
3. **Git** (可选，用于克隆仓库)

---

## 🚀 Installation / 安装步骤

1. **Clone the repository / 克隆仓库**:
   ```bash
   git clone https://github.com/YOUR_USERNAME/SmartCutPro.git
   cd SmartCutPro
   
   
   
   Create a virtual environment (Recommended) / 创建虚拟环境 (推荐):
code
Bash
python -m venv venv
# Windows
source venv/Scripts/activate


# Linux/macOS
source venv/bin/activate
Install dependencies / 安装依赖:
code
Bash
pip install -r requirements.txt
Run the application / 运行程序:
code
Bash
python main.py
📖 Usage Guide / 使用指南
Import Files / 导入素材: Drag and drop video files directly into the task queue or click + Import. (直接将视频拖入队列或点击“导入”)
Select Mode / 选择模式:
Smart Scene Split: Split video by content changes. (按场景分割)
Split Screen: Crop to left/right halves. (分屏裁切)
Composite Effects: Add watermark and BGM. (合成特效)
Configure / 配置参数: Set your watermark image, BGM, and worker threads. (设置水印、背景音乐及并行线程数)
Start / 开始: Click 🚀 Start Production! to begin. (点击“开启生产”开始处理)
📦 Dependencies / 依赖清单
CustomTkinter - Modern UI components
MoviePy - Video editing engine
PySceneDetect - Scene detection logic
TkinterDnD2 - Drag and drop support
OpenCV - Image/Video processing
📄 License / 许可证
This project is licensed under the MIT License. See the LICENSE file for details.
本项目基于 MIT License 开源。详情请参阅 LICENSE 文件。
🤝 Contributing / 贡献
Contributions are welcome! If you find a bug or have a feature request:
Fork the Project
Create your Feature Branch (git checkout -b feature/AmazingFeature)
Commit your Changes (git commit -m 'Add some AmazingFeature')
Push to the Branch (git push origin feature/AmazingFeature)
Open a Pull Request
欢迎贡献代码！如果你发现 Bug 或有功能建议：
Fork 本项目
创建特性分支 (git checkout -b feature/AmazingFeature)
提交更改 (git commit -m 'Add some AmazingFeature')
推送到分支 (git push origin feature/AmazingFeature)
发起 Pull Request
Developed with ❤️ by [Your Name/Username]
code
Code
---
