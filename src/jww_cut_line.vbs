Option Explicit
'==============================================================
' Jw_cad 外部変形 : 線切断   jww_cut_line.vbs
'
'   範囲選択した線データを、重なっている円・円弧・楕円・曲線
'   との交点で切断（分割）します。
'
'   ・バッチファイル(*.bat)から cscript で呼び出されます。
'   ・単体では動きません（jwc_temp.txt が必要）。
'
'   引数（省略時は入力ダイアログで指定）
'     /c:1       円・円弧・楕円・曲線 を切断の基準にする（既定）
'     /c:2       上記に加えて 直線 も切断の基準にする
'     /tol:数値  これより短い切れ端は作らない（既定 0.0001）
'     /q         ダイアログを出さない（引数だけで実行）
'
'   Jw_cad Version 8.20 で使用する想定
'==============================================================

'--- 要素の種類 -----------------------------------------------
Const KIND_RAW  = 0    ' そのまま書き戻す行（文字・点・属性など）
Const KIND_LINE = 1    ' 線データ
Const KIND_ARC  = 2    ' 円・円弧・楕円・楕円弧

'--- 切断の基準 -----------------------------------------------
Const CUT_ARC = 1      ' 円・円弧・楕円・曲線
Const CUT_ALL = 2      ' 上記＋直線

Const APPTITLE = "線切断"
Const EPS      = 0.000001

'--- グローバル -----------------------------------------------
Dim gFso        : Set gFso = CreateObject("Scripting.FileSystemObject")
Dim gScriptDir  : gScriptDir = gFso.GetParentFolderName(WScript.ScriptFullName)
Dim gIniPath    : gIniPath = gFso.BuildPath(gScriptDir, "jww_cut_line.ini")
Dim gPI         : gPI = 4 * Atn(1)

Dim gElems()                        ' 読み込んだ要素
Dim gElemCount                      ' 要素数
Dim gS()                            ' いま処理中の線の切断位置(0〜1)
Dim gSCount                         ' 切断位置の数
Dim gCurLen                         ' いま処理中の線の長さ
Dim gTol                            ' 許容誤差（これより短い切れ端は作らない）
Dim gLineCount                      ' 切断できる線の本数
Dim gArcCount                       ' 円・円弧の個数
Dim gCurveCount                     ' 曲線を構成する線の本数

'--- 要素 -----------------------------------------------------
Class Elem
    Public kind
    Public text                     ' 書き戻す文字列（切断後は複数行になる）
    Public x1, y1, x2, y2           ' 線データ
    Public cx, cy, r                ' 円・円弧の中心と半径
    Public sa, ea                   ' 始角・終角（度）
    Public flat, tilt               ' 扁平率・傾き（度）
    Public inCurve                  ' 曲線属性の中にあるか
End Class

Main

'==============================================================
' メイン
'==============================================================
Sub Main()
    Dim tempPath, lines, cutMode, nCut

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

    If gLineCount = 0 Then
        AbortWith tempPath, "切断できる線データが選択されていません。"
    End If

    '--- 切断の基準を決める -----------------------------------
    If Not GetSettings(cutMode) Then
        ' 中止。jwc_temp.txt は書き換えないので Jw_cad 側は「未実行」となり
        ' 図面は一切変更されない。
        WScript.Quit 0
    End If

    If cutMode = CUT_ARC And gArcCount = 0 And gCurveCount = 0 Then
        AbortWith tempPath, "切断の基準になる円・円弧・曲線が選択されていません。"
    End If

    '--- 交点を求めて切断 -------------------------------------
    nCut = CutAll(cutMode)

    If nCut = 0 Then
        AbortWith tempPath, "重なっている所がありませんでした。線は切断していません。"
    End If

    WriteResult tempPath
End Sub

'--- 何もせずに終わる（図面は変更されない） -------------------
Sub AbortWith(tempPath, msg)
    WriteAllText tempPath, "he " & msg & vbCrLf
    WScript.Quit 0
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
    ReDim gElems(255) : gElemCount = 0
    ReDim gS(31)      : gSCount = 0
    gCurLen = 0
    gTol = 0.0001
    gLineCount = 0 : gArcCount = 0 : gCurveCount = 0
End Sub

'==============================================================
' jwc_temp.txt の解析
'
'   ・h で始まる行   : 図面情報（出力しない。hq を消すことで
'                      Jw_cad 側が「実行済み」と判断する）
'   ・# で始まる行   : コメント（出力しない）
'   ・cs / ce        : 曲線属性の開始・終了。その間の線は曲線の
'                      一部なので、切断せずに切断の基準にする
'   ・ci で始まる行  : 円・円弧・楕円（切断の基準）
'   ・数値 4 つの行  : 線データ（切断の対象）
'   ・それ以外       : 文字・点・属性など。hd で消えてしまうため
'                      必ずそのまま出力する。
'==============================================================
Sub ParseTemp(lines)
    Dim i, raw, t, curve

    curve = False

    For i = 0 To UBound(lines)
        raw = lines(i)
        t = Trim(raw)

        If t = "" Then
            ' 空行は捨てる
        ElseIf Left(t, 1) = "#" Then
            ' コメント行は捨てる
        ElseIf IsWord(t, "cs") Then
            curve = True
            PushRaw raw
        ElseIf IsWord(t, "ce") Then
            curve = False
            PushRaw raw
        ElseIf Left(t, 1) = "h" Then
            ' 図面情報（hq を含む）は出力しない
        ElseIf Left(t, 3) = "ci " Then
            PushArc t, raw
        Else
            PushData t, raw, curve
        End If
    Next
End Sub

'--- 「cs」「ce」など単独の語かどうか -------------------------
Function IsWord(t, w)
    IsWord = (t = w) Or (Left(t, Len(w) + 1) = w & " ") Or _
             (Left(t, Len(w) + 1) = w & vbTab)
End Function

'--- 数値 4 つの行なら線データとして登録 ----------------------
Sub PushData(t, raw, curve)
    Dim toks, e

    toks = Tokenize(t)
    If UBound(toks) = 3 Then
        If IsNumToken(toks(0)) And IsNumToken(toks(1)) And _
           IsNumToken(toks(2)) And IsNumToken(toks(3)) Then

            Set e = NewElem(KIND_LINE, raw)
            e.x1 = ParseNum(toks(0)) : e.y1 = ParseNum(toks(1))
            e.x2 = ParseNum(toks(2)) : e.y2 = ParseNum(toks(3))
            e.inCurve = curve
            PushElem e

            If curve Then
                gCurveCount = gCurveCount + 1
            Else
                gLineCount = gLineCount + 1
            End If
            Exit Sub
        End If
    End If

    ' 線データではない行（文字・点・属性・未知のデータ）
    PushRaw raw
End Sub

'--- ci 行を円・円弧として登録 --------------------------------
'     ci 中心X 中心Y 半径                                … 円
'     ci 中心X 中心Y 半径 始角 終角 扁平率 傾き          … 円弧・楕円
Sub PushArc(t, raw)
    Dim toks, i, n, e

    toks = Tokenize(Mid(t, 3))
    n = 0
    For i = 0 To UBound(toks)
        If Not IsNumToken(toks(i)) Then Exit For
        n = n + 1
    Next

    If n < 3 Then PushRaw raw : Exit Sub

    Set e = NewElem(KIND_ARC, raw)
    e.cx = ParseNum(toks(0))
    e.cy = ParseNum(toks(1))
    e.r  = Abs(ParseNum(toks(2)))
    e.sa = 0 : e.ea = 0            ' 始角=終角 は全周とみなす
    e.flat = 1 : e.tilt = 0

    If n >= 7 Then
        e.sa   = ParseNum(toks(3))
        e.ea   = ParseNum(toks(4))
        e.flat = ParseNum(toks(5))
        e.tilt = ParseNum(toks(6))
        If Abs(e.flat) <= EPS Then e.flat = 1
    End If

    If e.r <= EPS Then PushRaw raw : Exit Sub    ' 半径 0 は基準にしない

    PushElem e
    gArcCount = gArcCount + 1
End Sub

'--- 要素の生成・登録 -----------------------------------------
Function NewElem(kind, raw)
    Dim e
    Set e = New Elem
    e.kind = kind
    e.text = raw
    e.inCurve = False
    e.flat = 1 : e.tilt = 0
    Set NewElem = e
End Function

Sub PushRaw(raw)
    PushElem NewElem(KIND_RAW, raw)
End Sub

Sub PushElem(e)
    If gElemCount > UBound(gElems) Then ReDim Preserve gElems(gElemCount * 2 + 1)
    Set gElems(gElemCount) = e
    gElemCount = gElemCount + 1
End Sub

'==============================================================
' すべての線を切断する
'   戻り値 : 切断した箇所の数
'==============================================================
Function CutAll(cutMode)
    Dim i, j, e, c, total

    total = 0

    For i = 0 To gElemCount - 1
        Set e = gElems(i)
        If IsTarget(e) Then
            gSCount = 0
            gCurLen = Dist(e.x1, e.y1, e.x2, e.y2)

            If gCurLen > gTol Then
                For j = 0 To gElemCount - 1
                    If j <> i Then
                        Set c = gElems(j)
                        If IsCutter(c, cutMode) Then
                            If BoxOverlap(e, c) Then
                                If c.kind = KIND_ARC Then
                                    CrossLineArc e, c
                                Else
                                    CrossLineLine e, c
                                End If
                            End If
                        End If
                    End If
                Next
            End If

            If gSCount > 0 Then
                SortS
                ApplyCuts e
                total = total + gSCount
            End If
        End If
    Next

    CutAll = total
End Function

'--- 切断される側か（曲線の一部は切断しない） -----------------
Function IsTarget(e)
    IsTarget = (e.kind = KIND_LINE) And (Not e.inCurve)
End Function

'--- 切断する側か ---------------------------------------------
Function IsCutter(e, cutMode)
    If e.kind = KIND_ARC Then
        IsCutter = True
    ElseIf e.kind = KIND_LINE Then
        ' 曲線は線の集まりとして渡ってくるので、その線は常に基準になる
        IsCutter = e.inCurve Or (cutMode = CUT_ALL)
    Else
        IsCutter = False
    End If
End Function

'--- 外接長方形が重なっているか（総当たりを減らすための前判定） -
Function BoxOverlap(a, b)
    Dim ax1, ay1, ax2, ay2, bx1, by1, bx2, by2

    ElemBox a, ax1, ay1, ax2, ay2
    ElemBox b, bx1, by1, bx2, by2

    BoxOverlap = Not (ax1 > bx2 + gTol Or bx1 > ax2 + gTol Or _
                      ay1 > by2 + gTol Or by1 > ay2 + gTol)
End Function

Sub ElemBox(e, ByRef x1, ByRef y1, ByRef x2, ByRef y2)
    Dim rr

    If e.kind = KIND_ARC Then
        ' 円弧の一部でも、まず外接する円（楕円）で判定する
        rr = e.r * Max2(1, Abs(e.flat))
        x1 = e.cx - rr : x2 = e.cx + rr
        y1 = e.cy - rr : y2 = e.cy + rr
    Else
        x1 = Min2(e.x1, e.x2) : x2 = Max2(e.x1, e.x2)
        y1 = Min2(e.y1, e.y2) : y2 = Max2(e.y1, e.y2)
    End If
End Sub

'==============================================================
' 線 L と 円・円弧 A の交点
'
'   楕円を円に戻す座標系（中心へ平行移動 → 傾きぶん逆回転 →
'   Y を扁平率で割る）に線を写すと、ただの直線と円の交点になる。
'   線の媒介変数 s は平行移動・回転・拡大で変わらないので、
'   求めた s をそのまま元の線の切断位置として使える。
'==============================================================
Sub CrossLineArc(L, A)
    Dim ca, sn, ux, uy, ax, ay, bx, by, dx, dy
    Dim qa, qb, qc, disc, sq, k, s, qx, qy

    ca = CosD(A.tilt)
    sn = SinD(A.tilt)

    ux = L.x1 - A.cx : uy = L.y1 - A.cy
    ax = ux * ca + uy * sn
    ay = (uy * ca - ux * sn) / A.flat

    ux = L.x2 - A.cx : uy = L.y2 - A.cy
    bx = ux * ca + uy * sn
    by = (uy * ca - ux * sn) / A.flat

    dx = bx - ax : dy = by - ay
    qa = dx * dx + dy * dy
    If qa <= 0 Then Exit Sub

    qb = 2 * (ax * dx + ay * dy)
    qc = ax * ax + ay * ay - A.r * A.r
    disc = qb * qb - 4 * qa * qc
    If disc < 0 Then Exit Sub

    sq = Sqr(disc)
    For k = 0 To 1
        If k = 0 Then
            s = (-qb - sq) / (2 * qa)
        Else
            s = (-qb + sq) / (2 * qa)
        End If

        qx = ax + s * dx
        qy = ay + s * dy
        If InArcRange(A, qx, qy) Then AddS s

        If sq <= 0 Then Exit For          ' 接している（重解）
    Next
End Sub

'--- 交点が円弧の描かれている範囲にあるか ---------------------
Function InArcRange(A, qx, qy)
    Dim span, d

    span = NormDeg(A.ea - A.sa)
    If span < EPS Then span = 360        ' 円（始角=終角）は全周
    If span >= 360 - EPS Then InArcRange = True : Exit Function

    d = NormDeg(Atan2Deg(qy, qx) - A.sa)
    ' d が 360 のすぐ手前なら、始角ぴったりの点が回り込んだもの
    InArcRange = (d <= span + EPS) Or (d >= 360 - EPS)
End Function

'==============================================================
' 線 L と 線 M の交点
'   M 側は端点を含めて内側にあれば交点とみなす（曲線のつなぎ目
'   をまたぐときに取りこぼさないため）。
'==============================================================
Sub CrossLineLine(L, M)
    Dim dx1, dy1, dx2, dy2, len1, len2, den, ex, ey, s, u, mt

    dx1 = L.x2 - L.x1 : dy1 = L.y2 - L.y1
    dx2 = M.x2 - M.x1 : dy2 = M.y2 - M.y1

    len1 = Sqr(dx1 * dx1 + dy1 * dy1)
    len2 = Sqr(dx2 * dx2 + dy2 * dy2)
    If len1 <= 0 Or len2 <= 0 Then Exit Sub

    den = dx1 * dy2 - dy1 * dx2
    ' 平行（重なっている場合も含む）は切断しない
    If Abs(den) <= len1 * len2 * 0.000000000001 Then Exit Sub

    ex = M.x1 - L.x1 : ey = M.y1 - L.y1
    s = (ex * dy2 - ey * dx2) / den
    u = (ex * dy1 - ey * dx1) / den

    mt = gTol / len2
    If u < -mt Or u > 1 + mt Then Exit Sub

    AddS s
End Sub

'==============================================================
' 切断位置の登録
'   ・端に寄りすぎている交点は捨てる（長さ 0 の線を作らない）
'   ・同じ場所の交点は 1 回だけ登録する
'==============================================================
Sub AddS(s)
    Dim k, d

    If gCurLen <= 0 Then Exit Sub
    d = gTol / gCurLen

    If s <= d Or s >= 1 - d Then Exit Sub

    For k = 0 To gSCount - 1
        If Abs(gS(k) - s) <= d Then Exit Sub
    Next

    If gSCount > UBound(gS) Then ReDim Preserve gS(gSCount * 2 + 1)
    gS(gSCount) = s
    gSCount = gSCount + 1
End Sub

'--- 切断位置を昇順に並べ替える（挿入ソート） -----------------
Sub SortS()
    Dim i, j, v

    For i = 1 To gSCount - 1
        v = gS(i)
        j = i - 1
        Do While j >= 0
            If gS(j) <= v Then Exit Do
            gS(j + 1) = gS(j)
            j = j - 1
        Loop
        gS(j + 1) = v
    Next
End Sub

'--- 切断位置で線を分割し、書き戻す文字列を作る ---------------
Sub ApplyCuts(e)
    Dim buf(), k, t0, t1, ax, ay, bx, by

    ReDim buf(gSCount)
    t0 = 0

    For k = 0 To gSCount
        If k < gSCount Then t1 = gS(k) Else t1 = 1

        If k = 0 Then
            ' 最初の切れ端の始点は元の座標をそのまま使う
            ax = e.x1 : ay = e.y1
        Else
            ax = e.x1 + (e.x2 - e.x1) * t0
            ay = e.y1 + (e.y2 - e.y1) * t0
        End If

        If k = gSCount Then
            ' 最後の切れ端の終点も元の座標をそのまま使う
            bx = e.x2 : by = e.y2
        Else
            bx = e.x1 + (e.x2 - e.x1) * t1
            by = e.y1 + (e.y2 - e.y1) * t1
        End If

        buf(k) = FmtNum(ax) & " " & FmtNum(ay) & " " & _
                 FmtNum(bx) & " " & FmtNum(by)
        t0 = t1
    Next

    e.text = Join(buf, vbCrLf)
End Sub

'==============================================================
' 結果の書き出し
'   先頭の hd で、選択された元のデータを削除する。
'   切断しなかった要素は読み込んだ行をそのまま書き戻す。
'==============================================================
Sub WriteResult(tempPath)
    Dim buf(), n, i

    ReDim buf(gElemCount)
    buf(0) = "hd"
    n = 1

    For i = 0 To gElemCount - 1
        If gElems(i).text <> "" Then
            buf(n) = gElems(i).text
            n = n + 1
        End If
    Next

    ReDim Preserve buf(n - 1)
    WriteAllText tempPath, Join(buf, vbCrLf) & vbCrLf
End Sub

'==============================================================
' 設定の取得（引数 → ダイアログ）
'   戻り値 : False なら中止
'==============================================================
Function GetSettings(ByRef cutMode)
    Dim args, quiet, s

    GetSettings = False
    Set args = WScript.Arguments.Named
    quiet = args.Exists("q")

    cutMode = CutOf(ParseNum(IniGet("CUT", "1")))
    gTol = ParseNum(IniGet("TOL", "0.0001"))
    If gTol <= 0 Then gTol = 0.0001

    If args.Exists("c")   Then cutMode = CutOf(ParseNum(args("c")))
    If args.Exists("tol") Then
        gTol = ParseNum(args("tol"))
        If gTol <= 0 Then gTol = 0.0001
    End If

    If Not quiet Then
        s = InputBox( _
            "切断の基準にする要素を番号で指定してください。" & vbCrLf & vbCrLf & _
            "  1 : 円・円弧・楕円・曲線で切断する" & vbCrLf & _
            "  2 : 直線でも切断する（すべての要素で切断）" & vbCrLf & vbCrLf & _
            "選択された要素" & vbCrLf & _
            "  切断できる線 : " & gLineCount & " 本" & vbCrLf & _
            "  円・円弧     : " & gArcCount & " 個" & vbCrLf & _
            "  曲線の線     : " & gCurveCount & " 本" & vbCrLf & vbCrLf & _
            "（空欄のまま OK、または キャンセル で中止）", _
            APPTITLE, CStr(cutMode))
        If Trim(s) = "" Then Exit Function
        cutMode = CutOf(ParseNum(s))
        SaveIni cutMode
    End If

    GetSettings = True
End Function

'--- 基準の正規化（範囲外の値でも落ちないように） -------------
Function CutOf(v)
    If v = CUT_ALL Then CutOf = CUT_ALL Else CutOf = CUT_ARC
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

Sub SaveIni(cutMode)
    Dim f
    On Error Resume Next
    Set f = gFso.CreateTextFile(gIniPath, True, False)
    If Err.Number <> 0 Then Err.Clear : Exit Sub
    f.WriteLine "[jww_cut_line]"
    f.WriteLine "; CUT : 1=円・円弧・曲線で切断  2=直線でも切断"
    f.WriteLine "CUT=" & cutMode
    f.WriteLine "; TOL : これより短い切れ端は作らない（図面の寸法）"
    f.WriteLine "TOL=" & FmtNum(gTol)
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
' 角度・距離
'==============================================================
Function CosD(d)
    CosD = Cos(d * gPI / 180)
End Function

Function SinD(d)
    SinD = Sin(d * gPI / 180)
End Function

'--- 0 以上 360 未満に正規化 ----------------------------------
Function NormDeg(ByVal a)
    a = a - Int(a / 360) * 360
    If a < 0 Then a = a + 360
    If a >= 360 Then a = a - 360
    NormDeg = a
End Function

'--- Atn しか無いので atan2 を自前で用意する ------------------
Function Atan2Deg(y, x)
    Dim a

    If x = 0 Then
        If y >= 0 Then a = gPI / 2 Else a = -gPI / 2
    Else
        a = Atn(y / x)
        If x < 0 Then a = a + gPI
    End If

    Atan2Deg = NormDeg(a * 180 / gPI)
End Function

Function Dist(x1, y1, x2, y2)
    Dim dx, dy
    dx = x2 - x1 : dy = y2 - y1
    Dist = Sqr(dx * dx + dy * dy)
End Function

Function Min2(a, b)
    If a < b Then Min2 = a Else Min2 = b
End Function

Function Max2(a, b)
    If a > b Then Max2 = a Else Max2 = b
End Function

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
