from datetime import date, timedelta

def week_monday(d: date) -> date:
    # Monday = 0 ... Sunday = 6
    return d - timedelta(days=d.weekday())

def next_monday(d: date) -> date:
    return week_monday(d) + timedelta(days=7)
