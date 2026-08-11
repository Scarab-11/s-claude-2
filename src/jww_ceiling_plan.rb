#!/usr/bin/env ruby
# coding: utf-8
#==============================================================
# Jw_cad 外部変形 : 天井伏図生成   jww_ceiling_plan.rb
#
#   範囲選択した平面図から、天井伏図のたたき台を作ります。
#
#   ・バッチファイル(*.bat)から ruby で呼び出されます。
#   ・単体では動きません(jwc_temp.txt が必要)。
#
#   やること
#     1. ルールファイルに従って、不要なレイヤの要素を落とす
#     2. 室名の文字を見つけて、その下に天井仕上記号を書く
#     3. 面積表記などの不要な文字を消す / 図面名を書き換える
#     4. 仕上表(凡例)を作図する
#     5. 以上を、指示した点を左下として作図する(元の平面図は残る)
#
#   引数
#     第1引数  jwc_temp.txt のパス
#              (省略時 カレントフォルダの jwc_temp.txt)
#     第2引数  ルールファイルのパス
#              (省略時 このスクリプトと同じ場所の 天伏図ルール.txt)
#
#   Jw_cad Version 8.20 で使用する想定
#==============================================================

APPTITLE = '天井伏図生成'
EPS      = 1.0e-9

# jwc_temp.txt / ルールファイル / ログはすべて Shift_JIS(CP932)。
# 機種依存文字(①など)を通すため Shift_JIS ではなく Windows-31J を使う。
CP932 = 'Windows-31J'

NUM = /[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?/

#--------------------------------------------------------------
# 文字コードまわり
#--------------------------------------------------------------
def read_cp932(path)
  data = File.open(path, 'rb') { |f| f.read }
  # ルールファイルをうっかり UTF-8 で保存してしまった場合の逃げ道。
  # BOM が付いていれば UTF-8 として読む。
  if data.start_with?("\xEF\xBB\xBF".b)
    return data.byteslice(3..-1).force_encoding('UTF-8').scrub('')
  end
  data.force_encoding(CP932)
      .encode('UTF-8', invalid: :replace, undef: :replace, replace: '')
end

def write_cp932(path, text)
  data = text.encode(CP932, invalid: :replace, undef: :replace, replace: '?')
  File.open(path, 'wb') { |f| f.write(data) }
end

def script_dir
  File.dirname(File.expand_path(__FILE__))
end

# コマンドライン引数のパスは、環境によって UTF-8 だったり CP932 だったり
# ASCII-8BIT だったりする。ログに書けるよう UTF-8 に寄せる。
def to_utf8(str)
  return '' if str.nil?
  s = str.dup
  return s if s.encoding == Encoding::UTF_8 && s.valid_encoding?
  [Encoding::UTF_8, Encoding.find(CP932)].each do |enc|
    c = s.dup.force_encoding(enc)
    next unless c.valid_encoding?
    return c.encode('UTF-8', invalid: :replace, undef: :replace, replace: '')
  end
  s.force_encoding('UTF-8').scrub('')
end

# 数値の書き出し。指数表記や不要な 0 を付けない。
def fmt(v)
  return '0' if v.abs < EPS
  s = format('%.6f', v)
  s = s.sub(/0+\z/, '').sub(/\.\z/, '')
  s = '0' if s == '-0'
  s
end

def to_num(s)
  Float(s)
rescue ArgumentError, TypeError
  nil
end

# 室名の照合用に正規化する。
# 空白(全角含む)を取り除き、全角英数を半角に寄せる。
# 「事　務　室」「洋室－１」のような書き方でも拾えるようにする。
def normalize_key(s)
  t = s.gsub(/[[:space:]　]/, '')
  begin
    t = t.unicode_normalize(:nfkc)
  rescue StandardError, NoMethodError
    # 古い Ruby では正規化なしで照合する
  end
  t
end

#--------------------------------------------------------------
# ルールファイル
#--------------------------------------------------------------
class Rules
  attr_reader :rooms, :legend, :droptext, :retext, :settings

  DEFAULTS = {
    # 既定の採否。keep = 指定が無いレイヤは残す / drop = 落とす
    'DEFAULT'        => 'keep',
    # 室名照合  exact = 完全一致のみ / prefix = 前方一致も見る
    'ROOM_MATCH'     => 'prefix',
    # 記号の文字種(1-10)
    'SYMBOL_CN'      => '3',
    # 室名の基準線から記号の基準線までの距離(図寸mm)
    'SYMBOL_DY'      => '4.0',
    # 記号を書くレイヤ  same = 室名と同じ / 例 0:5
    'SYMBOL_LAYER'   => 'same',
    # 記号の線色  same = 室名と同じ / 例 2
    'SYMBOL_COLOR'   => 'same',
    # 凡例の書き出し  all = 全部 / used = 実際に使った記号だけ / no = 書かない
    'LEGEND_MODE'    => 'all',
    # 凡例の位置  auto = 図の右上 / 例 1200,800 (図寸mm 絶対座標)
    'LEGEND_POS'     => 'auto',
    'LEGEND_W1'      => '12',    # 記号欄の幅(図寸mm)
    'LEGEND_W2'      => '70',    # 仕上欄の幅(図寸mm)
    'LEGEND_RH'      => '6',     # 行の高さ(図寸mm)
    'LEGEND_CN'      => '3',     # 凡例の文字種
    'LEGEND_LAYER'   => 'same',  # 凡例のレイヤ same = 書き込みレイヤ任せ
    'LEGEND_COLOR'   => 'same',
    'LEGEND_TITLE'   => '仕上表',
    # 文字データの解釈  auto / rel(長さ成分) / abs(終点座標)
    'CHFORMAT'       => 'auto',
  }.freeze

  def initialize
    @keep     = []          # [lg, ly]  nil = ワイルドカード
    @drop     = []
    @rooms    = {}          # 正規化した室名 => 記号
    @legend   = []          # [記号, 説明] 記述順
    @droptext = []          # Regexp
    @retext   = []          # [Regexp, 置換後]
    @settings = DEFAULTS.dup
    @errors   = []
  end

  attr_reader :errors

  def self.load(path)
    r = new
    r.parse(read_cp932(path))
    r
  end

  # 項目として読むのは、行のあたま(桁下げなし)が英大文字だけの語で
  # 始まる行に限る。それ以外は説明文とみなす。
  # こうしておくと、説明文にわざわざ # を付けなくてよい。
  def directive?(line)
    line =~ /\A[A-Z_]+(?:\s|\z)/
  end

  def parse(text)
    text.each_line.with_index(1) do |line, no|
      s = line.sub(/\r?\n\z/, '')
      next unless directive?(s)

      key, rest = s.strip.split(/\s+/, 2)
      case key.upcase
      when 'KEEP'  then add_layer(@keep, rest, no)
      when 'DROP'  then add_layer(@drop, rest, no)
      when 'ROOM'  then add_room(rest, no)
      when 'LEGEND' then add_legend(rest, no)
      when 'DROPTEXT' then add_regexp(@droptext, rest, no)
      when 'RETEXT'   then add_retext(rest, no)
      when 'SET'      then add_setting(rest, no)
      else
        @errors << "#{no}行目: 知らない項目です (#{key})"
      end
    end
  end

  # 「0:3」「*:5」「3」(グループ省略)を [lg, ly] にする。nil = 何でも可
  def add_layer(list, rest, no)
    if rest.nil? || rest.empty?
      @errors << "#{no}行目: レイヤの指定がありません"
      return
    end
    spec = rest.split(/\s+/, 2)[0]
    lg, ly = spec.include?(':') ? spec.split(':', 2) : ['*', spec]
    list << [parse_layer_no(lg), parse_layer_no(ly)]
  end

  # Jw_cad のレイヤ番号は 0-f の16進。10進の 0-15 も受け付ける。
  def parse_layer_no(s)
    return nil if s.nil? || s == '*' || s.empty?
    return s.to_i(16) if s =~ /\A[0-9a-fA-F]\z/
    return s.to_i     if s =~ /\A(?:1[0-5]|\d)\z/
    nil
  end

  def add_room(rest, no)
    if rest.nil?
      @errors << "#{no}行目: ROOM は「室名 記号」の形で書きます"
      return
    end
    parts = rest.split(/\s+/)
    if parts.size < 2
      @errors << "#{no}行目: ROOM は「室名 記号」の形で書きます"
      return
    end
    sym  = parts.pop
    name = parts.join
    @rooms[normalize_key(name)] = sym
  end

  def add_legend(rest, no)
    if rest.nil?
      @errors << "#{no}行目: LEGEND は「記号 説明」の形で書きます"
      return
    end
    sym, desc = rest.split(/\s+/, 2)
    @legend << [sym, desc.to_s]
  end

  def add_regexp(list, rest, no)
    return if rest.nil? || rest.empty?
    begin
      list << Regexp.new(rest)
    rescue RegexpError => e
      @errors << "#{no}行目: 検索文字の書き方が不正です (#{e.message})"
    end
  end

  # RETEXT 平面図 => 天井伏図
  def add_retext(rest, no)
    return if rest.nil? || rest.empty?
    pat, rep = rest.split(/\s*=>\s*/, 2)
    if pat.nil? || pat.strip.empty?
      @errors << "#{no}行目: RETEXT は「検索 => 置換後」の形で書きます"
      return
    end
    begin
      @retext << [Regexp.new(pat.strip), rep.to_s]
    rescue RegexpError => e
      @errors << "#{no}行目: 検索文字の書き方が不正です (#{e.message})"
    end
  end

  def add_setting(rest, no)
    key, val = rest.to_s.split(/\s+/, 2)
    if key.nil? || !@settings.key?(key.upcase)
      @errors << "#{no}行目: 知らない設定です (#{key})"
      return
    end
    @settings[key.upcase] = val.to_s.strip
  end

  def [](key)      = @settings[key]
  def num(key)     = to_num(@settings[key]).to_f
  def int(key)     = @settings[key].to_i
  def whitelist?   = !@keep.empty?

  # レイヤを残すか。KEEP が1つでもあれば、書いたものだけを残す。
  def keep_layer?(lg, ly)
    return false if match_any?(@drop, lg, ly)
    return match_any?(@keep, lg, ly) if whitelist?
    self['DEFAULT'].downcase != 'drop'
  end

  def match_any?(list, lg, ly)
    list.any? do |(rlg, rly)|
      (rlg.nil? || rlg == lg) && (rly.nil? || rly == ly)
    end
  end
end

#--------------------------------------------------------------
# jwc_temp.txt の読み込み
#
#   座標は図寸(mm)。hs が縮尺の分母。
#   要素
#     x1 y1 x2 y2                線
#     x  y                       点
#     pt x y                     点
#     ci cx cy r [開始角 終了角 …]  円・円弧
#     ch x y f3 f4 "文字列        文字
#   属性
#     lg? ly? lc? lt? cn? …      直前までの状態が要素に効く
#   図面情報
#     h で始まる行
#--------------------------------------------------------------
class Reader
  ATTR_ORDER = %w[lg ly lc lt cn].freeze

  attr_reader :elements, :hcw, :hch, :hcd, :hs, :hp1, :skipped

  def initialize
    @elements = []
    @hcw = Array.new(11, 3.0)
    @hch = Array.new(11, 3.0)
    @hcd = Array.new(11, 0.5)
    @hs  = 1.0
    @hp1 = nil
    @skipped = Hash.new(0)
    @state = {}
  end

  def parse(text)
    text.each_line do |raw|
      line = raw.sub(/\r?\n\z/, '')
      s = line.strip
      next if s.empty? || s.start_with?('#')

      if s.start_with?('h')
        read_header(s)
      elsif (el = read_element(s))
        @elements << el
      else
        read_attribute(s)
      end
    end
    self
  end

  def read_header(s)
    case s
    when /\Ahcw\s+(.*)\z/ then @hcw = char_table($1, @hcw)
    when /\Ahch\s+(.*)\z/ then @hch = char_table($1, @hch)
    when /\Ahcd\s+(.*)\z/ then @hcd = char_table($1, @hcd)
    when /\Ahs\s+(#{NUM})/o then @hs = $1.to_f
    when /\Ahp1\s+(#{NUM})\s+(#{NUM})/o then @hp1 = [$1.to_f, $2.to_f]
    end
  end

  # 文字種 1-10 の値。添字を文字種番号に合わせるため先頭に 1 つ詰める。
  def char_table(str, fallback)
    vals = str.split(/\s+/).map { |v| to_num(v) }.compact
    return fallback if vals.empty?
    ([vals[0]] + vals)[0, 11].tap { |a| a << a.last while a.size < 11 }
  end

  def read_attribute(s)
    key = s[/\A[a-z]+/]
    return if key.nil?
    # lg0 / ly3 / lc2 / lt1 / cn3 / cn0 4 4 0.5 2 など。
    # 属性名は英字部分だけを見る(番号は行ごと保持する)。
    @state = @state.merge(key => s)
  end

  def read_element(s)
    case s
    when /\Ach\s+(#{NUM})\s+(#{NUM})\s+(#{NUM})\s+(#{NUM})\s+(.*)\z/om
      make(:text, [$1, $2, $3, $4].map(&:to_f), str: $5.sub(/\A"/, ''))
    when /\Aci\s+(.*)\z/
      nums = $1.split(/\s+/).map { |v| to_num(v) }
      return nil if nums.size < 3 || nums[0, 3].any?(&:nil?)
      make(:arc, nums.map { |v| v || 0.0 })
    when /\Apt\s+(#{NUM})\s+(#{NUM})\s*\z/o
      make(:point, [$1.to_f, $2.to_f])
    when /\A(#{NUM})\s+(#{NUM})\s+(#{NUM})\s+(#{NUM})\s*\z/o
      make(:line, [$1, $2, $3, $4].map(&:to_f))
    when /\A(#{NUM})\s+(#{NUM})\s*\z/o
      make(:point, [$1.to_f, $2.to_f])
    when /\A[a-z]/
      nil                      # 属性行として扱う
    else
      @skipped[s[0, 2]] += 1   # 対応していない要素
      nil
    end
  end

  def make(type, nums, str: nil)
    { type: type, nums: nums, str: str, attr: @state,
      lg: layer_no('lg'), ly: layer_no('ly'), cn: cn_no }
  end

  def layer_no(key)
    m = @state[key]
    return 0 if m.nil?
    n = m[/\A[a-z]+([0-9a-fA-F])/, 1]
    n ? n.to_i(16) : 0
  end

  def cn_no
    m = @state['cn']
    return 3 if m.nil?
    n = m[/\Acn(\d+)/, 1]
    n ? n.to_i : 3
  end

  # 属性行のうち、要素に効くものを決まった順で返す
  def self.attr_lines(el)
    ATTR_ORDER.map { |k| el[:attr][k] }.compact +
      el[:attr].reject { |k, _| ATTR_ORDER.include?(k) }.values
  end
end

#--------------------------------------------------------------
# 天井伏図をつくる
#--------------------------------------------------------------
class CeilingPlan
  def initialize(doc, rules)
    @doc     = doc
    @rules   = rules
    @log     = []
    @used    = []            # 実際に置いた記号(記述順に並べ直す)
    @counts  = Hash.new(0)
  end

  attr_reader :log, :counts

  def build
    kept    = filter_layers(@doc.elements)
    kept    = process_texts(kept)
    symbols = place_symbols(kept)

    body    = kept + symbols
    if body.empty?
      raise "天井伏図にする要素がありません。ルールファイルの KEEP / DROP を見直してください。"
    end

    dx, dy  = offset(body)
    out     = body.map { |el| move(el, dx, dy) }
    out    += legend(out)
    out
  end

  #--- 1. レイヤで残す/落とす --------------------------------
  def filter_layers(elements)
    elements.select do |el|
      if @rules.keep_layer?(el[:lg], el[:ly])
        true
      else
        @counts[:layer_dropped] += 1
        false
      end
    end
  end

  #--- 2. 文字の削除と置換 -----------------------------------
  def process_texts(elements)
    elements.each_with_object([]) do |el, acc|
      if el[:type] != :text
        acc << el
        next
      end
      s = el[:str]
      if @rules.droptext.any? { |re| re.match?(s) }
        @counts[:text_dropped] += 1
        next
      end
      before = s
      @rules.retext.each { |(re, rep)| s = s.gsub(re, rep) }
      if s.strip.empty?
        @counts[:text_dropped] += 1
        next
      end
      if s == before
        acc << el
      else
        # 文字列が変わったので、文字データが持つ長さも取り直す。
        # そのままだと Jw_cad 側で文字が引き伸ばされる。
        @counts[:text_replaced] += 1
        ux, uy, = direction(el)
        w = text_width(s, el[:cn])
        acc << el.merge(str: s, span: [ux * w, uy * w])
      end
    end
  end

  #--- 3. 室名の下に天井仕上記号を置く -----------------------
  def place_symbols(elements)
    scn   = @rules.int('SYMBOL_CN').clamp(1, 10)
    dy    = @rules.num('SYMBOL_DY')
    out   = []

    elements.each do |el|
      next unless el[:type] == :text
      sym = lookup_room(el[:str])
      next if sym.nil?

      x, y = el[:nums][0], el[:nums][1]
      ux, uy, len = direction(el)
      # 文字の基準線に対して右まわり 90 度が「下」
      px, py = uy, -ux

      w  = text_width(sym, scn)
      cx = x + ux * len / 2.0 + px * dy
      cy = y + uy * len / 2.0 + py * dy
      sx = cx - ux * w / 2.0
      sy = cy - uy * w / 2.0

      out << { type: :text, nums: [sx, sy, 0, 0], str: sym,
               attr: symbol_attr(el, scn), lg: el[:lg], ly: el[:ly],
               cn: scn, span: [ux * w, uy * w] }
      @used << sym unless @used.include?(sym)
      @counts[:symbols] += 1
    end
    out
  end

  def lookup_room(str)
    key = normalize_key(str)
    return @rules.rooms[key] if @rules.rooms.key?(key)
    return nil unless @rules['ROOM_MATCH'].downcase == 'prefix'
    # 「事務室(14.46㎡)」のように後ろに何か付いている場合。
    # 取り違えを避けるため、長い室名から順に見る。
    name = @rules.rooms.keys.select { |k| key.start_with?(k) }
                            .max_by(&:length)
    name && @rules.rooms[name]
  end

  # 文字の向き。単位ベクトルと文字列の長さを返す。
  def direction(el)
    x, y, f3, f4 = el[:nums]
    dx, dy = if el[:span]
               el[:span]
             else
               @doc.rel_ch? ? [f3, f4] : [f3 - x, f4 - y]
             end
    len = Math.hypot(dx, dy)
    return [1.0, 0.0, text_width(el[:str], el[:cn])] if len < EPS
    [dx / len, dy / len, len]
  end

  # 図寸(mm)での文字列の長さ。半角は全角の半分で数える。
  def text_width(str, cn)
    w = @doc.hcw[cn] || 3.0
    d = @doc.hcd[cn] || 0.0
    zen = han = 0
    str.each_char do |c|
      (c.bytesize == 1 || c.ascii_only?) ? han += 1 : zen += 1
    end
    n = zen + han
    return 0.0 if n.zero?
    w * zen + w / 2.0 * han + d * (n - 1)
  end

  def symbol_attr(el, scn)
    a = el[:attr].dup
    a['cn'] = "cn#{scn}"
    case @rules['SYMBOL_LAYER'].downcase
    when 'same' then # そのまま
    else
      lg, ly = @rules['SYMBOL_LAYER'].include?(':') ?
                 @rules['SYMBOL_LAYER'].split(':', 2) : ['*', @rules['SYMBOL_LAYER']]
      a['lg'] = "lg#{lg}" unless lg == '*'
      a['ly'] = "ly#{ly}" unless ly == '*'
    end
    a['lc'] = "lc#{@rules['SYMBOL_COLOR']}" unless @rules['SYMBOL_COLOR'].downcase == 'same'
    a
  end

  #--- 4. 指示点へ移す ---------------------------------------
  def offset(elements)
    hp = @doc.hp1
    if hp.nil?
      @log << '作図位置の指示がなかったので、元の平面図と同じ位置に作図します。'
      return [0.0, 0.0]
    end
    x0, y0, = bbox(elements)
    [hp[0] - x0, hp[1] - y0]
  end

  def bbox(elements)
    xs = []
    ys = []
    elements.each do |el|
      case el[:type]
      when :line  then xs.concat([el[:nums][0], el[:nums][2]])
                       ys.concat([el[:nums][1], el[:nums][3]])
      when :point then xs << el[:nums][0]; ys << el[:nums][1]
      when :arc
        cx, cy, r = el[:nums]
        xs.concat([cx - r, cx + r]); ys.concat([cy - r, cy + r])
      when :text
        ux, uy, len = direction(el)
        x, y = el[:nums][0], el[:nums][1]
        xs.concat([x, x + ux * len]); ys.concat([y, y + uy * len])
      end
    end
    return [0.0, 0.0, 0.0, 0.0] if xs.empty?
    [xs.min, ys.min, xs.max, ys.max]
  end

  def move(el, dx, dy)
    return el if dx.abs < EPS && dy.abs < EPS
    n = el[:nums].dup
    case el[:type]
    when :line
      n[0] += dx; n[1] += dy; n[2] += dx; n[3] += dy
    when :point, :arc
      n[0] += dx; n[1] += dy
    when :text
      n[0] += dx; n[1] += dy
      # 終点座標で持っている書式なら、終点も動かす
      unless @doc.rel_ch? || el[:span]
        n[2] += dx; n[3] += dy
      end
    end
    el.merge(nums: n)
  end

  #--- 5. 仕上表(凡例) ---------------------------------------
  def legend(placed)
    mode = @rules['LEGEND_MODE'].downcase
    return [] if mode == 'no'

    rows = @rules.legend
    rows = rows.select { |(sym, _)| @used.include?(sym) } if mode == 'used'
    return [] if rows.empty?

    cn  = @rules.int('LEGEND_CN').clamp(1, 10)
    rh  = @rules.num('LEGEND_RH')
    th  = @doc.hch[cn] || 3.0
    pad = 2.0

    # 設定した幅は最小値として扱い、文字がはみ出すときは広げる。
    fit = lambda { |strs, min|
      [min, strs.map { |s| text_width(s.to_s, cn) }.max.to_f + pad * 2].max
    }
    w1 = fit.call(['記号'] + rows.map(&:first), @rules.num('LEGEND_W1'))
    w2 = fit.call([@rules['LEGEND_TITLE']] + rows.map(&:last), @rules.num('LEGEND_W2'))

    x0, y0 = legend_origin(placed, w1 + w2, rh * (rows.size + 1))
    w = w1 + w2
    h = rh * (rows.size + 1)
    attr = legend_attr

    out = []
    add = lambda { |type, nums, str|
      out << { type: type, nums: nums, str: str, attr: attr,
               lg: 0, ly: 0, cn: cn }
    }

    # 外枠と罫線
    add.call(:line, [x0, y0, x0 + w, y0], nil)
    add.call(:line, [x0, y0 + h, x0 + w, y0 + h], nil)
    add.call(:line, [x0, y0, x0, y0 + h], nil)
    add.call(:line, [x0 + w, y0, x0 + w, y0 + h], nil)
    add.call(:line, [x0 + w1, y0, x0 + w1, y0 + h], nil)
    (1..rows.size).each do |i|
      yy = y0 + rh * i
      add.call(:line, [x0, yy, x0 + w, yy], nil)
    end

    # 見出し(最上段)と各行。上から順に並べる。
    ty = ->(i) { y0 + h - rh * (i + 1) + (rh - th) / 2.0 }
    head = ['記号', @rules['LEGEND_TITLE']]
    add.call(:text, [x0 + pad, ty.call(0), 0, 0], head[0])
    add.call(:text, [x0 + w1 + pad, ty.call(0), 0, 0], head[1])
    rows.each_with_index do |(sym, desc), i|
      add.call(:text, [x0 + pad, ty.call(i + 1), 0, 0], sym)
      add.call(:text, [x0 + w1 + pad, ty.call(i + 1), 0, 0], desc)
    end

    out.each { |el| el[:span] = [text_width(el[:str], cn), 0.0] if el[:type] == :text }
    @counts[:legend_rows] = rows.size
    out
  end

  def legend_origin(placed, w, h)
    pos = @rules['LEGEND_POS'].strip
    if pos.downcase != 'auto' && pos =~ /\A(#{NUM})\s*,\s*(#{NUM})\z/o
      return [$1.to_f, $2.to_f - h]
    end
    x0, y0, x1, y1 = bbox(placed)
    _ = [x0, y0]
    [x1 + 10.0, y1 - h]
  end

  def legend_attr
    a = {}
    unless @rules['LEGEND_LAYER'].downcase == 'same'
      lg, ly = @rules['LEGEND_LAYER'].include?(':') ?
                 @rules['LEGEND_LAYER'].split(':', 2) : ['*', @rules['LEGEND_LAYER']]
      a['lg'] = "lg#{lg}" unless lg == '*'
      a['ly'] = "ly#{ly}" unless ly == '*'
    end
    a['lc'] = "lc#{@rules['LEGEND_COLOR']}" unless @rules['LEGEND_COLOR'].downcase == 'same'
    a['cn'] = "cn#{@rules.int('LEGEND_CN').clamp(1, 10)}"
    a
  end
end

#--------------------------------------------------------------
# 読み込んだ図面
#--------------------------------------------------------------
class Doc
  attr_reader :elements, :hcw, :hch, :hcd, :hs, :hp1, :skipped

  def initialize(reader, rules)
    @elements = reader.elements
    @hcw = reader.hcw
    @hch = reader.hch
    @hcd = reader.hcd
    @hs  = reader.hs
    @hp1 = reader.hp1
    @skipped = reader.skipped
    @rel = detect_ch_format(rules['CHFORMAT'])
  end

  def rel_ch? = @rel

  # 文字データ「ch 始点X 始点Y ○ ○ "文字列」の第3・第4フィールドは
  # 「文字列の長さ成分」と「終点座標」の2通りの説明がある。
  # 水平な文字なら、前者は第4=0、後者は第4=始点Y になるので、
  # 読み込んだデータから多数決で決める。
  def detect_ch_format(mode)
    case mode.to_s.downcase
    when 'rel' then return true
    when 'abs' then return false
    end

    rel = abs = 0
    @elements.each do |el|
      next unless el[:type] == :text
      y, f3, f4 = el[:nums][1], el[:nums][2], el[:nums][3]
      next if y.abs < EPS                    # 判定に使えない
      rel += 1 if f4.abs < EPS
      abs += 1 if (f4 - y).abs < EPS
      # 長さ成分なら第3フィールドは文字列の長さぶんしかない
      rel += 1 if f3.abs < el[:nums][0].abs * 0.5
    end
    abs > rel ? false : true                 # 判断がつかなければ長さ成分
  end
end

#--------------------------------------------------------------
# 書き出し
#--------------------------------------------------------------
class Writer
  ATTR_ORDER = %w[lg ly lc lt cn].freeze

  def initialize(rel_ch)
    @rel = rel_ch
    @cur = {}
    @out = []
  end

  def add(el)
    attrs(el[:attr] || {})
    @out << element_line(el)
  end

  def attrs(a)
    keys = ATTR_ORDER + (a.keys - ATTR_ORDER)
    keys.each do |k|
      v = a[k]
      next if v.nil? || @cur[k] == v
      @cur[k] = v
      @out << v
    end
  end

  def element_line(el)
    n = el[:nums]
    case el[:type]
    when :line  then [n[0], n[1], n[2], n[3]].map { |v| fmt(v) }.join(' ')
    when :point then "pt #{fmt(n[0])} #{fmt(n[1])}"
    when :arc   then "ci #{el[:nums].map { |v| fmt(v) }.join(' ')}"
    when :text  then text_line(el)
    end
  end

  def text_line(el)
    x, y = el[:nums][0], el[:nums][1]
    if el[:span]
      f3, f4 = el[:span]
      f3, f4 = [x + f3, y + f4] unless @rel
    else
      f3, f4 = el[:nums][2], el[:nums][3]
    end
    "ch #{fmt(x)} #{fmt(y)} #{fmt(f3)} #{fmt(f4)} \"#{el[:str]}"
  end

  # 先頭に hd を書かないので、範囲選択した元の平面図は消えずに残る。
  def to_s = (@out.join("\r\n") + "\r\n")
end

#--------------------------------------------------------------
# メイン
#--------------------------------------------------------------
def abort_with(temp_path, message)
  write_cp932(temp_path, "he #{message}\r\n") if temp_path && File.exist?(temp_path)
  warn "#{APPTITLE}: #{message}"
  exit 1
end

# jwc_temp.txt を探す。
#   Jw_cad はカレントディレクトリに作成するが、環境によって
#   バッチファイルのフォルダになることもあるので両方を見る。
def find_temp
  [File.join(Dir.pwd, 'jwc_temp.txt'),
   File.join(script_dir, 'jwc_temp.txt')].find { |p| File.exist?(p) }
end

def main
  temp  = ARGV[0] && !ARGV[0].empty? ? ARGV[0] : find_temp
  rpath = ARGV[1] && !ARGV[1].empty? ? ARGV[1] : File.join(script_dir, '天伏図ルール.txt')

  if temp.nil? || !File.exist?(temp)
    warn "#{APPTITLE}: jwc_temp.txt が見つかりません。" \
         "バッチファイルと jww_ceiling_plan.rb が同じフォルダにあるか確認してください。"
    exit 1
  end
  unless File.exist?(rpath)
    abort_with(temp, "ルールファイルが見つかりません。#{to_utf8(File.basename(rpath))} をスクリプトと同じ場所に置いてください。")
  end

  rules = Rules.load(rpath)
  unless rules.errors.empty?
    abort_with(temp, "ルールファイルに誤りがあります。 #{rules.errors.first}")
  end

  reader = Reader.new.parse(read_cp932(temp))
  if reader.elements.empty?
    abort_with(temp, '図形が選択されていません。')
  end

  doc  = Doc.new(reader, rules)
  plan = CeilingPlan.new(doc, rules)

  begin
    elements = plan.build
  rescue RuntimeError => e
    abort_with(temp, e.message)
  end

  writer = Writer.new(doc.rel_ch?)
  elements.each { |el| writer.add(el) }
  write_cp932(temp, writer.to_s)

  write_log(rpath, doc, plan, elements.size)
end

def write_log(rpath, doc, plan, written)
  c = plan.counts
  lines = []
  lines << "#{APPTITLE}  #{Time.now.strftime('%Y-%m-%d %H:%M:%S')}"
  lines << "ルールファイル : #{to_utf8(rpath)}"
  lines << "縮尺           : 1/#{fmt(doc.hs)}"
  lines << "文字データ書式 : #{doc.rel_ch? ? 'rel(長さ成分)' : 'abs(終点座標)'}"
  lines << "読み込んだ要素 : #{doc.elements.size}"
  lines << "レイヤで除外   : #{c[:layer_dropped]}"
  lines << "文字を削除     : #{c[:text_dropped]}"
  lines << "文字を置換     : #{c[:text_replaced]}"
  lines << "置いた記号     : #{c[:symbols]}"
  lines << "凡例の行数     : #{c[:legend_rows]}"
  lines << "書き出した要素 : #{written}"
  unless doc.skipped.empty?
    lines << ''
    lines << '対応していない要素があったため、複写されませんでした:'
    doc.skipped.each { |k, v| lines << "  #{k} … #{v} 個" }
  end
  plan.log.each { |m| lines << m }
  write_cp932(File.join(script_dir, 'jww_ceiling_plan.log'), lines.join("\r\n") + "\r\n")
rescue StandardError
  # ログが書けなくても作図は成立させる
end

main if $PROGRAM_NAME == __FILE__
