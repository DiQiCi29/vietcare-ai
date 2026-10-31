"""Validate and stage private media files. A failed submission leaves no files behind."""
from pathlib import Path
import uuid

from fastapi import HTTPException

from backend.app.core.config import settings

MAX_FILES = 5
MAX_TOTAL_BYTES = 50 * 1024 * 1024
TYPES = {
    '.jpg': ('image', 'image/jpeg'), '.jpeg': ('image', 'image/jpeg'),
    '.png': ('image', 'image/png'), '.gif': ('image', 'image/gif'),
    '.webp': ('image', 'image/webp'), '.mp4': ('video', 'video/mp4'),
    '.webm': ('video', 'video/webm'), '.mov': ('video', 'video/quicktime'),
}


def valid_signature(suffix, head):
    if suffix in ('.jpg', '.jpeg'):
        return head.startswith(b'\xff\xd8\xff')
    if suffix == '.png':
        return head.startswith(b'\x89PNG\r\n\x1a\n')
    if suffix == '.gif':
        return head.startswith((b'GIF87a', b'GIF89a'))
    if suffix == '.webp':
        return head.startswith(b'RIFF') and head[8:12] == b'WEBP'
    if suffix in ('.mp4', '.mov'):
        return len(head) >= 12 and head[4:8] == b'ftyp'
    return suffix == '.webm' and head.startswith(b'\x1aE\xdf\xa3')


def remove_staged(files):
    for file in files:
        Path(file['absolute_path']).unlink(missing_ok=True)


async def stage_media(files):
    if len(files) > MAX_FILES:
        raise HTTPException(422, 'Tối đa 5 ảnh/video cho mỗi yêu cầu')
    staged, total = [], 0
    try:
        root = Path(settings.UPLOAD_DIR).resolve()
        root.mkdir(parents=True, exist_ok=True)
        for file in files:
            name = (file.filename or '').replace('\\', '/').rsplit('/', 1)[-1][:255]
            suffix = Path(name).suffix.lower()
            if suffix not in TYPES:
                raise HTTPException(422, 'Chỉ nhận JPG, PNG, GIF, WebP, MP4, WebM hoặc MOV')
            kind, mime = TYPES[suffix]
            head = await file.read(64)
            if not valid_signature(suffix, head) or file.content_type not in (mime, 'application/octet-stream'):
                raise HTTPException(422, 'Nội dung tệp không khớp định dạng ảnh/video')
            filename = uuid.uuid4().hex + suffix
            target = root / filename
            record = dict(file_path=filename, file_type=kind, file_name=name, file_size=0, absolute_path=str(target))
            staged.append(record)
            with target.open('xb') as output:
                chunk = head
                while chunk:
                    record['file_size'] += len(chunk)
                    total += len(chunk)
                    if record['file_size'] > settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024:
                        raise HTTPException(413, f'Mỗi tệp tối đa {settings.MAX_UPLOAD_SIZE_MB} MB')
                    if total > MAX_TOTAL_BYTES:
                        raise HTTPException(413, 'Tổng dung lượng tối đa 50 MB cho mỗi yêu cầu')
                    output.write(chunk)
                    chunk = await file.read(1024 * 1024)
        return staged
    except BaseException:
        remove_staged(staged)
        raise
    finally:
        for file in files:
            await file.close()
