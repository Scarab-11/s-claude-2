#Requires AutoHotkey v2.0
#SingleInstance Force
;==============================================================
;  線の重なり順 ボタン
;
;  このファイルをダブルクリックすると、画面の右上に
;  [線の重なり順] という小さなボタンが出ます。
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
;==============================================================

; ── ここだけ、必要なら変更 ────────────────────
;    true にすると [選択確定] まで自動で押します（Enter も不要）
AUTO_OK := false
; ──────────────────────────────────────────

BAT := A_ScriptDir "\線の重なり順を直す.bat"
JW  := "ahk_exe jw_win.exe"

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

;--------------------------------------------------------------
; ボタンを押したときの動き
;--------------------------------------------------------------
Go(*) {
    global BAT, JW, AUTO_OK

    if !WinExist(JW) {
        MsgBox("Jw_cad が起動していません。", "線の重なり順", "Icon!")
        return
    }

    WinActivate(JW)
    if !WinWaitActive(JW, , 3) {
        MsgBox("Jw_cad を前面にできませんでした。", "線の重なり順", "Icon!")
        return
    }

    ; メニューは項目名でたどる（アクセラレータキーに依存しない）
    try {
        MenuSelect(JW, , "その他", "外部変形")
    } catch {
        MsgBox("[その他] － [外部変形] を開けませんでした。", "線の重なり順", "Icon!")
        return
    }

    ; 外部変形のファイル選択（標準の [開く] ダイアログ）
    if !WinWait("ahk_class #32770 " JW, , 5) {
        MsgBox("ファイル選択の画面が出ませんでした。", "線の重なり順", "Icon!")
        return
    }
    dlg := WinExist()

    try {
        ControlSetText(BAT, "Edit1", dlg)
        ControlSend("{Enter}", "Edit1", dlg)
    } catch {
        MsgBox("ファイル名を入れられませんでした。", "線の重なり順", "Icon!")
        return
    }

    ; ここで Jw_cad は範囲選択待ちになる。[全選択] を押して
    ; 表示部を全範囲選択の状態にする。
    ; （[全選択] が拾うのは編集可能なレイヤだけなので、
    ;   [表示のみ] のレイヤは自動的に外れる）
    if !WinWaitActive(JW, , 5)
        return
    Sleep 400

    try {
        ControlClick("全選択", JW)
    } catch {
        ; 押せなければ、そのまま手で範囲選択すればよい
        return
    }

    if !AUTO_OK
        return

    Sleep 200
    try {
        ControlClick("選択確定", JW)
    } catch {
        return
    }
}
