'==============================================================
' Jw_cad 外部変形 : 展開図を作図する
'
'   tenkaizu_data.txt（このファイルと同じフォルダ）の作図データを
'   jwc_temp.txt に書き出して Jw_cad に描かせます。
'   「REM #1」で指示された点 hp1 を左下として配置します。
'   指示点が無いときは図面原点（用紙中央）を左下にします。
'==============================================================
Option Explicit

Dim gFso : Set gFso = CreateObject("Scripting.FileSystemObject")

Dim scriptDir : scriptDir = gFso.GetParentFolderName(WScript.ScriptFullName)
' 第1引数で作図データのファイル名を指定できる（既定は tenkaizu_data.txt）
Dim dataName : dataName = "tenkaizu_data.txt"
If WScript.Arguments.Count >= 1 Then dataName = WScript.Arguments(0)
Dim dataPath  : dataPath  = gFso.BuildPath(scriptDir, dataName)
Dim tempPath  : tempPath  = FindTemp()

If tempPath = "" Then
    WScript.Echo "jwc_temp.txt が見つかりません。" & vbCrLf & _
                 "Jw_cad の外部変形から実行してください。"
    WScript.Quit 1
End If
If Not gFso.FileExists(dataPath) Then
    WScript.Echo dataName & " が見つかりません。" & vbCrLf & _
                 "バッチファイルと同じフォルダに置いてください。"
    WScript.Quit 1
End If

'--- 指示点 hp1 を読む ----------------------------------------
Dim ox, oy : ox = 0 : oy = 0
Dim lines, i, t, toks
lines = ReadAllLines(tempPath)
For i = 0 To UBound(lines)
    t = Trim(lines(i))
    If Left(t, 4) = "hp1 " Then
        toks = Tokenize(Mid(t, 5))
        If UBound(toks) >= 1 Then
            ox = ParseNum(toks(0))
            oy = ParseNum(toks(1))
        End If
        Exit For
    End If
Next

'--- 作図データを平行移動して出力 ------------------------------
Dim out : out = ""
lines = ReadAllLines(dataPath)
For i = 0 To UBound(lines)
    t = Trim(lines(i))
    ' 「#」は寸法図形の区切りとして意味を持つので捨てない
    If t <> "" Then
        out = out & Shift(t, ox, oy) & vbCrLf
    End If
Next
WriteAllText tempPath, out
WScript.Quit 0

'==============================================================
' 1 行を平行移動する
'   「x1 y1 x2 y2」（線）「ci x y r」（円）「pt x y」（実点）
'   「ch / cs 始点X 始点Y 長さX 長さY "文字列」（文字・寸法値）が対象。
'   ch の第3・4は文字列の長さベクトルなので、始点だけを移動する。
'   属性行（ly / lc / lt / cn / pn）と msg・# はそのまま返す。
'==============================================================
Function Shift(ByVal t, ByVal ox, ByVal oy)
    Dim toks, n, i

    If Left(t, 3) = "pt " Then
        toks = Tokenize(Mid(t, 4))
        If UBound(toks) >= 1 Then
            Shift = "pt " & FmtNum(ParseNum(toks(0)) + ox) & " " & _
                            FmtNum(ParseNum(toks(1)) + oy)
            Exit Function
        End If

    ElseIf Left(t, 3) = "ci " Then
        toks = Tokenize(Mid(t, 4))
        If UBound(toks) >= 2 Then
            Shift = "ci " & FmtNum(ParseNum(toks(0)) + ox) & " " & _
                            FmtNum(ParseNum(toks(1)) + oy) & " " & toks(2)
            Exit Function
        End If

    ElseIf Left(t, 3) = "ch " Or Left(t, 3) = "cs " Then
        Dim body, nums(3), st, cnt, c, rest
        body = Mid(t, 4) : cnt = 0 : i = 1 : rest = ""
        Do While i <= Len(body) And cnt < 4
            Do While i <= Len(body)
                c = Mid(body, i, 1)
                If c <> " " And c <> vbTab Then Exit Do
                i = i + 1
            Loop
            st = i
            Do While i <= Len(body)
                c = Mid(body, i, 1)
                If c = " " Or c = vbTab Then Exit Do
                i = i + 1
            Loop
            If i <= st Then Exit Do
            nums(cnt) = ParseNum(Mid(body, st, i - st))
            cnt = cnt + 1
        Loop
        If cnt = 4 Then
            rest = LTrim(Mid(body, i))
            ' 第3・4フィールドは文字列の長さベクトルなので平行移動しない
            Shift = Left(t, 3) & FmtNum(nums(0) + ox) & " " & FmtNum(nums(1) + oy) & " " & _
                            FmtNum(nums(2)) & " " & FmtNum(nums(3)) & " " & rest
            Exit Function
        End If

    Else
        toks = Tokenize(t)
        n = UBound(toks)
        If n = 3 Then
            If IsNumToken(toks(0)) And IsNumToken(toks(1)) And _
               IsNumToken(toks(2)) And IsNumToken(toks(3)) Then
                Shift = FmtNum(ParseNum(toks(0)) + ox) & " " & _
                        FmtNum(ParseNum(toks(1)) + oy) & " " & _
                        FmtNum(ParseNum(toks(2)) + ox) & " " & _
                        FmtNum(ParseNum(toks(3)) + oy)
                Exit Function
            End If
        End If
    End If

    Shift = t
End Function

'--- jwc_temp.txt を探す --------------------------------------
Function FindTemp()
    Dim cands, p, sh
    Set sh = CreateObject("WScript.Shell")
    cands = Array(gFso.BuildPath(sh.CurrentDirectory, "jwc_temp.txt"), _
                  gFso.BuildPath(scriptDir, "jwc_temp.txt"))
    For Each p In cands
        If gFso.FileExists(p) Then FindTemp = p : Exit Function
    Next
    FindTemp = ""
End Function

'--- 空白区切りに分ける ---------------------------------------
Function Tokenize(s)
    Dim res(), n, i, st, c
    ReDim res(31) : n = 0 : i = 1
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
        Tokenize = Array()
    Else
        ReDim Preserve res(n - 1)
        Tokenize = res
    End If
End Function

Function IsNumToken(s)
    Dim i, c, seen
    s = Trim(s) : seen = False
    If s = "" Then IsNumToken = False : Exit Function
    For i = 1 To Len(s)
        c = Mid(s, i, 1)
        If c >= "0" And c <= "9" Then
            seen = True
        ElseIf c = "." Then
        ElseIf (c = "-" Or c = "+") And i = 1 Then
        Else
            IsNumToken = False : Exit Function
        End If
    Next
    IsNumToken = seen
End Function

Function ParseNum(s)
    Dim v
    s = Trim(s)
    On Error Resume Next
    v = CDbl(s)
    If Err.Number <> 0 Then Err.Clear : v = 0
    On Error GoTo 0
    ParseNum = v
End Function

Function FmtNum(v)
    Dim s
    s = CStr(Round(v, 2))
    If InStr(s, ",") > 0 Then s = Replace(s, ",", ".")
    FmtNum = s
End Function

'--- ファイル入出力（Shift_JIS）--------------------------------
Function ReadAllLines(path)
    Dim st, f, txt
    On Error Resume Next
    Set st = CreateObject("ADODB.Stream")
    If Err.Number = 0 Then
        st.Type = 2 : st.Charset = "shift_jis" : st.Open
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
        st.Type = 2 : st.Charset = "shift_jis" : st.Open
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
