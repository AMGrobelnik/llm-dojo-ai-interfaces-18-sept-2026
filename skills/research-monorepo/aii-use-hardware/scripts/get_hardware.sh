#!/bin/bash
set -euo pipefail
echo "=== OS ===" && uname -sr &&
    grep -E '^(NAME|VERSION)=' /etc/os-release 2>/dev/null &&
    echo "=== CGROUP ===" &&
    (
        cg_type="none"
        cg_cpu=""
        cg_mem=""
        cg_pids=""
        if [ -f /sys/fs/cgroup/cgroup.controllers ]; then
            cg_type="v2"
            cg_cpu=$(cat /sys/fs/cgroup/cpu.max 2>/dev/null)
            cg_mem=$(cat /sys/fs/cgroup/memory.max 2>/dev/null)
            cg_pids=$(cat /sys/fs/cgroup/pids.max 2>/dev/null)
        elif [ -d /sys/fs/cgroup/memory ]; then
            cg_type="v1"
            cg1q=$(cat /sys/fs/cgroup/cpu/cpu.cfs_quota_us 2>/dev/null)
            cg1p=$(cat /sys/fs/cgroup/cpu/cpu.cfs_period_us 2>/dev/null)
            [ -n "$cg1q" ] && [ -n "$cg1p" ] && cg_cpu="${cg1q} ${cg1p}"
            cg_mem=$(cat /sys/fs/cgroup/memory/memory.limit_in_bytes 2>/dev/null)
            cg_pids=$(cat /sys/fs/cgroup/pids/pids.max 2>/dev/null)
        fi
        in_container="no"
        [ -f /.dockerenv ] && in_container="docker"
        grep -qsE 'docker|containerd|kubepods|libpod' /proc/1/cgroup 2>/dev/null && in_container="yes (cgroup)"
        [ -f /run/.containerenv ] && in_container="podman"
        echo "Type: cgroup $cg_type"
        echo "Container: $in_container"
        if [ "$cg_type" = "v2" ]; then
            echo "CPU quota: $cg_cpu (cpu.max: quota period)"
            if [ "$cg_mem" != "max" ] && [ -n "$cg_mem" ]; then
                echo "Memory limit: $((cg_mem / 1073741824)) GB ($cg_mem bytes)"
            else echo "Memory limit: unlimited"; fi
            echo "PIDs limit: ${cg_pids:-unlimited}"
            echo "Paths: /sys/fs/cgroup/{cpu.max,memory.max,memory.current}"
        elif [ "$cg_type" = "v1" ]; then
            echo "CPU quota: ${cg_cpu:-(unset)} (cfs_quota_us cfs_period_us)"
            if [ -n "$cg_mem" ] && [ "$cg_mem" -lt 1000000000000 ] 2>/dev/null; then
                echo "Memory limit: $((cg_mem / 1073741824)) GB ($cg_mem bytes)"
            else echo "Memory limit: unlimited"; fi
            echo "PIDs limit: ${cg_pids:-unlimited}"
            echo "Paths: /sys/fs/cgroup/{cpu/cpu.cfs_quota_us,memory/memory.limit_in_bytes,memory/memory.usage_in_bytes}"
        else
            echo "Not running under cgroup resource limits"
        fi
        if [ "$in_container" != "no" ]; then
            echo ""
            echo "IMPORTANT: You are in a container with cgroup resource limits."
            echo "Do NOT use psutil.virtual_memory().total, free -h, or /proc/meminfo for limits."
            echo "Do NOT use os.cpu_count() or nproc for CPU count."
            echo "Use the cgroup paths above or the Python helpers from SKILL.md."
        fi
    ) &&
    echo "=== CPU ===" &&
    (
        cpus=""
        cg2=$(cat /sys/fs/cgroup/cpu.max 2>/dev/null) &&
            [[ "$cg2" != "max"* ]] && q=${cg2%% *} && p=${cg2##* } &&
            cpus=$(((q + p - 1) / p))
        if [ -z "$cpus" ]; then
            cg1q=$(cat /sys/fs/cgroup/cpu/cpu.cfs_quota_us 2>/dev/null) &&
                cg1p=$(cat /sys/fs/cgroup/cpu/cpu.cfs_period_us 2>/dev/null) &&
                [[ "$cg1q" -gt 0 ]] && cpus=$(((cg1q + cg1p - 1) / cg1p))
        fi
        if [ -z "$cpus" ]; then
            aff=$(python3 -c "import os; print(len(os.sched_getaffinity(0)))" 2>/dev/null) &&
                [ -n "$aff" ] && cpus=$aff
        fi
        echo "${cpus:-$(nproc)} CPUs"
    ) &&
    lscpu | grep 'Model name' &&
    echo "=== RAM ===" &&
    (
        memlimit=$(cat /sys/fs/cgroup/memory.max 2>/dev/null ||
            cat /sys/fs/cgroup/memory/memory.limit_in_bytes 2>/dev/null)
        if [ -n "$memlimit" ] && [ "$memlimit" != "max" ] &&
            [ "$memlimit" -lt 1000000000000 ] 2>/dev/null; then
            echo "$((memlimit / 1073741824)) GB (container limit)"
        else free -h | awk '/Mem:/{print $2" total, "$7" available"}'; fi
    ) &&
    echo "=== DISK ===" && df -h . | awk 'NR==2{print $2" total, "$4" free"}' &&
    echo "=== GPU ===" &&
    (gpu=$(nvidia-smi --query-gpu=name,memory.total,memory.free,utilization.gpu \
        --format=csv,noheader 2>/dev/null) &&
        echo "$gpu" | awk -F', ' '{print $1", VRAM: "$2" ("$3" free), Util: "$4}' ||
        echo "No GPU")
