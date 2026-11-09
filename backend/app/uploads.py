import hashlib
import shutil
import tempfile
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException
from PIL import Image, UnidentifiedImageError
from starlette.datastructures import UploadFile

MAX_FILE_SIZE = 10 * 1024 * 1024
MAX_FILES = 5
MAX_BODY_SIZE = 52 * 1024 * 1024
IMAGE_TYPES = {
    "JPEG": ("image/jpeg", {".jpg", ".jpeg"}),
    "PNG": ("image/png", {".png"}),
    "WEBP": ("image/webp", {".webp"}),
}


def validate_content(path: Path, filename: str) -> str:
    extension = Path(filename).suffix.lower()
    with path.open("rb") as stream:
        header = stream.read(8)
    if extension == ".pdf":
        # PDFs are opaque downloads, never rendered inline by this application.
        if not header.startswith(b"%PDF-"):
            raise HTTPException(422, "Файл PDF имеет неверный формат")
        return "application/pdf"
    try:
        with Image.open(path, formats=list(IMAGE_TYPES)) as image:
            if image.width * image.height > 25_000_000:
                raise HTTPException(
                    422, "Размер изображения не должен превышать 25 мегапикселей"
                )
            media_type, extensions = IMAGE_TYPES[image.format]
            if extension not in extensions:
                raise HTTPException(
                    422, "Расширение изображения не соответствует его содержимому"
                )
            image.verify()
        return media_type
    except (
        UnidentifiedImageError,
        OSError,
        ValueError,
        SyntaxError,
        Image.DecompressionBombError,
    ):
        raise HTTPException(
            422, "Прикрепите корректное изображение JPEG, PNG, WebP или PDF"
        ) from None


class StagedUploads:
    """Bounded disk staging; any failed submission removes all its temporary files."""

    def __init__(self, root: Path, files: list[UploadFile]):
        self.root = root
        self.files = files
        self.temporary = None
        self.items: list[dict] = []
        self.destination: Path | None = None

    def __enter__(self):
        if len(self.files) > MAX_FILES:
            raise HTTPException(422, "Можно прикрепить не более 5 файлов")
        self.root.mkdir(parents=True, exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(prefix="staging-", dir=self.root)
        try:
            for upload in self.files:
                filename = (upload.filename or "").replace("\\", "/").split("/")[-1]
                filename = "".join(
                    character for character in filename if character.isprintable()
                ).strip()
                if not filename or len(filename) > 255:
                    raise HTTPException(
                        422, "Имя файла должно содержать от 1 до 255 символов"
                    )
                path = Path(self.temporary.name) / str(uuid4())
                size = 0
                fingerprint = hashlib.sha256()
                with path.open("wb") as output:
                    while chunk := upload.file.read(64 * 1024):
                        size += len(chunk)
                        if size > MAX_FILE_SIZE:
                            raise HTTPException(
                                413, f"Файл «{filename}» превышает 10 МБ"
                            )
                        fingerprint.update(chunk)
                        output.write(chunk)
                if size == 0:
                    raise HTTPException(422, f"Файл «{filename}» пуст")
                media_type = validate_content(path, filename)
                self.items.append(
                    {
                        "filename": filename,
                        "media_type": media_type,
                        "size": size,
                        "sha256": fingerprint.hexdigest(),
                        "name": path.name,
                    }
                )
        except BaseException:
            self.temporary.cleanup()
            raise
        return self

    def publish(self):
        if self.items:
            self.destination = self.root / str(uuid4())
            Path(self.temporary.name).rename(self.destination)
        return self.destination

    def __exit__(self, exc_type, exc, traceback):
        if exc_type and self.destination:
            shutil.rmtree(self.destination, ignore_errors=True)
        if self.temporary:
            self.temporary.cleanup()
