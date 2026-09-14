# coding=utf-8
"""跨进程 GPU 名额分配。

进程内的 threading.Lock 管不了 spawn 出去的子进程（video/tasks.py 的
hardsub_gpu_lock 就是这个毛病，它自己的注释也写了）。这里用文件锁，沿用
utils 那套批量提取脚本的写法：O_EXCL 建占位文件 + 文件里记 PID + 持有者
没了就回收僵死锁。那套在 338 个视频的批量里跑过。

名额数按显卡实际显存算，所以同一份代码在不同机器上行为不同：
    5070 Ti 16GB 单卡      -> 1 个名额（给 GLM-OCR 留出 reserve）
    5090 32GB 单卡         -> 4 个名额
    16GB + 16GB 双卡       -> 每卡 1 个，共 2 个，并按卡分配 CUDA_VISIBLE_DEVICES

环境变量可覆盖自动判断：
    VIDGO_GPU_SLOT_DIR   名额文件目录，默认 /tmp/vidgo_gpu_slots
    VIDGO_GPU_VISIBLE    只用这些卡，逗号分隔，如 "0,1"
    VIDGO_GPU_RESERVE_GB 每张卡给别的任务留多少，默认 8
    VIDGO_GPU_SLOTS      直接写死总名额数，调试用
"""
import atexit
import os
import subprocess

SLOT_DIR = os.environ.get("VIDGO_GPU_SLOT_DIR", "/tmp/vidgo_gpu_slots")
_held = []


def _gpus():
    """[(index, total_gb, free_gb)]。不依赖 torch。

    返回 None  = 探测失败（没有 nvidia-smi、超时、或一张卡都没报出来）
    返回 []    = 探测成功，但 VIDGO_GPU_VISIBLE 把所有卡都排除了
    两者必须分开：前者该保守放行，后者是运维的明确意图，不能擅自换一张卡跑。
    """
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=index,memory.total,memory.free",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=15).stdout
    except Exception:
        return None
    found = []
    for line in out.strip().splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) != 3 or not parts[0].isdigit():
            continue
        found.append((int(parts[0]), float(parts[1]) / 1024.0, float(parts[2]) / 1024.0))
    if not found:
        return None
    want = os.environ.get("VIDGO_GPU_VISIBLE", "").strip()
    if not want:
        return found
    keep = {int(x) for x in want.split(",") if x.strip().isdigit()}
    return [g for g in found if g[0] in keep]


def plan(need_gb=5.0, reserve_gb=None):
    """算出名额表 [(gpu_index, slot_k)]，不做任何占用，便于外部查看容量。"""
    if reserve_gb is None:
        reserve_gb = float(os.environ.get("VIDGO_GPU_RESERVE_GB", "8"))
    gpus = _gpus()
    if gpus is None:
        # 读不到显卡信息（容器里没注入 nvidia-smi、或者调用超时）。这时候**不能**返回空表：
        # 空表会让 acquire 永远失败，WeMM 被静默关掉而检索看起来还正常。保守给 1 个名额。
        print("  [gpu_slots] 读不到显卡信息，保守按 1 个名额处理", flush=True)
        return [(0, 0)]
    if not gpus:
        # 探测成功但被 VIDGO_GPU_VISIBLE 全排除了 —— 这是明确意图，不给名额，
        # 让调用方回落 bge，绝不能改放到一张被排除的卡上。
        print("  [gpu_slots] VIDGO_GPU_VISIBLE 排除了所有可见显卡，不分配名额", flush=True)
        return []
    slots = []
    for idx, total, _free in gpus:
        n = int(max(0.0, total - reserve_gb) // need_gb)
        slots.extend((idx, k) for k in range(n))
    if not slots:
        # 卡太小，扣掉 reserve 连一个都放不下。仍给 1 个名额，让现场显存检查去把关，
        # 否则小显存机器上 WeMM 永远起不来。
        print("  [gpu_slots] 显存扣除预留后不足一个名额，仍给 1 个，交由现场显存检查把关",
              flush=True)
        return [(gpus[0][0], 0)]
    forced = os.environ.get("VIDGO_GPU_SLOTS", "").strip()
    if forced.isdigit():
        want = int(forced)
        if want <= len(slots):
            slots = slots[:want]
        else:                                   # 调试时可以要求超过硬件推算的名额
            base = slots or [(0, 0)]
            slots = [(base[i % len(base)][0], i) for i in range(want)]
    return slots


def _claim(path, tag):
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, ("%s:%d" % (tag, os.getpid())).encode())
        os.close(fd)
        return True
    except FileExistsError:
        # 文件里记了 PID：持有者已经没了就是僵死锁，回收后重试一次。
        try:
            pid = int(open(path).read().split(":")[1])
            os.kill(pid, 0)
            return False                        # 还活着，这个名额确实被占
        except (ValueError, IndexError, ProcessLookupError, OSError):
            try:
                os.remove(path)
            except OSError:
                return False
            try:
                fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(fd, ("%s:%d" % (tag, os.getpid())).encode())
                os.close(fd)
                return True
            except OSError:
                return False
    except OSError:
        return False


def acquire(need_gb=5.0, tag="wemm", check_free=True):
    """拿到名额返回 (slot_path, gpu_index)，拿不到返回 None —— 调用方应当回落。

    除了名额本身，还要现场核一遍剩余显存：硬字幕那批进程并不参与这套名额，
    光有名额不代表显存真的够。
    """
    try:
        os.makedirs(SLOT_DIR, exist_ok=True)
    except OSError:
        return None
    live = {i: f for i, _t, f in (_gpus() or [])}
    for gpu, k in plan(need_gb=need_gb):
        path = os.path.join(SLOT_DIR, "gpu%d.slot%d" % (gpu, k))
        if not _claim(path, tag):
            continue
        # live 为空说明压根没探测到显卡，这时没有可信的剩余显存数，别拿 0 去判死
        if check_free and live and live.get(gpu, 0.0) < need_gb:
            release((path, gpu))                # 名额空着但显存被别人吃了，让出去
            continue
        _held.append((path, gpu))
        return path, gpu
    return None


def release(handle):
    if not handle:
        return
    path = handle[0] if isinstance(handle, (tuple, list)) else handle
    try:
        if ("%d" % os.getpid()) == open(path).read().split(":")[1]:
            os.remove(path)                     # 只删自己那把，别动别人的
    except (OSError, ValueError, IndexError):
        pass
    for h in list(_held):
        if h[0] == path:
            _held.remove(h)


@atexit.register
def _cleanup():
    for h in list(_held):
        release(h)
