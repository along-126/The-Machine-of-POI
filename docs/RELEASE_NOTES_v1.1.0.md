# The Machine of POI v1.1.0 — UI Redesign

> **发行说明草案 / Release-note draft.** 请先完成 PR 审查和 Windows 实机验收，再使用已合并的 `main` 提交创建正式 `v1.1.0` 标签与 GitHub Release。此文件本身不代表版本已发布。

## 中文

### 更新内容

- **新版启动交互：** `PROCESSING...` 加载进度条，完成后进入 `READY` 循环淡入淡出，使用 **Enter** 启动默认摄像头。
- **待启动画面：** 原创监控风格循环动画，可关闭；允许选择自己有权使用的本地视频作为待启动背景。
- **界面设置：** 右上角白色设置按钮可调整默认摄像头编号、待启动动画及启动视频，打开“边框说明”；右键单击加载状态或进度条可调整加载时长。
- **侧边控制栏：** 鼠标移至右侧边缘展开，移开自动收起；按 **F2** 锁定/解除锁定。
- **人物标签与 HUD：** 保留七种方框样式及十四个视觉标签，蓝色统一为 `ASSET CATALYST`。
- **可靠性：** SQLite 备份连接释放得到修复；GitHub Actions 在 Windows / Python 3.14 上运行语法检查和离线测试（当前 14 项测试通过）。
- **文档：** 更新中英文 README、启动说明、截图展示和安全提示。

### 安装 / 升级

从 GitHub Release 下载 **Source code (zip)**，或克隆仓库。按顺序执行 `01_install_environment.bat`、`02_download_models.bat` 和 `03_run.bat`。

若已经安装过旧版本，请先备份自己的 `data/`（人物数据库、设置）及其他本地数据，然后在**单独的目录**中安装和测试新版本。**不要覆盖或删除已有 `data/`、`models/`、`.venv/`。** 这些目录不包含在 Git 中。

### 验收要点

- `READY`、Enter 启动、F2 侧边栏、设置面板与人脸识别在 Windows 11 上可用。
- 运行 GitHub Actions 后测试通过。
- 摄像头识别使用本地模型，不自动上传人脸数据；网络视频仅在用户主动连接后访问。
- 当前一次仅支持一路识别输入；**本地视频文件导入、网络流兼容性增强及多画面**属于后续版本规划。

## English

### Highlights

- Refined `PROCESSING...` → pulsing `READY` boot UI and **Enter** to start the default local camera.
- Original animated standby screen, optionally disabled or replaced with a user-authorized local standby video.
- Top-right settings for the default camera index, standby video/animation, HUD legend and boot-progress timing.
- Hover-to-expand right-side panel with **F2** pin/unpin.
- Seven face-box styles and fourteen visual-only labels; unified blue label `ASSET CATALYST`.
- Explicit SQLite backup connection cleanup and Windows / Python 3.14 GitHub Actions checks.
- Updated bilingual README.

### Install / upgrade

Download **Source code (zip)** from the release, or clone the repository. Run `01_install_environment.bat`, `02_download_models.bat` and `03_run.bat` in order.

For upgrades, back up your existing `data/` and other local configuration, and try the new version in a **separate folder** first. Never overwrite or delete the existing `data/`, `models/` or `.venv/` directories.

**Known limitations:** One active video source at a time; live RTSP / HTTP(S) compatibility depends on provider and codecs. General-purpose local video-file import and multiview grids are planned for later versions. The project is a fan-made local visualization utility and is not Windows Hello or a threat-classification system.

---

License: MIT for original source; third-party software, model weights, fonts and visual assets retain their respective terms. No television footage or proprietary font files are included.
