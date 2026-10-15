import csv
import os
from game.config import LOG_DIR


class GameLogger:
    FIELDS = [
        "session_id", "episode", "pipe_index",
        "gap_size", "gap_center",
        "bird_y_at_pass", "bird_vel_at_pass",
        "time_since_last_pass",
        "success",
        "consecutive_successes_before",
        "consecutive_failures_before",
        "success_rate_last3",
        "success_rate_last5",
        "survival_time",
        "total_pipes_passed",
        "controller",
    ]

    def __init__(self, session_id, controller_name, log_dir=LOG_DIR):
        os.makedirs(log_dir, exist_ok=True)
        self.session_id = session_id
        self.controller_name = controller_name
        self.path = os.path.join(
            log_dir, f"session_{session_id}_{controller_name}.csv"
        )
        with open(self.path, "w", newline="") as f:
            csv.DictWriter(f, fieldnames=self.FIELDS).writeheader()

    def log(self, record: dict):
        row = {k: record.get(k, "") for k in self.FIELDS}
        row["session_id"] = self.session_id
        row["controller"] = self.controller_name
        with open(self.path, "a", newline="") as f:
            csv.DictWriter(f, fieldnames=self.FIELDS).writerow(row)

    def path(self):
        return self.path