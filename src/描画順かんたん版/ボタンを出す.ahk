#Requires AutoHotkey v2.0
#SingleInstance Force
;==============================================================
;  線の重なり順 ボタン
;
;  同じフォルダの「ボタンを出す.bat」をダブルクリックすると、
;  画面の右上に [線の重なり順] という小さなボタンが出ます。
;
;  （このファイルを直接ダブルクリックしても構いませんが、
;    .ahk が Jw_cad などに関連付けられていると、そちらが
;    起動してしまいます。bat のほうは AutoHotkey を自分で
;    探して起動するので、その影響を受けません。）
;
;  ボタンを押すと
;    [その他] － [外部変形] を開く
;      → 線の重なり順を直す.bat を選ぶ
;        → [全選択] を押す          ← ここまで自動
;  まで進みます。あとは Enter（または [選択確定]）を押すだけです。
;
;  設定は要りません。線の重なり順を直す.bat と同じフォルダに
;  置いておけば、そのまま動きます。
;
;  ボタンは常に手前に出ます。ドラッグして好きな場所に置けます。
;  終了はボタンの右上の × です。
;  Ctrl + Alt + L でも同じことができます。
;
;  うまく動かないときは Ctrl + Alt + M を押してください。
;  Jw_cad のメニューとボタンの一覧をメモ帳に出します。
;==============================================================

; ── ここだけ、必要なら変更 ────────────────────
;    true にすると [選択確定] まで自動で押します（Enter も不要）
AUTO_OK := false
; ──────────────────────────────────────────

BAT := A_ScriptDir "\線の重なり順を直す.bat"

WM_COMMAND    := 0x111
MF_BYPOSITION := 0x400

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
;  Jw_cad の窓を探す
;
;  Jw_cad はツールバーなども独立した窓として持っているので、
;  「jw_win.exe の窓」だけでは本体に当たらないことがある。
;  メニューバーを持っている窓＝本体、として探す。
;==============================================================
JwMain() {
    hits := WinGetList("ahk_exe jw_win.exe")
    for hwnd in hits {
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

;--- コントロールバーのボタンを押す ---------------------------
;    名前で押せなければ、その位置を実際にクリックする
ClickBar(hwnd, name) {
    try {
        ControlClick(name, "ahk_id " hwnd)
        return true
    } catch {
        ; 名前で押せなかった。位置を調べて実際にクリックする。
    }
    try {
        CoordMode("Mouse", "Client")
        ControlGetPos(&cx, &cy, &cw, &ch, name, "ahk_id " hwnd)
        Click((cx + cw // 2) " " (cy + ch // 2))
        return true
    } catch {
        return false
    }
}

;==============================================================
;  ボタンを押したときの動き
;==============================================================
Go(*) {
    global BAT, AUTO_OK, WM_COMMAND

    hwnd := JwMain()
    if !hwnd {
        if WinExist("ahk_exe jw_win.exe")
            MsgBox("Jw_cad の本体ウィンドウが見つかりませんでした。`n`n"
                 . "Ctrl + Alt + M で状態を書き出せます。"
                 , "線の重なり順", "Icon!")
        else
            MsgBox("Jw_cad が起動していません。", "線の重なり順", "Icon!")
        return
    }

    WinActivate("ahk_id " hwnd)
    if !WinWaitActive("ahk_id " hwnd, , 3) {
        MsgBox("Jw_cad を前面にできませんでした。", "線の重なり順", "Icon!")
        return
    }

    ; [外部変形] を実行する。メニューを開かずに、その項目の
    ; コマンド番号を直接送る（メニュー名に依存しない）。
    ok := false
    if (id := FindExtCmd(hwnd)) {
        PostMessage(WM_COMMAND, id, 0, , "ahk_id " hwnd)
        ok := true
    } else {
        ; 念のため、名前でたどる方法も試す
        try {
            MenuSelect("ahk_id " hwnd, , "その他", "外部変形")
            ok := true
        } catch {
            ok := false
        }
    }
    if !ok {
        MsgBox("[外部変形] のメニューが見つかりませんでした。`n`n"
             . "Ctrl + Alt + M を押すと、Jw_cad のメニュー一覧を"
             . "メモ帳に書き出します。", "線の重なり順", "Icon!")
        return
    }

    ; 外部変形のファイル選択（[開く] ダイアログ）
    dlg := WaitDialog(hwnd, 5)
    if !dlg {
        MsgBox("ファイル選択の画面を見つけられませんでした。`n`n"
             . "その画面を出したまま Ctrl + Alt + M を押すと、"
             . "中身をメモ帳に書き出します。", "線の重なり順", "Icon!")
        return
    }
    if !FillDialog(dlg, BAT)
        return

    ; ここで Jw_cad は範囲選択待ちになる。[全選択] を押して
    ; 表示部を全範囲選択の状態にする。
    ; （[全選択] が拾うのは編集可能なレイヤだけなので、
    ;   [表示のみ] のレイヤは自動的に外れる）
    if !WinWaitActive("ahk_id " hwnd, , 5)
        return
    Sleep 400

    if !ClickBar(hwnd, "全選択")
        return          ; 押せなければ、そのまま手で範囲選択すればよい

    if !AUTO_OK
        return

    Sleep 200
    ClickBar(hwnd, "選択確定")
}

;==============================================================
;  調べもの用（Ctrl + Alt + M）
;  Jw_cad のメニューとコントロールバーの中身を書き出す。
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
        ; そのウィンドウの中のボタン・入力欄
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
