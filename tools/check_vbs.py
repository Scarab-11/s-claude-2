"""src 配下の .vbs を静的に検査する。

VBScript は実行するまで誤りが分からず、Jw_cad から呼ぶと
エラー表示が一瞬で閉じるコンソールにしか出ない。編集の事故を
ビルドの時点で捕まえるため、次の 3 点を調べる。

  1. Sub / Function / If / For / Do / Select の対応
  2. 呼んでいるのに定義が無い手続き（Option Explicit ではエラー 500）
  3. 同じ名前の手続きの二重定義

2 は実際に起きた事故で、まとまり読み取りの関数を差し替えたときに
後続の関数 5 個をまとめて消してしまい、Jw_cad 側が「未実行」に
なった。
"""
import re
import sys
from pathlib import Path

# VBScript の組み込み。呼び出しと区別がつかないので除外する。
BUILTIN = set(
    """left right mid len trim ltrim rtrim lcase ucase split join replace instr instrrev
    asc ascw chr chrw cstr cint clng cdbl cbool cbyte ccur cdate csng
    isnumeric isempty isnull isarray isobject isdate ubound lbound array erase
    msgbox inputbox err wscript createobject getobject nothing typename vartype
    abs int fix sgn sqr exp log hex oct space string strcomp strreverse
    now date time timer dateadd datediff datepart dateserial datevalue
    year month day hour minute second weekday monthname formatnumber formatcurrency
    formatdatetime formatpercent round rnd randomize eval execute executeglobal
    getref filter rgb loadpicture scriptengine
    redim preserve set call exit then else elseif end if for each next
    do while loop until select case function sub dim const option explicit class
    public private property get let me new not and or xor mod is to step
    wend on error resume goto clear number description source raise quit
    arguments named unnamed exists item count scriptfullname scriptname echo sleep
    true false empty null""".split()
)

OPENERS = (
    (re.compile(r"^(?:public\s+|private\s+)?sub\s+\w", re.I), "Sub", "end sub"),
    (re.compile(r"^(?:public\s+|private\s+)?function\s+\w", re.I), "Function", "end function"),
    (re.compile(r"^class\s+\w", re.I), "Class", "end class"),
    (re.compile(r"^select\s+case\b", re.I), "Select", "end select"),
    (re.compile(r"^do\b", re.I), "Do", "loop"),
    (re.compile(r"^for\b", re.I), "For", "next"),
)
IF_OPEN = re.compile(r"^if\b.*\bthen\s*$", re.I)
CLOSERS = {
    "end sub": "Sub",
    "end function": "Function",
    "end class": "Class",
    "end select": "Select",
    "end if": "If",
    "loop": "Do",
    "next": "For",
}


def join_continuations(text):
    """行継続（末尾の _ ）をつなぎ、元の行番号を保つ。"""
    out, buf, start = [], "", None
    for i, line in enumerate(text.split("\n"), 1):
        if start is None:
            start = i
        s = line.rstrip()
        # 継続とみなすのは「空白 + _ 」で終わる行だけ。
        # it.ch_ のように識別子の一部が _ で終わる場合は継続ではない。
        if re.search(r"\s_$", s):
            buf += s[:-1] + " "
            continue
        out.append((start, buf + s))
        buf, start = "", None
    if buf:
        out.append((start, buf))
    return out


def strip_noise(line):
    """文字列リテラルとコメントを取り除く。"""
    line = re.sub(r'"(?:[^"]|"")*"', '""', line)
    return re.sub(r"'.*$", "", line)


def check(path):
    text = path.read_text(encoding="utf-8")
    lines = join_continuations(text)
    problems = []

    # --- 1. ブロックの対応 ---
    stack = []
    for ln, raw in lines:
        t = strip_noise(raw).strip()
        if not t:
            continue
        low = t.lower()
        closer = CLOSERS.get(low.split("  ")[0]) or CLOSERS.get(low)
        if closer is None:
            for word in ("loop", "next"):
                if low == word or low.startswith(word + " "):
                    closer = CLOSERS[word]
                    break
        if closer:
            if not stack:
                problems.append(f"行{ln}: 対応する開始が無い終端 「{t}」")
            elif stack[-1][0] != closer:
                problems.append(
                    f"行{ln}: 「{t}」が 行{stack[-1][1]} の {stack[-1][0]} と対応していない"
                )
                stack.pop()
            else:
                stack.pop()
            continue
        matched = False
        for pat, kind, _ in OPENERS:
            if pat.match(low):
                stack.append((kind, ln))
                matched = True
                break
        if not matched and IF_OPEN.match(low):
            stack.append(("If", ln))
    for kind, ln in stack:
        problems.append(f"行{ln}: {kind} が閉じられていない")

    # --- 2. 定義と呼び出し ---
    defined = {}
    for ln, raw in lines:
        m = re.match(r"^\s*(?:public\s+|private\s+)?(?:sub|function)\s+(\w+)", raw, re.I)
        if m:
            name = m.group(1).lower()
            if name in defined:
                problems.append(
                    f"行{ln}: 手続き {m.group(1)} が二重に定義されている（行{defined[name]}）"
                )
            else:
                defined[name] = ln

    called = {}
    for ln, raw in lines:
        t = strip_noise(raw)
        if re.match(r"^\s*(?:public\s+|private\s+)?(?:sub|function)\s+\w", t, re.I):
            continue
        for m in re.finditer(r"(?<![.\w])([A-Za-z_]\w*)\s*\(", t):
            called.setdefault(m.group(1).lower(), (ln, m.group(1)))
        # 括弧なしの Sub 呼び出し（行頭の識別子＋空白＋引数、= を含まない）
        m = re.match(r"^\s*([A-Za-z_]\w*)\s+\S.*$", t.rstrip())
        if m and "=" not in t:
            called.setdefault(m.group(1).lower(), (ln, m.group(1)))

    # 変数（配列・オブジェクト）は Dim で宣言されているので除外する
    declared = set()
    for _, raw in lines:
        for m in re.finditer(r"\bDim\s+([^\n']+)", strip_noise(raw)):
            declared |= {
                x.strip().split("(")[0].strip().lower() for x in m.group(1).split(",")
            }
    for _, raw in lines:
        m = re.match(r"^\s*(?:sub|function)\s+\w+\s*\((.*)\)\s*$", strip_noise(raw), re.I)
        if m and m.group(1).strip():
            declared |= {
                re.sub(r"^(?:byref|byval)\s+", "", x.strip(), flags=re.I).lower()
                for x in m.group(1).split(",")
            }

    for name, (ln, orig) in sorted(called.items(), key=lambda kv: kv[1][0]):
        if name in defined or name in BUILTIN or name in declared:
            continue
        problems.append(f"行{ln}: {orig} を呼んでいるが定義が無い")

    return problems


def main():
    root = Path(__file__).resolve().parent.parent / "src"
    ng = 0
    for path in sorted(root.rglob("*.vbs")):
        problems = check(path)
        rel = path.relative_to(root.parent)
        if problems:
            ng += 1
            print(f"NG   {rel}")
            for p in problems:
                print(f"       {p}")
        else:
            print(f"OK   {rel}")
    if ng:
        print(f"\n{ng} 個のファイルに問題があります。")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
