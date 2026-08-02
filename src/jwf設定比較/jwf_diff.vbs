Option Explicit
'==============================================================
' Jw_cad 環境設定ファイル比較   jwf_diff.vbs
'
'   2 つの jw_win.jwf を比べて、どのキーの何番目の数値が
'   変わったかを報告します。16進の数値どうしなら、どのビットが
'   ON / OFF になったかまで表示します。
'
'   基本設定のチェックを 1 つだけ変えて書き出した 2 つのファイルを
'   比べれば、そのチェックがどのビットなのかが確実に分かります。
'
'   使い方
'     jwf設定比較.bat に .jwf を 2 つドラッグ＆ドロップする
'     または  cscript jwf_diff.vbs 変更前.jwf 変更後.jwf
'==============================================================

Const APPTITLE = "jwf設定比較"

Dim gFso : Set gFso = CreateObject("Scripting.FileSystemObject")

Main

'==============================================================
' メイン
'==============================================================
Sub Main()
    Dim args, pathA, pathB, keysA, keysB, valsA, valsB
    Dim report, outPath

    Set args = WScript.Arguments.Unnamed

    If args.Count < 2 Then
        MsgBox "比べる環境設定ファイル (.jwf) を 2 つ指定してください。" & vbCrLf & vbCrLf & _
               "使い方" & vbCrLf & _
               "  1. Jw_cad の [設定] - [環境設定ファイル] - [書出し] で" & vbCrLf & _
               "     変更前の設定を「変更前.jwf」として保存する" & vbCrLf & _
               "  2. 基本設定でチェックを 1 つだけ変える" & vbCrLf & _
               "  3. もう一度 [書出し] で「変更後.jwf」として保存する" & vbCrLf & _
               "  4. この 2 つを jwf設定比較.bat にドラッグ＆ドロップする", _
               vbInformation, APPTITLE
        WScript.Quit 1
    End If

    pathA = args(0)
    pathB = args(1)

    If Not gFso.FileExists(pathA) Then
        MsgBox "ファイルが見つかりません:" & vbCrLf & pathA, vbExclamation, APPTITLE
        WScript.Quit 1
    End If
    If Not gFso.FileExists(pathB) Then
        MsgBox "ファイルが見つかりません:" & vbCrLf & pathB, vbExclamation, APPTITLE
        WScript.Quit 1
    End If

    ReadJwf pathA, keysA, valsA
    ReadJwf pathB, keysB, valsB

    report = BuildReport(pathA, pathB, keysA, valsA, keysB, valsB)

    outPath = gFso.BuildPath(gFso.GetParentFolderName(gFso.GetAbsolutePathName(pathA)), _
                             "jwf比較結果.txt")
    WriteAllText outPath, report

    CreateObject("WScript.Shell").Run "notepad.exe """ & outPath & """", 1, False
End Sub

'==============================================================
' jwf の読み込み
'   「キー = 値」の行だけを拾う。# で始まる行は注釈。
'==============================================================
Sub ReadJwf(path, ByRef keys, ByRef vals)
    Dim lines, i, t, p, n
    Dim k(), v()

    lines = ReadAllLines(path)
    ReDim k(UBound(lines))
    ReDim v(UBound(lines))
    n = 0

    For i = 0 To UBound(lines)
        t = Trim(lines(i))
        If t <> "" And Left(t, 1) <> "#" Then
            p = InStr(t, "=")
            If p > 1 Then
                k(n) = Trim(Left(t, p - 1))
                v(n) = Trim(Mid(t, p + 1))
                n = n + 1
            End If
        End If
    Next

    If n = 0 Then
        keys = Array()
        vals = Array()
    Else
        ReDim Preserve k(n - 1)
        ReDim Preserve v(n - 1)
        keys = k
        vals = v
    End If
End Sub

'==============================================================
' 比較レポートの作成
'==============================================================
Function BuildReport(pathA, pathB, keysA, valsA, keysB, valsB)
    Dim sb, i, j, key, a, b, found, nDiff

    sb = "============================================================" & vbCrLf & _
         " Jw_cad 環境設定ファイルの比較" & vbCrLf & _
         "============================================================" & vbCrLf & _
         " 変更前 : " & pathA & vbCrLf & _
         " 変更後 : " & pathB & vbCrLf & vbCrLf

    nDiff = 0

    '--- 変更前にあるキーを順に見る ---------------------------
    If UBound(keysA) >= 0 Then
        For i = 0 To UBound(keysA)
            key = keysA(i)
            found = False
            b = ""
            If UBound(keysB) >= 0 Then
                For j = 0 To UBound(keysB)
                    If keysB(j) = key Then
                        b = valsB(j)
                        found = True
                        Exit For
                    End If
                Next
            End If

            a = valsA(i)

            If Not found Then
                sb = sb & "[" & key & "]  変更後のファイルにはありません" & vbCrLf & vbCrLf
                nDiff = nDiff + 1
            ElseIf a <> b Then
                sb = sb & CompareValue(key, a, b)
                nDiff = nDiff + 1
            End If
        Next
    End If

    '--- 変更後にだけあるキー ---------------------------------
    If UBound(keysB) >= 0 Then
        For j = 0 To UBound(keysB)
            key = keysB(j)
            found = False
            If UBound(keysA) >= 0 Then
                For i = 0 To UBound(keysA)
                    If keysA(i) = key Then found = True : Exit For
                Next
            End If
            If Not found Then
                sb = sb & "[" & key & "]  変更前のファイルにはありません" & vbCrLf & _
                     "    " & valsB(j) & vbCrLf & vbCrLf
                nDiff = nDiff + 1
            End If
        Next
    End If

    If nDiff = 0 Then
        sb = sb & "違いはありませんでした。" & vbCrLf & vbCrLf & _
             "基本設定を変えたあと [設定] - [環境設定ファイル] - [書出し] を" & vbCrLf & _
             "実行し直したか確認してください。" & vbCrLf
    Else
        sb = sb & "------------------------------------------------------------" & vbCrLf & _
             "違いのあったキー : " & nDiff & " 個" & vbCrLf & vbCrLf & _
             "チェックを 1 つだけ変えたのに複数のキーが変わった場合は、" & vbCrLf & _
             "書き出しのたびに変わる項目（表示範囲など）が混ざっています。" & vbCrLf & _
             "同じ操作をもう一度行い、毎回変わるキーを除いて判断してください。" & vbCrLf
    End If

    BuildReport = sb
End Function

'==============================================================
' 1 つのキーの値を比べる
'   同じ個数の数値に分かれるなら、何番目が変わったかを示す。
'==============================================================
Function CompareValue(key, a, b)
    Dim ta, tb, i, sb, va, vb

    sb = "[" & key & "]" & vbCrLf

    ta = Tokenize(a)
    tb = Tokenize(b)

    If UBound(ta) <> UBound(tb) Then
        ' 個数が違うときは行ごと表示する
        sb = sb & "    変更前 : " & a & vbCrLf & _
                  "    変更後 : " & b & vbCrLf & vbCrLf
        CompareValue = sb
        Exit Function
    End If

    For i = 0 To UBound(ta)
        va = ta(i)
        vb = tb(i)
        If va <> vb Then
            sb = sb & "    " & (i + 1) & " 番目 : " & va & "  →  " & vb & vbCrLf
            sb = sb & BitNote(va, vb)
        End If
    Next

    CompareValue = sb & vbCrLf
End Function

'--- 16進の数値どうしなら、変わったビットを示す ----------------
Function BitNote(va, vb)
    Dim na, nb, x, i, bit, onList, offList

    BitNote = ""

    If Not IsHexToken(va) Or Not IsHexToken(vb) Then Exit Function

    na = HexVal(va)
    nb = HexVal(vb)
    If na < 0 Or nb < 0 Then Exit Function

    BitNote = "        16進として  " & va & " = " & BinStr(na) & vbCrLf & _
              "                    " & vb & " = " & BinStr(nb) & vbCrLf

    x = na Xor nb
    If x = 0 Then Exit Function

    onList = ""
    offList = ""
    For i = 0 To 30
        bit = 2 ^ i
        If bit > x Then Exit For
        If (x And bit) = bit Then
            If (nb And bit) = bit Then
                onList = onList & AddBit(onList, bit)
            Else
                offList = offList & AddBit(offList, bit)
            End If
        End If
    Next

    If onList <> "" Then
        BitNote = BitNote & "        ON になったビット  : " & onList & vbCrLf
    End If
    If offList <> "" Then
        BitNote = BitNote & "        OFF になったビット : " & offList & vbCrLf
    End If
End Function

Function AddBit(cur, bit)
    Dim s
    s = "0x" & Hex(bit) & "（10進 " & bit & "）"
    If cur <> "" Then s = " , " & s
    AddBit = s
End Function

'--- 2進表記（4桁ずつ区切る） ----------------------------------
Function BinStr(ByVal v)
    Dim s, i, bit, started

    s = ""
    started = False
    For i = 15 To 0 Step -1
        bit = 2 ^ i
        If (v And bit) = bit Then
            s = s & "1"
            started = True
        ElseIf started Or i < 8 Then
            s = s & "0"
        End If
        If (started Or i < 8) And (i Mod 4 = 0) And i > 0 Then s = s & " "
    Next

    If s = "" Then s = "0"
    BinStr = s
End Function

'--- 16進として読めるトークンか --------------------------------
Function IsHexToken(s)
    Dim i, c

    IsHexToken = False
    s = Trim(s)
    If Len(s) = 0 Or Len(s) > 8 Then Exit Function

    For i = 1 To Len(s)
        c = LCase(Mid(s, i, 1))
        If Not ((c >= "0" And c <= "9") Or (c >= "a" And c <= "f")) Then Exit Function
    Next

    IsHexToken = True
End Function

Function HexVal(ByVal s)
    Dim i, c, v, d

    HexVal = -1
    s = LCase(Trim(s))
    v = 0

    For i = 1 To Len(s)
        c = Mid(s, i, 1)
        If c >= "0" And c <= "9" Then
            d = Asc(c) - 48
        ElseIf c >= "a" And c <= "f" Then
            d = Asc(c) - 87
        Else
            Exit Function
        End If
        v = v * 16 + d
    Next

    HexVal = v
End Function

'==============================================================
' 文字列を空白で区切る
'==============================================================
Function Tokenize(s)
    Dim i, st, c, n
    Dim res()

    ReDim res(63)
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
