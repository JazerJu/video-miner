import re
import hashlib
import time
import requests
import json
import os
import subprocess
from urllib.parse import quote_plus
from django.http import JsonResponse,HttpResponse,HttpResponseNotAllowed,HttpResponseNotFound,Http404,FileResponse
from django.conf import settings  # Ensure this is at the top
from tqdm import tqdm
import argparse

# **0. Utils function
# 替换标题中的特殊字符 --> 用于文件命名。
def sanitize_filename(title: str, max_bytes: int = 200) -> str:
    """
    清理文件名中的特殊字符并限制长度

    Args:
        title: 原始标题
        max_bytes: 最大字节数（默认200，为文件扩展名和后缀预留空间）

    Returns:
        清理后的文件名
    """
    special_chars = r"[ |?？*:\"<>/\\&%#@!()+^~,\';.]"
    sanitized = re.sub(special_chars, "-", title)

    # 限制字节长度（考虑 UTF-8 编码，中文字符可能占 3 个字节）
    encoded = sanitized.encode('utf-8')
    if len(encoded) > max_bytes:
        # 截断到指定字节数，避免截断中文字符中间
        truncated = encoded[:max_bytes].decode('utf-8', errors='ignore')
        # 去除可能被截断的尾部破损字符
        sanitized = truncated.rstrip('-')

    return sanitized

from functools import reduce
from hashlib import md5
import urllib.parse
import time
import requests

mixinKeyEncTab = [
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35, 27, 43, 5, 49,
    33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13, 37, 48, 7, 16, 24, 55, 40,
    61, 26, 17, 0, 1, 60, 51, 30, 4, 22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11,
    36, 20, 34, 44, 52
]

def getMixinKey(orig: str):
    '对 imgKey 和 subKey 进行字符顺序打乱编码'
    return reduce(lambda s, i: s + orig[i], mixinKeyEncTab, '')[:32]

def encWbi(params: dict, img_key: str, sub_key: str):
    '为请求参数进行 wbi 签名'
    mixin_key = getMixinKey(img_key + sub_key)
    curr_time = round(time.time())
    params['wts'] = curr_time                                   # 添加 wts 字段
    params = dict(sorted(params.items()))                       # 按照 key 重排参数
    # 过滤 value 中的 "!'()*" 字符
    params = {
        k : ''.join(filter(lambda chr: chr not in "!'()*", str(v)))
        for k, v 
        in params.items()
    }
    query = urllib.parse.urlencode(params)                      # 序列化参数
    wbi_sign = md5((query + mixin_key).encode()).hexdigest()    # 计算 w_rid
    params['w_rid'] = wbi_sign
    return params

def getWbiKeys() -> tuple[str, str]:
    '获取最新的 img_key 和 sub_key'
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3',
        'Referer': 'https://www.bilibili.com/'
    }
    resp = requests.get('https://api.bilibili.com/x/web-interface/nav', headers=headers)
    resp.raise_for_status()
    json_content = resp.json()
    img_url: str = json_content['data']['wbi_img']['img_url']
    sub_url: str = json_content['data']['wbi_img']['sub_url']
    img_key = img_url.rsplit('/', 1)[1].split('.')[0]
    sub_key = sub_url.rsplit('/', 1)[1].split('.')[0]
    return img_key, sub_key

def get_encrypt_keys():
    img_key, sub_key = getWbiKeys()

    signed_params = encWbi(
        params={
            'foo': '114',
            'bar': '514',
            'baz': 1919810
        },
        img_key=img_key,
        sub_key=sub_key
    )
    query = urllib.parse.urlencode(signed_params)
    print(signed_params["wts"], signed_params["w_rid"]) # 两个关键参数
    wts,w_rid=signed_params["wts"], signed_params["w_rid"]
    return wts,w_rid

# **2. 视频基本信息**
# 解析 URL，判断 BV/AV 号及 P（视频的第N个分P）

def extract_av_bv_p(url: str) -> tuple:
    bvid = avid = p = None
    bv_match = re.search(r"(BV[0-9A-Za-z]+)", url)
    av_match = re.search(r"(av\d+)", url)
    p_match = re.search(r"[?&]p=(\d+)", url)
    if bv_match:
        bvid = bv_match.group(1)
        print(f"bvid: {bvid}")
    if av_match:
        avid = av_match.group(1)
        print(f"avid: {avid}")
    if p_match:
        p = p_match.group(1)
        print(f"p: {p}")
    return bvid, avid, p

# 获取视频的 CID 列表（如果有分P会返回列表）
def get_cid(bvid: str = None, avid: str = None) -> tuple:
    info_url = "https://api.bilibili.com/x/player/pagelist"
    headers = {
        'Referer': 'https://www.bilibili.com',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
    }
    if not bvid and not avid:
        raise ValueError("Either bvid or avid must be provided.")
    params = {'bvid': bvid} if bvid else {'aid': avid}
    resp = requests.get(info_url, headers=headers, params=params)
    j = resp.json()
    cids = [item['cid'] for item in j['data']]
    data = j['data']
    return cids, data

# 获取视频预览图链接，标题，作者等基本信息
def get_video_info(bvid: str = None, avid: str = None) -> dict:
    if bvid:
        url = f"https://api.bilibili.com/x/web-interface/wbi/view?bvid={bvid}"
    elif avid:
        url = f"https://api.bilibili.com/x/web-interface/wbi/view?aid={avid}"
    else:
        raise ValueError("Either bvid or avid must be provided.")
    headers = {
        'Referer': 'https://www.bilibili.com',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
    }
    resp = requests.get(url, headers=headers)
    resp.raise_for_status()
    data = resp.json()['data']
    with open('miaowu.txt', 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)   # ① obj ② fp
    pic_url = data['pic']
    title = data['title']
    duration = data['duration']
    owner = data['owner']["name"]

    if not bvid:
        bvid = data['bvid']
    return {'pic_url': pic_url,'owner':owner,'duration':duration, 'title': title,'bvid': bvid}

# 保存 JSON 到文件

def save_json_to_file(json_string: str, file_path: str):
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(json_string)

# 获取 1080p 视频原链接 JSON
import http.client
def get_video_url(bvid: str, cid: int, sessdata: str) -> dict:
    """
    Retrieves the playurl JSON for the given bvid and cid.
    Falls back to http.client if requests gets a 412 error.
    """
    quality_num=80
    wts,w_rid=get_encrypt_keys()  # 获取最新的 wts 和 w_rid
    print(wts,w_rid)
    path = (
        f"/x/player/wbi/playurl?bvid={bvid}&cid={cid}&qn=0&fnval={quality_num}&fnver=0&fourk=1&gaia_source=view-card&wts={wts}&w_rid={w_rid}" # 新的api
        # f"/x/player/playurl?bvid={bvid}&cid={cid}&qn=0&fnval={quality_num}&fnver=0&fourk=1" # 旧的api.
    )
    headers = {'Cookie': f"SESSDATA={sessdata}"}
    try:
        # Attempt with requests
        url = f"https://api.bilibili.com{path}"
        resp = requests.get(url, headers=headers)
        resp.raise_for_status()
        json_data = resp.json()
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 412:
            # Fallback to http.client for protected endpoint
            conn = http.client.HTTPSConnection("api.bilibili.com")
            conn.request("GET", path, headers=headers)
            res = conn.getresponse()
            raw = res.read().decode('utf-8')
            json_data = json.loads(raw)
        else:
            raise
    # Save for debugging
    save_json_to_file(json.dumps(json_data, indent=4), "videos_url.json")
    return json_data

# 解析流媒体链接

def parse_video_url(raw_vid_json: dict) -> dict:
    data = raw_vid_json.get('data', {}).get('dash', {})
    videos = data.get('video', [])
    audios = data.get('audio', [])
    # 优先选择1080P (id=80)
    video_item = next((v for v in videos if v.get('id') == 80), None)
    # 如果1080P不存在，则尝试720P (id=48)
    if not video_item:
        video_item = next((v for v in videos if v.get('id') == 64), None)
        if video_item:
            print("720P (id=48) available, using this stream.")
    # 否则使用第一个可用分辨率
    if not video_item and videos:
        video_item = videos[0]
        print("Neither 1080p nor 720p (id=64) found, using first available resolution.")
    audio_item = next((a for a in audios if a.get('id') == 30280), None)
    if not audio_item and audios:
        audio_item = audios[0]
        print("80分辨率的音频未找到，使用其他分辨率。")
    result = {}
    if video_item:
        result['vidBaseUrl'] = video_item.get('baseUrl')
        result['vidBackUrl'] = video_item.get('backupUrl', [None])[0]
    if audio_item:
        result['audBaseUrl'] = audio_item.get('baseUrl')
        result['audBackUrl'] = audio_item.get('backupUrl', [None])[0]
    return result

# 下载文件并显示进度

def download_file_with_progress(url: str, filename: str, progress_callback=None):
    """
    下载文件并实时报告进度

    Args:
        url: 下载URL
        filename: 保存文件名
        progress_callback: 进度回调函数 callback(percent: int)，范围 0-100
    """
    headers = {
        'Referer': 'https://www.bilibili.com',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
    }
    resp = requests.get(url, headers=headers, stream=True)
    total = int(resp.headers.get('content-length', 0))
    downloaded = 0
    chunk_size = 512 * 1024  # 优化：从1KB提升到512KB（参考GIL分析）

    with open(filename, 'wb') as f:
        for chunk in tqdm(resp.iter_content(chunk_size=chunk_size),
                          total=total // chunk_size,
                          unit='KB',
                          desc=f"Downloading {os.path.basename(filename)}"):
            if chunk:
                f.write(chunk)
                downloaded += len(chunk)

                # 🆕 回调进度百分比
                if progress_callback and total > 0:
                    percent = int((downloaded / total) * 100)
                    progress_callback(percent)

# 合并音视频文件

def merge_audio_video(audio_file: str, video_file: str, output_file: str, progress_callback=None):
    """
    使用FFmpeg合并音视频，支持真实进度回调

    Args:
        audio_file: 音频文件路径
        video_file: 视频文件路径
        output_file: 输出文件路径
        progress_callback: 进度回调函数 callback(percent: int)，范围 0-100
    """
    cmd = [
        'ffmpeg', '-y', '-i', video_file, '-i', audio_file,
        '-c:v', 'copy', '-c:a', 'aac', '-strict', 'experimental',
        '-progress', 'pipe:1',  # 输出进度到stdout
        output_file
    ]

    if not progress_callback:
        # 无需进度回调，直接运行
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        return

    # 🆕 获取视频总时长（用于计算进度百分比）
    import json
    probe_cmd = [
        'ffprobe', '-v', 'error',
        '-show_entries', 'format=duration',
        '-of', 'json',
        video_file
    ]
    probe_result = subprocess.run(probe_cmd, capture_output=True, text=True)
    duration = 0.0
    try:
        probe_data = json.loads(probe_result.stdout)
        duration = float(probe_data['format']['duration'])
    except (json.JSONDecodeError, KeyError, ValueError):
        duration = 0.0

    # 🆕 启动FFmpeg进程并解析进度
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)

    for line in process.stdout:
        line = line.strip()
        # FFmpeg进度输出格式：out_time_ms=12345678
        if line.startswith('out_time_ms='):
            try:
                time_ms = int(line.split('=')[1])
                current_time = time_ms / 1_000_000  # 微秒转秒
                if duration > 0:
                    percent = min(int((current_time / duration) * 100), 99)
                    progress_callback(percent)
            except (ValueError, IndexError):
                pass

    process.wait()
    if process.returncode != 0:
        raise subprocess.CalledProcessError(process.returncode, cmd)

    progress_callback(100)  # 完成时确保100%

from pathlib import Path           # 比 os.path 更好用
WORK_DIR = Path(settings.BASE_DIR, "work_dir")   # …/<your_project>/work_dir
WORK_DIR.mkdir(exist_ok=True)
def get_direct_media_link(bvid,cid=None,title=None,idx=None,sessdata=""):
    if cid is None or title is None :
        info = get_video_info(bvid=bvid, avid="") # 可以有，但是前端如果给了的话就不用了
        bvid = info['bvid']
        cid = info['cid']
        title = info['title']
    safe_title = sanitize_filename(f"{title}-{idx}")
    vid_json = get_video_url(bvid=bvid, cid=cid, sessdata=sessdata)
    urls = parse_video_url(vid_json)
    video  = WORK_DIR / f"{safe_title}_video.mp4"
    audio  = WORK_DIR / f"{safe_title}_audio.mp3"
    merged = WORK_DIR / f"{safe_title}_merged.mp4"
    return video,audio,merged,urls
    
# 主函数
def main_bili_downloader(url: str, sessdata: str, down_list: bool = False):
    bvid, avid, p = extract_av_bv_p(url)
    cids, data = get_cid(bvid=bvid, avid=avid)
    # 处理多 P
    if len(data) > 1 and not down_list:
        print("Multiple videos found. Please select which to download:")
        for idx, item in enumerate(data, 1):
            part = item.get('part') or f"Part {idx}"
            dur = item.get('duration')
            print(f"{idx}. {part} ({dur}s)")
        answer = input("Enter numbers (comma-separated) or 'full': ").strip().lower()
        if answer == 'full':
            selected = list(range(len(data)))
        else:
            selected = [int(i)-1 for i in answer.split(',')]
        data = [item for idx, item in enumerate(data) if idx in selected]
    # 下载每个分P
    for idx, item in enumerate(data, 1):
        info = get_video_info(bvid=bvid, avid=avid)
        bvid = info['bvid']
        cid = item['cid']
        title = info['title']
        safe_title = sanitize_filename(f"{title}-{idx}")
        vid_json = get_video_url(bvid=bvid, cid=cid, sessdata=sessdata)
        urls = parse_video_url(vid_json)
        video_file = f"work_dir/{safe_title}_video.mp4"
        audio_file = f"work_dir/{safe_title}_audio.mp3"
        output_file = f"work_dir/{safe_title}_merged.mp4"
        download_file_with_progress(urls['vidBaseUrl'], video_file)
        download_file_with_progress(urls['audBaseUrl'], audio_file)
        merge_audio_video(audio_file, video_file, output_file)
        # 清理中间文件
        # for fpath in [video_file, audio_file]:
        for fpath in [video_file]:
            try:
                os.remove(fpath)
            except OSError:
                pass

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Download Bilibili videos with audio merge')
    parser.add_argument('--url', default="https://www.bilibili.com/video/BV19e4y1q7JJ?spm_id_from=333.788.recommend_more_video.-1&vd_source=3d7594eace7bea23a96123faecc64e41", help='BV/AV URL')
    parser.add_argument('--sessdata',default="bd6c83c2%2C1768619794%2Ce2a7c%2A71CjBZZspc9z0-KH-fPDTEwRGeVY5_Rqj0FqU9saO4hRRX9crVvGBj6TS85gZLG3tWLfISVmc4WFhUTzJLMVdLVE80OThaNUdZNDZsODRUV3ZNRV9zc1NyUkZ5eVNtRHRGQ1dFSVJyUmhqNi0yTnJ6NXhEU3RvN3FWbVRsTWo4ODB4VGhiR1ZEQkJ3IIEC", help='SESSDATA cookie value')
    parser.add_argument('--down_list', action='store_true', help='Download all parts without prompt')
    args = parser.parse_args()
    main_bili_downloader(args.url, args.sessdata, args.down_list)
