"""Wall-clock bookstore agenda. No inference calls or per-browser clock authority."""
from datetime import datetime
from zoneinfo import ZoneInfo

ZONE = ZoneInfo("Asia/Shanghai")
SCHEDULE = [
    (540, 570, "opening", "开门、清洁、检查咖啡机", ["door", "counter", "coffee"]),
    (570, 660, "shelves", "整理书架、查看新书", ["shelf-a", "shelf-b", "shelf-c"]),
    (660, 750, "reading", "阅读、经营店铺", ["chair", "counter"]),
    (750, 900, "coffee", "制作咖啡、招待顾客", ["coffee", "counter"]),
    (900, 1020, "books", "整理书籍、阅读", ["shelf-b", "chair", "shelf-c"]),
    (1020, 1080, "closing", "清理店铺、关门", ["shelf-a", "counter", "door"]),
]


def agenda(at=None):
    current = (at or datetime.now(ZONE)).astimezone(ZONE)
    minute = current.hour * 60 + current.minute
    slot = next((s for s in SCHEDULE if s[0] <= minute < s[1]), None)
    opened = 540 <= minute < 1080
    seconds = current.hour * 3600 + current.minute * 60 + current.second
    targets = slot[4] if slot else ["chair"]
    return {
        "now": current.isoformat(), "timezone": "Asia/Shanghai",
        "open": opened, "lights_on": opened,
        "phase": slot[2] if slot else "closed",
        "activity": slot[3] if slot else "闭店休息",
        "target": targets[(seconds // 45) % len(targets)],
        "step": f"{current.date()}:{seconds // 45}",
        "schedule": [{"start": f"{s[0]//60:02}:{s[0]%60:02}",
                      "end": f"{s[1]//60:02}:{s[1]%60:02}", "activity": s[3]}
                     for s in SCHEDULE],
    }
