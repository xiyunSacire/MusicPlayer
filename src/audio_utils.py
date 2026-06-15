"""
音频元数据读取工具
"""
import os
from mutagen import File
from mutagen.mp3 import MP3
from mutagen.flac import FLAC
from mutagen.oggvorbis import OggVorbis

def get_audio_metadata(file_path):
    """
    获取音频文件的元数据
    返回：字典，包含 title, artist, duration (秒)
    """
    metadata = {
        'title': os.path.basename(file_path),
        'artist': '未知艺术家',
        'duration': 0
    }
    
    try:
        audio = File(file_path, easy=True)
        if audio is not None:
            # 标题
            if 'title' in audio and audio['title']:
                metadata['title'] = audio['title'][0]
            # 艺术家
            if 'artist' in audio and audio['artist']:
                metadata['artist'] = audio['artist'][0]
            # 时长
            if audio.info and hasattr(audio.info, 'length'):
                metadata['duration'] = int(audio.info.length)            
    
    except Exception as e:
        print(f"读取元数据失败: {file_path} - {e}")
        
    # --- 优化点：如果标签作者为空，则尝试从文件名解析 ---
    if metadata['artist'] == '未知艺术家' and metadata['title'] != os.path.basename(file_path):
        base_name = os.path.splitext(metadata['title'])[0]
        # 查找第一个 '-' 分隔符，假设作者在它前面
        if '-' in base_name:
            parts = base_name.split('-', 1)
            # 假设作者是第一个部分，并清理可能的空格
            potential_artist = parts[0].strip()
            if potential_artist:
                metadata['artist'] = potential_artist
    # ----------------------------------------------------
    
    return metadata

def format_duration(seconds):
    """将秒数格式化为 MM:SS 或 HH:MM:SS"""
    if seconds < 3600:
        minutes = seconds // 60
        secs = seconds % 60
        return f"{minutes:02d}:{secs:02d}"
    else:
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        secs = seconds % 60
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"