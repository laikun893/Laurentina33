"""xxjm 技能辅助脚本：阿拉伯数字 → 中文数字。

用法：
    python scripts/num2cn.py 12345
    python scripts/num2cn.py 3.14 -105 100000000
不带参数时运行内置示例。

注意：这只是把数字字符换成中文的“玩具加密”，不具备任何安全性。
"""

import sys

DIGITS = "零一二三四五六七八九"
BIG_DIGITS = "零壹贰叁肆伍陆柒捌玖"
UNITS = ["", "十", "百", "千"]
BIG_UNITS = ["", "拾", "佰", "仟"]
SECTIONS = ["", "万", "亿", "兆"]


def _section_to_cn(num, digits, units, leading_zero=False):
    """把 0-9999 的一节数字转换为中文数字。"""
    if num == 0:
        return "零" if leading_zero else ""
    out, zero_pending = "", False
    for i in range(3, -1, -1):
        d = (num // (10 ** i)) % 10
        if d == 0:
            if out:
                zero_pending = True
        else:
            if zero_pending:
                out += "零"
                zero_pending = False
            out += digits[d] + units[i]
    return out


def int_to_cn(n, big=False):
    """整数转中文数字；big=True 时使用大写（壹贰叁…）。"""
    digits = BIG_DIGITS if big else DIGITS
    units = BIG_UNITS if big else UNITS
    if n == 0:
        return "零"
    sign = "负" if n < 0 else ""
    n = abs(n)
    parts, idx, leading_zero = [], 0, False
    while n > 0:
        section = n % 10000
        if section == 0:
            leading_zero = True
        else:
            text = _section_to_cn(section, digits, units, leading_zero)
            parts.insert(0, text + SECTIONS[idx])
            leading_zero = True
        n //= 10000
        idx += 1
    return sign + "".join(parts)


def num_to_cn(value, big=False, strict_shi=False):
    """把阿拉伯数字（含小数、负数）转换为中文数字。

    :param big: 是否使用大写数字（壹贰叁…）
    :param strict_shi: True 时保留“一十五”的写法，默认输出“十五”
    """
    digits = BIG_DIGITS if big else DIGITS
    text = str(value).strip()
    sign = ""
    if text.startswith("-"):
        sign, text = "负", text[1:]

    int_part, _, dec_part = text.partition(".")
    int_cn = int_to_cn(int(int_part or 0), big=big)

    result = int_cn
    dec_cn = "".join(digits[int(c)] for c in dec_part if c.isdigit())
    if dec_cn:
        point = "点"
        result = (int_cn if int_cn != "零" else "") + point + dec_cn

    if not strict_shi and result.startswith("一十"):
        result = result[1:]
    return sign + result


def main(argv):
    values = argv[1:]
    if not values:
        values = ["0", "10", "15", "105", "1200", "10001", "100000000", "-3.14"]
    for value in values:
        try:
            print(f"{value} -> {num_to_cn(value)}")
        except (ValueError, TypeError):
            print(f"{value} -> 错误：不是合法的数字")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main(sys.argv)
