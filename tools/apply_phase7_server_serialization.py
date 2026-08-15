from pathlib import Path

path = Path("python/origins_integration/phase7_server.py")
text = path.read_text(encoding="utf-8")

text = text.replace("import os\n", "import os\nimport threading\n", 1)
text = text.replace(
    "    runtime = Phase7Runtime.from_env()\n\n    class Handler",
    "    runtime = Phase7Runtime.from_env()\n    transition_lock = threading.Lock()\n\n    class Handler",
    1,
)
text = text.replace(
    '''            path = urlparse(self.path).path\n            try:\n                body = self._body()\n''',
    '''            path = urlparse(self.path).path\n            transition_lock.acquire()\n            try:\n                body = self._body()\n''',
    1,
)
text = text.replace(
    '''            ) as exc:\n                self._conflict(exc)\n\n        def do_PUT''',
    '''            ) as exc:\n                self._conflict(exc)\n            finally:\n                transition_lock.release()\n\n        def do_PUT''',
    1,
)

if text.count("transition_lock.acquire()") != 1 or text.count("transition_lock.release()") != 1:
    raise SystemExit("Phase 7 POST serialization patch did not apply exactly once")
path.write_text(text, encoding="utf-8")
