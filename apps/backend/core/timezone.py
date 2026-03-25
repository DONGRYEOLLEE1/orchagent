from datetime import datetime

import pytz

KST = pytz.timezone("Asia/Seoul")


def now_kst() -> datetime:
    return datetime.now(KST)


def iso_now_kst() -> str:
    return now_kst().isoformat()
