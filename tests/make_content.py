"""Generate the binary payloads used by the Mininet experiments."""

from pathlib import Path
import os


ROOT = Path(__file__).resolve().parent.parent
CONTENT = ROOT / "content"
FILES = {
    "video1.bin": 20 * 1024 * 1024,
    "video2.bin": 100 * 1024 * 1024,
    "exp.bin": 5 * 1024 * 1024,
    "small.bin": 2 * 1024 * 1024,
}
CHUNK_SIZE = 1024 * 1024


def main():
    CONTENT.mkdir(exist_ok=True)
    for name, size in FILES.items():
        path = CONTENT / name
        with path.open("wb") as output:
            remaining = size
            while remaining:
                chunk_size = min(CHUNK_SIZE, remaining)
                output.write(os.urandom(chunk_size))
                remaining -= chunk_size
        print(f"{path.relative_to(ROOT)}: {size:,} bytes")


if __name__ == "__main__":
    main()
