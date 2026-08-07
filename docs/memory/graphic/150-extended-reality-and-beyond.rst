第150章：扩展现实与未来显示
========================

核心知识点
----------

XR 的本质是“感知—状态估计—渲染—显示—交互”的闭环
   VR、AR、MR 与未来空间显示都不再只是把场景画到屏幕。传感器、tracking、runtime、renderer、AI 与显示系统共同决定一帧图像是否在正确时间、正确空间和正确质量下出现。

XR Camera 来自身体与空间状态
   Head pose、eye pose、gaze、hand/controller、anchor 和真实环境都可能影响最终视图。相机矩阵必须围绕 predicted display time 构造，避免旧 pose 进入最终 frame。

空间定位是所有虚实融合的基础
   虚拟对象要稳定贴在真实设备、桌面或房间上，必须依赖统一 reference space、anchor 和 tracking state。厘米级漂移通常不是 shader 问题，而是坐标、tracking 或时间语义失配。

Occlusion 决定虚拟内容是否真正进入现实空间
   Passthrough MR 可以使用 environment depth、scene mesh、segmentation 或 hand depth 判断真实/虚拟前后关系；光学透视设备的合成能力不同。遮挡路径必须明确真实世界数据来源和可信度。

光照一致性服务空间可信度
   Exposure、environment light、reflection probe、shadow direction、tone mapping 与 display calibration 共同影响虚拟物体是否“浮在现实之上”。目标不是绝对物理精确，而是让亮度、阴影和反射关系在头动和环境变化下保持一致。

低延迟是 XR 的硬约束
   Sensor sample → prediction → app render → GPU → runtime compositor → reprojection → scanout 的总延迟决定 world-locked 内容是否稳定。平均 FPS 达标仍可能因 pose age 或 queue 过深产生漂移。

Eye Tracking 会直接参与质量调度
   Gaze 可驱动 dynamic foveated rendering，让高 shading rate 聚焦于注视区域。眼动样本必须对齐目标显示时间，并与 head/eye pose 使用同一空间约定。

Hand/Gesture 会改变交互与遮挡
   手势数据不仅驱动 UI hit test，还可能影响 hand occlusion、highlight、haptic/visual feedback 与空间 UI 状态。输入置信度和 tracking validity 应进入交互状态机。

XR UI 的第一目标是可读和稳定
   字体大小、视距、对比度、背景遮罩、观看角度、depth、head/gaze movement 都会影响读取。空间 UI 不应跟随主场景质量降级一起失去可操作性。

Light Field Rendering 把输出从二维像素扩展到位置—方向采样
   用户在一定视区内移动时，需要获得连续视差。View count、angular resolution、spatial resolution、refresh 与 color depth 会快速放大渲染和传输数据量。

Holographic Display 更接近重建波前
   输出可能涉及 phase、amplitude、interference、diffraction、calibration map 与空间光调制器。传统 geometry/material/shading 仍有用，但最终还要转换成显示硬件可执行的光学控制数据。

未来显示会反向约束渲染表达
   HMD 重视低延迟和双眼稳定；透明 AR 重视亮度、光学效率和轻量化；passthrough MR 重视 camera/depth/compositor；light field 重视 view density；holographic display 重视波前与校准。Renderer 必须先知道 display 能表达什么。

多视点系统的核心难题是采样密度
   视点太少会产生跳变、ghosting 和遮挡断裂；视点太多会超出算力与带宽。Depth-aware reprojection、view synthesis、neural interpolation、tile streaming 与 perceptual compression 都是在降低视图采样成本。

未来 XR 渲染应采用“Render Plan”而非固定画质配置
   Render plan 根据 spatial、visual、interaction 和 budget state 决定各 pass 的分辨率、foveation、RT/AI 级别、UI layer 与更新频率。每帧质量分配都应由当前任务和资源状态驱动。

空间状态、视觉状态、交互状态和预算状态应统一输入渲染决策
   Spatial 包含 pose/anchor/depth/scene mesh；visual 包含 exposure/gamut/foveal region；interaction 包含 hand/gaze/focus；budget 包含 frame time/thermal/battery/bandwidth/inference queue。

移动 XR 是功耗受限的异构系统
   CPU、GPU、NPU、ISP、sensor、display 与 wireless 共享热和电池预算。某个 AI 或 graphics pass 单独快，不代表整个设备能长期维持目标性能。

Thermal Degradation 应优先保护空间正确性与交互
   高温时可降低远景、反射、阴影、周边 shading rate、低优先级 AI 与背景重建频率，但应优先保留 pose prediction、anchor stability、UI readability、hand feedback 和必要 occlusion。

AI、传感器与渲染会进一步融合
   Scene data 将从 mesh/material/light 扩展到 anchor confidence、tracking quality、semantic class、sensor timestamp、AI confidence 与 privacy permission。未来 renderer 面对的是持续更新的世界状态，而不是静态资产集合。

AI 适合承担估计、补全与压缩，传统渲染继续承担可控性和确定性
   语义识别、depth completion、view synthesis、neural reconstruction、foveated quality prediction 都可以用 AI；geometry transform、resource lifetime、composition contract 与 fallback 仍需要明确工程规则。

关键路径
--------

XR 闭环：

::

   camera / IMU / depth / eye / hand sensors
   → tracking + sensor fusion
   → head/eye/hand/anchor state
   → scene understanding + AI estimation
   → render plan
   → raster / RT / neural passes
   → runtime compositor + reprojection
   → display optics
   → user perception and interaction
   → next sensor state

未来显示数据流：

::

   scene representation
   → per-view / directional samples
   → view synthesis or wavefront generation
   → compression / streaming
   → display calibration
   → light-field / holographic output
   → visual continuity validation

性能与热预算：

::

   frame timing + thermal + battery
   → classify CPU/GPU/NPU/sensor/display pressure
   → preserve pose/anchor/UI/occlusion
   → reduce low-priority geometry/effects/AI
   → lower peripheral quality or update frequency
   → verify reprojection, readability and stability

概念辨析
--------

* **XR Rendering 与 Ordinary 3D Rendering**：前者还受实时 tracking、真实环境、display optics 和身体反馈闭环约束。
* **AR Occlusion 与 Alpha Blending**：遮挡解决真实/虚拟前后关系，alpha 只描述像素混合。
* **Light Field 与 Stereo**：stereo 只有少量离散 view，light field 要在更宽视区提供位置—方向连续性。
* **Holographic Rendering 与 Multi-View Rendering**：前者面向波前/光学控制，后者主要生成离散视点图像。
* **AI Estimation 与 Spatial Truth**：AI 可以补全缺失状态，但输出应带 confidence，不能自动当作确定空间事实。
* **Quality Degradation 与 Spatial Degradation**：可降低视觉细节，不应优先牺牲 anchor、pose、occlusion 和交互正确性。

本章结论
--------

XR 与未来显示应按“Sensor—Space/Time State—Scene Understanding—Render Plan—Raster/RT/AI—Runtime/Display—User Feedback—Power Budget”理解。未来图形系统的关键不在某一种新显示或神经算法，而在把真实世界感知、渲染生成和显示反馈收束到同一空间、同一时间和同一预算中；只有空间稳定、交互可信、性能可持续时，先进显示和 AI 才真正成为可用图形能力。