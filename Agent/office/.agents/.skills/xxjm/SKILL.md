---
name: xxjm
description: 小小加密工具，把阿拉伯数字转换成中文数字（如 12345 → 一万二千三百四十五），支持整数、小数、负数与超大数；当用户需要把数字写成中文读法、做简单的数字“加密”转换或票据金额阅读时使用。
---

# xxjm — 小小加密工具（阿拉伯数字 → 中文数字）

把阿拉伯数字（`0-9`）转换为中文数字字符（`零一二三四五六七八九`），
是一种最朴素的“加密”玩法：转换结果只有懂规则的人才能一眼读懂。

## 功能范围

- 正整数、负整数、零
- 小数（逐位读作“点”后的数字）
- 大数（万、亿、兆级），自动处理零的省略规则
- 可选输出风格：**小写**（一二三…）或 **大写**（壹贰叁…，用于票据金额）

## 转换规则

1. 数字逐位映射：`0→零 1→一 2→二 3→三 4→四 5→五 6→六 7→七 8→八 9→九`
2. 按四位一节分组，节内单位：`个、十、百、千`；节间单位：`万、亿、兆`
3. **零的规则**：
   - 连续的零只读一个“零”；
   - 节末的零不读（如 `1200` → 一千二百）；
   - 节首的零不读，但若整节为零则整节省略（如 `100000000` → 一亿）。
4. **十的口语规则**：`10-19` 在最高位时读作“十…”，如 `15` → 十五；
   若需要严格格式（一十五），可关闭该规则。
5. 负数前缀“负”；小数部分逐位读，如 `3.14` → 三点一四。

## 执行步骤

1. 明确用户输入的数字，以及期望的风格（小写/大写）和是否保留“一十”。
2. 直接按上述规则转换；数字较长时按四位一节从高位到低位逐节处理。
3. 转换结果需自检：
   - 不应出现“零”连续重复；
   - 不应出现“零”结尾（如“二百零”应为“二百”）；
   - 万、亿等节单位后若整节为零，不应输出多余的“零万”“零亿”。
4. 若需要批量转换，或希望得到可复用的脚本，请在本技能目录创建
   `scripts/num2cn.py`（见下方参考实现），然后用 `RunCil` 运行验证。

## 参考实现（可写入 scripts/num2cn.py）

```python
DIGITS = "零一二三四五六七八九"
UNITS = ["", "十", "百", "千"]
SECTIONS = ["", "万", "亿", "兆"]


def _section_to_cn(num: int, leading_zero: bool = False) -> str:
    """转换 0-9999 的一节数字。"""
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
            out += DIGITS[d] + UNITS[i]
    return out


def int_to_cn(n: int) -> str:
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
            text = _section_to_cn(section, leading_zero)
            parts.insert(0, text + SECTIONS[idx])
            leading_zero = True
        n //= 10000
        idx += 1
    return sign + "".join(parts)


def num_to_cn(value, strict_shi: bool = False) -> str:
    text = str(value).strip()
    sign = ""
    if text.startswith("-"):
        sign, text = "负", text[1:]
    int_part, _, dec_part = text.partition(".")
    int_cn = int_to_cn(int(int_part or 0))
    result = int_cn
    if dec_part:
        dec_cn = "".join(DIGITS[int(c)] for c in dec_part if c.isdigit())
        result = (int_cn if int_cn != "零" else "") + "点" + dec_cn
    if not strict_shi and result.startswith("一十"):
        result = result[1:]
    return sign + result


if __name__ == "__main__":
    for demo in ["0", "10", "15", "105", "1200", "10001", "100000000", "-3.14"]:
        print(f"{demo} -> {num_to_cn(demo)}")
```

## 注意事项

- 本技能只是把数字字符替换成中文的“玩具加密”，**不具备任何安全性**，
  切勿用于真实的数据加密或密码保护。
- 遇到用户要求“严格格式”（如金额大写“壹拾伍元整”）时，需要额外的大写映射表：
  `0→零 1→壹 2→贰 3→叁 4→肆 5→伍 6→陆 7→柒 8→捌 9→玖`，以及 `十→拾 百→佰 千→仟`。
- 输入非数字内容时应礼貌提示，不要臆造转换结果。
