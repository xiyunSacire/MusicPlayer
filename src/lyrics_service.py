# -*- coding: utf-8 -*-
"""
歌词服务模块

负责从音频文件内置标签、网易云 API 或本地文件获取歌词数据。
"""

import os
import json
import re
import requests
from mutagen import File

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


def get_local_lyrics(title: str, artist: str) -> str:
    """从项目本地歌词目录读取歌词

    Args:
        title: 歌曲标题
        artist: 歌手名称

    Returns:
        歌词文本，未找到则返回空字符串
    """
    filename = _get_lyrics_filename(title, artist)
    lrc_path = os.path.join(LYRICS_DIR, filename)

    if os.path.exists(lrc_path):
        try:
            with open(lrc_path, 'r', encoding='utf-8') as f:
                return f.read()
        except Exception as e:
            print(f"读取本地歌词失败: {e}")
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


def _search_netease(title: str, artist: str) -> list:
    """网易云音乐搜索歌曲

    Args:
        title: 歌曲标题
        artist: 歌手名称

    Returns:
        歌曲列表，失败返回空列表
    """
    keyword = f"{title} {artist}".strip()

    url = "https://music.163.com/api/search/get/web"
    params = {
        "csrf_token": "",
        "hlpretag": "",
        "hlposttag": "",
        "s": keyword,
        "type": 1,
        "offset": 0,
        "total": "true",
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

    try:
        resp = requests.get(url, params=params, headers=headers, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        if data.get("code") == 200:
            return data.get("result", {}).get("songs", [])
        return []
    except Exception as e:
        print(f"网易云搜索失败: {e}")
        return []


def _get_lyric_by_id(song_id: int) -> str:
    """根据歌曲 ID 从网易云获取歌词

    Args:
        song_id: 网易云歌曲 ID

    Returns:
        歌词文本，失败返回空字符串
    """
    url = "https://music.163.com/api/song/lyric"
    params = {"id": song_id, "lv": 1, "kv": 1, "tv": -1}

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://music.163.com/"
    }

    try:
        resp = requests.get(url, params=params, headers=headers, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        if data.get("code") == 200 and data.get("lrc") and data["lrc"].get("lyric"):
            return data["lrc"]["lyric"]
        return ""
    except Exception as e:
        print(f"获取网易云歌词失败: {e}")
        return ""


def fetch_lyrics_from_netease(title: str, artist: str) -> str:
    """从网易云音乐 API 获取歌词（主入口）

    Args:
        title: 歌曲标题
        artist: 歌手名称

    Returns:
        歌词文本，失败返回空字符串
    """
    songs = _search_netease(title, artist)
    if not songs:
        return ""

    song_id = songs[0].get("id")
    if not song_id:
        return ""

    return _get_lyric_by_id(song_id)


def save_lyrics_to_file(title: str, artist: str, lyrics: str) -> bool:
    """将歌词保存到项目本地歌词目录

    Args:
        title: 歌曲标题
        artist: 歌手名称
        lyrics: 歌词内容

    Returns:
        保存是否成功
    """
    if not lyrics or not title:
        return False

    try:
        filename = _get_lyrics_filename(title, artist)
        lrc_path = os.path.join(LYRICS_DIR, filename)

        with open(lrc_path, 'w', encoding='utf-8') as f:
            f.write(lyrics)

        print(f"歌词已保存到: {lrc_path}")
        return True
    except Exception as e:
        print(f"保存歌词失败: {e}")
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

    # 3. 尝试网易云
    netease_lyrics = fetch_lyrics_from_netease(title, artist)
    if netease_lyrics and netease_lyrics.strip():
        return netease_lyrics, "netease"

    return "", ""
