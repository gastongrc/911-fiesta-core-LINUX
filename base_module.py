class BaseModule:
    name = "Module"
    def __init__(self):
        self.card = None
    def process(self, block, sr):
        """Implementar en cada analizador. block: (N, C) float32"""
        pass
