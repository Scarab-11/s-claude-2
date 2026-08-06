#Requires AutoHotkey v2.0
#SingleInstance Force
;==============================================================
;  Jw_cad 外部変形「描画順」 常駐ホットキー
;
;  Jw_cad にはプラグインの仕組みが無いため、CAD の中に住みついて
;  描画順を自動で面倒みるツールは作れません。
;  代わりにこのスクリプトを常駐させておくと、Jw_cad を操作中に
;  キー一発で [その他] － [外部変形] を開き、目的のバッチファイル
;  まで選んでくれます。範囲選択からは通常どおりの操作です。
;
;  必要なもの : AutoHotkey v2 （https://www.autohotkey.com/）
;  使い方     : このファイルをダブルクリックするだけ。
;               タスクトレイに常駐します。終了は右クリック － Exit。
;               Windows のスタートアップに入れておくと便利です。
;
;  ホットキー （Jw_cad がアクティブなときだけ効きます）
;    Ctrl + Alt + ↑    選んだものを最前面へ
;    Ctrl + Alt + ↓    指定した線色を最背面へ
;    Ctrl + Alt + L    線色順 1,2,3,4,6,5,7,8 に並べ替え（範囲は手で選ぶ）
;    Ctrl + Alt + A    同上を図面全体に適用（全選択 － 選択確定 まで自動）
;    Ctrl + Alt + O    描画順（対話式）
;
;  Ctrl + Alt + A について
;    [全選択] が拾うのは「編集可能なレイヤー」のデータだけです。
;    ブロック図形は外部変形を通すと消えます（分解ではありません）。
;    ブロック図形を置いたレイヤーは [表示のみ] にしておいて
;    ください。全選択の対象から外れます。
;    曲線属性の図形と寸法図形は、まとまりを保ったまま並べ替え
;    られるので、範囲に入れて構いません。
;==============================================================

;--------------------------------------------------------------
; 設定 － 環境に合わせてここだけ書き換えてください
;--------------------------------------------------------------

; 描画順フォルダの場所（末尾の \ を忘れずに）
BAT_DIR := "C:\jww\外変\描画順\"

; Jw_cad の実行ファイル名
JW_EXE := "jw_win.exe"

; メニューの項目名。先頭が一致すれば良いので "その他" のように
; 途中まででかまいません。日本語版以外では変更してください。
MENU_TOP := "その他"
MENU_SUB := "外部変形"

; ファイル選択ダイアログを待つ秒数
DLG_WAIT := 5

; 範囲選択まで自動で行うときに押すコントロールバーのボタン名
BTN_ALL := "全選択"
BTN_OK  := "選択確定"

; ボタンの押し方
;   false … ControlClick でボタンに直接クリックを送る（マウスは動かない）
;   true  … 実際にマウスを動かしてクリックする
;           ControlClick が効かない環境ではこちらにしてください
;           （クリック後、マウスの位置は元に戻します）
REAL_CLICK := false

;--------------------------------------------------------------
; ホットキー
;--------------------------------------------------------------
#HotIf WinActive("ahk_exe " JW_EXE)

^!Up::   RunGaihen("描画順_最前面へ.bat")
^!Down:: RunGaihen("描画順_線色指定で最背面.bat")
^!l::    RunGaihen("描画順_線色順_12346578.bat")
^!a::    RunGaihen("描画順_線色順_12346578.bat", true)   ; 図面全体に適用
^!o::    RunGaihen("描画順.bat")

#HotIf

;--------------------------------------------------------------
; [その他] － [外部変形] を開いて、バッチファイルを選ぶ
;--------------------------------------------------------------
RunGaihen(batName, autoRange := false) {
    global BAT_DIR, JW_EXE, MENU_TOP, MENU_SUB, DLG_WAIT, BTN_ALL, BTN_OK

    batPath := BAT_DIR . batName

    if !FileExist(batPath) {
        MsgBox("外部変形のバッチファイルが見つかりません。`n`n"
             . batPath . "`n`n"
             . "このスクリプトの先頭にある BAT_DIR を、実際に置いた"
             . "フォルダに書き換えてください。", "描画順", "Icon!")
        return
    }

    jwHwnd := WinExist("A")

    ; メニューを項目名でたどる。アクセラレータキーに依存しないので
    ; メニューの並びが変わっても動く。
    try {
        MenuSelect("ahk_id " jwHwnd, , MENU_TOP, MENU_SUB)
    } catch as e {
        MsgBox("Jw_cad の [" MENU_TOP "] － [" MENU_SUB "] を開けませんでした。`n`n"
             . "このスクリプトの先頭にある MENU_TOP / MENU_SUB を、"
             . "お使いの Jw_cad のメニュー表示に合わせてください。`n`n"
             . e.Message, "描画順", "Icon!")
        return
    }

    ; 外部変形のファイル選択ダイアログ（標準の [開く] ダイアログ）
    if !WinWait("ahk_class #32770 ahk_exe " JW_EXE, , DLG_WAIT) {
        MsgBox("外部変形のファイル選択ダイアログが開きませんでした。",
               "描画順", "Icon!")
        return
    }
    dlg := WinExist()

    ; ファイル名欄にフルパスを入れて確定する
    try {
        ControlSetText(batPath, "Edit1", dlg)
        ControlSend("{Enter}", "Edit1", dlg)
    } catch as e {
        MsgBox("ファイル名を入力できませんでした。`n`n" e.Message, "描画順", "Icon!")
        return
    }

    ; ここまでで Jw_cad は範囲選択待ちになっている。
    ; autoRange が false なら、あとはコントロールバーの指示に
    ; したがって手で範囲選択する。
    if !autoRange
        return

    ; --- 図面全体に適用する（全選択 － 選択確定） ---------------
    ;
    ; [全選択] が拾うのは「編集可能なレイヤー」のデータだけ。
    ; 触りたくないもの（ブロック図形）は、そのレイヤーを
    ; [表示のみ] にしておけば対象から外れる。
    if !WinWaitActive("ahk_exe " JW_EXE, , 5) {
        MsgBox("Jw_cad が範囲選択の状態になりませんでした。", "描画順", "Icon!")
        return
    }
    Sleep 300

    if !ClickBar(BTN_ALL) {
        MsgBox("コントロールバーの [" BTN_ALL "] を押せませんでした。`n`n"
             . "続きは手で操作してください。`n"
             . "うまくいかない場合は、このスクリプトの先頭にある"
             . " REAL_CLICK を true にしてみてください。", "描画順", "Icon!")
        return
    }
    Sleep 200

    if !ClickBar(BTN_OK) {
        MsgBox("コントロールバーの [" BTN_OK "] を押せませんでした。`n`n"
             . "続きは手で操作してください。", "描画順", "Icon!")
        return
    }
}

;--------------------------------------------------------------
; コントロールバーのボタンを押す
;--------------------------------------------------------------
ClickBar(text) {
    global JW_EXE, REAL_CLICK

    if !REAL_CLICK {
        try {
            ControlClick(text, "ahk_exe " JW_EXE)
            return true
        } catch
            return false
    }

    ; ControlClick が効かない環境向け。実際にマウスを動かして押し、
    ; 終わったら元の位置に戻す。
    try {
        ControlGetPos(&cx, &cy, &cw, &ch, text, "ahk_exe " JW_EXE)
    } catch
        return false

    if (cw = 0 or ch = 0)
        return false

    px := cx + cw // 2
    py := cy + ch // 2

    MouseGetPos(&ox, &oy)
    prev := CoordMode("Mouse", "Client")
    Click(px " " py)
    CoordMode("Mouse", prev)
    MouseMove(ox, oy, 0)
    return true
}
