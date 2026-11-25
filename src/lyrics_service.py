# -*- coding: utf-8 -*-
"""
歌词服务模块

负责从音频文件内置标签、网易云 API 或本地文件获取歌词数据。
"""

import os
import json
import re
import unicodedata
import requests
from mutagen import File
from PyQt5.QtCore import QThread, pyqtSignal

# 项目内歌词缓存目录
LYRICS_DIR = os.path.join(os.path.dirname(__file__), 'resources', 'lyrics')
os.makedirs(LYRICS_DIR, exist_ok=True)


def _get_lyrics_filename(title: str, artist: str) -> str:
    """生成安全的歌词文件名"""
    # 合并歌手和歌名作为文件名基础
    name = f"{artist} - {title}" if artist and artist != '未知艺术家' else title
    # 去除 Windows 非法字符
    name = re.sub(r'[\\/:*?"<>|]', '_', name)
    # 去除首尾空白
    name = name.strip()
    # 限制长度避免路径过长
    if len(name) > 100:
        name = name[:100]
    return name + ".lrc"


def _read_lyrics_text(path: str) -> str:
    """读取歌词文件，按常见编码依次尝试（兼容 BOM 与 GBK 老文件）"""
    for encoding in ('utf-8-sig', 'utf-8', 'gb18030'):
        try:
            with open(path, 'r', encoding=encoding) as f:
                content = f.read()
            if content and content.strip():
                return content
        except UnicodeDecodeError:
            continue
        except Exception as e:
            print(f"读取歌词失败 {path}: {e}")
            return ""
    return ""


_AUDIO_EXTS_FOR_LRC = ('.flac', '.mp3', '.wav', '.m4a', '.ogg', '.ape', '.opus', '.aac', '.wma')
_CJK_TEXT = re.compile(r'[\u3040-\u30ff\u4e00-\u9fff]')


def _strip_lyrics_suffix(name: str) -> str:
    """把歌词文件名还原成歌曲标识：去掉 .lrc，再去掉可能残留的音频扩展名"""
    base = name[:-4] if name.lower().endswith('.lrc') else name
    lower = base.lower()
    for ext in _AUDIO_EXTS_FOR_LRC:
        if lower.endswith(ext):
            base = base[:-len(ext)]
            break
    return base.strip()


def _normalize_lyrics_name(text: str) -> str:
    """规范化名称用于匹配：全角转半角、小写、去标点、压空格"""
    try:
        text = unicodedata.normalize('NFKC', text or '')
    except Exception:
        text = text or ''
    text = text.lower()
    text = re.sub(r'[\s\-_.,:;!?\'"()\[\]{}~/\\]+', ' ', text)
    return re.sub(r'\s+', ' ', text).strip()


def _match_lyrics_file(title: str, artist: str, file_path: str = "") -> str:
    """在歌词目录里按规范名兜底匹配已有文件

    存在的历史命名并不统一，例如 "2：23 AM.flac.lrc"（全角冒号 + 带音频扩展名）、
    "未知 - Ayase - 夜撫でるメノウ (Ayase ver.).flac.lrc"。只按 "标题.lrc" 精确
    查找会漏掉这些文件，这里再做一次名称归一化匹配。
    """
    try:
        entries = [e for e in os.listdir(LYRICS_DIR) if e.lower().endswith('.lrc')]
    except Exception:
        return ""
    if not entries:
        return ""

    # 1. 文件名直接相等（不区分大小写），兼容 "<文件名>.flac.lrc" 等历史形态
    direct = set()
    if file_path:
        base = os.path.basename(file_path)
        direct.add(base + '.lrc')
        direct.add(os.path.splitext(base)[0] + '.lrc')
    if title:
        direct.add(title + '.lrc')
    lowered = {name.lower(): name for name in entries}
    for name in direct:
        hit = lowered.get(name.lower())
        if hit:
            return os.path.join(LYRICS_DIR, hit)

    # 2. 归一化比较
    keys = []
    for text in (title,
                 f"{artist} - {title}" if artist and artist != '未知艺术家' else '',
                 os.path.splitext(os.path.basename(file_path))[0] if file_path else ''):
        normalized = _normalize_lyrics_name(text)
        if normalized:
            keys.append(normalized)
    if not keys:
        return ""

    best_name, best_score = "", 0.0
    for name in entries:
        target = _normalize_lyrics_name(_strip_lyrics_suffix(name))
        if not target:
            continue
        score = 0.0
        for key in keys:
            if target == key:
                score = max(score, 1.0)
            elif key in target and (len(key) >= 6 or _CJK_TEXT.search(key)):
                # 短英文名（如 "Sold"）容易误命中别人的文件，要求足够长或含中日文
                score = max(score, 0.8)
            else:
                tokens = key.split()
                if len(tokens) >= 2 and all(t in target.split() for t in tokens):
                    score = max(score, 0.7)
        if score > best_score:
            best_name, best_score = name, score
    if best_name and best_score >= 0.7:
        return os.path.join(LYRICS_DIR, best_name)
    return ""


def get_local_lyrics(title: str, artist: str, file_path: str = "") -> str:
    """从本地读取歌词（优先音频文件同名.lrc，其次项目资源歌词目录）

    Args:
        title: 歌曲标题
        artist: 歌手名称
        file_path: 音频文件绝对路径（可选）

    Returns:
        歌词文本，未找到则返回空字符串
    """
    # 1. 优先检查音频文件同目录下的同名 .lrc 文件
    if file_path and os.path.exists(file_path):
        base_no_ext = os.path.splitext(file_path)[0]
        same_dir_lrc = base_no_ext + ".lrc"
        if os.path.exists(same_dir_lrc):
            content = _read_lyrics_text(same_dir_lrc)
            if content:
                return content

    # 2. 检查项目本地资源歌词目录 (src/resources/lyrics)
    possible_names = []
    if title:
        possible_names.append(_get_lyrics_filename(title, artist))
        safe_title = re.sub(r'[\\/:*?"<>|]', '_', title).strip() + ".lrc"
        if safe_title not in possible_names:
            possible_names.append(safe_title)
    if file_path:
        base_name = os.path.splitext(os.path.basename(file_path))[0]
        safe_base = re.sub(r'[\\/:*?"<>|]', '_', base_name).strip() + ".lrc"
        if safe_base not in possible_names:
            possible_names.append(safe_base)

    for fname in possible_names:
        lrc_path = os.path.join(LYRICS_DIR, fname)
        if os.path.exists(lrc_path):
            content = _read_lyrics_text(lrc_path)
            if content:
                return content

    # 3. 兜底：按名称归一化匹配（兼容历史命名不规范的歌词文件）
    matched_path = _match_lyrics_file(title, artist, file_path)
    if matched_path:
        content = _read_lyrics_text(matched_path)
        if content:
            return content

    return ""


def get_embedded_lyrics(file_path: str) -> str:
    """读取音频文件内部的内置歌词

    Args:
        file_path: 音频文件路径

    Returns:
        歌词文本，未找到则返回空字符串
    """
    if not file_path or not os.path.exists(file_path):
        return ""

    try:
        audio = File(file_path)
        if audio is None:
            return ""

        # 1. 尝试 FLAC / OGG 的 Vorbis Comment
        if hasattr(audio, 'tags') and audio.tags:
            for key in ['LYRICS', 'UNSYNCEDLYRICS', 'SYNCEDLYRICS']:
                if key in audio.tags:
                    return str(audio.tags[key][0])

        # 2. 尝试 MP3 ID3 的 USLT (非同步歌词)
        if hasattr(audio, 'tags') and audio.tags:
            for key in list(audio.tags.keys()):
                if key.startswith('USLT'):
                    uslt = audio.tags[key]
                    if hasattr(uslt, 'text'):
                        return str(uslt.text)
                    else:
                        return str(uslt)

        return ""
    except Exception as e:
        print(f"读取内置歌词失败: {e}")
        return ""


_ARTIST_SEPARATOR = re.compile(r'[、,;／/&×]')
_BRACKET_CONTENT = re.compile(r'[\(（\[【].*?[\)）\]】]')
_NON_WORD = re.compile(r'[^\w\u4e00-\u9fff]+', re.UNICODE)
_NOISE_WORDS = re.compile(r'伴奏|instrumental|karaoke|off ?vocal|翻唱|cover|remix|live',
                          re.IGNORECASE)


def split_artists(artist: str) -> list:
    """把 "A、B、C / A & B / A feat. B" 这类多歌手串拆成单个歌手

    整串拿去搜索会把结果带偏：网易云会返回翻唱版本，取词为空直接判失败。
    """
    if not artist:
        return []
    parts = []
    for chunk in _ARTIST_SEPARATOR.split(artist):
        chunk = re.sub(r'\b(feat|ft)\.?\s.*$', '', chunk, flags=re.IGNORECASE).strip()
        if chunk:
            parts.append(chunk)
    return parts


def normalize_text(text: str) -> str:
    """规范化歌名/歌手用于匹配：去括号内容、去标点、小写、压空格"""
    text = _BRACKET_CONTENT.sub(' ', text or '')
    text = _NON_WORD.sub(' ', text.lower())
    return re.sub(r'\s+', ' ', text).strip()


def build_search_variants(title: str, artist: str) -> list:
    """生成从精确到宽松的搜索候选，按优先级排序

    Returns:
        [(title, artist), ...]，第一项最精确
    """
    title = (title or '').strip()
    artists = split_artists(artist)
    variants = []

    def add(t, a):
        t = (t or '').strip()
        a = (a or '').strip()
        if t and (t, a) not in variants:
            variants.append((t, a))

    if title and artists:
        add(title, artists[0])          # 歌名 + 第一歌手，最可靠
    if title:
        add(title, '')

    # 标题里混进"歌手 - 歌名"（很多文件没有 artist 标签）
    if ' - ' in title:
        left, right = (part.strip() for part in title.split(' - ', 1))
        add(left, right)
        add(left, '')
        add(right, left)
        add(right, '')

    # 去掉括号里的 (feat.xxx) / (Live) 等再试
    cleaned = re.sub(r'\s+', ' ', _BRACKET_CONTENT.sub(' ', title)).strip()
    if cleaned and cleaned != title:
        add(cleaned, artists[0] if artists else '')
        add(cleaned, '')

    if not variants:
        add(title, artist)
    return variants


def rank_candidates(songs: list, title: str, artist: str) -> list:
    """按"歌名匹配优先、歌手匹配次之、伴奏/翻唱降权"排序候选"""
    expect_title = normalize_text(title)
    expect_artists = {normalize_text(a) for a in split_artists(artist) if normalize_text(a)}

    def score(song):
        name = normalize_text(song.get('name') or song.get('title') or '')
        value = 0
        if name and expect_title:
            if name == expect_title:
                value += 6
            elif expect_title in name or name in expect_title:
                value += 4
        song_artists = {normalize_text(a.get('name', ''))
                        for a in (song.get('artists') or song.get('ar') or [])}
        if expect_artists & song_artists:
            value += 3
        if _NOISE_WORDS.search(name):
            value -= 2
        return value

    return sorted(songs, key=score, reverse=True)


def _search_netease(title: str, artist: str) -> list:
    """网易云音乐搜索歌曲

    Args:
        title: 歌曲标题
        artist: 歌手名称

    Returns:
        歌曲列表，失败返回空列表
    """
    keyword = f"{title} {artist}".strip()

    url = "https://music.163.com/api/cloudsearch/pc"
    data = {
        "s": keyword,
        "type": 1,
        "offset": 0,
        "limit": 5
    }

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Referer": "https://music.163.com/"
    }

    resp = requests.post(url, data=data, headers=headers, timeout=10)
    resp.raise_for_status()
    res_data = resp.json()

    if res_data.get("code") == 200:
        result = res_data.get("result", {})
        if isinstance(result, dict):
            return result.get("songs", [])
    return []


_LRC_TIME_TAG = re.compile(r'\[(\d{2}):(\d{2})\.(\d{2,3})\]')


def merge_translation(lrc_text: str, trans_text: str) -> str:
    """把翻译歌词按时间戳合并进原文，输出标准的双语 LRC

    双语 LRC 的惯例：原文行与翻译行使用同一时间戳，原文在前、翻译紧随其后。
    歌词制作工具也是这么保存的，两处格式统一后主界面就能一起显示。

    Args:
        lrc_text: 原文 LRC 文本
        trans_text: 翻译 LRC 文本（时间戳与原文对应）

    Returns:
        合并后的 LRC 文本；没有可用翻译时原样返回
    """
    if not lrc_text or not trans_text or not trans_text.strip():
        return lrc_text

    trans_map = {}
    for line in trans_text.splitlines():
        match = _LRC_TIME_TAG.search(line)
        if not match:
            continue
        text = line[match.end():].strip()
        if text:
            trans_map[line[:match.end()]] = text

    if not trans_map:
        return lrc_text

    merged = []
    for line in lrc_text.splitlines():
        merged.append(line)
        match = _LRC_TIME_TAG.search(line)
        if not match:
            continue
        tag = line[:match.end()]
        if tag in trans_map and trans_map[tag] != line[match.end():].strip():
            merged.append(f"{tag}{trans_map[tag]}")
    return "\n".join(merged)


def _get_lyric_by_id(song_id: int) -> str:
    """根据歌曲 ID 从网易云获取歌词（含翻译）

    Args:
        song_id: 网易云歌曲 ID

    Returns:
        歌词文本，失败返回空字符串
    """
    url = "https://music.163.com/api/song/lyric"
    params = {"id": song_id, "lv": 1, "kv": 1, "tv": 1}

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://music.163.com/"
    }

    resp = requests.get(url, params=params, headers=headers, timeout=10)
    resp.raise_for_status()
    data = resp.json()

    if data.get("code") == 200 and data.get("lrc") and data["lrc"].get("lyric"):
        lrc_text = data["lrc"]["lyric"]
        trans_text = (data.get("tlyric") or {}).get("lyric") or ""
        return merge_translation(lrc_text, trans_text)
    return ""


def fetch_lyrics_from_netease(title: str, artist: str, notify=None) -> str:
    """从网易云音乐 API 获取歌词（主入口）

    Args:
        title: 歌曲标题
        artist: 歌手名称
        notify: 可选进度回调，接收用于界面展示的中文阶段描述

    Returns:
        歌词文本，失败返回空字符串

    Raises:
        网络相关异常会向上抛出，由调用方转换为友好提示
    """
    def report(message):
        if notify:
            try:
                notify(message)
            except Exception:
                pass

    report("正在连接网易云音乐…")

    variants = build_search_variants(title, artist)
    fallback_song = None
    attempts = 0
    max_attempts = 6          # 一次取词最多试 6 个候选，避免拖太久

    for variant_title, variant_artist in variants:
        keyword = f"{variant_title} {variant_artist}".strip()
        report(f"正在搜索「{keyword}」…")

        songs = _search_netease(variant_title, variant_artist)
        if not songs:
            continue

        ranked = rank_candidates(songs, variant_title, variant_artist)
        if fallback_song is None:
            fallback_song = ranked[0]

        report(f"「{keyword}」共 {len(ranked)} 个候选，正在获取歌词…")
        for song in ranked[:2]:
            song_id = song.get("id")
            if not song_id:
                continue
            attempts += 1
            lyrics = _get_lyric_by_id(song_id)
            if lyrics and lyrics.strip():
                report("歌词下载完成")
                return lyrics
            if attempts >= max_attempts:
                break
        if attempts >= max_attempts:
            break

    # 所有关键词都没取到：用最像的那个再兜底试一次
    if fallback_song is not None:
        song_id = fallback_song.get("id")
        if song_id:
            lyrics = _get_lyric_by_id(song_id)
            if lyrics and lyrics.strip():
                report("歌词下载完成")
                return lyrics

    return ""


def save_lyrics_to_file(title: str, artist: str, lyrics: str, file_path: str = "") -> bool:
    """将歌词严格保存到项目本地资源歌词目录 (src/resources/lyrics)，禁止写入外部音频目录

    Args:
        title: 歌曲标题
        artist: 歌手名称
        lyrics: 歌词内容
        file_path: 兼容参数（不再向音频文件同级目录保存）

    Returns:
        保存是否成功
    """
    if not lyrics or not title:
        return False

    try:
        os.makedirs(LYRICS_DIR, exist_ok=True)
        filename = _get_lyrics_filename(title, artist)
        lrc_path = os.path.join(LYRICS_DIR, filename)

        with open(lrc_path, 'w', encoding='utf-8') as f:
            f.write(lyrics)

        print(f"歌词已严格保存到项目资源歌词目录: {lrc_path}")
        return True
    except Exception as e:
        print(f"保存歌词到项目资源目录失败: {e}")
        return False


def get_lyrics(file_path: str, title: str, artist: str) -> tuple:
    """获取歌词的主入口（优先级：内置歌词 → 本地缓存 → 网易云 API）

    Args:
        file_path: 音频文件路径
        title: 歌曲标题
        artist: 歌手名称

    Returns:
        (lyrics: str, source: str) 来源可为 "embedded", "local", "netease", ""
    """
    # 1. 尝试内置歌词
    embedded = get_embedded_lyrics(file_path)
    if embedded and embedded.strip():
        return embedded, "embedded"

    # 2. 尝试本地缓存歌词
    local_lyrics = get_local_lyrics(title, artist)
    if local_lyrics and local_lyrics.strip():
        return local_lyrics, "local"

    # 3. 尝试网易云（网络异常时按"没有歌词"处理，保持本函数不抛异常）
    try:
        netease_lyrics = fetch_lyrics_from_netease(title, artist)
    except Exception as e:
        print(f"网易云歌词获取异常: {e}")
        netease_lyrics = ""
    if netease_lyrics and netease_lyrics.strip():
        return netease_lyrics, "netease"

    return "", ""


class LyricsFetchThread(QThread):
    """后台异步获取网易云歌词线程，彻底杜绝主界面卡顿，支持随时安全中断"""
    fetched = pyqtSignal(str, str, str, str)  # lyrics, title, artist, file_path
    failed = pyqtSignal(str)                   # error message
    progress = pyqtSignal(str)                 # 阶段进度描述（供界面显示）

    def __init__(self, title: str, artist: str, file_path: str = ""):
        super().__init__()
        self.title = title
        self.artist = artist
        self.file_path = file_path
        self._is_cancelled = False

    def cancel(self):
        """标记取消当前获取任务"""
        self._is_cancelled = True

    def is_cancelled(self) -> bool:
        return self._is_cancelled

    def run(self):
        def notify(message):
            if not self._is_cancelled:
                self.progress.emit(message)

        try:
            if self._is_cancelled:
                return
            lyrics = fetch_lyrics_from_netease(self.title, self.artist, notify=notify)
            if self._is_cancelled:
                return
            if lyrics and lyrics.strip():
                self.fetched.emit(lyrics, self.title, self.artist, self.file_path)
            else:
                self.failed.emit("未检索到匹配歌词（网易云无对应结果）")
        except requests.exceptions.Timeout:
            if not self._is_cancelled:
                self.failed.emit("连接网易云超时，请检查网络后重试")
        except requests.exceptions.ConnectionError:
            if not self._is_cancelled:
                self.failed.emit("无法连接网易云音乐，请检查网络或代理设置")
        except ValueError as e:
            if not self._is_cancelled:
                self.failed.emit(f"网易云返回数据异常：{e}")
        except Exception as e:
            if not self._is_cancelled:
                self.failed.emit(str(e))

