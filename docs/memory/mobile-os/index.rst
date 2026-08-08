Mobile OS 必背课本
==================

本目录与 AIBook 的 ``docs/MobileOS`` 一一对应。AIBook 保留完整讲解、平台资料、案例和系统路径，这里只保留稳定、必须掌握、可以直接复习的移动操作系统架构模型。

Part 1：Mobile OS Architecture Model
------------------------------------

* `第001章：Mobile OS and Desktop OS Shared Foundations, Different Constraints <001-mobile-os-and-desktop-os-shared-foundations-different-constraints.rst>`_；
* `第002章：The Core System Chain Hardware, Kernel, Driver, Service, Framework, App <002-the-core-system-chain-hardware-kernel-driver-service-framework-app.rst>`_；
* `第003章：Hardware Capability Mediation and System Control <003-hardware-capability-mediation-and-system-control.rst>`_；
* `第004章：Mobile Platform Constraint Model <004-mobile-platform-constraint-model.rst>`_；
* `第005章：Hardware Boundary, System Boundary, Runtime Boundary, App Boundary <005-hardware-boundary-system-boundary-runtime-boundary-app-boundary.rst>`_；
* `第006章：Kernel, Operating System, and Mobile Platform <006-kernel-operating-system-and-mobile-platform.rst>`_；
* `第007章：Android Above Linux and Apple Above XNU <007-android-above-linux-and-apple-above-xnu.rst>`_；
* `第008章：Capability Path as the Reading Model <008-capability-path-as-the-reading-model.rst>`_。

Part 2：Smartphone Hardware Platform
------------------------------------

* `第009章：Mobile SoC Component Map <009-mobile-soc-component-map.rst>`_；
* `第010章：SoC Integration and Mobile Hardware Topology <010-soc-integration-and-mobile-hardware-topology.rst>`_；
* `第011章：CPU Core Topology and Scheduling Pressure <011-cpu-core-topology-and-scheduling-pressure.rst>`_；
* `第012章：GPU, Display Engine, Hardware Composer, and Frame Output <012-gpu-display-engine-hardware-composer-and-frame-output.rst>`_；
* `第013章：NPU and Specialized Compute Units <013-npu-and-specialized-compute-units.rst>`_；
* `第014章：ISP, Camera Sensor, Lens, and Imaging Hardware <014-isp-camera-sensor-lens-and-imaging-hardware.rst>`_；
* `第015章：Memory, Flash Storage, and Mobile IO Characteristics <015-memory-flash-storage-and-mobile-io-characteristics.rst>`_；
* `第016章：Peripheral Devices Display, Touch, Audio, Camera, and Haptics <016-peripheral-devices-display-touch-audio-camera-and-haptics.rst>`_；
* `第017章：Wireless Hardware Wi-Fi, Bluetooth, NFC, GPS, Cellular Modem <017-wireless-hardware-wifi-bluetooth-nfc-gps-cellular-modem.rst>`_；
* `第018章：Battery, Charging, Thermal Sensors, and Power Hardware <018-battery-charging-thermal-sensors-and-power-hardware.rst>`_。

Part 3：Boot Chain and System Startup
------------------------------------

* `第019章：Power-On Sequence and Boot Entry <019-power-on-sequence-and-boot-entry.rst>`_；
* `第020章：Boot ROM, Bootloader, Firmware, Kernel Image, Verified Boot <020-boot-rom-bootloader-firmware-kernel-image-verified-boot.rst>`_；
* `第021章：Secure Boot and Trust Chain <021-secure-boot-and-trust-chain.rst>`_；
* `第022章：Signature Verification and System Integrity <022-signature-verification-and-system-integrity.rst>`_；
* `第023章：System Partitions, Recovery, OTA Update, Rollback Protection <023-system-partitions-recovery-ota-update-rollback-protection.rst>`_；
* `第024章：Android Startup Path Bootloader, Kernel, init, Zygote, system_server <024-android-startup-path-bootloader-kernel-init-zygote-system-server.rst>`_；
* `第025章：Apple Startup Path Secure Boot, XNU, launchd, System Services <025-apple-startup-path-secure-boot-xnu-launchd-system-services.rst>`_；
* `第026章：Startup Security and Platform Trust Establishment <026-startup-security-and-platform-trust-establishment.rst>`_。

Part 4：Mobile Kernel Foundations
---------------------------------

* `第027章：Kernel Responsibilities in a Mobile Platform <027-kernel-responsibilities-in-a-mobile-platform.rst>`_；
* `第028章：Process, Thread, Scheduler, Foreground Responsiveness <028-process-thread-scheduler-foreground-responsiveness.rst>`_；
* `第029章：Virtual Memory, Physical Memory, OOM, Memory Pressure <029-virtual-memory-physical-memory-oom-memory-pressure.rst>`_；
* `第030章：System Call Boundary and Kernel Object Model <030-system-call-boundary-and-kernel-object-model.rst>`_；
* `第031章：Interrupt, DMA, Device Driver, Hardware Event <031-interrupt-dma-device-driver-hardware-event.rst>`_；
* `第032章：Timer, Wakeup, Scheduling Latency, Power Sensitivity <032-timer-wakeup-scheduling-latency-power-sensitivity.rst>`_；
* `第033章：Sleep, Wakeup, Thermal Control, Power State Management <033-sleep-wakeup-thermal-control-power-state-management.rst>`_；
* `第034章：Kernel Isolation, Access Control, Attack Surface <034-kernel-isolation-access-control-attack-surface.rst>`_；
* `第035章：Android Linux Kernel and Apple XNU <035-android-linux-kernel-and-apple-xnu.rst>`_。

Part 5：Driver Model, Hardware Abstraction, and Vendor Boundary
--------------------------------------------------------------

* `第036章：Device Driver Role in Mobile Systems <036-device-driver-role-in-mobile-systems.rst>`_；
* `第037章：Hardware Event Translation and Driver Interface <037-hardware-event-translation-and-driver-interface.rst>`_；
* `第038章：Capability Interface Instead of Raw Device Access <038-capability-interface-instead-of-raw-device-access.rst>`_；
* `第039章：Android HAL and Vendor Boundary <039-android-hal-and-vendor-boundary.rst>`_；
* `第040章：Camera HAL, Audio HAL, Sensors HAL, Bluetooth HAL, Graphics HAL <040-camera-hal-audio-hal-sensors-bluetooth-hal-graphics-hal.rst>`_；
* `第041章：Vendor Partition, Device Tree, Firmware, Board Support <041-vendor-partition-device-tree-firmware-board-support.rst>`_；
* `第042章：Apple IOKit, DriverKit, and Controlled Driver Access <042-apple-iokit-driverkit-and-controlled-driver-access.rst>`_；
* `第043章：Hardware Abstraction, Platform Update, Device Fragmentation <043-hardware-abstraction-platform-update-device-fragmentation.rst>`_。

Part 6：System Services and Capability Mediation
------------------------------------------------

* `第044章：System Service Model <044-system-service-model.rst>`_；
* `第045章：System Service as Hardware Proxy <045-system-service-as-hardware-proxy.rst>`_；
* `第046章：Resource Arbitration Camera, Audio, Location, Display, Sensor <046-resource-arbitration-camera-audio-location-display-sensor.rst>`_；
* `第047章：Permission Enforcement in System Services <047-permission-enforcement-in-system-services.rst>`_；
* `第048章：Service State, Resource Ownership, Client Tracking <048-service-state-resource-ownership-client-tracking.rst>`_；
* `第049章：Android system_server, Native Services, Service Manager <049-android-system-server-native-services-service-manager.rst>`_；
* `第050章：Apple Daemons, Framework Frontends, Service Backends <050-apple-daemons-framework-frontends-service-backends.rst>`_；
* `第051章：Service Isolation and Failure Containment <051-service-isolation-and-failure-containment.rst>`_。

Part 7：Runtime Layer and Application Execution
-----------------------------------------------

* `第052章：Runtime Responsibilities in Mobile Platforms <052-runtime-responsibilities-in-mobile-platforms.rst>`_；
* `第053章：Android Runtime DEX, ART, Class Loading, JIT, AOT, GC <053-android-runtime-dex-art-class-loading-jit-aot-gc.rst>`_；
* `第054章：Zygote Preload, Fork Model, App Process Startup <054-zygote-preload-fork-model-app-process-startup.rst>`_；
* `第055章：Apple Runtime Mach-O, dyld, Swift Runtime, Objective-C Runtime <055-apple-runtime-mach-o-dyld-swift-runtime-objective-c-runtime.rst>`_；
* `第056章：Native Libraries, Frameworks, ABI Boundary <056-native-libraries-frameworks-abi-boundary.rst>`_；
* `第057章：Dynamic Linking, Shared Libraries, Framework Loading <057-dynamic-linking-shared-libraries-framework-loading.rst>`_；
* `第058章：Startup Cost, Memory Sharing, Launch Performance <058-startup-cost-memory-sharing-launch-performance.rst>`_；
* `第059章：Runtime Design, Battery, Memory, Responsiveness <059-runtime-design-battery-memory-responsiveness.rst>`_。

Part 8：App Process Model and Lifecycle Policy
----------------------------------------------

* `第060章：App Process as a Managed System Entity <060-app-process-as-a-managed-system-entity.rst>`_；
* `第061章：Foreground, Background, Suspended, Cached, Killed <061-foreground-background-suspended-cached-killed.rst>`_；
* `第062章：Lifecycle Policy and System Resource Management <062-lifecycle-policy-and-system-resource-management.rst>`_；
* `第063章：Android App Component Process Model <063-android-app-component-process-model.rst>`_；
* `第064章：Apple App Lifecycle Process Model <064-apple-app-lifecycle-process-model.rst>`_；
* `第065章：Background Process Reclamation <065-background-process-reclamation.rst>`_；
* `第066章：Cold Start, Warm Start, Resume Path <066-cold-start-warm-start-resume-path.rst>`_；
* `第067章：State Restoration Under Process Death <067-state-restoration-under-process-death.rst>`_。

Part 9：IPC and System Service Access
-------------------------------------

* `第068章：IPC as the Mobile OS Service Spine <068-ipc-as-the-mobile-os-service-spine.rst>`_；
* `第069章：IPC Concepts Handle, Message, Transaction, Port, Object Reference <069-ipc-concepts-handle-message-transaction-port-object-reference.rst>`_；
* `第070章：Android Binder Service Access Path <070-android-binder-service-access-path.rst>`_；
* `第071章：Binder Driver, Service Manager, AIDL, Parcelable <071-binder-driver-service-manager-aidl-parcelable.rst>`_；
* `第072章：Apple Mach Port, XPC, launchd, System Daemon <072-apple-mach-port-xpc-launchd-system-daemon.rst>`_；
* `第073章：Caller Identity, Permission Check, Capability Boundary <073-caller-identity-permission-check-capability-boundary.rst>`_；
* `第074章：IPC Performance Copy, Shared Memory, Latency, Blocking <074-ipc-performance-copy-shared-memory-latency-blocking.rst>`_；
* `第075章：Deep Path Location Request and Camera Request <075-deep-path-location-request-and-camera-request.rst>`_。

Part 10：Security, Sandbox, Permission, Signature, Entitlement, and Trust
------------------------------------------------------------------------

* `第076章：Mobile Platform Security Model <076-mobile-platform-security-model.rst>`_；
* `第077章：Process Isolation, File Isolation, User Data Protection <077-process-isolation-file-isolation-user-data-protection.rst>`_；
* `第078章：Camera, Microphone, Location, Photos, Bluetooth, Notification Permission <078-camera-microphone-location-photos-bluetooth-notification-permission.rst>`_；
* `第079章：Code Signing and App Identity <079-code-signing-and-app-identity.rst>`_；
* `第080章：Android UID, Permission, SELinux, Keystore, Verified Boot <080-android-uid-permission-selinux-keystore-verified-boot.rst>`_；
* `第081章：Apple Code Signing, Entitlement, Sandbox, Keychain, Secure Enclave <081-apple-code-signing-entitlement-sandbox-keychain-secure-enclave.rst>`_；
* `第082章：App Store, Certificate, Installation Policy, Platform Trust <082-app-store-certificate-installation-policy-platform-trust.rst>`_；
* `第083章：Over-Permission, Background Abuse, Data Leakage <083-over-permission-background-abuse-data-leakage.rst>`_。

Part 11：File System, App Container, Storage, and User Data
----------------------------------------------------------

* `第084章：Mobile File System Model <084-mobile-file-system-model.rst>`_；
* `第085章：App Container and Private Storage <085-app-container-and-private-storage.rst>`_；
* `第086章：Shared Storage, Media Library, Photos, Documents, User Consent <086-shared-storage-media-library-photos-documents-user-consent.rst>`_；
* `第087章：Android Storage Access Model <087-android-storage-access-model.rst>`_；
* `第088章：Apple Storage Access Model <088-apple-storage-access-model.rst>`_；
* `第089章：SQLite, Preferences, Key-Value Storage, Local Database <089-sqlite-preferences-key-value-storage-local-database.rst>`_；
* `第090章：Backup, Restore, Cloud Sync, Data Migration <090-backup-restore-cloud-sync-data-migration.rst>`_；
* `第091章：File Access as Security Boundary <091-file-access-as-security-boundary.rst>`_。

Part 12：Graphics and Display Pipeline
--------------------------------------

* `第092章：App Drawing to Screen Pixel Pipeline <092-app-drawing-to-screen-pixel-pipeline.rst>`_；
* `第093章：View Tree, Layer Tree, Surface, Buffer, Frame <093-view-tree-layer-tree-surface-buffer-frame.rst>`_；
* `第094章：GPU Rendering, Composition, VSync, Buffering, Frame Deadline <094-gpu-rendering-composition-vsync-buffering-frame-deadline.rst>`_；
* `第095章：Android Graphics Pipeline <095-android-graphics-pipeline.rst>`_；
* `第096章：Apple Graphics View, Layer, Core Animation, Metal, WindowServer, Display <096-apple-graphics-view-layer-core-animation-metal-windowserver-display.rst>`_；
* `第097章：Jank, Main Thread, Render Thread, GPU, Missed Frame <097-jank-main-thread-render-thread-gpu-missed-frame.rst>`_；
* `第098章：High Refresh Rate, Display Power, Smoothness <098-high-refresh-rate-display-power-smoothness.rst>`_；
* `第099章：GPU Composition, Overlay Plane, Display System Policy <099-gpu-composition-overlay-plane-display-system-policy.rst>`_。

Part 13：Input System and Event Dispatch
----------------------------------------

* `第100章：Touch Hardware to App Event Pipeline <100-touch-hardware-to-app-event-pipeline.rst>`_；
* `第101章：Touch Controller, Driver, Input Queue, Event Dispatch <101-touch-controller-driver-input-queue-event-dispatch.rst>`_；
* `第102章：Gesture Recognition and Raw Touch Translation <102-gesture-recognition-and-raw-touch-translation.rst>`_；
* `第103章：Android InputReader, InputDispatcher, Window Target, View Dispatch <103-android-inputreader-inputdispatcher-window-target-view-dispatch.rst>`_；
* `第104章：Apple Touch Event, RunLoop, Responder Chain, Gesture Recognizer <104-apple-touch-event-runloop-responder-chain-gesture-recognizer.rst>`_；
* `第105章：Main Thread, Event Loop, Looper, RunLoop <105-main-thread-event-loop-looper-runloop.rst>`_；
* `第106章：Input Latency and Touch Responsiveness <106-input-latency-and-touch-responsiveness.rst>`_。

Part 14：Audio System Pipeline
------------------------------

* `第107章：Audio Hardware, Codec, Microphone, Speaker, Audio Route <107-audio-hardware-codec-microphone-speaker-audio-route.rst>`_；
* `第108章：Capture, Playback, Mixing, Resampling, Latency <108-capture-playback-mixing-resampling-latency.rst>`_；
* `第109章：Android AudioRecord, AudioTrack, AudioFlinger, Audio HAL, Driver <109-android-audiorecord-audiotrack-audioflinger-audio-hal-driver.rst>`_；
* `第110章：Apple AVAudioEngine, Core Audio, Audio Unit, Audio Session <110-apple-avaudioengine-core-audio-audio-unit-audio-session.rst>`_；
* `第111章：Audio Focus, Interruption, Background Audio, Permission <111-audio-focus-interruption-background-audio-permission.rst>`_；
* `第112章：Low-Latency Audio and Real-Time Constraint <112-low-latency-audio-and-real-time-constraint.rst>`_；
* `第113章：Audio Routing as System Policy <113-audio-routing-as-system-policy.rst>`_。

Part 15：Video and Media Pipeline
---------------------------------

* `第114章：Container, Codec, Frame, Timestamp, Synchronization <114-container-codec-frame-timestamp-synchronization.rst>`_；
* `第115章：Decode, Encode, Render, Mux, Demux <115-decode-encode-render-mux-demux.rst>`_；
* `第116章：Android MediaExtractor, MediaCodec, MediaMuxer, Surface, Hardware Codec <116-android-mediaextractor-mediacodec-mediamuxer-surface-hardware-codec.rst>`_；
* `第117章：Apple Video Media Pipeline <117-apple-video-media-pipeline.rst>`_；
* `第118章：Playback Pipeline Buffering, Seeking, Sync, DRM <118-playback-pipeline-buffering-seeking-sync-drm.rst>`_；
* `第119章：Recording Pipeline Capture, Encode, Mux, Save, Metadata <119-recording-pipeline-capture-encode-mux-save-metadata.rst>`_；
* `第120章：Media as Cross-Layer System Pipeline <120-media-as-cross-layer-system-pipeline.rst>`_。

Part 16：Camera System Pipeline
-------------------------------

* `第121章：Camera as a Cross-Layer Mobile Subsystem <121-camera-as-a-cross-layer-mobile-subsystem.rst>`_；
* `第122章：Camera Sensor, Lens, ISP, Buffer, Exposure, Focus, Image Pipeline <122-camera-sensor-lens-isp-buffer-exposure-focus-image-pipeline.rst>`_；
* `第123章：Preview, Capture, Burst, HDR, Night Mode, Computational Photography <123-preview-capture-burst-hdr-night-mode-computational-photography.rst>`_；
* `第124章：Android Camera2, CameraService, Camera HAL, Driver, ISP, Sensor <124-android-camera2-cameraservice-camera-hal-driver-isp-sensor.rst>`_；
* `第125章：Apple Camera Capture Pipeline <125-apple-camera-capture-pipeline.rst>`_；
* `第126章：Camera Privacy and Resource Arbitration <126-camera-privacy-and-resource-arbitration.rst>`_；
* `第127章：Device-Level Imaging Differences <127-device-level-imaging-differences.rst>`_；
* `第128章：Camera Hardware, Algorithm, Media, Privacy, UX Integration <128-camera-hardware-algorithm-media-privacy-ux-integration.rst>`_。

阅读方式
--------

每章依次保留“核心知识点”“关键路径”“概念辨析”和“本章结论”。阅读时优先沿 ``App → Framework → IPC → System Service / Daemon → HAL / Driver → Kernel → Hardware`` 定位能力所有者，再把 permission、lifecycle、power、thermal、privacy、sandbox 和 distribution policy 放回对应边界。