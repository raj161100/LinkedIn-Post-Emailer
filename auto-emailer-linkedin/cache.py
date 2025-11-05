
import hashlib
import json
import os
from typing import Iterable

class SeenCache:
    def __init__(self, path: str):
        self.path = path
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self._fp = open(self.path, "a+", encoding="utf-8")
        self._seen = set()
        self._fp.seek(0)
        for line in self._fp:
            try:
                obj = json.loads(line)
                self._seen.add(obj["hash"])
            except Exception:
                pass

    def _hash(self, value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    def has(self, value: str) -> bool:
        return self._hash(value) in self._seen

    def add_all(self, values: Iterable[str]):
        for v in values:
            h = self._hash(v)
            if h not in self._seen:
                self._seen.add(h)
                self._fp.write(json.dumps({"hash": h, "value": v}) + "\n")
                self._fp.flush()

    def close(self):
        try:
            self._fp.close()
        except Exception:
            pass
