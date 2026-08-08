第075章：Deep Path Location Request and Camera Request
=====================================================

核心知识点
----------

* Deep Path 分析把一次 App 可见请求拆成五个稳定边界：Framework API、IPC、System Service、Policy、Provider / HAL / Hardware。
* 位置请求是持续订阅型能力，系统需要联合处理权限精度、前后台状态、provider、功耗、缓存和回调频率；相机请求更接近独占 session，强调 owner、stream 配置、buffer 和实时性。
* Android 位置路径中，``LocationManager`` 通过 Binder 进入 ``LocationManagerService``，服务端把 listener / PendingIntent 与 UID、package、permission、foreground state 绑定，再调度 location provider。
* Android 相机路径中，``CameraManager`` / Camera2 进入 Binder ``CameraService``，随后检查 permission、AppOps、前台状态、设备占用和 stream capability，再进入 camera provider / HAL。
* Apple 位置通过 Core Location 暴露授权与结果，系统后端结合用途声明、授权状态、精度、后台能力和 provider 策略返回位置；私有 daemon 实现不是公共契约。
* Apple 相机通过 AVFoundation 暴露 capture session / device / output，系统后端统一处理隐私授权、资源占用、媒体 pipeline 和 buffer 交付。
* “权限已授权”只说明请求资格成立；位置仍可能因 provider、信号、后台策略失败，相机仍可能因 owner、session 配置、温控或硬件状态失败。

关键路径
--------

通用 Deep Path：

``App intent → Framework API → IPC → System Service / Daemon → caller identity → permission → lifecycle / policy → resource arbitration → Provider / HAL → Driver / Hardware → callback / error``

Android Location：

``LocationManager → Binder → LocationManagerService → permission/precision/background policy → Provider → GNSS/Wi-Fi/Cell/Sensors → callback``

Android Camera：

``CameraManager / CameraDevice → Binder → CameraService → permission/AppOps/owner/stream check → Camera HAL → ISP/Sensor → buffer & metadata callback``

Apple 路径应按公开边界追踪：``Core Location / AVFoundation → system IPC/backend → privacy & lifecycle policy → provider/media pipeline → public callback``。

概念辨析
--------

* **Location request ≠ direct GNSS request**：系统可能使用缓存、网络、蜂窝、Wi-Fi 和传感器融合。
* **Camera API open ≠ camera hardware ownership**：只有系统服务完成权限和资源仲裁后，session 才真正取得设备能力。
* **Authorization status ≠ result availability**：授权允许调用，provider / device 仍可能不可用。
* **Framework error ≠ failure origin**：Framework 只是把服务、HAL 或硬件边界的失败翻译成公开异常和 callback。
* **Android / Apple API 名称不同 ≠ 系统问题不同**：两者都需要完成身份、授权、生命周期、资源和硬件状态的联合判断。

本章结论
--------

排查位置和相机问题时，不应停在公开 API。固定沿 ``API → IPC → Service → Policy → Hardware`` 逐层记录身份、授权、生命周期、资源 owner、session 和 callback 顺序，就能把“没有结果”“打开失败”“黑屏”“回调慢”还原成可定位的系统责任链。
