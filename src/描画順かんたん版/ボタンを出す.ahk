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
;
;  Jw_cad の図面を複数開いている場合、外部変形の対象になるのは
;  「最後に触っていた図面」です。対象の図面名は、ボタンのすぐ下に
;  常に表示されます。対象を変えたいときは、目的の図面の画面を
;  一度クリックしてから [線の重なり順] を押してください。
;
;  隣の [?] は調べもの用です。うまく動かないときに押すと、
;  そのときの Jw_cad の中身をメモ帳に書き出します。
;
;  ホットキー（キーの常時監視）は使っていません。
;  ウイルス対策ソフトに「キーロガー」と誤認されないためです。
;==============================================================

BAT := A_ScriptDir "\線の重なり順を直す.bat"

WM_COMMAND    := 0x111
MF_BYPOSITION := 0x400

; [その他] － [外部変形] のコマンド番号（Jw_cad 8.20 で確認）
; メニューから探せなかったときだけ、この番号を使う。
EXT_CMD := 32913

; 最後に触っていた Jw_cad の図面ウィンドウ
gLastJw := 0

if !FileExist(BAT) {
    MsgBox("線の重なり順を直す.bat が見つかりません。`n`n"
         . "このファイルは 線の重なり順を直す.bat と同じフォルダに"
         . "置いてください。`n`n" BAT, "線の重なり順", "Iconx")
    ExitApp
}

;--- ボタンを出す ---------------------------------------------
btn := Gui("+AlwaysOnTop +ToolWindow", "線順")
btn.SetFont("s10")
btn.AddButton("xm ym w110 h30", "線の重なり順").OnEvent("Click", Go)
btn.AddButton("x+4 yp w28 h30", "?").OnEvent("Click", (*) => DumpJw())
btn.SetFont("s8")
gTargetLabel := btn.AddText("xm y+4 w142 h30", "対象 : Jw_cad の図面を`nクリックしてください")
btn.OnEvent("Close", (*) => ExitApp())
btn.Show("x" (A_ScreenWidth - 190) " y8 NoActivate")

;--- 対象の図面を追いかける -----------------------------------
;    Jw_cad の図面を複数開いていると、どれが対象なのかを
;    決められない。そこで「最後に触っていた図面」を覚えておき、
;    対象の図面名を画面に出し続ける。
SetTimer(WatchJw, 200)

WatchJw() {
    global gLastJw, gTargetLabel

    h := 0
    try h := WinGetID("A")
    catch
        return
    if !h
        return

    ; Jw_cad の図面ウィンドウ（メニューを持つ窓）だけを覚える
    name := ""
    try name := WinGetProcessName("ahk_id " h)
    catch
        return
    if (name != "jw_win.exe")
        return
    if !DllCall("GetMenu", "ptr", h, "ptr")
        return

    if (h = gLastJw)
        return
    gLastJw := h

    title := ""
    try title := WinGetTitle("ahk_id " h)
    catch
        title := ""
    title := StrReplace(title, " - jw_win", "")
    gTargetLabel.Text := "対象 : " title
}

;==============================================================
;  ボタンを押したときの動き（ここが全部）
;==============================================================
Go(*) {
    global BAT, WM_COMMAND, EXT_CMD

    hwnd := JwMain()
    if !hwnd {
        if WinExist("ahk_exe jw_win.exe")
            MsgBox("外部変形の対象になる図面が決まっていません。`n`n"
                 . "目的の図面の画面を一度クリックしてから、`n"
                 . "[線の重なり順] を押してください。", "線の重なり順", "Icon!")
        else
            MsgBox("Jw_cad が起動していません。", "線の重なり順", "Icon!")
        return
    }

    WinActivate("ahk_id " hwnd)
    if !WinWaitActive("ahk_id " hwnd, , 3) {
        MsgBox("Jw_cad を前面にできませんでした。", "線の重なり順", "Icon!")
        return
    }

    ;--- ⓪ 前回の外部変形が残っていたら終わらせる --------------
    ;    外部変形を実行し終えると、コントロールバーに
    ;    [外部変形再選択] [再実行] [点指示終了] が出たまま残る。
    ;    残ったままだと外部変形をもう一度起動できないので、
    ;    先に [点指示終了] を押してコマンドから抜ける。
    ctl := FindBarIn(hwnd, "点指示終了")
    if (ctl != "") {
        try ControlClick(ctl, "ahk_id " hwnd)
        Sleep 250
    }

    ;--- ① 外部変形を起動 --------------------------------------
    ;    メニューを開かずに、[外部変形] のコマンド番号を直接送る
    id := FindExtCmd(hwnd)
    if !id
        id := EXT_CMD
    PostMessage(WM_COMMAND, id, 0, , "ahk_id " hwnd)

    ;--- ② バッチを選ぶ ----------------------------------------
    ;    Jw_cad の [ファイル選択] は Windows 標準の画面ではなく
    ;    Jw_cad 独自のもので、ファイル名を打ち込む欄が無い。
    ;    そこで、一覧の中から目的の行を選んで開く。
    dlg := WaitDialog(5)
    if !dlg {
        Fail("ファイル選択の画面が出ませんでした。")
        return
    }

    if !PickBat(dlg, BAT) {
        ; 一覧に無い＝別のフォルダを見ている。
        ; 最初の 1 回だけ手で選んでもらう。Jw_cad はそのフォルダを
        ; 覚えるので、次からは上の自動選択が当たる。
        ToolTip("最初の 1 回だけ、この画面で`n"
              . "「線の重なり順を直す.bat」を選んでください。`n"
              . "次からはボタンだけで最後まで進みます。")
        ok := WinWaitClose("ahk_id " dlg, , 60)
        ToolTip()
        if !ok {
            MsgBox("ファイル選択の画面が閉じないまま 60 秒たちました。`n`n"
                 . "Jw_cad のファイル選択の画面を閉じてから、`n"
                 . "[線の重なり順] を押し直してください。", "線の重なり順", "Icon!")
            return
        }
    }

    ;--- ③ 表示部を全範囲選択 ----------------------------------
    ;    [全選択] が拾うのは編集可能なレイヤだけなので、
    ;    [表示のみ] のレイヤは自動的に外れる
    ;
    ;    コントロールバーは外部変形の起動が終わってから
    ;    作り直されるので、固定時間で待たずに
    ;    ボタンが出てくるまで待つ。
    ;
    ;    図面を複数開いている場合に別の図面のボタンを押さないよう、
    ;    探す範囲は対象の図面ウィンドウの中だけに限る。
    if !ClickBarIn(hwnd, "全選択", 5) {
        Fail("[全選択] のボタンが出てきませんでした。")
        return
    }

    ;--- ④ 選択確定 --------------------------------------------
    ;    [選択確定] は範囲が決まってから出るので、これも待つ
    if !ClickBarIn(hwnd, "選択確定", 5) {
        ; ボタンが押せなくても、Enter で確定できる
        WinActivate("ahk_id " hwnd)
        Send("{Enter}")
    }
}

;--- 途中で止まったとき --------------------------------------
;    そのときの Jw_cad の中身をそのまま書き出す。
;    [?] ボタンを押してもらう手間を省く。
Fail(msg) {
    MsgBox(msg "`n`n"
         . "このときの Jw_cad の状態を「Jw_cad調査.txt」に"
         . "書き出してメモ帳で開きます。", "線の重なり順", "Icon!")
    DumpJw()
}

;==============================================================
;  外部変形の対象にする図面ウィンドウを決める
;
;  Jw_cad は図面を 1 枚開くごとに独立した窓を作る。
;  スタートアップで複数の jww を開いていると窓が何個も並ぶため、
;  「見つかった順の 1 個目」では対象を決められない。
;  WatchJw() が覚えた「最後に触っていた図面」を対象にする。
;
;  Jw_cad はツールバーなども独立した窓として持っているので、
;  メニューバーを持っている窓＝図面ウィンドウ、として区別する。
;==============================================================
JwMain() {
    global gLastJw

    if (gLastJw && WinExist("ahk_id " gLastJw))
        return gLastJw

    ; まだ一度も Jw_cad を触っていない場合に限り、
    ; 開いている図面が 1 枚だけならそれを対象にする。
    found := 0
    for hwnd in WinGetList("ahk_exe jw_win.exe") {
        if !DllCall("GetMenu", "ptr", hwnd, "ptr")
            continue
        if found
            return 0        ; 2 枚以上あるので決められない
        found := hwnd
    }
    return found
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
;  外部変形の [ファイル選択] が出るのを待つ
;
;  Jw_cad 独自の画面で、題名が「ファイル選択」。
;  題名で当たらないときは、メニューを持たない表示中の窓を拾う。
;  図面ウィンドウは必ずメニューを持つので、メニューの有無で
;  図面ウィンドウとダイアログを区別できる。
;==============================================================
WaitDialog(sec) {
    t := A_TickCount
    while (A_TickCount - t < sec * 1000) {
        cand := 0
        for h in WinGetList("ahk_exe jw_win.exe") {
            if DllCall("GetMenu", "ptr", h, "ptr")
                continue                    ; 図面ウィンドウなので対象外
            if !DllCall("IsWindowVisible", "ptr", h)
                continue
            if InStr(WinGetTitle("ahk_id " h), "ファイル選択")
                return h
            if !cand
                cand := h
        }
        if cand
            return cand
        Sleep 50
    }
    return 0
}

;--- 中にある指定の種類のコントロールを探す -------------------
FindByClass(hwnd, cls) {
    ctls := []
    try {
        ctls := WinGetControls("ahk_id " hwnd)
    } catch {
        return ""
    }
    for ctl in ctls {
        if (InStr(ctl, cls) = 1)
            return ctl
    }
    return ""
}

;==============================================================
;  [ファイル選択] の一覧から、目的のバッチを選んで開く
;
;  この画面にはファイル名を打ち込む欄が無い。文字を打ち込むと
;  別の入力欄に入って「整数を入力してください。」になるので、
;  絶対に打ち込まないこと。一覧の行を選ぶだけにする。
;
;  戻り値 : 選べて画面が閉じたら true
;==============================================================
PickBat(dlg, batPath) {
    SplitPath(batPath, &fname, , , &base)

    lv := FindByClass(dlg, "SysListView32")
    if (lv = "")
        return false

    rows := ""
    try {
        rows := ListViewGetContent("Col1", lv, "ahk_id " dlg)
    } catch {
        return false
    }

    idx := 0
    n   := 0
    Loop Parse rows, "`n", "`r" {
        n++
        if (A_LoopField = "")
            continue
        ; 拡張子ありでも無しでも当たるようにする
        if (A_LoopField = fname || A_LoopField = base
            || InStr(A_LoopField, base)) {
            idx := n
            break
        }
    }
    if !idx
        return false

    try {
        ControlFocus(lv, "ahk_id " dlg)
        Sleep 60
        ControlSend("{Home}", lv, "ahk_id " dlg)
        if (idx > 1)
            ControlSend("{Down " (idx - 1) "}", lv, "ahk_id " dlg)
        Sleep 80
        ControlSend("{Enter}", lv, "ahk_id " dlg)
    } catch {
        return false
    }

    return WinWaitClose("ahk_id " dlg, , 3) ? true : false
}

;==============================================================
;  指定した図面ウィンドウの中から、コントロールバーのボタンを探す
;
;  Jw_cad のコントロールバーはコマンドごとに作り直されるので、
;  ボタンの ClassNN は決め打ちできない。指定された図面ウィンドウ
;  の中だけを見て、その文字を持つボタンを探す。
;
;  図面を複数開いていても別の図面のボタンを押さないよう、
;  探す範囲を 1 つの図面ウィンドウに限っている。
;==============================================================
FindBarIn(hwnd, name) {
    ctls := []
    try {
        ctls := WinGetControls("ahk_id " hwnd)
    } catch {
        return ""
    }
    for ctl in ctls {
        txt := ""
        try {
            txt := ControlGetText(ctl, "ahk_id " hwnd)
        } catch {
            continue
        }
        if InStr(txt, name)
            return ctl
    }
    return ""
}

;--- ボタンが出てくるのを待って、押す -------------------------
;    押せなければ、その場所を実際にクリックする
ClickBarIn(hwnd, name, sec) {
    t   := A_TickCount
    ctl := ""
    Loop {
        ctl := FindBarIn(hwnd, name)
        if (ctl != "")
            break
        if (A_TickCount - t > sec * 1000)
            return false
        Sleep 100
    }

    try {
        ControlClick(ctl, "ahk_id " hwnd)
        return true
    } catch {
        ; コントロールとして押せなかった。実際にクリックする。
    }
    try {
        WinActivate("ahk_id " hwnd)
        CoordMode("Mouse", "Client")
        ControlGetPos(&cx, &cy, &cw, &ch, ctl, "ahk_id " hwnd)
        Click((cx + cw // 2) " " (cy + ch // 2))
        return true
    } catch {
        return false
    }
}

;==============================================================
;  調べもの用（[?] ボタン）
;  Jw_cad のウィンドウ・メニュー・ボタンの中身を書き出す。
;  うまく動かないときに、この内容を見れば原因がわかる。
;==============================================================
DumpJw(*) {
    global gLastJw

    tgt := JwMain()
    out := "外部変形の対象にする図面 : "
         . (tgt ? ("hwnd=" tgt "  " WinGetTitle("ahk_id " tgt))
                : "決まっていません（図面を一度クリックしてください）")
         . "`r`n`r`n"
         . "Jw_cad ウィンドウ一覧`r`n"
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
            ; 一覧は中身も書き出す（ファイル選択の画面の確認用）
            if (InStr(ctl, "SysListView32") = 1) {
                rows := ""
                try {
                    rows := ListViewGetContent("Col1", ctl, "ahk_id " hwnd)
                } catch {
                    rows := "(読めません)"
                }
                Loop Parse rows, "`n", "`r" {
                    if (A_LoopField != "")
                        out .= "        > " A_LoopField "`r`n"
                }
            }
        }
    }

    ; メニュー番号はどの図面ウィンドウでも同じなので、
    ; 対象が決まっていないときは最初の図面ウィンドウから書き出す。
    hwnd := tgt
    if !hwnd {
        for h in hits {
            if DllCall("GetMenu", "ptr", h, "ptr") {
                hwnd := h
                break
            }
        }
    }
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
