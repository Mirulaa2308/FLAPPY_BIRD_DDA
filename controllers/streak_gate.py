"""Shared streak gate for the Reactive and ML Adaptive controllers.

Counts consecutive failures and consecutive successes. It only "opens" when one
streak reaches its threshold, so a single loss or single success never changes
the gap. A success resets the failure streak and a failure resets the success
streak. Both counters reset to 0 after the gate opens.
"""


class StreakGate:
    EASIER = 1    # failure streak reached -> increase gap
    HARDER = -1   # success streak reached -> decrease gap
    HOLD = 0      # no change allowed

    def __init__(self, loss_threshold=5, success_threshold=5):
        self.loss_threshold = max(1, int(loss_threshold))
        self.success_threshold = max(1, int(success_threshold))
        self.consecutive_losses = 0
        self.consecutive_successes = 0

    def update(self, success):
        """Record one outcome. Returns EASIER, HARDER or HOLD."""
        if success:
            self.consecutive_successes += 1
            self.consecutive_losses = 0          # opposite event resets the streak
        else:
            self.consecutive_losses += 1
            self.consecutive_successes = 0       # opposite event resets the streak

        if self.consecutive_losses >= self.loss_threshold:
            self.reset()
            return self.EASIER
        if self.consecutive_successes >= self.success_threshold:
            self.reset()
            return self.HARDER
        return self.HOLD

    def reset(self):
        self.consecutive_losses = 0
        self.consecutive_successes = 0
