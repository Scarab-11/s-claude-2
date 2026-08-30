Option Explicit
'==============================================================
' Jw_cad 外部変形 : 文字位置揃え   jww_text_align.vbs
'
'   範囲選択した文字の位置を、横方向(X)・縦方向(Y) それぞれ
'   独立に指定して揃えます。
'
'   ・バッチファイル(*.bat)から cscript で呼び出されます。
'   ・単体では動きません（jwc_temp.txt が必要）。
'
'   引数（省略時は入力ダイアログで指定）
'     /x:0-6   横方向 0=揃えない 1=左 2=中央 3=右 4=数値指定
'                     5=等間隔(左端) 6=等間隔(すき間)
'     /y:0-6   縦方向 0=揃えない 1=下 2=中央 3=上 4=数値指定
'                     5=等間隔(下端) 6=等間隔(すき間)
'     /xv:数値 /yv:数値   モード4のときの基準座標
'     /q       ダイアログを出さない（引数だけで実行）
'
'   バッチファイルに「REM #1」を書いて点を指示させると、その点に
'   一番近い文字が「基準文字」になり、モード1～3はその文字に
'   合わせます（指示が無ければ選択した文字全体が基準）。
'
'   Jw_cad Version 8.20 で使用する想定
'==============================================================

'--- モード定数 -----------------------------------------------
Const MODE_NONE   = 0    ' 揃えない
Const MODE_MIN    = 1    ' X:左揃え / Y:下揃え
Const MODE_CENTER = 2    ' 中央揃え
Const MODE_MAX    = 3    ' X:右揃え / Y:上揃え
Const MODE_VALUE  = 4    ' 数値指定
Const MODE_SPACE  = 5    ' 等間隔（左端 / 下端を等間隔に）
Const MODE_GAP    = 6    ' 等間隔（文字のすき間を等間隔に）
Const MODE_MAXNO  = 6

Const APPTITLE = "文字位置揃え"
Const EPS      = 0.000001

'--- グローバル -----------------------------------------------
Dim gFso        : Set gFso = CreateObject("Scripting.FileSystemObject")
Dim gScriptDir  : gScriptDir = gFso.GetParentFolderName(WScript.ScriptFullName)
Dim gIniPath    : gIniPath = gFso.BuildPath(gScriptDir, "jww_text_align.ini")

Dim gHcw(10), gHch(10), gHcd(10)   ' 文字種1-10 の 幅 / 高さ / 間隔
Dim gOut()                          ' 出力行
Dim gOutCount                       ' 出力行数
Dim gItems()                        ' 文字要素
Dim gItemCount                      ' 文字要素数
Dim gHasRef                         ' 基準点(REM #1)の指示があったか
Dim gRefX, gRefY                    ' 指示された基準点

'--- 文字要素 -------------------------------------------------
Class TextItem
    Public x, y, f3, f4      ' ch の 4 つの数値
    Public sPart             ' 「"文字列」の部分
    Public outIndex          ' 出力行での位置
    Public cw, ch_, cd       ' 文字種の 幅 / 高さ / 間隔
    Public xMin, xMax, yMin, yMax
    Public dx, dy            ' 移動量
End Class

Main

'==============================================================
' メイン
'==============================================================
Sub Main()
    Dim tempPath, lines, xMode, yMode, xVal, yVal

    tempPath = FindTempFile()
    If tempPath = "" Then
        MsgBox "jwc_temp.txt が見つかりません。" & vbCrLf & vbCrLf & _
               "この外部変形は Jw_cad の [その他]-[外部変形] から" & vbCrLf & _
               "実行してください。", vbExclamation, APPTITLE
        WScript.Quit 1
    End If

    InitArrays
    lines = ReadAllLines(tempPath)
    ParseTemp lines

    If gItemCount = 0 Then
        WriteAllText tempPath, "he 文字が選択されていません。" & vbCrLf
        WScript.Quit 0
    End If

    '--- 揃え方の決定 -----------------------------------------
    If Not GetSettings(xMode, yMode, xVal, yVal) Then
        ' 中止。jwc_temp.txt は書き換えないので Jw_cad 側は「未実行」となり
        ' 図面は一切変更されない。
        WScript.Quit 0
    End If

    If xMode = MODE_NONE And yMode = MODE_NONE Then WScript.Quit 0

    '--- 位置計算 ---------------------------------------------
    MeasureItems
    AlignItems xMode, yMode, xVal, yVal

    '--- 出力 -------------------------------------------------
    WriteResult tempPath
End Sub

'==============================================================
' jwc_temp.txt を探す
'   Jw_cad はカレントディレクトリに作成するが、環境によって
'   バッチファイルのフォルダになることもあるので両方を見る。
'==============================================================
Function FindTempFile()
    Dim shell, cur, cand
    FindTempFile = ""

    On Error Resume Next
    Set shell = CreateObject("WScript.Shell")
    cur = shell.CurrentDirectory
    On Error GoTo 0

    If cur <> "" Then
        cand = gFso.BuildPath(cur, "jwc_temp.txt")
        If gFso.FileExists(cand) Then FindTempFile = cand : Exit Function
    End If

    cand = gFso.BuildPath(gScriptDir, "jwc_temp.txt")
    If gFso.FileExists(cand) Then FindTempFile = cand : Exit Function
End Function

'==============================================================
' 配列の初期化
'==============================================================
Sub InitArrays()
    Dim i
    For i = 0 To 10
        gHcw(i) = 0 : gHch(i) = 0 : gHcd(i) = 0
    Next
    ReDim gOut(255)   : gOutCount = 0
    ReDim gItems(63)  : gItemCount = 0
    gHasRef = False : gRefX = 0 : gRefY = 0
End Sub

'==============================================================
' jwc_temp.txt の解析
'
'   ・h で始まる行  : 図面情報（hcw/hch/hcd だけ取り込み、出力しない）
'   ・# で始まる行  : コメント（出力しない）
'   ・ch で始まる行 : 文字要素（座標を書き換えて出力）
'   ・それ以外      : 属性行(ly/lc/cn 等)や未知のデータ。
'                     hd で消えてしまうため必ずそのまま出力する。
'==============================================================
Sub ParseTemp(lines)
    Dim i, raw, t, curCw, curCh, curCd

    curCw = 0 : curCh = 0 : curCd = 0

    For i = 0 To UBound(lines)
        raw = lines(i)
        t = Trim(raw)

        If t = "" Then
            ' 空行は捨てる
        ElseIf Left(t, 1) = "#" Then
            ' コメント行は捨てる
        ElseIf Left(t, 3) = "hcw" Then
            ReadCharTable Mid(t, 4), gHcw
        ElseIf Left(t, 3) = "hch" Then
            ReadCharTable Mid(t, 4), gHch
        ElseIf Left(t, 3) = "hcd" Then
            ReadCharTable Mid(t, 4), gHcd
        ElseIf Left(t, 4) = "hp1 " Then
            ' 「REM #1」で指示された点。hp1ch / hp1ln などは対象外。
            ReadRefPoint Mid(t, 4)
        ElseIf Left(t, 1) = "h" Then
            ' その他の図面情報（hq を含む）は出力しない
        ElseIf Left(t, 2) = "cn" Then
            UpdateCharType t, curCw, curCh, curCd
            PushOut raw
        ElseIf Left(t, 3) = "ch " Or t = "ch" Then
            PushText t, curCw, curCh, curCd
        Else
            PushOut raw
        End If
    Next
End Sub

'--- hcw / hch / hcd （文字種1-10の寸法）を取り込む -----------
Sub ReadCharTable(body, ByRef tbl)
    Dim toks, i
    toks = Tokenize(body)
    For i = 0 To UBound(toks)
        If i + 1 <= 10 Then tbl(i + 1) = ParseNum(toks(i))
    Next
End Sub

'--- hp1（指示された基準点）を取り込む ------------------------
Sub ReadRefPoint(body)
    Dim toks
    toks = Tokenize(body)
    If UBound(toks) >= 1 Then
        If IsNumToken(toks(0)) And IsNumToken(toks(1)) Then
            gRefX = ParseNum(toks(0))
            gRefY = ParseNum(toks(1))
            gHasRef = True
        End If
    End If
End Sub

'--- cn 行から現在の文字種の寸法を求める ----------------------
Sub UpdateCharType(t, ByRef cw, ByRef ch_, ByRef cd)
    Dim head, toks, n

    ' 「cn0 幅 高さ 間隔 色 …」 or 「cn1」～「cn10」
    toks = Tokenize(t)
    head = toks(0)                       ' cn0 / cn3 / ...
    n = ParseNum(Mid(head, 3))

    If n = 0 Then
        ' 任意サイズ文字。同じ行に 幅 高さ 間隔 色 が並ぶ
        If UBound(toks) >= 2 Then
            cw  = ParseNum(toks(1))
            ch_ = ParseNum(toks(2))
        End If
        If UBound(toks) >= 3 Then cd = ParseNum(toks(3)) Else cd = 0
    ElseIf n >= 1 And n <= 10 Then
        cw  = gHcw(n)
        ch_ = gHch(n)
        cd  = gHcd(n)
    End If
End Sub

'--- ch 行を文字要素として登録 --------------------------------
Sub PushText(t, cw, ch_, cd)
    Dim body, nums, rest, ok, it

    body = Mid(t, 3)                      ' 「ch」の後ろ
    SplitCh body, nums, rest, ok

    If Not ok Then
        ' 想定外の書式。hd で消えないよう、そのまま出力する。
        PushOut t
        Exit Sub
    End If

    Set it = New TextItem
    it.x  = nums(0)
    it.y  = nums(1)
    it.f3 = nums(2)
    it.f4 = nums(3)
    If rest = "" Then rest = """"
    it.sPart = rest
    it.cw = cw : it.ch_ = ch_ : it.cd = cd

    PushOut ""                            ' 場所だけ確保
    it.outIndex = gOutCount - 1

    If gItemCount > UBound(gItems) Then ReDim Preserve gItems(gItemCount * 2 + 1)
    Set gItems(gItemCount) = it
    gItemCount = gItemCount + 1
End Sub

'--- 出力行の追加 ---------------------------------------------
Sub PushOut(s)
    If gOutCount > UBound(gOut) Then ReDim Preserve gOut(gOutCount * 2 + 1)
    gOut(gOutCount) = s
    gOutCount = gOutCount + 1
End Sub

'==============================================================
' 「ch」の後ろを 4 つの数値 ＋ 文字列 に分ける
'==============================================================
Sub SplitCh(ByVal body, ByRef nums, ByRef rest, ByRef ok)
    Dim i, st, tok, cnt, c
    Dim buf(3)

    cnt = 0 : i = 1 : ok = False : rest = ""

    Do While i <= Len(body) And cnt < 4
        Do While i <= Len(body)
            c = Mid(body, i, 1)
            If c <> " " And c <> vbTab Then Exit Do
            i = i + 1
        Loop
        If i > Len(body) Then Exit Do

        st = i
        Do While i <= Len(body)
            c = Mid(body, i, 1)
            If c = " " Or c = vbTab Then Exit Do
            If c = """" And i > st Then Exit Do   ' 数値と文字列が続いている場合
            i = i + 1
        Loop

        tok = Mid(body, st, i - st)
        If Not IsNumToken(tok) Then Exit Do

        buf(cnt) = ParseNum(tok)
        cnt = cnt + 1
    Loop

    nums = buf
    If cnt = 4 Then
        rest = LTrim(Mid(body, i))
        ok = True
    End If
End Sub

'==============================================================
' 各文字の占める範囲を求める
'==============================================================
Sub MeasureItems()
    Dim i, it, vx, vy, isHoriz, fmt

    fmt = ChFormat()

    For i = 0 To gItemCount - 1
        Set it = gItems(i)

        If fmt = "abs" Then
            vx = it.f3 - it.x            ' 第3・第4が終点座標の場合
            vy = it.f4 - it.y
        Else
            vx = it.f3                   ' 第3・第4が長さ成分の場合
            vy = it.f4
        End If

        it.xMin = Min2(it.x, it.x + vx)
        it.xMax = Max2(it.x, it.x + vx)
        it.yMin = Min2(it.y, it.y + vy)
        it.yMax = Max2(it.y, it.y + vy)

        ' 水平な文字だけ、文字高さぶんを上端に加える。
        ' 傾いた文字は基準点(左下)を基準に揃える。
        isHoriz = (Abs(vy) <= Abs(vx) * 0.0001)
        If isHoriz And it.ch_ > 0 Then it.yMax = it.yMax + it.ch_
    Next
End Sub

'==============================================================
' ch 第3・第4フィールドの解釈を判定する
'   rel : 文字列の長さ成分（水平文字なら第4=0）
'   abs : 文字列の終点座標  （水平文字なら第4=始点Y）
'==============================================================
Function ChFormat()
    Dim i, it, c0, cy, n, est, relErr, absErr, forced

    forced = LCase(Trim(IniGet("CHFORMAT", "auto")))
    If forced = "rel" Or forced = "abs" Then ChFormat = forced : Exit Function

    c0 = 0 : cy = 0
    For i = 0 To gItemCount - 1
        Set it = gItems(i)
        If Abs(it.f4) < EPS Then c0 = c0 + 1
        If Abs(it.f4 - it.y) < EPS And Abs(it.y) > EPS Then cy = cy + 1
    Next

    If cy > 0 And c0 = 0 Then ChFormat = "abs" : Exit Function
    If c0 > 0 And cy = 0 Then ChFormat = "rel" : Exit Function

    ' 判定できないときは文字列の長さを推定して比較する
    relErr = 0 : absErr = 0 : n = 0
    For i = 0 To gItemCount - 1
        Set it = gItems(i)
        est = EstimateWidth(it)
        If est > 0 Then
            relErr = relErr + Abs(Abs(it.f3) - est)
            absErr = absErr + Abs(Abs(it.f3 - it.x) - est)
            n = n + 1
        End If
    Next

    If n > 0 And absErr < relErr Then ChFormat = "abs" Else ChFormat = "rel"
End Function

'--- 文字種と文字数から文字列の長さを推定 ---------------------
Function EstimateWidth(it)
    Dim s, i, c, code, cnt

    EstimateWidth = 0
    If it.cw <= 0 Then Exit Function

    s = it.sPart
    If Left(s, 1) = """" Then s = Mid(s, 2)
    If Len(s) = 0 Then Exit Function

    cnt = 0
    For i = 1 To Len(s)
        c = Mid(s, i, 1)
        code = AscW(c)
        If code < 0 Then code = code + 65536
        If code < 128 Or (code >= &HFF61 And code <= &HFF9F) Then
            cnt = cnt + 0.5              ' 半角
        Else
            cnt = cnt + 1                ' 全角
        End If
    Next

    EstimateWidth = cnt * it.cw + (Len(s) - 1) * it.cd
End Function

'==============================================================
' 揃え計算
'==============================================================
Sub AlignItems(xMode, yMode, xVal, yVal)
    Dim i, it, fmt, refIdx

    fmt = ChFormat()
    refIdx = FindRefItem()

    For i = 0 To gItemCount - 1
        gItems(i).dx = 0
        gItems(i).dy = 0
    Next

    AlignAxis True,  xMode, xVal, refIdx
    AlignAxis False, yMode, yVal, refIdx

    For i = 0 To gItemCount - 1
        Set it = gItems(i)

        it.x = it.x + it.dx
        it.y = it.y + it.dy
        If fmt = "abs" Then
            it.f3 = it.f3 + it.dx        ' 終点座標も動かす
            it.f4 = it.f4 + it.dy
        End If

        gOut(it.outIndex) = "ch " & FmtNum(it.x) & " " & FmtNum(it.y) & " " & _
                            FmtNum(it.f3) & " " & FmtNum(it.f4) & " " & it.sPart
    Next
End Sub

'--- 片方向（横 or 縦）の移動量を求める -----------------------
'   isX = True なら横方向、False なら縦方向
Sub AlignAxis(isX, mode, val, refIdx)
    Dim i, it, lo, hi, target, e

    If mode = MODE_NONE Then Exit Sub

    If mode = MODE_SPACE Or mode = MODE_GAP Then
        SpreadAxis isX, mode
        Exit Sub
    End If

    '--- 合わせる先の座標を決める -----------------------------
    If mode = MODE_VALUE Then
        target = val
    ElseIf refIdx >= 0 Then
        ' 指示された基準文字に合わせる
        Set it = gItems(refIdx)
        Select Case mode
            Case MODE_MIN    : target = EdgeMin(it, isX)
            Case MODE_MAX    : target = EdgeMax(it, isX)
            Case MODE_CENTER : target = (EdgeMin(it, isX) + EdgeMax(it, isX)) / 2
        End Select
    Else
        ' 選択した文字全体を基準にする
        lo = EdgeMin(gItems(0), isX)
        hi = EdgeMax(gItems(0), isX)
        For i = 1 To gItemCount - 1
            Set it = gItems(i)
            If EdgeMin(it, isX) < lo Then lo = EdgeMin(it, isX)
            If EdgeMax(it, isX) > hi Then hi = EdgeMax(it, isX)
        Next
        Select Case mode
            Case MODE_MIN    : target = lo
            Case MODE_MAX    : target = hi
            Case MODE_CENTER : target = (lo + hi) / 2
        End Select
    End If

    '--- 各文字の移動量 ---------------------------------------
    For i = 0 To gItemCount - 1
        Set it = gItems(i)
        Select Case mode
            Case MODE_MIN, MODE_VALUE : e = EdgeMin(it, isX)
            Case MODE_MAX             : e = EdgeMax(it, isX)
            Case MODE_CENTER          : e = (EdgeMin(it, isX) + EdgeMax(it, isX)) / 2
        End Select
        AddDelta it, isX, target - e
    Next
End Sub

'--- 等間隔配置 -----------------------------------------------
'   両端の文字は動かさず、間の文字を割り付ける。
'     MODE_SPACE … 文字の左端(下端)どうしを等間隔にする
'     MODE_GAP   … 文字と文字のすき間を等間隔にする
Sub SpreadAxis(isX, mode)
    Dim idx()
    Dim n, i, j, k, tmp, cur, gapv, sumW, spanStart, spanEnd, stepv

    n = gItemCount
    If n < 3 Then Exit Sub               ' 2個以下は割り付けようがない

    ReDim idx(n - 1)
    For i = 0 To n - 1
        idx(i) = i
    Next

    ' 挿入ソート（小さい側の端で並べ替え）
    For i = 1 To n - 1
        tmp = idx(i)
        j = i - 1
        Do While j >= 0
            If EdgeMin(gItems(idx(j)), isX) <= EdgeMin(gItems(tmp), isX) Then Exit Do
            idx(j + 1) = idx(j)
            j = j - 1
        Loop
        idx(j + 1) = tmp
    Next

    spanStart = EdgeMin(gItems(idx(0)), isX)

    If mode = MODE_SPACE Then
        spanEnd = EdgeMin(gItems(idx(n - 1)), isX)
        stepv = (spanEnd - spanStart) / (n - 1)
        For k = 0 To n - 1
            AddDelta gItems(idx(k)), isX, _
                     (spanStart + stepv * k) - EdgeMin(gItems(idx(k)), isX)
        Next
    Else
        spanEnd = EdgeMax(gItems(idx(n - 1)), isX)
        sumW = 0
        For k = 0 To n - 1
            sumW = sumW + (EdgeMax(gItems(idx(k)), isX) - EdgeMin(gItems(idx(k)), isX))
        Next
        gapv = (spanEnd - spanStart - sumW) / (n - 1)
        cur = spanStart
        For k = 0 To n - 1
            AddDelta gItems(idx(k)), isX, cur - EdgeMin(gItems(idx(k)), isX)
            cur = cur + (EdgeMax(gItems(idx(k)), isX) - EdgeMin(gItems(idx(k)), isX)) + gapv
        Next
    End If
End Sub

'--- 指示された基準点に一番近い文字を探す ---------------------
Function FindRefItem()
    Dim i, it, d, best, bestIdx

    FindRefItem = -1
    If Not gHasRef Then Exit Function

    bestIdx = -1
    For i = 0 To gItemCount - 1
        Set it = gItems(i)
        d = RectDist(gRefX, gRefY, it.xMin, it.yMin, it.xMax, it.yMax)
        If bestIdx < 0 Then
            best = d : bestIdx = i
        ElseIf d < best Then
            best = d : bestIdx = i
        End If
    Next

    FindRefItem = bestIdx
End Function

'--- 点と長方形の距離（内側なら 0） ---------------------------
Function RectDist(px, py, x1, y1, x2, y2)
    Dim ddx, ddy

    ddx = 0 : ddy = 0
    If px < x1 Then ddx = x1 - px
    If px > x2 Then ddx = px - x2
    If py < y1 Then ddy = y1 - py
    If py > y2 Then ddy = py - y2

    RectDist = Sqr(ddx * ddx + ddy * ddy)
End Function

Function EdgeMin(it, isX)
    If isX Then EdgeMin = it.xMin Else EdgeMin = it.yMin
End Function

Function EdgeMax(it, isX)
    If isX Then EdgeMax = it.xMax Else EdgeMax = it.yMax
End Function

Sub AddDelta(it, isX, d)
    If isX Then it.dx = it.dx + d Else it.dy = it.dy + d
End Sub

'==============================================================
' 結果の書き出し
'   先頭の hd で、選択された元の文字を削除する。
'==============================================================
Sub WriteResult(tempPath)
    Dim i, sb

    sb = "hd" & vbCrLf
    For i = 0 To gOutCount - 1
        If gOut(i) <> "" Then sb = sb & gOut(i) & vbCrLf
    Next

    WriteAllText tempPath, sb
End Sub

'==============================================================
' 揃え方の取得（引数 → ダイアログ）
'   戻り値 : False なら中止
'==============================================================
Function GetSettings(ByRef xMode, ByRef yMode, ByRef xVal, ByRef yVal)
    Dim args, quiet, s

    GetSettings = False
    Set args = WScript.Arguments.Named
    quiet = args.Exists("q")

    xMode = ModeOf(ParseNum(IniGet("X", "1")))
    yMode = ModeOf(ParseNum(IniGet("Y", "0")))
    xVal  = ParseNum(IniGet("XV", "0"))
    yVal  = ParseNum(IniGet("YV", "0"))

    If args.Exists("x")  Then xMode = ModeOf(ParseNum(args("x")))
    If args.Exists("y")  Then yMode = ModeOf(ParseNum(args("y")))
    If args.Exists("xv") Then xVal  = ParseNum(args("xv"))
    If args.Exists("yv") Then yVal  = ParseNum(args("yv"))

    If Not quiet Then
        s = InputBox( _
            "横方向(X)の揃え方を番号で指定してください。" & vbCrLf & vbCrLf & _
            "  0 : 揃えない" & vbCrLf & _
            "  1 : 左揃え  （" & RefWord("指示した文字の左端に合わせる", _
                                        "一番左の文字に合わせる") & "）" & vbCrLf & _
            "  2 : 中央揃え（" & RefWord("指示した文字の中心に合わせる", _
                                        "左右の中心に合わせる") & "）" & vbCrLf & _
            "  3 : 右揃え  （" & RefWord("指示した文字の右端に合わせる", _
                                        "一番右の文字に合わせる") & "）" & vbCrLf & _
            "  4 : X座標を数値で指定（文字の左端）" & vbCrLf & _
            "  5 : 等間隔（文字の左端どうしを等間隔に）" & vbCrLf & _
            "  6 : 等間隔（文字のすき間を等間隔に）" & vbCrLf & vbCrLf & _
            "選択された文字 : " & gItemCount & " 個" & RefNote() & vbCrLf & _
            "（空欄のまま OK、または キャンセル で中止）", _
            APPTITLE & " (1/2) 横方向", CStr(xMode))
        If Trim(s) = "" Then Exit Function
        xMode = ModeOf(ParseNum(s))

        If xMode = MODE_VALUE Then
            s = InputBox("文字の左端を合わせる X座標を入力してください。", _
                         APPTITLE & " 基準X座標", FmtNum(xVal))
            If Trim(s) = "" Then Exit Function
            xVal = ParseNum(s)
        End If

        s = InputBox( _
            "縦方向(Y)の揃え方を番号で指定してください。" & vbCrLf & vbCrLf & _
            "  0 : 揃えない" & vbCrLf & _
            "  1 : 下揃え  （" & RefWord("指示した文字の下端に合わせる", _
                                        "一番下の文字に合わせる") & "）" & vbCrLf & _
            "  2 : 中央揃え（" & RefWord("指示した文字の中心に合わせる", _
                                        "上下の中心に合わせる") & "）" & vbCrLf & _
            "  3 : 上揃え  （" & RefWord("指示した文字の上端に合わせる", _
                                        "一番上の文字に合わせる") & "）" & vbCrLf & _
            "  4 : Y座標を数値で指定（文字の下端）" & vbCrLf & _
            "  5 : 等間隔（文字の下端どうしを等間隔に）" & vbCrLf & _
            "  6 : 等間隔（文字のすき間を等間隔に）" & vbCrLf & vbCrLf & _
            "（空欄のまま OK、または キャンセル で中止）", _
            APPTITLE & " (2/2) 縦方向", CStr(yMode))
        If Trim(s) = "" Then Exit Function
        yMode = ModeOf(ParseNum(s))

        If yMode = MODE_VALUE Then
            s = InputBox("文字の下端を合わせる Y座標を入力してください。", _
                         APPTITLE & " 基準Y座標", FmtNum(yVal))
            If Trim(s) = "" Then Exit Function
            yVal = ParseNum(s)
        End If

        SaveIni xMode, yMode, xVal, yVal
    End If

    GetSettings = True
End Function

'==============================================================
' 設定ファイル（前回値の記憶）
'==============================================================
Function IniGet(key, defVal)
    Dim f, line, p, k

    IniGet = defVal
    If Not gFso.FileExists(gIniPath) Then Exit Function

    On Error Resume Next
    Set f = gFso.OpenTextFile(gIniPath, 1, False)
    If Err.Number <> 0 Then Err.Clear : Exit Function

    Do Until f.AtEndOfStream
        line = Trim(f.ReadLine)
        p = InStr(line, "=")
        If p > 1 And Left(line, 1) <> "[" And Left(line, 1) <> ";" Then
            k = UCase(Trim(Left(line, p - 1)))
            If k = UCase(key) Then IniGet = Trim(Mid(line, p + 1))
        End If
    Loop
    f.Close
    On Error GoTo 0
End Function

Sub SaveIni(xMode, yMode, xVal, yVal)
    Dim f
    On Error Resume Next
    Set f = gFso.CreateTextFile(gIniPath, True, False)
    If Err.Number <> 0 Then Err.Clear : Exit Sub
    f.WriteLine "[jww_text_align]"
    f.WriteLine "X=" & xMode
    f.WriteLine "Y=" & yMode
    f.WriteLine "XV=" & FmtNum(xVal)
    f.WriteLine "YV=" & FmtNum(yVal)
    f.WriteLine "; CHFORMAT : auto / rel / abs"
    f.WriteLine "CHFORMAT=" & IniGet("CHFORMAT", "auto")
    f.Close
    On Error GoTo 0
End Sub

'==============================================================
' ファイル入出力（Shift_JIS）
'==============================================================
Function ReadAllLines(path)
    Dim st, txt, f

    txt = Empty
    On Error Resume Next
    Set st = CreateObject("ADODB.Stream")
    If Err.Number = 0 Then
        st.Type = 2
        st.Charset = "shift_jis"
        st.Open
        st.LoadFromFile path
        txt = st.ReadText(-1)
        st.Close
    End If
    If Err.Number <> 0 Or IsEmpty(txt) Then
        Err.Clear
        Set f = gFso.OpenTextFile(path, 1, False)
        If Not f.AtEndOfStream Then txt = f.ReadAll Else txt = ""
        f.Close
    End If
    On Error GoTo 0

    txt = Replace(txt, vbCrLf, vbLf)
    txt = Replace(txt, vbCr, vbLf)
    ReadAllLines = Split(txt, vbLf)
End Function

Sub WriteAllText(path, txt)
    Dim st, f, done

    done = False
    On Error Resume Next
    Set st = CreateObject("ADODB.Stream")
    If Err.Number = 0 Then
        st.Type = 2
        st.Charset = "shift_jis"
        st.Open
        st.WriteText txt
        st.SaveToFile path, 2
        st.Close
        If Err.Number = 0 Then done = True
    End If
    If Not done Then
        Err.Clear
        Set f = gFso.CreateTextFile(path, True, False)
        f.Write txt
        f.Close
    End If
    On Error GoTo 0
End Sub

'==============================================================
' 数値の入出力（小数点がロケールに影響されないよう自前で処理）
'==============================================================
Function Tokenize(s)
    Dim i, st, c, n
    Dim res()

    ReDim res(31)
    n = 0 : i = 1
    Do While i <= Len(s)
        Do While i <= Len(s)
            c = Mid(s, i, 1)
            If c <> " " And c <> vbTab Then Exit Do
            i = i + 1
        Loop
        If i > Len(s) Then Exit Do

        st = i
        Do While i <= Len(s)
            c = Mid(s, i, 1)
            If c = " " Or c = vbTab Then Exit Do
            i = i + 1
        Loop

        If n > UBound(res) Then ReDim Preserve res(n * 2 + 1)
        res(n) = Mid(s, st, i - st)
        n = n + 1
    Loop

    If n = 0 Then
        ReDim res(0)
        res(0) = ""
    Else
        ReDim Preserve res(n - 1)
    End If
    Tokenize = res
End Function

Function IsNumToken(s)
    Dim i, c, digits, dots

    IsNumToken = False
    s = Trim(s)
    If Len(s) = 0 Then Exit Function

    digits = 0 : dots = 0
    For i = 1 To Len(s)
        c = Mid(s, i, 1)
        If c >= "0" And c <= "9" Then
            digits = digits + 1
        ElseIf c = "." Then
            dots = dots + 1
            If dots > 1 Then Exit Function
        ElseIf c = "+" Or c = "-" Then
            If i > 1 Then
                If UCase(Mid(s, i - 1, 1)) <> "E" Then Exit Function
            End If
        ElseIf UCase(c) = "E" Then
            If digits = 0 Then Exit Function
        Else
            Exit Function
        End If
    Next

    IsNumToken = (digits > 0)
End Function

Function ParseNum(ByVal s)
    Dim i, c, sign, ip, fp, fs, seen, v, esign, ep

    ParseNum = 0
    s = Trim(s)
    If Len(s) = 0 Then Exit Function

    sign = 1 : i = 1
    c = Mid(s, 1, 1)
    If c = "+" Then i = 2
    If c = "-" Then sign = -1 : i = 2

    ip = 0 : fp = 0 : fs = 1 : seen = False

    Do While i <= Len(s)
        c = Mid(s, i, 1)
        If c < "0" Or c > "9" Then Exit Do
        ip = ip * 10 + (Asc(c) - 48)
        seen = True
        i = i + 1
    Loop

    If i <= Len(s) Then
        c = Mid(s, i, 1)
        If c = "." Or c = "," Then
            i = i + 1
            Do While i <= Len(s)
                c = Mid(s, i, 1)
                If c < "0" Or c > "9" Then Exit Do
                fs = fs * 10
                fp = fp * 10 + (Asc(c) - 48)
                seen = True
                i = i + 1
            Loop
        End If
    End If

    If Not seen Then Exit Function
    v = ip + fp / fs

    If i <= Len(s) Then
        If UCase(Mid(s, i, 1)) = "E" Then
            i = i + 1
            esign = 1 : ep = 0
            If i <= Len(s) Then
                c = Mid(s, i, 1)
                If c = "+" Then i = i + 1
                If c = "-" Then esign = -1 : i = i + 1
            End If
            Do While i <= Len(s)
                c = Mid(s, i, 1)
                If c < "0" Or c > "9" Then Exit Do
                ep = ep * 10 + (Asc(c) - 48)
                i = i + 1
            Loop
            If ep > 0 Then v = v * (10 ^ (esign * ep))
        End If
    End If

    ParseNum = sign * v
End Function

Function FmtNum(ByVal v)
    Dim neg, scaled, ip, fp, fs, s

    If Abs(v) < 0.0000005 Then FmtNum = "0" : Exit Function

    neg = (v < 0)
    v = Abs(v)

    scaled = Int(v * 1000000 + 0.5)
    ip = Int(scaled / 1000000)
    fp = scaled - ip * 1000000

    fs = Right("00000" & CStr(CLng(fp)), 6)
    Do While Len(fs) > 0
        If Right(fs, 1) <> "0" Then Exit Do
        fs = Left(fs, Len(fs) - 1)
    Loop

    s = CStr(ip)
    If InStr(s, ".") > 0 Then s = Left(s, InStr(s, ".") - 1)
    If InStr(s, ",") > 0 Then s = Left(s, InStr(s, ",") - 1)
    If Len(fs) > 0 Then s = s & "." & fs
    If neg Then s = "-" & s

    FmtNum = s
End Function

'--- 揃えモードの正規化（範囲外・巨大値でも落ちないように） ----
Function ModeOf(v)
    If v < 0 Or v > MODE_MAXNO Then
        ModeOf = MODE_NONE
    Else
        ModeOf = CInt(v)
    End If
End Function

'--- ダイアログ用の文言（基準文字の指示があるかで変える） ------
Function RefWord(withRef, noRef)
    If gHasRef Then RefWord = withRef Else RefWord = noRef
End Function

Function RefNote()
    If gHasRef Then
        RefNote = " / 基準文字の指示あり"
    Else
        RefNote = ""
    End If
End Function

Function Min2(a, b)
    If a < b Then Min2 = a Else Min2 = b
End Function

Function Max2(a, b)
    If a > b Then Max2 = a Else Max2 = b
End Function
