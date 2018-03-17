from datetime import datetime, timezone

def utctimestamp(utcdt: datetime):
    return utcdt.replace(tzinfo=timezone.utc).timestamp()
