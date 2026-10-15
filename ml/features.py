"""Feature extraction shared by training and inference.

The feature vector captures both current state and gameplay history.
The history features are the key differentiator between this ML approach
and simple reactive rules.
"""

FEATURE_NAMES = [
    "gap_size",
    "bird_y_norm",
    "bird_vel_norm",
    "consecutive_successes",
    "consecutive_failures",
    "success_rate_last3",
    "success_rate_last5",
    "success_rate_last10",
    "trend_success_rate",     # last3 - last5 (captures change)
    "pipes_since_start_norm",
]


def extract_features(record: dict, history: list = None) -> list:
    """
    record: outcome dict from game.logger (must contain gap_size, bird_y_at_pass,
            bird_vel_at_pass, consecutive_successes_before, consecutive_failures_before,
            success_rate_last3, success_rate_last5).
    history: optional full history of success (1/0) in this episode, oldest first.
             Used to compute longer-window features not in the record.
    """
    history = history or []

    gap = float(record.get("gap_size", 165))
    bird_y = float(record.get("bird_y_at_pass", 320))
    bird_vel = float(record.get("bird_vel_at_pass", 0))
    cons_succ = float(record.get("consecutive_successes_before", 0))
    cons_fail = float(record.get("consecutive_failures_before", 0))
    rate3 = float(record.get("success_rate_last3", 0))
    rate5 = float(record.get("success_rate_last5", 0))

    last10 = history[-10:]
    rate10 = sum(last10) / len(last10) if last10 else 0.0
    trend = rate3 - rate5

    pipes_so_far = float(record.get("total_pipes_passed", 0))

    return [
        gap / 240.0,
        bird_y / 640.0,
        max(-1.0, min(1.0, bird_vel / 10.0)),
        min(cons_succ / 10.0, 1.0),
        min(cons_fail / 10.0, 1.0),
        rate3,
        rate5,
        rate10,
        trend,
        min(pipes_so_far / 20.0, 1.0),
    ]
