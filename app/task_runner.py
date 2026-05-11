import threading
from datetime import datetime


task_status: dict = {"running": False, "message": "Idle", "progress": []}
activity_log: list[dict] = []
_lock = threading.Lock()
_MAX_PROGRESS = 500
_MAX_ACTIVITY = 1000


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def append_activity(message: str, level: str = "info", source: str = "task") -> None:
    entry = {
        "ts": _now_iso(),
        "level": level,
        "source": source,
        "message": str(message),
    }
    with _lock:
        activity_log.append(entry)
        del activity_log[:-_MAX_ACTIVITY]


def get_activity_log() -> dict:
    with _lock:
        return {
            "running": bool(task_status.get("running")),
            "message": task_status.get("message", "Idle"),
            "entries": list(activity_log),
        }


def get_task_status() -> dict:
    with _lock:
        return {
            "running": bool(task_status.get("running")),
            "message": task_status.get("message", "Idle"),
            "progress": list(task_status.get("progress") or []),
            "result": task_status.get("result"),
        }


def clear_activity_log() -> None:
    with _lock:
        activity_log.clear()


def run_background(fn, *args) -> bool:
    """Start a background task. Returns True if started, False if already running."""
    with _lock:
        if task_status["running"]:
            return False
        task_status["running"] = True
        task_status["progress"] = []
        task_status["result"] = None
    append_activity("Started background task", "info", "task")

    def runner():
        def progress(msg):
            with _lock:
                task_status["message"] = msg
                task_status["progress"].append(msg)
                del task_status["progress"][:-_MAX_PROGRESS]
            append_activity(msg, "info", "progress")

        try:
            result = fn(*args, progress_callback=progress)
            with _lock:
                task_status["result"] = result
                task_status["message"] = "Done"
            append_activity("Background task finished", "ok", "task")
        except Exception as exc:
            with _lock:
                task_status["result"] = {"success": False, "error": str(exc)}
                task_status["message"] = f"Error: {exc}"
            append_activity(f"Error: {exc}", "error", "task")
        finally:
            with _lock:
                task_status["running"] = False

    threading.Thread(target=runner, daemon=True).start()
    return True
