import hashlib
import io
import json
import re
import zipfile
from pathlib import Path

import numpy as np

from .limits import MAX_CHECKPOINT_BYTES

SAFE_NAME = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,79}$")


def safe_path(root: Path, name: str, suffix="") -> Path:
    if not isinstance(name, str) or not SAFE_NAME.fullmatch(name):
        raise ValueError("Invalid artifact identifier")
    path = (root / (name + suffix)).resolve()
    if path.parent != root.resolve() or path.is_symlink():
        raise ValueError("Artifact escapes storage")
    return path


def digest(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as file:
        for block in iter(lambda: file.read(1 << 20), b""):
            value.update(block)
    return value.hexdigest()


def read_json(path, limit=100_000):
    if path.stat().st_size > limit:
        raise ValueError("JSON size limit")
    def reject(value):
        raise ValueError("Non-finite JSON")
    return json.loads(path.read_text(encoding="utf-8-sig"), parse_constant=reject)


def atomic_json(path, value):
    content = json.dumps(value, indent=2, allow_nan=False)
    temp = path.with_suffix(path.suffix + ".part")
    temp.write_text(content, encoding="utf-8")
    temp.replace(path)


def validate_npz(path, specs, expected_hash, limit=MAX_CHECKPOINT_BYTES):
    path = Path(path)
    if path.suffix != ".npz" or not path.is_file() or not 0 < path.stat().st_size <= limit:
        raise ValueError("NPZ file limit/format")
    if not isinstance(expected_hash, str) or digest(path) != expected_hash:
        raise ValueError("NPZ hash mismatch")
    try:
        with zipfile.ZipFile(path) as archive:
            members = archive.infolist()
            if len(members) != len(specs) or {m.filename for m in members} != {k + ".npy" for k in specs}:
                raise ValueError("Unexpected tensor names")
            total = 0
            for member in members:
                total += member.file_size
                if total > limit or member.file_size / max(1, member.compress_size) > 1000:
                    raise ValueError("NPZ expansion limit")
                if member.flag_bits & 1 or member.external_attr >> 16 & 0o170000 == 0o120000:
                    raise ValueError("Unsafe NPZ member")
                # Read only bounded header before NumPy can allocate based on attacker-controlled shapes.
                with archive.open(member) as stream:
                    version = np.lib.format.read_magic(stream)
                    if version not in {(1, 0), (2, 0)}:
                        raise ValueError("NPY version")
                    shape, order, dtype = (np.lib.format.read_array_header_1_0 if version == (1, 0) else np.lib.format.read_array_header_2_0)(stream, max_header_size=4096)
                    name = member.filename[:-4]
                    wanted_shape, wanted_dtype = specs[name]
                    if tuple(shape) != tuple(wanted_shape) or dtype != np.dtype(wanted_dtype) or dtype.hasobject or order:
                        raise ValueError("Tensor shape/dtype")
                    if int(np.prod(shape)) * dtype.itemsize + stream.tell() != member.file_size:
                        raise ValueError("Truncated tensor")
        with np.load(path, allow_pickle=False) as arrays:
            result = {key: arrays[key].copy() for key in specs}
        if any(not np.all(np.isfinite(value)) for value in result.values()):
            raise ValueError("Non-finite tensor")
        return result
    except (OSError, zipfile.BadZipFile, EOFError, KeyError) as error:
        raise ValueError("Corrupt NPZ") from error


def graph_fingerprint(ids, pre, post, count, sign):
    h = hashlib.sha256()
    for array in (ids, pre, post, count, sign):
        h.update(array.tobytes())
    return h.hexdigest()

