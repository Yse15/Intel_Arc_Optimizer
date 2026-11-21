# Intel Arc GPU Optimizer & Shader Cache Cleaner

Автономная утилита для тонкой настройки видеокарт **Intel Arc** (поколения Xe2 Battlemage B-series / Xe Alchemist A-series) и комплексной очистки кэша шейдеров.

## 🚀 Возможности

- **Твики Intel Arc в 1 клик (100% подтверждённые ключи oem21.inf и 3DKeys драйвера)**:
  - **Direct Async Flip и мгновенный HSync**: снятие задержек развёртки без тиринга в окне и полноэкранном режиме (`Display1_DisableAsyncFlips=0`, `DisableFlipImmediateOnHSync=0`, `Global_AsyncFlipMode=1`).
  - **Отключение встроенного Adaptive VSync**: выключение принудительной вертикальной синхронизации драйвера (`AdaptiveVsyncEnable=0`), передача полного контроля игре.
  - **Отключение энергосбережения дисплейного движка**: запрет снижения тактовой частоты контроллера дисплея (`DisableEnergySaving=1`).
  - **VRR Windowed BLT**: поддержка переменной частоты обновления для оконных и безрамочных игр (`Global_VRRWindowedBLT=1`).
  - **IGCL & Frame Generation**: аппаратный конвейер XeSS Frame Generation (`IGCLFrameGeneration=1`, `Global_FrameGeneration=1`).
  - **3DKeys Low-Latency CS2 Профиль**: режим Ultra Low Latency (`cs2.exe_LowLatency=2`), прямой флип (`cs2.exe_AsyncFlipMode=32`) и предкомпиляция шейдеров (`Global_PrebuiltShaders=1`).
  - **Адаптивная резкость в 3D играх (Intel CAS)**: аппаратный фильтр Contrast Adaptive Sharpening (`Global_AdaptiveSharpening=1`, `cs2.exe_AdaptiveSharpening=1`, `Disable_OverlayDSQualityEnhancement=0`). Устраняет мыло TAA без потери FPS.
  - **Аппаратное ИИ-суперразрешение видео (Intel VSR)**: масштабирование потокового видео на базе ядер XMX на Arc B580 (`SuperResolutionEnabled=1` в `MediaKeys`). Для YouTube/Twitch в Chrome/Edge (`chrome://flags/#enable-intel-vpp-super-resolution`).
  - **Повышенная резкость видео (Intel VPP Detail 70%)**: аппаратное повышение детализации видео до 70.0% (`SharpnessFactor=1116471296`, `SharpnessEnabledAlways=1`) вместо заводских мутных 44.0%.
  - **Аппаратные MSI-прерывания**: приоритетный режим `MessageSignaledInterruptProperties` (MSISupported=1, DevicePriority=3) для снижения DPC-latency и стабилизации 0.1% low FPS.

- **Комплексная очистка кэша шейдеров**:
  - Intel Arc IGSDS Prebuilt Shaders (`C:\ProgramData\Intel\IGSDS\PrebuiltShaderBinaries`)
  - Intel System & Local Shader Caches (`ProgramData`, `AppData\Local`)
  - Intel IEShaders, DX12, Vulkan, Arc Control Caches
  - Общесистемный кэш DirectX D3D (`%LOCALAPPDATA%\D3DSCache`)
  - Предкомпилированный кэш шейдеров Counter-Strike 2 и Steam Pre-Caching на всех дисках (C:, D:, F: и др.)

- **Безопасность и отказоустойчивость**:
  - Динамическое определение активного видеоадаптера Intel Arc в `HKLM:\...\Class\{4d36e968-...}` (без хардкода `\0000`).
  - Корректное считывание 64-битного объема VRAM (`qwMemorySize` до 12+ ГБ).
  - Безопасная временная приостановка служб Intel (`IntelGraphicsSoftwareService`, `IGSDSserviceDiscrete`) на время очистки с гарантированным перезапуском.
  - Кнопка отката к заводским дефолтам драйвера.
  - Параметры сохраняются в реестре HKLM нативно и не требуют лишних фоновых задач.

## 🛠 Запуск

### Вариант 1: Готовый исполняемый файл (Рекомендуется)
Скачайте и запустите **`Intel_Arc_Optimizer.exe`**.
- Не требует установки Python или библиотек.
- Автоматически запрашивает права Администратора через встроенный манифест UAC.

### Вариант 2: Запуск из исходного кода
Запустите файл `run.bat` (он автоматически запросит права администратора) или выполните в терминале с правами администратора:
```powershell
py -3 main.py
```

> **Совет:** После применения настроек нажмите сочетание клавиш **Win + Ctrl + Shift + B** для мгновенного перезапуска видеодрайвера без перезагрузки системы.
