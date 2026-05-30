import os
from pathlib import Path
from types import SimpleNamespace

from app.api.v1.endpoints.trainers import ALLOWED_DOC_EXTENSIONS
from app.core.upload_security import scan_bytes_for_malware, upload_path, validate_document_upload
from app.services.s3_storage import object_exists, trainer_object_key, upload_private_object


_CONTENT_TYPES = {
    ".pdf": "application/pdf",
    ".doc": "application/msword",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


def main() -> None:
    source_dir = Path(upload_path("trainers"))
    if not source_dir.exists():
        print(f"No trainer upload directory found at {source_dir}")
        return

    migrated = 0
    skipped = 0
    for path in sorted(source_dir.iterdir()):
        if not path.is_file():
            continue
        ext = path.suffix.lower()
        if ext not in ALLOWED_DOC_EXTENSIONS:
            print(f"Skipping unsupported file: {path.name}")
            skipped += 1
            continue

        data = path.read_bytes()
        upload_file = SimpleNamespace(filename=path.name, content_type=_CONTENT_TYPES.get(ext))
        validate_document_upload(upload_file, data, ALLOWED_DOC_EXTENSIONS)
        scan_bytes_for_malware(data, require_scanner=True)

        key = trainer_object_key(path.name)
        if object_exists(key):
            print(f"Already exists in S3: {key}")
            skipped += 1
            continue

        upload_private_object(
            key=key,
            data=data,
            content_type=_CONTENT_TYPES.get(ext, "application/octet-stream"),
            original_filename=os.path.basename(path.name),
        )
        print(f"Migrated: {path.name} -> {key}")
        migrated += 1

    print(f"Done. Migrated: {migrated}. Skipped: {skipped}.")


if __name__ == "__main__":
    main()
