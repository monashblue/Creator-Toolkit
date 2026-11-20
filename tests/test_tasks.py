import threading
import unittest

from core.tasks import CancelToken, OperationCancelled, TaskContext


class TaskTests(unittest.TestCase):
    def test_token_cancellation(self) -> None:
        token = CancelToken()
        token.raise_if_cancelled()
        token.cancel()
        self.assertTrue(token.cancelled)
        with self.assertRaises(OperationCancelled):
            token.raise_if_cancelled()

    def test_context_clamps_progress_and_forwards_items(self) -> None:
        seen, items = [], []
        ctx = TaskContext(on_progress=lambda p, m: seen.append((p, m)), on_item=items.append)
        ctx.report(-5, "a")
        ctx.report(42.9, "b")
        ctx.report(250, "c")
        ctx.emit_item("x")
        self.assertEqual(seen, [(0, "a"), (42, "b"), (100, "c")])
        self.assertEqual(items, ["x"])

    def test_context_without_callbacks_is_safe(self) -> None:
        ctx = TaskContext()
        ctx.report(10)
        ctx.emit_item(1)
        ctx.check_cancel()

    def test_cancel_from_another_thread_stops_a_worker_loop(self) -> None:
        ctx = TaskContext()
        started, done = threading.Event(), threading.Event()
        iterations = []

        def work() -> None:
            try:
                while True:
                    ctx.check_cancel()
                    iterations.append(1)
                    started.set()
                    threading.Event().wait(0.005)
            except OperationCancelled:
                done.set()

        thread = threading.Thread(target=work)
        thread.start()
        self.assertTrue(started.wait(2))
        ctx.token.cancel()
        self.assertTrue(done.wait(2))
        thread.join(2)
        self.assertFalse(thread.is_alive())


if __name__ == "__main__":
    unittest.main()
