"""Calendar ranges for daily diesel transactions in weekly reports."""

from datetime import timedelta
from dateutil.relativedelta import relativedelta


def diesel_periods(mode, week_start, previous_week=None):
    """Inclusive daily ranges, as of the selected week's Saturday.

    Year-to-date is anchored to the selected Sunday, matching the report year.
    At year end it is capped at December 31 to exclude the next year's fuel.
    """
    week_end = week_start + timedelta(days=6)
    if mode == "WoW":
        previous = ((previous_week, previous_week + timedelta(days=6))
                    if previous_week else None)
        return (week_start, week_end), previous
    if mode == "MoM":
        month_start = week_start.replace(day=1)
        month_end = month_start + relativedelta(months=1) - timedelta(days=1)
        current_end = min(week_end, month_end)
        prior_end = current_end - relativedelta(months=1)
        return ((month_start, current_end),
                (prior_end.replace(day=1), prior_end))
    if mode in {"YTD", "YoY"}:
        current = (week_start.replace(month=1, day=1),
                   min(week_end, week_start.replace(month=12, day=31)))
        comparison_end = current[1] - timedelta(weeks=52)
        previous = ((comparison_end.replace(month=1, day=1), comparison_end)
                    if mode == "YoY" else None)
        return current, previous
    raise ValueError(f"Unknown comparison mode: {mode}")
