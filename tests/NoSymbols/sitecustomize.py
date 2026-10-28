"""Test-only Python audit hook: record and refuse debug-symbol dependencies.

The release test adds this to the extracted embedded interpreter, never the ZIP.
"""
import json
import os
import sys
import time

_log_directory = os.path.join(os.getcwd(), "BepInEx", "cache", "compatibility")
os.makedirs(_log_directory, exist_ok=True)
_log_path = os.path.join(_log_directory, "no-symbols-audit.jsonl")


def _record(kind, event=None, value=None):
    with open(_log_path, "a", encoding="utf-8") as stream:
        stream.write(json.dumps({"kind": kind, "event": event, "value": value,
                                 "pid": os.getpid(), "time": time.time()}) + "\n")


def _path(value):
    try:
        return os.fsdecode(os.fspath(value)).replace("\\", "/").lower()
    except TypeError:
        return ""


def _audit(event, arguments):
    value = None
    if event == "open" and arguments:
        path = _path(arguments[0])
        if path.endswith(".pdb") or path.rsplit("/", 1)[-1].startswith("pdbsymbols."):
            value = path
    elif event == "ctypes.dlopen" and arguments:
        path = _path(arguments[0])
        if path.rsplit("/", 1)[-1].startswith("msdia"):
            value = path
    elif event == "subprocess.Popen" and arguments:
        command = str(arguments[0] or arguments[1]).lower()
        if "pdbsymbols." in command:
            value = command
    elif event in ("socket.getaddrinfo", "http.client.connect") and arguments:
        host = str(arguments[1] if event == "http.client.connect" else arguments[0]).lower()
        if "symbolserver" in host or "msdl.microsoft.com" in host:
            value = host
    if value is not None:
        _record("blocked", event, value)
        raise PermissionError("The release test forbids debug-symbol access: " + value)


sys.addaudithook(_audit)
_record("installed")
