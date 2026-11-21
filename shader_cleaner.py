"""
GPU Shader Cache Scanner & Cleaner
Очистка кэша шейдеров Intel Arc (IGSDS Prebuilt Binaries, IntelGraphicsSoftware, DX12, Vulkan), DirectX и CS2/Steam на всех дисках.
"""

import os
import re
from config_intel import run_ps, INTEL_SVCS


def get_all_steam_libraries() -> list[str]:
    """
    Находит основной путь установки Steam и все дополнительные библиотеки
    (на всех локальных дисках) через libraryfolders.vdf.
    Пути строго нормализуются и дедуплицируются с учетом регистра (normcase).
    """
    discovered_roots = []
    seen_normalized = set()

    try:
        import winreg
        for root in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
            for subkey in (r"Software\Valve\Steam", r"SOFTWARE\WOW6432Node\Valve\Steam"):
                try:
                    with winreg.OpenKey(root, subkey) as k:
                        for val_name in ("InstallPath", "SteamPath"):
                            try:
                                val, _ = winreg.QueryValueEx(k, val_name)
                                if val and os.path.isdir(val):
                                    norm_key = os.path.normcase(os.path.abspath(val))
                                    if norm_key not in seen_normalized:
                                        seen_normalized.add(norm_key)
                                        discovered_roots.append(os.path.normpath(val))
                            except OSError:
                                pass
                except OSError:
                    pass
    except Exception:
        pass

    default_paths = [
        r"C:\Program Files (x86)\Steam",
        r"C:\Program Files\Steam",
        r"C:\Steam",
        r"D:\Steam",
        r"D:\SteamLibrary",
        r"E:\SteamLibrary",
        r"F:\SteamLibrary",
    ]
    for dp in default_paths:
        if os.path.isdir(dp):
            norm_key = os.path.normcase(os.path.abspath(dp))
            if norm_key not in seen_normalized:
                seen_normalized.add(norm_key)
                discovered_roots.append(os.path.normpath(dp))

    all_libraries = list(discovered_roots)
    for sr in discovered_roots:
        vdf_path = os.path.join(sr, "steamapps", "libraryfolders.vdf")
        if os.path.isfile(vdf_path):
            try:
                with open(vdf_path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                matches = re.findall(r'"path"\s+"([^"]+)"', content)
                for m in matches:
                    clean_m = m.replace(r"\\", "\\").strip()
                    if os.path.isdir(clean_m):
                        norm_key = os.path.normcase(os.path.abspath(clean_m))
                        if norm_key not in seen_normalized:
                            seen_normalized.add(norm_key)
                            all_libraries.append(os.path.normpath(clean_m))
            except Exception:
                pass

    return all_libraries


def get_shader_cache_targets() -> list[dict]:
    """
    Возвращает список всех поддерживаемых локаций кэша шейдеров:
    Intel Arc IGSDS, ShaderCache, IEShaders, DX12, Vulkan, ArcControl, DirectX и CS2 на всех дисках.
    """
    local_app_data = os.environ.get("LOCALAPPDATA", "")
    program_data = os.environ.get("ProgramData", r"C:\ProgramData")

    raw_targets = [
        {
            "id": "intel_igsds",
            "name": "Intel Arc IGSDS Prebuilt Shaders",
            "desc": "Скомпилированные бинарники шейдеров Intel Discrete Graphics Shader Distributor (Arc B580 / Alchemist)",
            "path": os.path.join(program_data, "Intel", "IGSDS", "PrebuiltShaderBinaries"),
            "needs_svc_stop": True,
        },
        {
            "id": "intel_pd_shadercache",
            "name": "Intel System Shader Cache",
            "desc": "Общесистемный кэш шейдеров драйвера Intel Graphics в ProgramData",
            "path": os.path.join(program_data, "Intel", "ShaderCache"),
            "needs_svc_stop": True,
        },
        {
            "id": "intel_local_shadercache",
            "name": "Intel User Shader Cache",
            "desc": "Пользовательский кэш шейдеров Intel в локальном профиле AppData",
            "path": os.path.join(local_app_data, "Intel", "ShaderCache"),
            "needs_svc_stop": False,
        },
        {
            "id": "intel_ieshaders",
            "name": "Intel IEShaders Cache",
            "desc": "Кэш шейдерных инструкций Intel Execution Unit Shaders",
            "path": os.path.join(local_app_data, "Intel", "IEShaders"),
            "needs_svc_stop": False,
        },
        {
            "id": "intel_dx12_shadercache",
            "name": "Intel DX12 Shader Cache",
            "desc": "Аппаратный кэш шейдеров Intel для Direct3D 12",
            "path": os.path.join(local_app_data, "Intel", "DX12ShaderCache"),
            "needs_svc_stop": False,
        },
        {
            "id": "intel_vulkan_shadercache",
            "name": "Intel Vulkan Shader Cache",
            "desc": "Скомпилированные конвейеры шейдеров Intel Vulkan API",
            "path": os.path.join(local_app_data, "Intel", "VulkanShaderCache"),
            "needs_svc_stop": False,
        },
        {
            "id": "intel_arccontrol",
            "name": "Intel Arc Control Cache",
            "desc": "Кэш графических ресурсов и оверлея приложения Intel Arc Control",
            "path": os.path.join(local_app_data, "Intel", "ArcControl", "ShaderCache"),
            "needs_svc_stop": False,
        },
        {
            "id": "intel_software_shadercache",
            "name": "Intel Graphics Software Shaders",
            "desc": "Кэш шейдеров графического интерфейса и профилей драйвера Intel",
            "path": os.path.join(local_app_data, "Intel", "IntelGraphicsSoftware", "Default", "ShaderCache"),
            "needs_svc_stop": False,
        },
        {
            "id": "intel_software_grshaders",
            "name": "Intel GrShader / Graphite Dawn Cache",
            "desc": "Кэш шейдеров графического рендеринга GrShaderCache и Dawn",
            "path": os.path.join(local_app_data, "Intel", "IntelGraphicsSoftware", "Default", "GrShaderCache"),
            "needs_svc_stop": False,
        },
        {
            "id": "d3d_cache",
            "name": "DirectX D3D Shader Cache",
            "desc": "Основной общесистемный кэш шейдеров DirectX 11 / DirectX 12 в AppData",
            "path": os.path.join(local_app_data, "D3DSCache"),
            "needs_svc_stop": False,
        },
        {
            "id": "ms_d3d_cache",
            "name": "Windows DirectX Shader Cache",
            "desc": "Кэш шейдеров системных компонентов Microsoft DirectX",
            "path": os.path.join(local_app_data, "Microsoft", "DirectX Shader Cache"),
            "needs_svc_stop": False,
        },
    ]

    # CS2 и Steam Shader Pre-Caching по всем библиотекам (с уникальным индексом)
    for idx, lib in enumerate(get_all_steam_libraries()):
        cs2_shader = os.path.join(lib, "steamapps", "common", "Counter-Strike Global Offensive", "game", "csgo", "shadercache")
        steam_cs2_shader = os.path.join(lib, "steamapps", "shadercache", "730")
        drive_letter = os.path.splitdrive(lib)[0].replace(":", "").upper() or "DEF"

        if os.path.isdir(cs2_shader) or os.path.isdir(os.path.join(lib, "steamapps", "common", "Counter-Strike Global Offensive")):
            raw_targets.append({
                "id": f"cs2_shader_{idx}_{drive_letter}",
                "name": f"CS2 Game Pipeline Cache ({drive_letter}: #{idx+1})",
                "desc": f"Локальный кэш предкомпилированных шейдеров Counter-Strike 2 ({lib})",
                "path": cs2_shader,
                "needs_svc_stop": False,
            })
        if os.path.isdir(steam_cs2_shader) or os.path.isdir(os.path.join(lib, "steamapps", "shadercache")):
            raw_targets.append({
                "id": f"steam_cs2_{idx}_{drive_letter}",
                "name": f"Steam Shader Pre-Caching CS2 ({drive_letter}: #{idx+1})",
                "desc": f"Сетевой предзагруженный кэш шейдеров Steam для CS2 ({lib})",
                "path": steam_cs2_shader,
                "needs_svc_stop": False,
            })

    # Строгая дедупликация целей по нормализованному пути
    unique_targets = []
    seen_paths = set()
    for t in raw_targets:
        norm_p = os.path.normcase(os.path.abspath(t["path"]))
        if norm_p not in seen_paths:
            seen_paths.add(norm_p)
            unique_targets.append(t)

    return unique_targets


def format_bytes(num_bytes: int) -> str:
    """Преобразует байты в форматированную строку (Б, КБ, МБ, ГБ)."""
    if num_bytes >= 1073741824:
        return f"{num_bytes / 1073741824:.2f} ГБ"
    elif num_bytes >= 1048576:
        return f"{num_bytes / 1048576:.1f} МБ"
    elif num_bytes >= 1024:
        return f"{num_bytes / 1024:.0f} КБ"
    else:
        return f"{num_bytes} Б"


def scan_cache_location(target: dict) -> dict:
    """Подсчитывает количество файлов и занимаемый объем в указанной папке."""
    p = target["path"]
    exists = os.path.isdir(p)
    file_count = 0
    total_bytes = 0

    if exists:
        try:
            for root, dirs, files in os.walk(p, followlinks=False):
                for f in files:
                    fp = os.path.join(root, f)
                    try:
                        if not os.path.islink(fp):
                            total_bytes += os.path.getsize(fp)
                            file_count += 1
                    except OSError:
                        pass
        except OSError:
            pass

    size_str = format_bytes(total_bytes)
    res = dict(target)
    res.update({
        "exists": exists,
        "file_count": file_count,
        "size_bytes": total_bytes,
        "size_formatted": size_str
    })
    return res


def scan_all_caches() -> list[dict]:
    """Сканирует все доступные папки кэша шейдеров."""
    targets = get_shader_cache_targets()
    return [scan_cache_location(t) for t in targets]


def clean_caches(target_ids: list[str] = None) -> tuple[int, int, list[str]]:
    """
    Очищает выбранные кэши шейдеров.
    Файлы и байты подсчитываются строго в момент РЕАЛЬНОГО удаления через os.remove,
    что исключает ложную статистику при заблокированных файлах.
    Не производит лишнего предварительного сканирования всех папок диска.
    """
    all_targets = get_shader_cache_targets()
    if target_ids is not None:
        targets_to_clean = [t for t in all_targets if t["id"] in target_ids and os.path.isdir(t["path"])]
    else:
        targets_to_clean = [t for t in all_targets if os.path.isdir(t["path"])]

    if not targets_to_clean:
        return 0, 0, ["ℹ️ Выбранные папки кэша пусты или не существуют."]

    needs_service_restart = any(t.get("needs_svc_stop") for t in targets_to_clean)

    log_messages = []
    total_deleted_files = 0
    total_freed_bytes = 0
    running_svcs = []

    if needs_service_restart:
        log_messages.append("⏸ Временная приостановка служб Intel Graphics для разблокировки файлов...")
        svc_list = ", ".join(f"'{s}'" for s in INTEL_SVCS)
        ps_stop = (
            f"$_stopped = @(); foreach($_s in @({svc_list})) {{ "
            "  $_svc = Get-Service $_s -EA SilentlyContinue; "
            "  if($_svc -and $_svc.Status -eq 'Running') { "
            "    Stop-Service $_s -Force -EA SilentlyContinue; $_stopped += $_s "
            "  } "
            "}; "
            "Write-Output ($_stopped -join '|')"
        )
        try:
            r = run_ps(ps_stop, timeout=12)
            out = (r.stdout or b"").decode("utf-8", errors="ignore").strip()
            if out:
                running_svcs = [s for s in out.split("|") if s]
        except Exception:
            # Презумпция сбоя: если вызов завершился исключением/таймаутом,
            # службы могли быть остановлены — гарантируем попытку их старта в finally
            running_svcs = list(INTEL_SVCS)

    try:
        for t in targets_to_clean:
            p = t["path"]
            deleted_here = 0
            bytes_here = 0
            failed_files = 0
            if not os.path.exists(p):
                continue

            try:
                for root, dirs, files in os.walk(p, topdown=False, followlinks=False):
                    for f in files:
                        fp = os.path.join(root, f)
                        try:
                            if not os.path.islink(fp):
                                sz = os.path.getsize(fp)
                                os.remove(fp)
                                deleted_here += 1
                                bytes_here += sz
                        except OSError:
                            failed_files += 1
                    for d in dirs:
                        dp = os.path.join(root, d)
                        try:
                            if not os.path.islink(dp):
                                os.rmdir(dp)
                        except OSError:
                            pass
            except Exception as e:
                log_messages.append(f"⚠️ Ошибка доступа к {t['name']}: {e}")

            if deleted_here > 0:
                msg = f"✓ [{t['name']}] Удалено {deleted_here} файлов ({format_bytes(bytes_here)})"
                if failed_files > 0:
                    msg += f" (пропущено {failed_files} заблокированных файлов)"
                log_messages.append(msg)
                total_deleted_files += deleted_here
                total_freed_bytes += bytes_here
            elif failed_files > 0:
                log_messages.append(f"⚠️ [{t['name']}] Не удалось удалить {failed_files} файлов (файлы заблокированы процессами)")
            else:
                log_messages.append(f"✓ [{t['name']}] Кэш уже пуст")

    finally:
        # Возобновляем остановленные службы
        if running_svcs:
            log_messages.append("▶ Возобновление служб Intel Graphics...")
            svc_list = ", ".join(f"'{s}'" for s in running_svcs)
            try:
                run_ps(f"foreach($_s in @({svc_list})) {{ Start-Service $_s -EA SilentlyContinue }}", timeout=10)
            except Exception:
                pass

    return total_deleted_files, total_freed_bytes, log_messages
