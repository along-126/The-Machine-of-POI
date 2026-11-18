# Third-party licenses / 第三方许可证说明

The MIT license in this repository applies to the project's own source code only. It does **not** relicense third-party components, models, or television materials. This source repository does not bundle the runtime packages or ONNX model weights; installation scripts retrieve them separately.

本仓库的 MIT 许可证仅适用于项目自身有权授权的源代码，不会改变第三方依赖、模型或影视素材的原有许可。本源码仓库不直接包含运行时依赖包或 ONNX 模型权重；用户通过安装脚本分别下载。

| Component / 组件 | Purpose / 用途 | Original license / 原有许可 | Upstream / 官方来源 |
| --- | --- | --- | --- |
| OpenCV Zoo YuNet | Face detection / 人脸检测 | MIT | https://github.com/opencv/opencv_zoo/blob/main/models/face_detection_yunet/LICENSE |
| OpenCV Zoo SFace | Face feature extraction / 人脸特征提取 | Apache License 2.0 | https://github.com/opencv/opencv_zoo/blob/main/models/face_recognition_sface/LICENSE |
| PySide6 / Qt for Python | Desktop interface / 桌面图形界面 | LGPLv3 / GPL / commercial options; comply with the license chosen for distribution | https://doc.qt.io/qtforpython-6/ |
| opencv-python | Python OpenCV distribution / OpenCV Python 包 | Package build scripts: MIT; underlying bundled components have their own notices | https://github.com/opencv/opencv-python |

For releases that redistribute dependencies or model files (such as a packaged Windows executable), include the applicable full license texts and copyright notices, and separately review PySide6/Qt distribution obligations. This file is an attribution overview, not a substitute for the original license terms or legal advice.

若日后发布打包了依赖库或模型的 Windows EXE 等发行物，请附上相关完整许可证与版权声明，并核查 PySide6/Qt 的再分发义务。本文件仅作归属和许可概览，不能替代原始许可文本或法律意见。

The Machine of POI is an unofficial fan-inspired project and is not endorsed by the *Person of Interest* rights holders.

The Machine of POI 是非官方爱好者项目，不代表《疑犯追踪》版权方或得到其背书。
