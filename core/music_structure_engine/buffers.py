# buffers.py — Ring buffers for temporal memory
import numpy as np


class RingBuffer:
    """Fixed-capacity circular buffer storing float scalars."""

    __slots__ = ("_buf", "_cap", "_wr", "_len")

    def __init__(self, capacity: int):
        self._cap = max(1, int(capacity))
        self._buf = np.zeros(self._cap, dtype=np.float64)
        self._wr = 0
        self._len = 0

    def push(self, value: float):
        self._buf[self._wr] = value
        self._wr = (self._wr + 1) % self._cap
        if self._len < self._cap:
            self._len += 1

    def push_array(self, values):
        arr = np.asarray(values, dtype=np.float64).ravel()
        n = arr.size
        if n == 0:
            return
        if n >= self._cap:
            self._buf[:] = arr[-self._cap:]
            self._wr = 0
            self._len = self._cap
            return
        end = self._wr + n
        if end <= self._cap:
            self._buf[self._wr:end] = arr
        else:
            k = self._cap - self._wr
            self._buf[self._wr:] = arr[:k]
            self._buf[:end - self._cap] = arr[k:]
        self._wr = end % self._cap
        self._len = min(self._cap, self._len + n)

    def get_last(self, n: int) -> np.ndarray:
        n = min(n, self._len)
        if n == 0:
            return np.empty(0, dtype=np.float64)
        start = (self._wr - n) % self._cap
        if start + n <= self._cap:
            return self._buf[start:start + n].copy()
        k = self._cap - start
        return np.concatenate((self._buf[start:], self._buf[:n - k]))

    def get_all(self) -> np.ndarray:
        return self.get_last(self._len)

    @property
    def length(self) -> int:
        return self._len

    @property
    def capacity(self) -> int:
        return self._cap

    def mean(self, n: int = 0) -> float:
        data = self.get_last(n) if n > 0 else self.get_all()
        return float(np.mean(data)) if data.size > 0 else 0.0

    def clear(self):
        self._buf[:] = 0.0
        self._wr = 0
        self._len = 0


class RingBuffer2D:
    """Fixed-capacity circular buffer storing float vectors (rows)."""

    __slots__ = ("_buf", "_cap", "_cols", "_wr", "_len")

    def __init__(self, capacity: int, cols: int):
        self._cap = max(1, int(capacity))
        self._cols = int(cols)
        self._buf = np.zeros((self._cap, self._cols), dtype=np.float64)
        self._wr = 0
        self._len = 0

    def push(self, row):
        self._buf[self._wr, :] = row
        self._wr = (self._wr + 1) % self._cap
        if self._len < self._cap:
            self._len += 1

    def get_last(self, n: int) -> np.ndarray:
        n = min(n, self._len)
        if n == 0:
            return np.empty((0, self._cols), dtype=np.float64)
        start = (self._wr - n) % self._cap
        if start + n <= self._cap:
            return self._buf[start:start + n].copy()
        k = self._cap - start
        return np.vstack((self._buf[start:], self._buf[:n - k]))

    def get_all(self) -> np.ndarray:
        return self.get_last(self._len)

    @property
    def length(self) -> int:
        return self._len

    def clear(self):
        self._buf[:] = 0.0
        self._wr = 0
        self._len = 0
