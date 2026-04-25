from proglog import ProgressBarLogger
class GUIProgressBarLogger(ProgressBarLogger):
    def __init__(self, progress_callback, start_offset=0.0, scale=1.0):
        super().__init__()
        self.progress_callback = progress_callback
        self.start_offset = start_offset
        self.scale = scale
    def bars_callback(self, bar, attr, value, old_value=None):
        if attr == 'index':
            total = self.bars[bar]['total']
            if total > 0:
                final = self.start_offset + ((value / total) * 100 * self.scale)
                self.progress_callback(final)
