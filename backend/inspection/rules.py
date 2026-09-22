PASS_VERDICT = "合格"
PASS_NOTE = "光强与方位均在限内"
FAIL_VERDICT = "不合格"

BEARING_TOLERANCE_DEG = 2


def judge(measured_cd: float, required_cd: float, bearing_error_deg: float) -> tuple[str, str]:
    if measured_cd < required_cd:
        return FAIL_VERDICT, "光强不足"
    if abs(bearing_error_deg) > BEARING_TOLERANCE_DEG:
        return FAIL_VERDICT, "方位偏差过大"
    return PASS_VERDICT, PASS_NOTE
