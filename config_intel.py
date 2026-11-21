"""
Intel Arc GPU Configuration & Optimization Registry Database
Поддерживает поколения Intel Arc (Alchemist Xe-HPG, Battlemage Xe2-HPG, Core Ultra iGPU).
"""

import subprocess
import os

# Публичный список служб драйвера Intel Graphics
INTEL_SVCS = ("IntelGraphicsSoftwareService", "IGSDSserviceDiscrete")
_INTEL_SVCS = INTEL_SVCS  # Алиас для обратной совместимости


def run_ps(cmd: str, timeout: int = 35) -> subprocess.CompletedProcess:
    """Выполняет команду PowerShell с гарантированным выводом в UTF-8 без окна консоли."""
    wrapped_cmd = f"[Console]::OutputEncoding=[System.Text.Encoding]::UTF8; {cmd}"
    encoded = subprocess.list2cmdline([
        "powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", wrapped_cmd
    ])
    startupinfo = None
    creationflags = 0
    if os.name == "nt":
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 0
        creationflags = subprocess.CREATE_NO_WINDOW
    return subprocess.run(
        encoded,
        capture_output=True,
        timeout=timeout,
        startupinfo=startupinfo,
        creationflags=creationflags
    )


def cleanup_legacy_persistence():
    """
    Разовая миграция: удаляет устаревшую задачу планировщика Windows 'IntelArcOptimizer_Startup'
    и остаточный скрипт intel_tweaks.ps1 (в AppData и ProgramData).
    Использует флаг-файл для мгновенного завершения (< 0.1 мс) при повторных вызовах.
    """
    data_dir = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "IntelArcOptimizer")
    flag_file = os.path.join(data_dir, ".migration_done")

    if os.path.isfile(flag_file):
        return

    try:
        os.makedirs(data_dir, exist_ok=True)

        if os.name == "nt":
            # 1. Проверяем наличие задачи в планировщике
            q = subprocess.run(
                ["schtasks", "/query", "/tn", "IntelArcOptimizer_Startup"],
                capture_output=True,
                timeout=10,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            # 2. Если задача есть — удаляем её в первую очередь
            if q.returncode == 0:
                subprocess.run(
                    ["schtasks", "/delete", "/tn", "IntelArcOptimizer_Startup", "/f"],
                    capture_output=True,
                    timeout=15,
                    creationflags=subprocess.CREATE_NO_WINDOW
                )

        # 3. После удаления задачи удаляем остаточные файлы скрипта
        script_paths = [
            os.path.join(data_dir, "intel_tweaks.ps1"),
            os.path.join(os.environ.get("ProgramData", r"C:\ProgramData"), "IntelArcOptimizer", "intel_tweaks.ps1"),
        ]
        for sp in script_paths:
            if os.path.isfile(sp):
                try:
                    os.remove(sp)
                except OSError:
                    pass

        # 4. Устанавливаем флаг успешной разовой миграции
        try:
            with open(flag_file, "w", encoding="utf-8") as f:
                f.write("migrated")
        except OSError:
            pass

    except Exception:
        pass


def detect_gpu_info() -> dict:
    """
    Определяет видеокарту, версию драйвера, 64-битный объем VRAM (qwMemorySize),
    точный подключ реестра {GUID}\\000X с приоритизацией Arc и объема памяти.
    """
    info = {
        "name": "Не найдено",
        "vendor": "unknown",
        "driver_version": "Неизвестно",
        "driver_date": "Неизвестно",
        "vram_gb": 0.0,
        "is_arc": False,
        "is_battlemage": False,
        "adapter_reg_path": "",
        "services": []
    }

    ps_script = (
        "$cls = 'HKLM:\\SYSTEM\\CurrentControlSet\\Control\\Class\\{4d36e968-e325-11ce-bfc1-08002be10318}'; "
        "$adapters = @(Get-ItemProperty (Join-Path $cls '0*') -EA SilentlyContinue | "
        "  Where-Object { $_.DriverDesc -and $_.MatchingDeviceId }); "
        "$intel = $adapters | Where-Object { $_.DriverDesc -match 'Arc|Intel' -and $_.MatchingDeviceId -match 'VEN_8086' } | "
        "  Sort-Object -Property @( "
        "    @{ Expression = { if ($_.DriverDesc -match 'Arc') { 3 } else { 1 } } }, "
        "    @{ Expression = { "
        "        $m = $_.'HardwareInformation.qwMemorySize'; "
        "        if ($m -is [byte[]] -and $m.Length -ge 8) { [BitConverter]::ToInt64($m, 0) } elseif ($m -is [int64]) { $m } else { 0 } "
        "    } } "
        "  ) -Descending | Select-Object -First 1; "
        "if ($intel) { "
        "  $m = $intel.'HardwareInformation.qwMemorySize'; "
        "  if ($m -is [byte[]] -and $m.Length -ge 8) { $m = [BitConverter]::ToInt64($m, 0) } elseif ($m -is [byte[]]) { $m = 0 }; "
        "  $vram = if ($m) { [math]::Round($m / 1GB, 1) } else { 0.0 }; "
        "  $cleanPath = Join-Path $cls $intel.PSChildName; "
        "  Write-Output ('INTEL_GPU:' + $intel.DriverDesc + '|' + $intel.DriverVersion + '|' + $intel.DriverDate + '|' + $vram + '|' + $cleanPath); "
        "} else { "
        "  $first = $adapters | Select-Object -First 1; "
        "  if ($first) { "
        "    $cleanPath = Join-Path $cls $first.PSChildName; "
        "    Write-Output ('OTHER_GPU:' + $first.DriverDesc + '|' + $first.DriverVersion + '||0|' + $cleanPath) "
        "  } "
        "}; "
        "foreach($s in @('IntelGraphicsSoftwareService', 'IGSDSserviceDiscrete')) { "
        "  $st = (Get-Service $s -EA SilentlyContinue).Status; "
        "  if ($st) { Write-Output ('SVC:' + $s + '|' + $st) } "
        "}"
    )

    try:
        r = run_ps(ps_script, timeout=12)
        lines = (r.stdout or b"").decode("utf-8", errors="ignore").splitlines()
        for line in lines:
            line = line.strip()
            if line.startswith("INTEL_GPU:"):
                parts = line[10:].split("|")
                info["name"] = parts[0] if len(parts) > 0 else "Intel Graphics"
                info["vendor"] = "intel"
                info["driver_version"] = parts[1] if len(parts) > 1 else "Неизвестно"
                info["driver_date"] = parts[2] if len(parts) > 2 else ""
                try:
                    info["vram_gb"] = float(parts[3]) if len(parts) > 3 and parts[3] else 0.0
                except ValueError:
                    info["vram_gb"] = 0.0
                info["adapter_reg_path"] = parts[4] if len(parts) > 4 else ""
                lower_name = info["name"].lower()
                if "arc" in lower_name:
                    info["is_arc"] = True
                if any(k in lower_name for k in ("b580", "b570", "battlemage", "b-series")):
                    info["is_battlemage"] = True
            elif line.startswith("OTHER_GPU:") and info["vendor"] != "intel":
                parts = line[10:].split("|")
                info["name"] = parts[0] if len(parts) > 0 else "Дискретный адаптер"
                info["driver_version"] = parts[1] if len(parts) > 1 else ""
                info["adapter_reg_path"] = parts[4] if len(parts) > 4 else ""
            elif line.startswith("SVC:"):
                sp = line[4:].split("|")
                if len(sp) == 2:
                    info["services"].append((sp[0], sp[1]))
    except Exception:
        pass

    return info


# База подтверждённых нативных твиков Intel Arc (Xe2 Battlemage / Alchemist).
# Все команды используют $p (путь к адаптеру HKLM:\...) и $k3d ($p\3DKeys).
# Все параметры типа REG_DWORD явно пишутся через -Type DWord для надежности.
INTEL_TWEAKS = {
    "intel_async_flip": {
        "label": "Direct Async Flip и мгновенный HSync (Ультра-низкая задержка)",
        "desc": "Активирует аппаратный Async Flip в окне и полноэкранном режиме (Display1_DisableAsyncFlips=0, DisableFlipImmediateOnHSync=0, Global_AsyncFlipMode=1). Устраняет задержки развёртки без тиринга.",
        "cat": "Отображение и Кадры",
        "recommended": True,
        "ps": (
            "Set-ItemProperty -Path $p -Name 'Display1_DisableAsyncFlips' -Value 0 -Type DWord -Force -EA Stop; "
            "Set-ItemProperty -Path $p -Name 'DisableFlipImmediateOnHSync' -Value 0 -Type DWord -Force -EA Stop; "
            "Set-ItemProperty -Path $k3d -Name 'Global_AsyncFlipMode' -Value 1 -Type DWord -Force -EA Stop"
        ),
        "revert_ps": (
            "Remove-ItemProperty -Path $p -Name 'Display1_DisableAsyncFlips' -Force -EA SilentlyContinue; "
            "Remove-ItemProperty -Path $p -Name 'DisableFlipImmediateOnHSync' -Force -EA SilentlyContinue; "
            "Remove-ItemProperty -Path $k3d -Name 'Global_AsyncFlipMode' -Force -EA SilentlyContinue"
        ),
    },
    "intel_adaptive_vsync_off": {
        "label": "Отключение встроенного Adaptive VSync",
        "desc": "Отключает принудительную адаптивную вертикальную синхронизацию драйвера (AdaptiveVsyncEnable=0 из oem21.inf), передавая полный контроль движку игры.",
        "cat": "Отображение и Кадры",
        "recommended": True,
        "ps": (
            "Set-ItemProperty -Path $p -Name 'AdaptiveVsyncEnable' -Value 0 -Type DWord -Force -EA Stop"
        ),
        "revert_ps": (
            "Remove-ItemProperty -Path $p -Name 'AdaptiveVsyncEnable' -Force -EA SilentlyContinue"
        ),
    },
    "intel_vrr_windowed": {
        "label": "VRR и Adaptive Sync для Оконного и Безрамочного режимов",
        "desc": "Включает поддержку переменной частоты обновления для оконных и безрамочных игр (Global_VRRWindowedBLT=1 в 3DKeys).",
        "cat": "Отображение и Кадры",
        "recommended": True,
        "ps": (
            "Set-ItemProperty -Path $k3d -Name 'Global_VRRWindowedBLT' -Value 1 -Type DWord -Force -EA Stop"
        ),
        "revert_ps": (
            "Remove-ItemProperty -Path $k3d -Name 'Global_VRRWindowedBLT' -Force -EA SilentlyContinue"
        ),
    },
    "intel_igcl_framegen": {
        "label": "Аппаратный оверлей IGCL & Frame Generation",
        "desc": "Разрешает аппаратный конвейер оверлея Intel Graphics Control Library (IGCLFrameGeneration=1 из oem21.inf).",
        "cat": "Игровые Технологии",
        "recommended": True,
        "ps": (
            "Set-ItemProperty -Path $p -Name 'IGCLFrameGeneration' -Value 1 -Type DWord -Force -EA Stop"
        ),
        "revert_ps": (
            "Remove-ItemProperty -Path $p -Name 'IGCLFrameGeneration' -Force -EA SilentlyContinue"
        ),
    },
    "intel_arc_cs2_lowlatency": {
        "label": "Ultra-Low Latency профиль CS2 (3DKeys драйвера)",
        "desc": "Устанавливает нативные параметры драйвера Intel для cs2.exe: режим Ultra Low Latency (значение 2), прямой флип (AsyncFlipMode 32) и предкомпиляцию шейдеров (Global_PrebuiltShaders 1).",
        "cat": "Игровые Технологии",
        "recommended": True,
        "ps": (
            "Set-ItemProperty -Path $k3d -Name 'cs2.exe_LowLatency' -Value 2 -Type DWord -Force -EA Stop; "
            "Set-ItemProperty -Path $k3d -Name 'cs2.exe_AsyncFlipMode' -Value 32 -Type DWord -Force -EA Stop; "
            "Set-ItemProperty -Path $k3d -Name 'cs2.exe_GlobalOrPerApp' -Value 1 -Type DWord -Force -EA Stop; "
            "Set-ItemProperty -Path $k3d -Name 'Global_PrebuiltShaders' -Value 1 -Type DWord -Force -EA Stop"
        ),
        "revert_ps": (
            "Remove-ItemProperty -Path $k3d -Name 'cs2.exe_LowLatency' -Force -EA SilentlyContinue; "
            "Remove-ItemProperty -Path $k3d -Name 'cs2.exe_AsyncFlipMode' -Force -EA SilentlyContinue; "
            "Remove-ItemProperty -Path $k3d -Name 'cs2.exe_GlobalOrPerApp' -Force -EA SilentlyContinue; "
            "Remove-ItemProperty -Path $k3d -Name 'Global_PrebuiltShaders' -Force -EA SilentlyContinue"
        ),
    },
    "intel_msi_mode": {
        "label": "MSI Прерывания видеокарты (Message Signaled-Based Interrupts)",
        "desc": "Переводит Intel GPU в режим аппаратных MSI-прерываний с высоким приоритетом (DevicePriority=3). Снижает DPC-latency и микрофризы. Требует прав Администратора.",
        "cat": "Ядро и Драйвер",
        "recommended": True,
        "ps": (
            "$devs = Get-PnpDevice | Where-Object { $_.FriendlyName -match 'Intel|Arc' -and $_.Class -eq 'Display' -and $_.Status -eq 'OK' }; "
            "if (-not $devs) { throw 'Intel Display device not found' }; "
            "foreach($d in $devs) { "
            "  $msiPath = 'HKLM:\\SYSTEM\\CurrentControlSet\\Enum\\' + $d.InstanceId + '\\Device Parameters\\Interrupt Management\\MessageSignaledInterruptProperties'; "
            "  if (-not (Test-Path $msiPath)) { New-Item -Path $msiPath -Force | Out-Null }; "
            "  Set-ItemProperty -Path $msiPath -Name 'MSISupported' -Value 1 -Type DWord -Force -EA Stop; "
            "  Set-ItemProperty -Path $msiPath -Name 'MessageNumberLimit' -Value 4 -Type DWord -Force -EA Stop; "
            "  $affPath = 'HKLM:\\SYSTEM\\CurrentControlSet\\Enum\\' + $d.InstanceId + '\\Device Parameters\\Interrupt Management\\Affinity Policy'; "
            "  if (-not (Test-Path $affPath)) { New-Item -Path $affPath -Force | Out-Null }; "
            "  Set-ItemProperty -Path $affPath -Name 'DevicePriority' -Value 3 -Type DWord -Force -EA Stop "
            "}"
        ),
        "revert_ps": (
            "$devs = Get-PnpDevice | Where-Object { $_.FriendlyName -match 'Intel|Arc' -and $_.Class -eq 'Display' -and $_.Status -eq 'OK' }; "
            "foreach($d in $devs) { "
            "  $msiPath = 'HKLM:\\SYSTEM\\CurrentControlSet\\Enum\\' + $d.InstanceId + '\\Device Parameters\\Interrupt Management\\MessageSignaledInterruptProperties'; "
            "  if (Test-Path $msiPath) { "
            "    Remove-ItemProperty -Path $msiPath -Name 'MSISupported' -Force -EA SilentlyContinue; "
            "    Remove-ItemProperty -Path $msiPath -Name 'MessageNumberLimit' -Force -EA SilentlyContinue "
            "  }; "
            "  $affPath = 'HKLM:\\SYSTEM\\CurrentControlSet\\Enum\\' + $d.InstanceId + '\\Device Parameters\\Interrupt Management\\Affinity Policy'; "
            "  if (Test-Path $affPath) { Remove-ItemProperty -Path $affPath -Name 'DevicePriority' -Force -EA SilentlyContinue } "
            "}"
        ),
    },
    "intel_game_adaptive_sharpening": {
        "label": "Адаптивная резкость в играх (Intel 3D Adaptive Sharpening / CAS)",
        "desc": "Включает драйверный фильтр адаптивной резкости Contrast Adaptive Sharpening для 3D-приложений и CS2 (Global_AdaptiveSharpening=1, cs2.exe_AdaptiveSharpening=1). Устраняет замыливание TAA без потери производительности.",
        "cat": "Игровые Технологии",
        "recommended": True,
        "ps": (
            "Set-ItemProperty -Path $k3d -Name 'Global_AdaptiveSharpening' -Value 1 -Type DWord -Force -EA Stop; "
            "Set-ItemProperty -Path $k3d -Name 'cs2.exe_AdaptiveSharpening' -Value 1 -Type DWord -Force -EA Stop; "
            "Set-ItemProperty -Path $p -Name 'Disable_OverlayDSQualityEnhancement' -Value 0 -Type DWord -Force -EA Stop"
        ),
        "revert_ps": (
            "Remove-ItemProperty -Path $k3d -Name 'Global_AdaptiveSharpening' -Force -EA SilentlyContinue; "
            "Remove-ItemProperty -Path $k3d -Name 'cs2.exe_AdaptiveSharpening' -Force -EA SilentlyContinue; "
            "Remove-ItemProperty -Path $p -Name 'Disable_OverlayDSQualityEnhancement' -Force -EA SilentlyContinue"
        ),
    },
    "intel_video_super_resolution": {
        "label": "Аппаратное ИИ-суперразрешение видео (Intel VSR / Super Resolution)",
        "desc": "Активирует нейросетевое масштабирование и повышение четкости видео с использованием матричных ядер XMX на Arc B580 (SuperResolutionEnabled=1). Улучшает видео на YouTube/Twitch в Chrome и Edge.",
        "cat": "Видео и Качество",
        "recommended": True,
        "ps": (
            "Set-ItemProperty -Path $kMedia -Name 'SuperResolutionEnabled' -Value 1 -Type DWord -Force -EA Stop; "
            "$cui = 'HKLM:\\Software\\Intel\\Display\\igfxcui\\MediaKeys'; "
            "if (-not (Test-Path $cui)) { New-Item -Path $cui -Force -EA SilentlyContinue | Out-Null }; "
            "Set-ItemProperty -Path $cui -Name 'SuperResolutionEnabled' -Value 1 -Type DWord -Force -EA SilentlyContinue"
        ),
        "revert_ps": (
            "Set-ItemProperty -Path $kMedia -Name 'SuperResolutionEnabled' -Value 0 -Type DWord -Force -EA SilentlyContinue; "
            "$cui = 'HKLM:\\Software\\Intel\\Display\\igfxcui\\MediaKeys'; "
            "if (Test-Path $cui) { Set-ItemProperty -Path $cui -Name 'SuperResolutionEnabled' -Value 0 -Type DWord -Force -EA SilentlyContinue }"
        ),
    },
    "intel_video_sharpness_boost": {
        "label": "Повышенная резкость видео (Intel VPP Detail Enhancement 70%)",
        "desc": "Включает аппаратный блок контурной резкости видеопроцессора (SharpnessEnabledAlways=1) и повышает коэффициент детализации до 70% вместо заводских 44% (SharpnessFactor=70.0% Float).",
        "cat": "Видео и Качество",
        "recommended": True,
        "ps": (
            "Set-ItemProperty -Path $kMedia -Name 'SharpnessEnabledAlways' -Value 1 -Type DWord -Force -EA Stop; "
            "Set-ItemProperty -Path $kMedia -Name 'SharpnessFactor' -Value 1116471296 -Type DWord -Force -EA Stop; "
            "$cui = 'HKLM:\\Software\\Intel\\Display\\igfxcui\\MediaKeys'; "
            "if (-not (Test-Path $cui)) { New-Item -Path $cui -Force -EA SilentlyContinue | Out-Null }; "
            "Set-ItemProperty -Path $cui -Name 'SharpnessEnabledAlways' -Value 1 -Type DWord -Force -EA SilentlyContinue; "
            "Set-ItemProperty -Path $cui -Name 'SharpnessFactor' -Value 1116471296 -Type DWord -Force -EA SilentlyContinue"
        ),
        "revert_ps": (
            "Set-ItemProperty -Path $kMedia -Name 'SharpnessFactor' -Value 1110441984 -Type DWord -Force -EA SilentlyContinue; "
            "$cui = 'HKLM:\\Software\\Intel\\Display\\igfxcui\\MediaKeys'; "
            "if (Test-Path $cui) { Set-ItemProperty -Path $cui -Name 'SharpnessFactor' -Value 1110441984 -Type DWord -Force -EA SilentlyContinue }"
        ),
    },
}


def get_adapter_resolution_header() -> str:
    """
    Генерирует строгий префикс для автоматического определения реального пути к адаптеру Intel Arc ($p).
    Использует двухуровневую сортировку (Arc-приоритет + VRAM) без строковых замен.
    """
    return (
        "$cls = 'HKLM:\\SYSTEM\\CurrentControlSet\\Control\\Class\\{4d36e968-e325-11ce-bfc1-08002be10318}'; "
        "$adapters = @(Get-ItemProperty (Join-Path $cls '0*') -EA SilentlyContinue | "
        "  Where-Object { $_.DriverDesc -and $_.MatchingDeviceId }); "
        "$intel = $adapters | Where-Object { $_.DriverDesc -match 'Arc|Intel' -and $_.MatchingDeviceId -match 'VEN_8086' } | "
        "  Sort-Object -Property @( "
        "    @{ Expression = { if ($_.DriverDesc -match 'Arc') { 3 } else { 1 } } }, "
        "    @{ Expression = { "
        "        $m = $_.'HardwareInformation.qwMemorySize'; "
        "        if ($m -is [byte[]] -and $m.Length -ge 8) { [BitConverter]::ToInt64($m, 0) } elseif ($m -is [int64]) { $m } else { 0 } "
        "    } } "
        "  ) -Descending | Select-Object -First 1; "
        "if (-not $intel) { throw 'Intel Arc GPU not found in registry' }; "
        "$p = Join-Path $cls $intel.PSChildName; "
        "$k3d = Join-Path $p '3DKeys'; "
        "if (-not (Test-Path $k3d)) { New-Item -Path $k3d -Force -EA SilentlyContinue | Out-Null }; "
        "$kMedia = Join-Path $p 'MediaKeys'; "
        "if (-not (Test-Path $kMedia)) { New-Item -Path $kMedia -Force -EA SilentlyContinue | Out-Null };"
    )


def build_intel_batch_script(keys: list) -> tuple[str, list]:
    """
    Собирает один PS-скрипт с 1 остановкой и 1 запуском служб Intel.
    Каждый шаг обёрнут в $( ... ) | Out-Null для надёжного выполнения сложных выражений.
    """
    ordered = [k for k in keys if k in INTEL_TWEAKS and INTEL_TWEAKS[k].get("ps")]
    svc_list = ", ".join(f"'{s}'" for s in INTEL_SVCS)
    lines = [
        get_adapter_resolution_header(),
        f"$_svcsRunning = @(); foreach($_s in @({svc_list})) {{ "
        "$_svc = Get-Service $_s -EA SilentlyContinue; "
        "if($_svc -and $_svc.Status -eq 'Running') { Stop-Service $_s -Force -EA SilentlyContinue; $_svcsRunning += $_s } "
        "}; if($_svcsRunning.Count -gt 0){ "
        "  Write-Output ('INTEL_SVCS_STOPPED:' + ($_svcsRunning -join '|')); "
        "  Start-Sleep -Milliseconds 600 "
        "}; "
        "try {",
        "  @('TurboAcPolicy','TurboDcPolicy','EnableGTTurboMode','ConnectedStandbyPlatform','PowerAcPolicy','PowerDcPolicy','PowerPolicy','ACUserPreferencePolicy','DCUserPreferencePolicy','DisableEnergySaving','PP_DisablePowerContainment') | ForEach-Object { Remove-ItemProperty -Path $p -Name $_ -Force -EA SilentlyContinue };"
    ]
    for k in ordered:
        ps_code = INTEL_TWEAKS[k]["ps"]
        lines.append(
            f"  try {{ $( {ps_code} ) | Out-Null; Write-Output 'INTEL_STEP:{k}:OK' }} "
            f"  catch {{ Write-Output ('INTEL_STEP:{k}:FAIL:' + $_.Exception.Message) }}"
        )
    lines.append(
        "} finally { "
        "  foreach($_s in $_svcsRunning) { Start-Service $_s -EA SilentlyContinue } "
        "}"
    )
    return "\n".join(lines), ordered


def build_intel_revert_batch_script(keys: list) -> tuple[str, list]:
    """Собирает один PS-скрипт для отката Intel твиков к заводским дефолтам."""
    ordered = [k for k in keys if k in INTEL_TWEAKS and INTEL_TWEAKS[k].get("revert_ps")]
    svc_list = ", ".join(f"'{s}'" for s in INTEL_SVCS)
    lines = [
        get_adapter_resolution_header(),
        f"$_svcsRunning = @(); foreach($_s in @({svc_list})) {{ "
        "$_svc = Get-Service $_s -EA SilentlyContinue; "
        "if($_svc -and $_svc.Status -eq 'Running') { Stop-Service $_s -Force -EA SilentlyContinue; $_svcsRunning += $_s } "
        "}; if($_svcsRunning.Count -gt 0){ "
        "  Write-Output ('INTEL_SVCS_STOPPED:' + ($_svcsRunning -join '|')); "
        "  Start-Sleep -Milliseconds 600 "
        "}; "
        "try {",
        "  @('TurboAcPolicy','TurboDcPolicy','EnableGTTurboMode','ConnectedStandbyPlatform','PowerAcPolicy','PowerDcPolicy','PowerPolicy','ACUserPreferencePolicy','DCUserPreferencePolicy','DisableEnergySaving','PP_DisablePowerContainment') | ForEach-Object { Remove-ItemProperty -Path $p -Name $_ -Force -EA SilentlyContinue };"
    ]
    for k in ordered:
        ps_code = INTEL_TWEAKS[k]["revert_ps"]
        lines.append(
            f"  try {{ $( {ps_code} ) | Out-Null; Write-Output 'INTEL_REVERT:{k}:OK' }} "
            f"  catch {{ Write-Output ('INTEL_REVERT:{k}:FAIL:' + $_.Exception.Message) }}"
        )
    lines.append(
        "} finally { "
        "  foreach($_s in $_svcsRunning) { Start-Service $_s -EA SilentlyContinue } "
        "}"
    )
    return "\n".join(lines), ordered


def parse_batch_output(stdout: str, ordered_keys: list, prefix: str = "INTEL_STEP:") -> dict:
    results = {k: (False, "Нет вывода") for k in ordered_keys}
    for line in stdout.splitlines():
        line = line.strip()
        if line.startswith(prefix):
            rest = line[len(prefix):]
            parts = rest.split(":", 2)
            if len(parts) >= 2:
                k = parts[0]
                status = parts[1]
                err = parts[2] if len(parts) > 2 else ""
                results[k] = (status == "OK", err)
    return results
