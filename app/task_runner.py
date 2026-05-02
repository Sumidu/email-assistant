import threading


task_status: dict = {"running": False, "message": "Idle", "progress": []}


def run_background(fn, *args) -> None:
    def runner():
        task_status["running"] = True
        task_status["progress"] = []

        def progress(msg):
            print(f"[BG] {msg}")
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
