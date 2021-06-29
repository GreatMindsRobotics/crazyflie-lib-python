class MovingAverage:
    def __init__(self, size, fill=0.0):
        self._elements = [fill] * size
        self._sum = fill * size
        self.average = fill

    def update(self, value):
        self._sum -= self._elements[0]
        self._sum += value
        self._elements.pop(0)
        self._elements.append(value)

    def getAverage(self):
        return float(self._sum) / len(self._elements)