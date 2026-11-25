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
    if metadata['artist'] == '未知艺术家':
        file_base = os.path.splitext(os.path.basename(file_path))[0]
        if '-' in file_base:
            parts = file_base.split('-', 1)
            potential_artist = parts[0].strip()
            potential_title = parts[1].strip()
            if potential_artist:
                metadata['artist'] = potential_artist
            if metadata['title'] == os.path.basename(file_path) and potential_title:
                metadata['title'] = potential_title
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

def get_audio_cover_bytes(file_path: str):
    """
    读取音频元数据中的专辑封面图片二进制数据
    支持格式：FLAC (pictures), MP3 (ID3 APIC), M4A/MP4 (covr), OGG/Vorbis, 以及同级目录封面图片
    返回：bytes 或 None
    """
    if not file_path or not os.path.exists(file_path):
        return None

    try:
        f = File(file_path)
        if f is not None:
            # 1. FLAC / OGG 内嵌 pictures 属性
            if hasattr(f, 'pictures') and f.pictures:
                for pic in f.pictures:
                    if hasattr(pic, 'data') and pic.data:
                        return pic.data

            # 2. 检查标签字典 (ID3, Vorbis, MP4)
            if hasattr(f, 'tags') and f.tags:
                # 2.1 ID3 APIC (MP3, WAV, AIFF)
                for key, val in f.tags.items():
                    if key.startswith('APIC'):
                        if hasattr(val, 'data') and val.data:
                            return val.data
                # 2.2 MP4 / M4A covr
                if 'covr' in f.tags and f.tags['covr']:
                    covr = f.tags['covr'][0]
                    return bytes(covr)
                # 2.3 OGG / FLAC metadata_block_picture
                if 'metadata_block_picture' in f.tags and f.tags['metadata_block_picture']:
                    try:
                        import base64
                        from mutagen.flac import Picture
                        pic_data = base64.b64decode(f.tags['metadata_block_picture'][0])
                        pic = Picture(pic_data)
                        if pic.data:
                            return pic.data
                    except Exception:
                        pass
    except Exception as e:
        print(f"读取封面失败: {file_path} - {e}")

    # 3. 本地同目录备用封面文件
    try:
        folder = os.path.dirname(file_path)
        base_name = os.path.splitext(os.path.basename(file_path))[0]
        # 常见封面名称
        candidates = [
            f"{base_name}.jpg", f"{base_name}.png", f"{base_name}.jpeg",
            "cover.jpg", "cover.png", "cover.jpeg",
            "folder.jpg", "folder.png", "album.jpg", "front.jpg"
        ]
        for name in candidates:
            cand_path = os.path.join(folder, name)
            if os.path.exists(cand_path):
                with open(cand_path, 'rb') as img_f:
                    return img_f.read()
    except Exception as e:
        print(f"读取本地备用封面失败: {e}")

    return None