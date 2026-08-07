第075章：生产工作流集成
======================

核心知识点
----------

生产工作流管理的是“可复现镜头状态”，不只是渲染命令
   一个正式镜头提交应固定 scene assembly、资产版本、动画/特效缓存、灯光、相机、render profile、AOV schema、color config、输出命名和交付规格。只有这些输入可回溯，后续 render、comp 和 review 才能形成同一生产事实。

Render Package 是离线渲染进入生产链的核心契约
   它把镜头当前需要的场景描述、依赖清单、renderer version、采样参数、帧范围、AOV 和输出规则打包为可提交对象。Worker 不应依赖艺术家工作站中的临时状态或本地路径推断任务输入。

Asset Pipeline 的衔接点是发布版本与依赖 Manifest
   模型、材质、贴图、rig、Alembic、USD、VDB、light rig 等都应以 publish/version/hash 进入依赖清单。正式提交优先消费 approved/locked 发布数据，work 数据若必须使用，应在 manifest 中显式标记。

源文件、发布文件与渲染缓存要分层
   Source file 服务创作，可能包含本地依赖和临时节点；publish 是稳定生产入口；cache 是面向渲染和装配优化后的 USD/Alembic/VDB/mip 等派生数据。Farm 应尽量读取发布与缓存，而不是直接打开艺术家源场景。

路径解析必须在提交前完成
   用户目录、相对路径、平台路径和 DCC 私有引用需要重写为农场可访问的逻辑资产引用。稳定路径解析应保留资产语义和版本关系，使本地机房、远端机房和云 Worker 都能解析到同一发布内容。

Scene Assembly 是资产与镜头覆盖的组合层
   它将 asset publish、shot animation、FX cache、lighting layer、camera 和局部 override 组合成 renderer 可消费的场景。生产问题常来自装配层未刷新、局部 override 覆盖错误或版本组合不一致，因此 scene assembly 本身必须可版本化。

Render Settings 与 AOV Schema 都应发布化
   Samples、bounce、motion blur、volume step、resolution、device、denoise 和 AOV 不应散落在 DCC 当前 UI 状态中。应使用可版本化 profile/schema，让同一镜头的 preview、low-sample 和 final 任务只通过明确 profile 区分。

DCC Export 的目标是去除交互状态
   Maya、Houdini、Blender、Katana 等工具中的 viewport、临时 layer、用户路径和插件私有状态不应成为 Farm 隐式依赖。Export 应生成明确 geometry、camera、material binding、instance、light、cache 与 metadata，并记录 DCC/plugin version 和帧范围。

自动化应分阶段推进风险
   稳定路径通常是 preflight → key-frame preview → low-sample full range → final render → output QC → delivery package。每一阶段都把结果写回状态系统，只有上一阶段满足验证条件才继续，提高最终全量渲染前发现错误的概率。

Preflight 应尽量在昂贵渲染之前失败
   文件存在性、版本状态、路径、帧范围、AOV schema、renderer version、输出权限和 scene package 解析都可在提交前验证。能在几秒内发现的错误不应进入数小时的 Farm 任务。

失败重跑必须区分临时故障与稳定输入错误
   Worker 失联、短暂存储错误和节点重启可以自动 retry；missing asset、shader compile failure、scene parse error、schema mismatch、持续 OOM 需要修复输入或资源预算。自动重跑必须有次数上限和 failure signature，避免无限占用队列。

Incremental Render 依赖可靠依赖图
   角色局部材质修改可能只影响部分 frame/layer，灯光全局变化可能要求 beauty 和多个 AOV 重算。只有资产变化能映射到 shot、frame、layer 和 output 时，增量重渲才安全；缺少依赖图时宁可保守重算，也不能漏掉受影响结果。

质量监控应覆盖提交前、执行中、输出后、图像内容和合成接口
   Farm completed 只说明任务结束。生产系统还要检查缺帧、EXR header、AOV 通道、metadata、黑帧、NaN、alpha、噪声、色彩、命名以及 comp template 是否能正确读取。最终状态应区分 rendered、missing、failed、qc_failed、approved。

AOV 接口错误不能靠盲目全量重跑解决
   Beauty 正常但 Cryptomatte 缺失时，先检查 render profile、AOV schema、EXR header 与 comp mapping。只有接口修复并通过关键帧验证后，再重渲真正受影响的帧或 layer。

生产归档要保存结果产生过程
   最终 EXR、review proxy、render package、资产依赖、renderer/profile/schema version、QC、失败修复与重跑记录都应归档。未来复查必须能重建“哪个输入经过哪次任务产生这个交付版本”。

关键路径
--------

镜头生产路径：

::

   asset publish
   → dependency manifest
   → shot scene assembly
   → render package
   → preflight
   → preview / low-sample validation
   → farm submit
   → final EXR + AOV
   → output QC
   → compositing load
   → review / approval
   → delivery archive

自动化与重跑：

::

   template task
   → validate inputs
   → execute stage
   → write status / artifacts
   → classify failure
   → transient: bounded retry
   → input/schema/resource error: stop and repair
   → rerun affected frame / layer
   → QC again

质量检查：

::

   manifest / profile / schema
   → worker log / runtime state
   → frame sequence completeness
   → EXR header / channel / metadata
   → black / NaN / alpha / luminance / noise checks
   → color transform validation
   → comp template load
   → delivery naming / package

概念辨析
--------

* **Source、Publish 与 Cache**：Source 服务编辑，Publish 是稳定版本入口，Cache 是为下游消费优化的派生数据。
* **Render Package 与 DCC Scene**：Render package 是可提交生产契约，DCC scene 只是其中一个上游来源。
* **Asset Version 与 Shot Version**：资产版本描述可复用对象，镜头版本描述当前镜头组合、覆盖和渲染状态。
* **Render Profile 与 AOV Schema**：Profile 控制渲染质量/设备参数，Schema 定义输出层和接口；二者应独立版本化。
* **Preflight 与 QC**：Preflight 在计算前验证输入，QC 在输出后验证结果，不能互相替代。
* **Retry 与 Rerender**：Retry 通常针对同一输入的临时执行失败；rerender 可以发生在输入修复或版本变化后。
* **Task Complete 与 Shot Approved**：前者是计算状态，后者还需要输出检查、合成读取和审片确认。
* **Incremental Render 与缓存复用**：增量渲染依据依赖图决定哪些输出失效，缓存只是加速手段，不能替代失效判断。

本章结论
--------

生产工作流集成应按“资产发布—依赖清单—镜头装配—渲染包—分阶段自动化—Farm 执行—多层 QC—合成与交付”理解。稳定性来自明确版本、可解析路径、发布化 profile/schema、失败分类和状态回写；效率来自 preflight、模板任务、增量重渲和有界 retry。图像只是最终可见结果，真正被生产系统管理的是从输入状态到交付结果的可复现证据链。