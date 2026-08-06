Option Explicit
'==============================================================
' Jw_cad 外部変形 : 描画順（重なり順）   jww_draw_order.vbs
'
'   範囲選択したデータを「番号」の順に並べ替えて書き戻し、
'   重なり順（描画順）を指定します。
'
'   Jw_cad は jwc_temp.txt に書かれた順にデータを作図するので、
'   ファイルの後ろにあるものほど上（後から描画）になります。
'   この外部変形は、選択したデータを hd でいったん消してから、
'   指定した順番で書き戻すことで重なり順を入れ替えます。
'
'   「番号」として使えるもの
'     線色番号(lc) / 線種番号(lt) / レイヤ番号(ly) / レイヤグループ番号(lg)
'
'   ・バッチファイル(*.bat)から cscript で呼び出されます。
'   ・単体では動きません（jwc_temp.txt が必要）。
'
'   引数（省略時は入力ダイアログで指定）
'     /m:0-5   0 = そのまま最前面へ（並べ替えない）
'              1 = 番号順（番号の大きいものが上）
'              2 = 番号順（番号の小さいものが上）
'              3 = 並び順を指定（/n: の先頭が下、末尾が上）
'              4 = /n: の番号だけを最前面へ
'              5 = /n: の番号だけを最背面へ
'     /k:1-4   番号の種類 1=線色 2=線種 3=レイヤ 4=レイヤグループ
'     /n:...   番号の並び／対象番号（カンマ区切り  例 /n:3,1,2）
'     /q       ダイアログを出さない（引数だけで実行）
'     /qn      番号だけを聞く（並べ方と番号の種類は引数で固定）
'     /nowarn  寸法図形などが混ざっていても警告を出さない
'     /dump    調査用。Jw_cad から受け取った jwc_temp.txt と
'              書き戻した jwc_temp.txt を、このスクリプトと
'              同じフォルダに次の名前で保存する。
'                jwc_temp_元.txt    … Jw_cad が書き出したもの
'                jwc_temp_結果.txt  … 書き戻したもの
'              どの種類のデータが Jw_cad から渡されていないかを
'              調べるために使う（ブロック図形など）。
'
'   Jw_cad Version 8.20 で使用する想定
'==============================================================

'--- モード定数 -----------------------------------------------
Const MODE_FRONT    = 0    ' そのまま最前面へ
Const MODE_BIGTOP   = 1    ' 番号の大きいものが上
Const MODE_SMALLTOP = 2    ' 番号の小さいものが上
Const MODE_CUSTOM   = 3    ' 並び順を指定
Const MODE_UP       = 4    ' 指定番号だけを最前面へ
Const MODE_DOWN     = 5    ' 指定番号だけを最背面へ
Const MODE_MAXNO    = 5

'--- 番号の種類 -----------------------------------------------
Const KEY_COLOR = 1        ' 線色番号   lc1～lc9
Const KEY_TYPE  = 2        ' 線種番号   lt1～lt9 / lt11～lt19
Const KEY_LAYER = 3        ' レイヤ番号 ly0～ly9 / lya～lyf
Const KEY_GROUP = 4        ' レイヤグループ番号 lg0～lg9 / lga～lgf
Const KEY_MAXNO = 4

Const APPTITLE = "描画順"

'--- グローバル -----------------------------------------------
Dim gFso        : Set gFso = CreateObject("Scripting.FileSystemObject")
Dim gScriptDir  : gScriptDir = gFso.GetParentFolderName(WScript.ScriptFullName)
Dim gIniPath    : gIniPath = gFso.BuildPath(gScriptDir, "jww_draw_order.ini")

Dim gRecs()                 ' 要素レコード
Dim gRecCount               ' 要素数
Dim gTailPend               ' 末尾に残った未知の行
Dim gEndLg, gEndLy, gEndLc, gEndLt   ' 読み終えた時点の属性（書込状態の復元用）
Dim gUnknownCount           ' 分類できなかった行の数
Dim gUnknownFirst           ' その最初の 1 行
Dim gDimCount               ' 寸法コマンドで作られた文字(cs)の数

'--- 要素レコード ---------------------------------------------
'   Jw_cad のデータは「属性行 → 要素行」の順に並び、属性行は
'   次に属性行が現れるまで有効。並べ替えると継承関係が崩れる
'   ため、各要素が自分の属性を持ち歩けるようにしておく。
Class Rec
    Public lg, ly, lc, lt   ' 有効だった属性行（lg0 / ly3 / lc2 / lt1 …）
    Public cn               ' 有効だった文字種行（文字要素のときだけ使う）
    Public prefix           ' 直前にあった未知の修飾行（vbLf 区切り）
    Public body             ' 要素行そのもの
    Public seq              ' 元の並び順（安定ソート用）
    Public rank             ' 並べ替えの順位
End Class

Main

'==============================================================
' メイン
'==============================================================
Sub Main()
    Dim tempPath, lines, mode, keyKind, nums

    tempPath = FindTempFile()
    If tempPath = "" Then
        MsgBox "jwc_temp.txt が見つかりません。" & vbCrLf & vbCrLf & _
               "この外部変形は Jw_cad の [その他]-[外部変形] から" & vbCrLf & _
               "実行してください。", vbExclamation, APPTITLE
        WScript.Quit 1
    End If

    ' 調査用。Jw_cad が書き出した内容を、手を付ける前に保存する。
    DumpIfAsked tempPath, "jwc_temp_元.txt"

    InitArrays
    lines = ReadAllLines(tempPath)
    ParseTemp lines

    If gRecCount = 0 Then
        WriteAllText tempPath, "he 並べ替えるデータが選択されていません。" & vbCrLf
        WScript.Quit 0
    End If

    '--- 危ないデータが混ざっていないか確かめる ----------------
    If Not ConfirmRisky() Then WScript.Quit 0

    '--- 並べ替え方の決定 -------------------------------------
    If Not GetSettings(mode, keyKind, nums) Then
        ' 中止。jwc_temp.txt は書き換えないので Jw_cad 側は「未実行」となり
        ' 図面は一切変更されない。
        WScript.Quit 0
    End If

    '--- 並べ替え ---------------------------------------------
    SetRanks mode, keyKind, nums
    SortRecs

    '--- 出力 -------------------------------------------------
    WriteResult tempPath

    ' 調査用。書き戻した内容も保存する。
    DumpIfAsked tempPath, "jwc_temp_結果.txt"
End Sub

'==============================================================
' 調査用のコピーを作る（/dump が指定されたときだけ）
'
'   Jw_cad がどの種類のデータを外部変形に渡しているのかは、
'   jwc_temp.txt を直接見ないと分からない。ブロック図形のように
'   「範囲選択には入るのに書き出されない」ものがあるため、
'   受け取った内容と書き戻した内容の両方を残せるようにする。
'==============================================================
Sub DumpIfAsked(tempPath, saveName)
    Dim args, dest

    Set args = WScript.Arguments.Named
    If Not args.Exists("dump") Then Exit Sub
    If Not gFso.FileExists(tempPath) Then Exit Sub

    dest = gFso.BuildPath(gScriptDir, saveName)
    On Error Resume Next
    gFso.CopyFile tempPath, dest, True
    On Error GoTo 0
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
    ReDim gRecs(255)
    gRecCount = 0
    gTailPend = ""
    gEndLg = "" : gEndLy = "" : gEndLc = "" : gEndLt = ""
    gUnknownCount = 0 : gUnknownFirst = ""
    gDimCount = 0
End Sub

'==============================================================
' jwc_temp.txt の解析
'
'   ・空行 / # で始まる行 : 捨てる
'   ・h  で始まる行       : 図面情報。書き戻さない（hq を残すと
'                           「未実行」になるため必ず捨てる）
'   ・lg/ly/lc/lt         : 属性。状態として覚え、要素に持たせる
'   ・cn                  : 文字種。状態として覚える
'   ・要素行              : レコードにする
'   ・それ以外            : 分類できない行。Jw_cad のデータでは
'                           要素を修飾する行は必ずその要素の前に
'                           置かれるので、次の要素にくっつけて
'                           一緒に動かす（ソリッドの色指定など）
'==============================================================
Sub ParseTemp(lines)
    Dim i, raw, t
    Dim curLg, curLy, curLc, curLt, curCn, pend

    curLg = "" : curLy = "" : curLc = "" : curLt = "" : curCn = ""
    pend = ""

    For i = 0 To UBound(lines)
        raw = lines(i)
        t = Trim(raw)

        If t = "" Then
            ' 空行は捨てる
        ElseIf Left(t, 1) = "#" Then
            ' コメント行は捨てる
        ElseIf IsAttrLine(t, "lg") Then
            curLg = t
        ElseIf IsAttrLine(t, "ly") Then
            curLy = t
        ElseIf IsAttrLine(t, "lc") Then
            curLc = t
        ElseIf IsAttrLine(t, "lt") Then
            curLt = t
        ElseIf Left(t, 2) = "cn" Then
            curCn = t
        ElseIf Left(t, 1) = "h" Then
            ' 図面情報（hq を含む）は出力しない
        ElseIf IsElementLine(t) Then
            If LCase(Left(t, 2)) = "cs" Then gDimCount = gDimCount + 1
            PushRec curLg, curLy, curLc, curLt, curCn, pend, raw
            pend = ""
        Else
            gUnknownCount = gUnknownCount + 1
            If gUnknownFirst = "" Then gUnknownFirst = t
            If pend = "" Then pend = raw Else pend = pend & vbLf & raw
        End If
    Next

    gTailPend = pend
    gEndLg = curLg : gEndLy = curLy : gEndLc = curLc : gEndLt = curLt
End Sub

'--- 「lg0」「lya」「lt11」のような属性行か ---------------------
Function IsAttrLine(t, prefix)
    Dim i, c

    IsAttrLine = False
    If Len(t) < 3 Then Exit Function
    If LCase(Left(t, 2)) <> prefix Then Exit Function

    ' 後ろは 0-9 / a-f の 1～2 文字だけ（lt11～lt19 があるため 2 文字まで）
    If Len(t) > 4 Then Exit Function
    For i = 3 To Len(t)
        c = LCase(Mid(t, i, 1))
        If Not ((c >= "0" And c <= "9") Or (c >= "a" And c <= "f")) Then Exit Function
    Next

    IsAttrLine = True
End Function

'--- 作図要素の行か -------------------------------------------
'   線 は「x1 y1 x2 y2」と数値で始まる。ほかは 2 文字の識別子。
Function IsElementLine(t)
    Dim c, h2

    IsElementLine = False

    c = Left(t, 1)
    If (c >= "0" And c <= "9") Or c = "-" Or c = "+" Or c = "." Then
        IsElementLine = True
        Exit Function
    End If

    h2 = LCase(Left(t, 2))
    Select Case h2
        Case "ci"       ' 円・円弧・楕円
            IsElementLine = True
        Case "pt"       ' 点
            IsElementLine = True
        Case "ch"       ' 文字（横書き）
            IsElementLine = True
        Case "cv"       ' 文字（縦書き）
            IsElementLine = True
        Case "cs"       ' 寸法コマンドで作成した文字
            IsElementLine = True
        Case "sl"       ' ソリッド
            IsElementLine = True
    End Select
End Function

'--- 文字要素か（cn を書き出す必要があるか） -------------------
Function IsTextBody(body)
    Dim h2
    h2 = LCase(Left(LTrim(body), 2))
    IsTextBody = (h2 = "ch" Or h2 = "cv" Or h2 = "cs")
End Function

'--- レコードの追加 -------------------------------------------
Sub PushRec(lg, ly, lc, lt, cn, prefix, body)
    Dim r

    Set r = New Rec
    r.lg = lg : r.ly = ly : r.lc = lc : r.lt = lt
    r.cn = cn
    r.prefix = prefix
    r.body = body
    r.seq = gRecCount
    r.rank = 0

    If gRecCount > UBound(gRecs) Then ReDim Preserve gRecs(gRecCount * 2 + 1)
    Set gRecs(gRecCount) = r
    gRecCount = gRecCount + 1
End Sub

'==============================================================
' 並べ替えの順位を決める
'   rank が小さいものほど先に出力される ＝ 下になる。
'   同じ rank どうしは元の順番を保つ（安定ソート）。
'==============================================================
Sub SetRanks(mode, keyKind, nums)
    Dim i, r, k, p

    For i = 0 To gRecCount - 1
        Set r = gRecs(i)
        k = KeyOf(r, keyKind)

        Select Case mode
            Case MODE_FRONT
                r.rank = 0

            Case MODE_BIGTOP
                r.rank = k

            Case MODE_SMALLTOP
                r.rank = -k

            Case MODE_CUSTOM
                p = IndexOfNum(nums, k)
                If p >= 0 Then
                    ' 指定された並び。先頭が下、末尾が上。
                    r.rank = p
                Else
                    ' 指定に無い番号は、指定されたものより下に
                    ' まとめて置く（番号の小さい順）。
                    r.rank = -100000 + k
                End If

            Case MODE_UP
                If IndexOfNum(nums, k) >= 0 Then r.rank = 1 Else r.rank = 0

            Case MODE_DOWN
                If IndexOfNum(nums, k) >= 0 Then r.rank = -1 Else r.rank = 0
        End Select
    Next
End Sub

'--- レコードの「番号」を取り出す -----------------------------
Function KeyOf(r, keyKind)
    Select Case keyKind
        Case KEY_COLOR : KeyOf = AttrNum(r.lc)
        Case KEY_TYPE  : KeyOf = AttrNum(r.lt)
        Case KEY_LAYER : KeyOf = AttrNum(r.ly)
        Case KEY_GROUP : KeyOf = AttrNum(r.lg)
        Case Else      : KeyOf = 0
    End Select
End Function

'--- 「lc2」「lya」「lt11」から数値を取り出す ------------------
'   レイヤ・レイヤグループは 16 進 1 桁（a～f は 10～15）。
Function AttrNum(attr)
    Dim body, i, c, v, d

    AttrNum = 0
    If Len(attr) < 3 Then Exit Function

    body = LCase(Mid(attr, 3))
    v = 0
    For i = 1 To Len(body)
        c = Mid(body, i, 1)
        If c >= "0" And c <= "9" Then
            d = Asc(c) - 48
        ElseIf c >= "a" And c <= "f" Then
            d = Asc(c) - 87
        Else
            Exit Function
        End If
        ' 「lt11」のような 2 桁は 10 進として扱う
        If Len(body) > 1 Then v = v * 10 + d Else v = d
    Next

    AttrNum = v
End Function

'==============================================================
' rank で並べ替える（安定ソート）
'   rank の種類は多くても数十なので、rank を昇順に走査しながら
'   元の順番で拾い直す。こうすると同順位の並びが必ず保たれる。
'==============================================================
Sub SortRecs()
    Dim ranks, nRank, i, j, n, tmp
    Dim sorted()

    ranks = DistinctRanks(nRank)

    ' rank の一覧を昇順に（要素数が少ないので単純な挿入ソート）
    For i = 1 To nRank - 1
        tmp = ranks(i)
        j = i - 1
        Do While j >= 0
            If ranks(j) <= tmp Then Exit Do
            ranks(j + 1) = ranks(j)
            j = j - 1
        Loop
        ranks(j + 1) = tmp
    Next

    ReDim sorted(gRecCount - 1)
    n = 0
    For i = 0 To nRank - 1
        For j = 0 To gRecCount - 1
            If gRecs(j).rank = ranks(i) Then
                Set sorted(n) = gRecs(j)
                n = n + 1
            End If
        Next
    Next

    For i = 0 To gRecCount - 1
        Set gRecs(i) = sorted(i)
    Next
End Sub

'--- rank の種類を集める --------------------------------------
Function DistinctRanks(ByRef nRank)
    Dim i, j, v, found
    Dim res()

    ReDim res(31)
    nRank = 0

    For i = 0 To gRecCount - 1
        v = gRecs(i).rank
        found = False
        For j = 0 To nRank - 1
            If res(j) = v Then found = True : Exit For
        Next
        If Not found Then
            If nRank > UBound(res) Then ReDim Preserve res(nRank * 2 + 1)
            res(nRank) = v
            nRank = nRank + 1
        End If
    Next

    DistinctRanks = res
End Function

'==============================================================
' 結果の書き出し
'   先頭の hd で選択された元データを削除し、続けて並べ替えた
'   順番に書き戻す。書き戻した順がそのまま描画順になる。
'==============================================================
Sub WriteResult(tempPath)
    Dim out()
    Dim n, i, r
    Dim lastLg, lastLy, lastLc, lastLt, lastCn

    ' 1 要素あたり 属性 4 行＋文字種 1 行＋本体 1 行、それに
    ' 分類できなかった行と末尾の属性復元ぶんを足しておけば足りる。
    ReDim out(gRecCount * 6 + gUnknownCount + 16)
    n = 0

    out(n) = "hd" : n = n + 1

    lastLg = "" : lastLy = "" : lastLc = "" : lastLt = "" : lastCn = ""

    For i = 0 To gRecCount - 1
        Set r = gRecs(i)

        ' 並べ替えで属性の継承が崩れるので、変わったところだけ書き直す
        If r.lg <> "" And r.lg <> lastLg Then out(n) = r.lg : n = n + 1 : lastLg = r.lg
        If r.ly <> "" And r.ly <> lastLy Then out(n) = r.ly : n = n + 1 : lastLy = r.ly
        If r.lc <> "" And r.lc <> lastLc Then out(n) = r.lc : n = n + 1 : lastLc = r.lc
        If r.lt <> "" And r.lt <> lastLt Then out(n) = r.lt : n = n + 1 : lastLt = r.lt

        If IsTextBody(r.body) Then
            If r.cn <> "" And r.cn <> lastCn Then out(n) = r.cn : n = n + 1 : lastCn = r.cn
        End If

        If r.prefix <> "" Then
            n = AppendLines(out, n, Split(r.prefix, vbLf))
        End If

        out(n) = r.body : n = n + 1
    Next

    If gTailPend <> "" Then n = AppendLines(out, n, Split(gTailPend, vbLf))

    ' 読み終えた時点の書込属性に戻しておく（並べ替えの有無で
    ' 書込レイヤ・線色が変わってしまわないように）
    If gEndLg <> "" And gEndLg <> lastLg Then out(n) = gEndLg : n = n + 1 : lastLg = gEndLg
    If gEndLy <> "" And gEndLy <> lastLy Then out(n) = gEndLy : n = n + 1 : lastLy = gEndLy
    If gEndLc <> "" And gEndLc <> lastLc Then out(n) = gEndLc : n = n + 1 : lastLc = gEndLc
    If gEndLt <> "" And gEndLt <> lastLt Then out(n) = gEndLt : n = n + 1 : lastLt = gEndLt

    ReDim Preserve out(n - 1)
    WriteAllText tempPath, Join(out, vbCrLf) & vbCrLf
End Sub

'--- 出力配列に複数行を追加（out はあらかじめ十分な大きさ） ----
Function AppendLines(out, ByVal n, arr)
    Dim i
    For i = 0 To UBound(arr)
        If Trim(arr(i)) <> "" Then
            out(n) = arr(i)
            n = n + 1
        End If
    Next
    AppendLines = n
End Function

'==============================================================
' 形が崩れる可能性のあるデータが混ざっていないか確かめる
'
'   外部変形は「選択されたデータをいったん消して描き直す」ため、
'   寸法図形やブロック図形は範囲に入れた時点で分解されてしまう。
'   スクリプト側で選んで残すことはできない（消すか消さないかは
'   hd による全消しか、何もしないかの二択しかない）。
'   そこで、見つかったときは実行前に知らせて中止できるようにする。
'
'   戻り値 : False なら中止（jwc_temp.txt を書き換えないので
'            Jw_cad 側は「未実行」となり図面は変わらない）
'==============================================================
Function ConfirmRisky()
    Dim args, msg

    ConfirmRisky = True

    Set args = WScript.Arguments.Named
    If args.Exists("nowarn") Then Exit Function
    If gDimCount = 0 And gUnknownCount = 0 Then Exit Function

    msg = "選択した範囲に、並べ替えると形が崩れるかもしれない" & vbCrLf & _
          "データが含まれています。" & vbCrLf & vbCrLf

    If gDimCount > 0 Then
        msg = msg & "  ・寸法コマンドで作られた文字 : " & gDimCount & " 個" & vbCrLf & _
                    "    寸法図形はバラバラの線と文字になります" & vbCrLf & vbCrLf
    End If

    If gUnknownCount > 0 Then
        msg = msg & "  ・種類の分からないデータ : " & gUnknownCount & " 行" & vbCrLf & _
                    "    ブロック図形などの可能性があります" & vbCrLf & _
                    "    例 : " & Left(gUnknownFirst, 30) & vbCrLf & vbCrLf
    End If

    msg = msg & "外したいときは [いいえ] を選んでください。図面は" & vbCrLf & _
                "変わりません。そのデータのあるレイヤを [表示のみ] に" & vbCrLf & _
                "してから選び直すと、範囲選択の対象から外れます。" & vbCrLf & vbCrLf & _
                "このまま並べ替えますか？"

    If MsgBox(msg, vbYesNo + vbExclamation + vbDefaultButton2, APPTITLE) <> vbYes Then
        ConfirmRisky = False
    End If
End Function

'==============================================================
' 並べ替え方の取得（引数 → ダイアログ）
'   戻り値 : False なら中止
'==============================================================
Function GetSettings(ByRef mode, ByRef keyKind, ByRef nums)
    Dim args, quiet, askNumOnly, s, numStr

    GetSettings = False
    Set args = WScript.Arguments.Named
    quiet      = args.Exists("q")
    askNumOnly = args.Exists("qn")

    mode    = ModeOf(ParseInt(IniGet("MODE", "1")))
    keyKind = KeyOf2(ParseInt(IniGet("KEY", "1")))
    numStr  = IniGet("NUMS", "")

    If args.Exists("m") Then mode    = ModeOf(ParseInt(args("m")))
    If args.Exists("k") Then keyKind = KeyOf2(ParseInt(args("k")))
    If args.Exists("n") Then numStr  = args("n")

    If Not quiet And Not askNumOnly Then
        s = InputBox( _
            "重なり順の付け方を番号で指定してください。" & vbCrLf & vbCrLf & _
            "  0 : 最前面へ（選択したものを、そのまま一番上に）" & vbCrLf & _
            "  1 : 番号順（番号の大きいものが上）" & vbCrLf & _
            "  2 : 番号順（番号の小さいものが上）" & vbCrLf & _
            "  3 : 並び順を自分で指定（次の画面で入力）" & vbCrLf & _
            "  4 : 指定した番号だけを最前面へ" & vbCrLf & _
            "  5 : 指定した番号だけを最背面へ" & vbCrLf & vbCrLf & _
            "選択されたデータ : " & gRecCount & " 個" & UnknownNote() & vbCrLf & _
            "（空欄のまま OK、または キャンセル で中止）", _
            APPTITLE & " (1/2) 並べ方", CStr(mode))
        If Trim(s) = "" Then Exit Function
        mode = ModeOf(ParseInt(s))

        If mode <> MODE_FRONT Then
            s = InputBox( _
                "順番を決める「番号」の種類を指定してください。" & vbCrLf & vbCrLf & _
                "  1 : 線色番号        （線色1～線色9）" & vbCrLf & _
                "  2 : 線種番号        （実線=1 …）" & vbCrLf & _
                "  3 : レイヤ番号      （0～15）" & vbCrLf & _
                "  4 : レイヤグループ番号（0～15）" & vbCrLf & vbCrLf & _
                "（空欄のまま OK、または キャンセル で中止）", _
                APPTITLE & " (2/2) 番号の種類", CStr(keyKind))
            If Trim(s) = "" Then Exit Function
            keyKind = KeyOf2(ParseInt(s))
        End If
    End If

    If Not quiet Then
        If mode = MODE_CUSTOM Then
            s = InputBox( _
                "下から上へ並べる順番を、" & KeyWord(keyKind) & "をカンマで" & vbCrLf & _
                "区切って入力してください。" & vbCrLf & vbCrLf & _
                "  例） 3,1,2   … 3 が一番下、2 が一番上" & vbCrLf & vbCrLf & _
                "ここに書かなかった番号は、いちばん下にまとめられます。" & vbCrLf & _
                "（空欄のまま OK、または キャンセル で中止）", _
                APPTITLE & " 並び順（" & KeyWord(keyKind) & "）", numStr)
            If Trim(s) = "" Then Exit Function
            numStr = s
        ElseIf mode = MODE_UP Or mode = MODE_DOWN Then
            s = InputBox( _
                MoveWord(mode) & "する" & KeyWord(keyKind) & "を、カンマで" & vbCrLf & _
                "区切って入力してください。" & vbCrLf & vbCrLf & _
                "  例） 2,5   … 番号 2 と 5 のものを" & MoveWord(mode) & "する" & vbCrLf & vbCrLf & _
                "選択されたデータ : " & gRecCount & " 個" & vbCrLf & _
                "（空欄のまま OK、または キャンセル で中止）", _
                APPTITLE & " " & MoveWord(mode) & "（" & KeyWord(keyKind) & "）", numStr)
            If Trim(s) = "" Then Exit Function
            numStr = s
        End If

        SaveIni mode, keyKind, numStr
    End If

    nums = ParseNumList(numStr)

    If (mode = MODE_CUSTOM Or mode = MODE_UP Or mode = MODE_DOWN) Then
        If UBound(nums) < 0 Then
            MsgBox "番号が指定されていません。", vbExclamation, APPTITLE
            Exit Function
        End If
    End If

    GetSettings = True
End Function

Function MoveWord(mode)
    If mode = MODE_DOWN Then MoveWord = "最背面へ" Else MoveWord = "最前面へ"
End Function

Function KeyWord(keyKind)
    Select Case keyKind
        Case KEY_TYPE  : KeyWord = "線種番号"
        Case KEY_LAYER : KeyWord = "レイヤ番号"
        Case KEY_GROUP : KeyWord = "レイヤグループ番号"
        Case Else      : KeyWord = "線色番号"
    End Select
End Function

Function UnknownNote()
    If gUnknownCount > 0 Then
        UnknownNote = vbCrLf & "（種類の分からない行が " & gUnknownCount & " 行あります。" & _
                      "例：" & Left(gUnknownFirst, 20) & vbCrLf & _
                      "　これらは直後のデータと一緒に動かします）"
    Else
        UnknownNote = ""
    End If
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

Sub SaveIni(mode, keyKind, numStr)
    Dim f
    On Error Resume Next
    Set f = gFso.CreateTextFile(gIniPath, True, False)
    If Err.Number <> 0 Then Err.Clear : Exit Sub
    f.WriteLine "[jww_draw_order]"
    f.WriteLine "MODE=" & mode
    f.WriteLine "KEY=" & keyKind
    f.WriteLine "NUMS=" & numStr
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
' 数値の入力
'==============================================================
Function ParseInt(ByVal s)
    Dim i, c, sign, v, seen

    ParseInt = 0
    s = Trim(s)
    If Len(s) = 0 Then Exit Function

    sign = 1 : i = 1
    c = Mid(s, 1, 1)
    If c = "+" Then i = 2
    If c = "-" Then sign = -1 : i = 2

    v = 0 : seen = False
    Do While i <= Len(s)
        c = Mid(s, i, 1)
        If c < "0" Or c > "9" Then Exit Do
        v = v * 10 + (Asc(c) - 48)
        seen = True
        i = i + 1
    Loop

    If seen Then ParseInt = sign * v
End Function

'--- 「3,1,2」「3 1 2」を数値の配列にする ----------------------
Function ParseNumList(ByVal s)
    Dim parts, i, t, n
    Dim res()

    ReDim res(31)
    n = 0

    s = Replace(s, vbTab, " ")
    s = Replace(s, ";", ",")
    s = Replace(s, " ", ",")
    s = Replace(s, "、", ",")
    s = Replace(s, "，", ",")
    parts = Split(s, ",")

    For i = 0 To UBound(parts)
        t = Trim(parts(i))
        If t <> "" Then
            If n > UBound(res) Then ReDim Preserve res(n * 2 + 1)
            res(n) = ParseInt(t)
            n = n + 1
        End If
    Next

    If n = 0 Then
        ParseNumList = Array()
    Else
        ReDim Preserve res(n - 1)
        ParseNumList = res
    End If
End Function

Function IndexOfNum(nums, v)
    Dim i
    IndexOfNum = -1
    If UBound(nums) < 0 Then Exit Function
    For i = 0 To UBound(nums)
        If nums(i) = v Then IndexOfNum = i : Exit Function
    Next
End Function

'--- 範囲外・巨大値でも落ちないように --------------------------
Function ModeOf(v)
    If v < 0 Or v > MODE_MAXNO Then ModeOf = MODE_FRONT Else ModeOf = CInt(v)
End Function

Function KeyOf2(v)
    If v < 1 Or v > KEY_MAXNO Then KeyOf2 = KEY_COLOR Else KeyOf2 = CInt(v)
End Function
