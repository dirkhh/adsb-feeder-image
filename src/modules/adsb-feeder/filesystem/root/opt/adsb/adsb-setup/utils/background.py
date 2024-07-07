from threading import Timer


class Background:
    def __init__(self, delay, function):
        self._delay = delay
        self._function = function
        self._running = False

        self._timer = None
        self.schedule()

    def schedule(self):
        if not self._running:
            self._running = True
            self._timer = Timer(self._delay, self._run)
            self._timer.start()

    def _run(self):
        # immediately schedule the next instance
        self._running = False
        self.schedule()
        self._function()

    def cancel(self):
        self._timer.cancel()
        self._running = False
