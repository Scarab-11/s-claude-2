#Requires AutoHotkey v2.0
#SingleInstance Force
;==============================================================
;  線の重なり順 ボタン
;
;  同じフォルダの「ボタンを出す.bat」をダブルクリックすると、
;  画面の右上に [線の重なり順] という小さなボタンが出ます。
;
;  ボタンを 1 回押すだけで、次が最後まで自動で走ります。
;
;      外部変形（線の重なり順を直す）を起動
;        → 表示部を全範囲選択
;          → 選択確定（Enter）
;
;  操作はこれだけです。設定はひとつもありません。
;
;  ボタンは常に手前に出ます。ドラッグして好きな場所に置けます。
;  終了はボタンの右上の × です。
;  Ctrl + Alt + L でも同じことができます。
;
;  うまく動かないときは Ctrl + Alt + M を押してください。
;  Jw_cad の中身をメモ帳に書き出します（調べもの用）。
;==============================================================

BAT := A_ScriptDir "\線の重なり順を直す.bat"

WM_COMMAND    := 0x111
MF_BYPOSITION := 0x400

; [その他] － [外部変形] のコマンド番号（Jw_cad 8.20 で確認）
; メニューから探せなかったときだけ、この番号を使う。
EXT_CMD := 32913

if !FileExist(BAT) {
    MsgBox("線の重なり順を直す.bat が見つかりません。`n`n"
         . "このファイルは 線の重なり順を直す.bat と同じフォルダに"
         . "置いてください。`n`n" BAT, "線の重なり順", "Iconx")
    ExitApp
}

;--- ボタンを出す ---------------------------------------------
btn := Gui("+AlwaysOnTop +ToolWindow", "線順")
btn.SetFont("s10")
btn.AddButton("w110 h30", "線の重なり順").OnEvent("Click", Go)
btn.OnEvent("Close", (*) => ExitApp())
btn.Show("x" (A_ScreenWidth - 160) " y8 NoActivate")

^!l::Go()
^!m::DumpJw()

;==============================================================
;  ボタンを押したときの動き（ここが全部）
;==============================================================
Go(*) {
    global BAT, WM_COMMAND, EXT_CMD

    hwnd := JwMain()
    if !hwnd {
        if WinExist("ahk_exe jw_win.exe")
            Fail("Jw_cad の本体ウィンドウが見つかりませんでした。")
        else
            MsgBox("Jw_cad が起動していません。", "線の重なり順", "Icon!")
        return
    }

    WinActivate("ahk_id " hwnd)
    if !WinWaitActive("ahk_id " hwnd, , 3) {
        MsgBox("Jw_cad を前面にできませんでした。", "線の重なり順", "Icon!")
        return
    }

    ;--- ① 外部変形を起動 --------------------------------------
    ;    メニューを開かずに、[外部変形] のコマンド番号を直接送る
    id := FindExtCmd(hwnd)
    if !id
        id := EXT_CMD
    PostMessage(WM_COMMAND, id, 0, , "ahk_id " hwnd)

    ;--- ② バッチを選ぶ ----------------------------------------
    dlg := WaitDialog(hwnd, 5)
    if !dlg {
        Fail("ファイル選択の画面が出ませんでした。")
        return
    }
    if !FillDialog(dlg, BAT) {
        Fail("ファイル名を入れられませんでした。")
        return
    }

    ;--- ③ 表示部を全範囲選択 ----------------------------------
    ;    [全選択] が拾うのは編集可能なレイヤだけなので、
    ;    [表示のみ] のレイヤは自動的に外れる
    ;
    ;    コントロールバーは外部変形の起動が終わってから
    ;    作り直されるので、固定時間で待たずに
    ;    ボタンが出てくるまで待つ。
    if !ClickBar("全選択", 5) {
        Fail("[全選択] のボタンが出てきませんでした。")
        return
    }

    ;--- ④ 選択確定 --------------------------------------------
    ;    [選択確定] は範囲が決まってから出るので、これも待つ
    if !ClickBar("選択確定", 5) {
        ; ボタンが押せなくても、Enter で確定できる
        WinActivate("ahk_id " hwnd)
        Send("{Enter}")
    }
}

;--- 途中で止まったとき --------------------------------------
;    そのときの Jw_cad の中身をそのまま書き出す。
;    Ctrl + Alt + M を押してもらう手間を省く。
Fail(msg) {
    MsgBox(msg "`n`n"
         . "このときの Jw_cad の状態を「Jw_cad調査.txt」に"
         . "書き出してメモ帳で開きます。", "線の重なり順", "Icon!")
    DumpJw()
}

;==============================================================
;  Jw_cad の本体ウィンドウを探す
;
;  Jw_cad はツールバーなども独立した窓として持っているので、
;  「jw_win.exe の窓」だけでは本体に当たらないことがある。
;  メニューバーを持っている窓＝本体、として探す。
;==============================================================
JwMain() {
    for hwnd in WinGetList("ahk_exe jw_win.exe") {
        if DllCall("GetMenu", "ptr", hwnd, "ptr")
            return hwnd
    }
    return 0
}

;--- メニュー項目の文字列（&（下線）を取り除いたもの）----------
MenuText(hMenu, pos) {
    global MF_BYPOSITION
    buf := Buffer(1024, 0)
    len := DllCall("GetMenuStringW", "ptr", hMenu, "uint", pos
                 , "ptr", buf, "int", 511, "uint", MF_BYPOSITION, "int")
    if !len
        return ""
    return StrReplace(StrGet(buf, "UTF-16"), "&", "")
}

;==============================================================
;  「外部変形」のコマンド番号を探す
;
;  メニュー名を決め打ちせず、全部のメニューを見て
;  「外部変形」を含む項目を探す。名前が [その他] でなくても、
;  項目の位置が違っても当たる。
;==============================================================
FindExtCmd(hwnd) {
    hMenu := DllCall("GetMenu", "ptr", hwnd, "ptr")
    if !hMenu
        return 0

    top := DllCall("GetMenuItemCount", "ptr", hMenu, "int")
    Loop top {
        sub := DllCall("GetSubMenu", "ptr", hMenu, "int", A_Index - 1, "ptr")
        if !sub
            continue
        cnt := DllCall("GetMenuItemCount", "ptr", sub, "int")
        Loop cnt {
            pos := A_Index - 1
            if !InStr(MenuText(sub, pos), "外部変形")
                continue
            id := DllCall("GetMenuItemID", "ptr", sub, "int", pos, "uint")
            if (id != 0 && id != 0xFFFFFFFF)
                return id
        }
    }
    return 0
}

;==============================================================
;  外部変形のファイル選択画面が出るのを待つ
;  （本体とは別の、あとから出てきたウィンドウ）
;==============================================================
WaitDialog(mainHwnd, sec) {
    t := A_TickCount
    while (A_TickCount - t < sec * 1000) {
        for h in WinGetList("ahk_exe jw_win.exe") {
            if (h = mainHwnd)
                continue
            if !DllCall("IsWindowVisible", "ptr", h)
                continue
            if (WinGetClass("ahk_id " h) = "#32770")
                return h
        }
        Sleep 50
    }
    return 0
}

;==============================================================
;  ファイル名を入れて確定する
;
;  ①「ファイル名」欄に直接書き込む
;  ② 駄目なら、実際にキーを打ち込む
;     （日本語のファイル名でも {Text} なら確実に入る）
;==============================================================
FillDialog(dlg, path) {
    try {
        ControlSetText(path, "Edit1", "ahk_id " dlg)
        Sleep 100
        if (ControlGetText("Edit1", "ahk_id " dlg) = path) {
            ControlSend("{Enter}", "Edit1", "ahk_id " dlg)
            return true
        }
    } catch {
        ; ①が使えなかった。②へ。
    }

    try {
        WinActivate("ahk_id " dlg)
        if !WinWaitActive("ahk_id " dlg, , 2)
            return false
        Sleep 100
        SendInput("{Text}" path)
        Sleep 150
        SendInput("{Enter}")
        return true
    } catch {
        return false
    }
}

;==============================================================
;  コントロールバーのボタンを探す
;
;  Jw_cad のコントロールバーはコマンドごとに作り直されるので、
;  ボタンの ClassNN は決め打ちできない。jw_win.exe の全ウィンドウ
;  の中を見て、その文字を持つボタンを探す。
;==============================================================
FindBar(name) {
    for hwnd in WinGetList("ahk_exe jw_win.exe") {
        ctls := []
        try {
            ctls := WinGetControls("ahk_id " hwnd)
        } catch {
            continue
        }
        for ctl in ctls {
            txt := ""
            try {
                txt := ControlGetText(ctl, "ahk_id " hwnd)
            } catch {
                continue
            }
            if InStr(txt, name)
                return { win: hwnd, ctl: ctl }
        }
    }
    return 0
}

;--- ボタンが出てくるのを待って、押す -------------------------
;    押せなければ、その場所を実際にクリックする
ClickBar(name, sec) {
    t := A_TickCount
    f := 0
    Loop {
        f := FindBar(name)
        if f
            break
        if (A_TickCount - t > sec * 1000)
            return false
        Sleep 100
    }

    try {
        ControlClick(f.ctl, "ahk_id " f.win)
        return true
    } catch {
        ; コントロールとして押せなかった。実際にクリックする。
    }
    try {
        WinActivate("ahk_id " f.win)
        CoordMode("Mouse", "Client")
        ControlGetPos(&cx, &cy, &cw, &ch, f.ctl, "ahk_id " f.win)
        Click((cx + cw // 2) " " (cy + ch // 2))
        return true
    } catch {
        return false
    }
}

;==============================================================
;  調べもの用（Ctrl + Alt + M）
;  Jw_cad のウィンドウ・メニュー・ボタンの中身を書き出す。
;  うまく動かないときに、この内容を見れば原因がわかる。
;==============================================================
DumpJw(*) {
    out := "Jw_cad ウィンドウ一覧`r`n"
         . "==============================`r`n"

    hits := WinGetList("ahk_exe jw_win.exe")
    if !hits.Length {
        MsgBox("Jw_cad が起動していません。", "線の重なり順", "Icon!")
        return
    }

    for hwnd in hits {
        hMenu := DllCall("GetMenu", "ptr", hwnd, "ptr")
        vis   := DllCall("IsWindowVisible", "ptr", hwnd)
        out .= "`r`nhwnd=" hwnd
             . "  class=" WinGetClass("ahk_id " hwnd)
             . "  menu=" (hMenu ? "あり" : "なし")
             . "  表示=" (vis ? "する" : "しない")
             . "`r`n  title=" WinGetTitle("ahk_id " hwnd) "`r`n"
        ctls := []
        try {
            ctls := WinGetControls("ahk_id " hwnd)
        } catch {
            ctls := []
        }
        for ctl in ctls {
            txt := ""
            try {
                txt := ControlGetText(ctl, "ahk_id " hwnd)
            } catch {
                txt := "(読めません)"
            }
            out .= "    " ctl "`t" txt "`r`n"
        }
    }

    hwnd := JwMain()
    if !hwnd {
        out .= "`r`nメニューを持つウィンドウがありません。`r`n"
    } else {
        hMenu := DllCall("GetMenu", "ptr", hwnd, "ptr")
        out .= "`r`n`r`nメニュー（hwnd=" hwnd "）`r`n"
             . "==============================`r`n"
        top := DllCall("GetMenuItemCount", "ptr", hMenu, "int")
        Loop top {
            i := A_Index - 1
            out .= "[" MenuText(hMenu, i) "]`r`n"
            sub := DllCall("GetSubMenu", "ptr", hMenu, "int", i, "ptr")
            if !sub
                continue
            cnt := DllCall("GetMenuItemCount", "ptr", sub, "int")
            Loop cnt {
                p  := A_Index - 1
                id := DllCall("GetMenuItemID", "ptr", sub, "int", p, "uint")
                out .= "    " Format("{:5}", (id = 0xFFFFFFFF ? "-" : id))
                     . "  " MenuText(sub, p) "`r`n"
            }
        }
    }

    path := A_ScriptDir "\Jw_cad調査.txt"
    try {
        if FileExist(path)
            FileDelete(path)
        FileAppend(out, path, "UTF-8")
        Run('notepad.exe "' path '"')
    } catch {
        MsgBox("書き出せませんでした。`n" path, "線の重なり順", "Iconx")
    }
}
