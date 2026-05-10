import threading


task_status: dict = {"running": False, "message": "Idle", "progress": []}
_lock = threading.Lock()


def run_background(fn, *args) -> bool:
    """Start a background task. Returns True if started, False if already running."""
    with _lock:
        if task_status["running"]:
            return False
        task_status["running"] = True
        task_status["progress"] = []

    def runner():
        def progress(msg):
            task_status["message"] = msg
            task_status["progress"].append(msg)

        try:
            result = fn(*args, progress_callback=progress)
            task_status["result"] = result
            task_status["message"] = "Done"
        except Exception as exc:
            task_status["result"] = {"success": False, "error": str(exc)}
            task_status["message"] = f"Error: {exc}"
        finally:
            task_status["running"] = False

    threading.Thread(target=runner, daemon=True).start()
    return True
