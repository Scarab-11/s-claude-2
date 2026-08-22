# ComfyUI ワークフロー集

画風・構図・顔を別々の画像で指定するためのワークフロー。

| ファイル | 内容 |
|---|---|
| `Flux1_StyleRef_x_ControlNet.json` | **推奨。** FLUX.1-dev 版。Image1 の画風 × Image2 の構図。8GB VRAM 向け |
| `Flux1_StyleBlend_TwoImages.json` | FLUX.1-dev 版。**2枚の画風を融合**させる（構図制御なし）。8GB VRAM 向け |
| `Flux1_FaceSwap_StyleFromImage1.json` | FLUX.1-dev 版。**Image1 の画風のまま顔だけ Image2 に差し替える**。8GB VRAM 向け |
| `Flux1_Repaint_Image2_in_Image1Style.json` | FLUX.1-dev 版。**Image1 の画風で Image2 を丸ごと描き直す**。位置合わせ不要。8GB VRAM 向け |
| `Flux2Klein_FaceSwap_StyleFromImage1.json` | FLUX.2 Klein 9B + Best Face Swap LoRA。**顔は Image2、画風は Image1**。マスク不要 |
| `Flux1_ShapeOnly_FaceFromImage2.json` | FLUX.1-dev 版。**Image2 からは形だけ**を取り、画風は Image1。前処理は depth / canny / lineart などから選択式、2 種併用可。8GB VRAM 向け |
| `Flux2_StyleRef_x_ControlNet.json` | FLUX.2-dev 版。同じ構成だが **VRAM 16GB 以上が必要** |
| `Krea2_StyleRef_x_Structure.json` | Krea2 版。depth ControlNet と img2img を切り替えられる統合版 |
| `Krea2_StyleRef_x_DepthControlNet.json` | Krea2 版。depth ControlNet のみの初版 |
| `Krea2_StyleRef_x_LineArtReference.json` | Krea2 版。線画を参照画像として渡す試作 |

- [FLUX.2 版](#flux2-版)
- [FLUX.1 版](#flux1-版) — 画風 × 構図
- [2枚の画風を融合する版](#2枚の画風を融合する版)
- [Face Swap 版](#face-swap-版)
- [Image1 の画風で Image2 を描き直す版](#image1-の画風で-image2-を描き直す版)
- [Klein Face Swap 版](#klein-face-swap-版)
- [形だけを渡す版](#形だけを渡す版)
- [Krea2 版](#krea2-版)

このドキュメントでは、ノードを**キャンバス上のタイトル**（例:「Image1 — 画風の参照」）で
指しています。ノードのタイトルバーに表示されている文字列がそれです。

---

## Krea2 版

`Krea2_StyleRef_x_Structure.json`

| 入力 | ノード | 決めるもの |
|---|---|---|
| **Image1** | 「Image1 — 画風の参照」 | 画風・色調・タッチ |
| **Image2** | 「Image2 — 形・構図」 | 形・構図・レイアウト |

### 構成

```
Image1 → Kontext 用にリサイズ → プロンプト（Image1 を画風として渡す）
                                 └ 画風 LoRA が画風として解釈

Image2 → Kontext 用にリサイズ ─┬→ Image2 → latent → サンプラー
                               │
                               └→ Depth 前処理 → サイズ合わせ → 構図の適用（Krea2 Control）

拡散モデルの読み込み → Ostris Edit のモデルパッチ → 画風 LoRA
                     → depth Control LoRA → 構図の適用 → サンプラー
```

出力解像度は「Image2 を Kontext 用にリサイズ ◀ 出力解像度を決める」が決めるため、
**Image2 のアスペクト比**に追従する。

### モード切替

`MODE A - depth ControlNet` グループのタイトルバーを右クリック →
**Bypass Group Nodes** で一括バイパスできる。

| | ControlNet グループ | 「サンプラー」の `denoise` | 用途 |
|---|---|---|---|
| **Mode A** | 有効 | `1.00` | Image2 が写真・3DCG |
| **Mode B** | バイパス | `0.60`〜`0.75` | Image2 が線画・ラフ |
| **Mode C** | 有効 | `0.80`〜`0.90` | 構図を固定しつつ元画像の色味も引き継ぐ |

Mode A で `denoise` が `1.00` のとき、「Image2 → latent」の内容は完全にノイズで
打ち消される。flow-matching の `noise_scaling` は `sigma * noise + (1 - sigma) * latent` で、
`denoise=1.0` では `sigma=1.0` となり latent 項の係数が 0 になるため、
空の latent を使った場合と数学的に等価になる。

#### Mode B の denoise 目安

- `0.50` — 線画の形をほぼ保持。ただし白背景も残りやすい
- `0.65` — 標準。形は保ちつつ塗りと質感が入る
- `0.80` — 大きく描き変わる。線画は構図のあたり程度

### 必要なもの

カスタムノード:

- [ostris/ComfyUI-Krea2-Ostris-Edit](https://github.com/ostris/ComfyUI-Krea2-Ostris-Edit)
- [facok/comfyui-krea2-controlnet](https://github.com/facok/comfyui-krea2-controlnet) — Mode A のみ
- [Fannovel16/comfyui_controlnet_aux](https://github.com/Fannovel16/comfyui_controlnet_aux) —
  「Depth 前処理」用。深度マップを自前で用意するなら不要（Ctrl+B でバイパス）

モデル:

```
models/loras/Krea2/
├── krea2_style_reference.safetensors   # ostris/krea2_turbo_style_reference
└── depth-control-lora.safetensors      # Patil/Krea-2-depth-controlnet (862MB, Mode A のみ)
```

Mode B だけを使う場合、ControlNet 側のノードパックと LoRA はどちらも不要。

### Control LoRA の対応状況

| 制御タイプ | 公開重み |
|---|---|
| depth | [Patil/Krea-2-depth-controlnet](https://huggingface.co/Patil/Krea-2-depth-controlnet) |
| pose | [thedeoxen/Krea-2-pose-controlnet](https://huggingface.co/thedeoxen/Krea-2-pose-controlnet) |
| canny / lineart / tile / normal | 未公開（[学習コード](https://github.com/Tanmaypatil123/Krea-2-controlnet)のみ） |

`comfyui-krea2-controlnet` が canny や lineart の前処理出力を受け取れるのは
入力仕様の話であって、対応する Control LoRA が存在するという意味ではない。
depth LoRA に canny 画像を流しても制御は効かない（期待する入力分布が違う）。
線画を構図ソースにする場合は Mode B を使う。

pose に差し替える場合:

1. 「depth Control LoRA の読み込み」の LoRA を pose 用に変更
2. 「Depth 前処理」を `DWPreprocessor` / `OpenposePreprocessor` に差し替え
3. 「深度マップのサイズ合わせ」の `channel_mode` を `rgb`、`normalize` を `none` に変更
   （骨格図は色が意味を持つため。深度マップはグレースケール＋正規化）

### 調整の勘所

- 構図が効きすぎて画風が乗らない → 「depth Control LoRA の読み込み」の `strength` を 0.6〜0.8 に下げる
- 構図が守られない → 同上を上げる、または「画風 LoRA（krea2_style_reference）」を下げる
- ControlNet 併用時は「サンプラー」の `steps` を 8 → 10 前後にすると安定しやすい
- `cfg` は 1.0（turbo 系）のため、「ネガティブプロンプト」は実質無効

---

## FLUX.2 版

`Flux2_StyleRef_x_ControlNet.json`

Krea2 では Style Reference と ControlNet を同時に成立させられなかった
（公開 Control LoRA が depth / pose のみで、線画を構図として渡す手段が無い）。
FLUX.2 は両方を素直に併用できる。

| 入力 | ノード | 決めるもの |
|---|---|---|
| **Image1** | 「Image1 — 画風の参照」 | 画風・色調・タッチ |
| **Image2** | 「Image2 — 形・構図」 | 形・構図 |

```
Image1 → 約1MPに縮小 → latent 化 → 画風を conditioning に付与 ┐
                                                              ├→ 構図の適用 → ガイダンス
Image2 → 生成解像度に合わせる ────────────────────────────────┘
                        └→ ControlNet に渡る実際の画像
```

「構図の適用（Flux2 Fun ControlNet）」は conditioning を複製して制御情報を足すだけなので、
「画風を conditioning に付与（ReferenceLatent）」が入れた参照ラテントはそのまま残る。
ControlNet 側も参照ラテントを認識し、制御を本画像の部分にのみ適用する。
よって両者は競合しない。

### ControlNet の対応種別

pose / canny / depth / HED / MLSD / tile を**自動判別**する。
種別を切り替えるノードは無く、**線画はそのまま入れてよい**（前処理ノード不要）。

### 調整箇所

| 症状 | 変更するノード | 変更内容 |
|---|---|---|
| 構図が Image2 に従わない | 「構図の適用（Flux2 Fun ControlNet）」 | `strength` 0.75 → 0.90 |
| 線画の線が出力に残る | 同上 | `strength` 0.75 → 0.60 |
| 画風が乗らない | 「プロンプト」 | style の記述を具体化する |

解像度は「width（生成幅）」「height（生成高さ）」の 2 つだけ変えれば、
latent・scheduler・Image2 のリサイズの 3 つに伝わる。

### VRAM 要件（重要）

**8GB では動作しない。** 「ControlNet モデルの読み込み」は

```python
controlnet.to(device=device, dtype=dtype)
```

でチェックポイント全体を VRAM に常駐させる。ComfyUI のモデルマネージャの管理外なので
オフロードされない。8.3GB のこのモデルでは 8GB カードがそれだけで埋まり、
後続の VAE エンコードが 128MB すら確保できずに OOM になる。

また この ControlNet は **flux2-dev 専用**で、Klein 4B / 9B では使えない
（[HF discussion](https://huggingface.co/alibaba-pai/FLUX.2-dev-Fun-Controlnet-Union/discussions/3)）。
テキストエンコーダも T5 ではなく Mistral 3 Small が必要。

8GB 環境では `Flux1_StyleRef_x_ControlNet.json` を使うこと。

### 必要なもの

| 種類 | ファイル | 置き場所 |
|---|---|---|
| diffusion model | `flux2-dev`（bf16 / fp8 / gguf q4_k_m） | `models/diffusion_models/` |
| text encoder | `mistral_3_small_flux2_*.safetensors` | `models/text_encoders/` |
| VAE | `flux2-vae.safetensors` | `models/vae/` |
| ControlNet | `FLUX.2-dev-Fun-Controlnet-Union.safetensors`（約 8.3GB） | `models/controlnet/` |

カスタムノードは [`bryanmcguire/comfyui-flux2fun-controlnet`](https://github.com/bryanmcguire/comfyui-flux2fun-controlnet) の 1 つだけ。
ControlNet 本体は [`alibaba-pai/FLUX.2-dev-Fun-Controlnet-Union`](https://huggingface.co/alibaba-pai/FLUX.2-dev-Fun-Controlnet-Union)。

---

## FLUX.1 版

`Flux1_StyleRef_x_ControlNet.json`

FLUX.2 版と同じ役割分担を、8GB VRAM で動く構成にしたもの。
ベースは ComfyUI 公式テンプレート `flux_redux_model_example.json`。

| 入力 | ノード | 決めるもの |
|---|---|---|
| **Image1** | 「Image1 — 画風の参照」 | 画風・色調・タッチ |
| **Image2** | 「Image2 — 形・構図」 | 形・構図 |

```
プロンプト → 画風の強さ（Redux）┐
                                ├→ 構図の適用（ControlNet）→ サンプラー → 最終出力
Image1 → 画風として読み取る ────┘

Image2 → 生成解像度に合わせる → Canny 前処理 ─┬→ 構図の適用（ControlNet）
                                              └→ ControlNet に渡る実際の画像
```

### 「Union の制御タイプ」は画像を加工しない

このノードがやるのは、どの mode embedding を使うかを ControlNet に伝えることだけ。
`canny` や `lineart` を選んでも、**写真は写真のまま**渡る。
線を取り出すには前処理が必要なので、ComfyUI 標準の
「Canny 前処理（線を抽出）」を間に入れてある。

さらに **Union Pro 2.0 では型指定そのものが無視される。**
2.0 は mode embedding を持たないため、`auto` でも手動指定でも結果は同じ。
型指定を効かせたい場合は「ControlNet モデルの読み込み」で Union Pro **1.0** を読み込む。

選べる型は ComfyUI 本体の `comfy/cldm/control_types.py` に定義された 8 種類と `auto`。

| 入れる画像 | 選ぶ値 |
|---|---|
| 線画 / canny / MLSD | `canny/lineart/anime_lineart/mlsd` |
| ラフ線 / scribble / HED | `hed/pidi/scribble/ted` |
| 深度マップ | `depth` |
| ポーズ | `openpose` |
| 法線マップ | `normal` |
| セグメンテーション | `segment` |
| タイル | `tile` |
| 部分描き直し | `repaint` |

### 「Canny 前処理（線を抽出）」の使い分け

| Image2 の中身 | 扱い |
|---|---|
| 写真・イラスト | そのまま有効。線が抽出される |
| 最初から線画 | このノードを選んで **Ctrl+B** でバイパス（素通し） |

「ControlNet に渡る実際の画像」に、ControlNet が受け取るのと同じ画像が出る。
実行後にここを見れば、線が取れているか、構図が切れていないかが分かる。
この表示は「Union の制御タイプ」の値には影響されない（経路が別のため）。

### 調整箇所

| 症状 | 変更するノード | 変更内容 |
|---|---|---|
| 構図が Image2 に従わない | 「構図の適用（ControlNet）」 | `strength` 0.75 → 0.90 |
| 線画の線が出力に残る | 同上 | `end_percent` 0.85 → 0.60 |
| 画風が乗らない | 「画風の強さ（Redux）」 | `strength` 0.6 → 0.9 |
| 画風が強すぎる | 同上 | `strength` 0.6 → 0.3 |
| 線が少なすぎる | 「Canny 前処理（線を抽出）」 | `low_threshold` 0.2 → 0.1 |
| 線が多すぎる・ノイズだらけ | 同上 | `high_threshold` 0.5 → 0.8 |

実際に良い結果が出た組み合わせは 画風 `0.9` / 構図 `0.90` / `end_percent` `0.85`。

解像度は「width（生成幅）」「height（生成高さ）」の 2 つだけ変えれば、
latent・ModelSamplingFlux・Image2 のリサイズの 3 つに伝わる。8GB なら 832×1216 程度まで。

### 配線の注意

「構図の適用（ControlNet）」の `negative` には「ネガティブプロンプト（空でよい）」を、
`vae` には「VAE の読み込み」を繋いである。Union Pro 2.0 は latent 空間で
制御情報を作るため VAE が必須で、未接続だとサンプリング開始時に
`This Controlnet needs a VAE but none was provided` で落ちる。

### 必要なもの

| 種類 | ファイル | 置き場所 |
|---|---|---|
| diffusion model | `flux1-dev-fp8.safetensors` | `models/diffusion_models/` |
| text encoder | `t5xxl_fp8_e4m3fn_scaled.safetensors` + `clip_l.safetensors` | `models/text_encoders/` |
| VAE | `ae.safetensors` | `models/vae/` |
| style model | `flux1-redux-dev.safetensors` | `models/style_models/` |
| clip vision | `sigclip_vision_patch14_384.safetensors` | `models/clip_vision/` |
| ControlNet | [`Shakker-Labs/FLUX.1-dev-ControlNet-Union-Pro-2.0`](https://huggingface.co/Shakker-Labs/FLUX.1-dev-ControlNet-Union-Pro-2.0) | `models/controlnet/` |

**カスタムノードは不要。** すべて ComfyUI 標準ノードで構成されている。

`depth` や `openpose` の前処理ノードは標準には無い。必要なら
[`comfyui_controlnet_aux`](https://github.com/Fannovel16/comfyui_controlnet_aux)
を入れて「Canny 前処理（線を抽出）」を差し替える。

### Union Pro 1.0 と 2.0 の比較

| | 1.0 | 2.0 |
|---|---|---|
| ファイルサイズ | 6.15 GB | **3.98 GB** |
| mode embedding | あり（型指定が効く） | なし（型指定は無視） |
| canny / pose の品質 | — | **向上** |
| soft edge | なし | **あり** |
| tile | **あり** | 削除 |

**8GB 環境では 2.0 を推奨。** 2.2GB 小さいぶん FLUX 本体のオフロードが減って速い。
canny と pose の品質も改善されている。1.0 が要るのは tile モードを使うときだけ。

手元のファイルがどちらかは、起動ログの `ControlNetFlux` のサイズで判別できる
（約 4000 MB なら 2.0、約 6300 MB なら 1.0）。

### 既知の衝突: comfyui-flux2fun-controlnet

FLUX.2 用の [`comfyui-flux2fun-controlnet`](https://github.com/bryanmcguire/comfyui-flux2fun-controlnet)
を入れていると、この FLUX.1 版がサンプリング開始直後に落ちる。

```
TypeError: patched_forward_orig() got an unexpected keyword argument 'timestep_zero_index'
```

原因は、このノードパックが **import 時に無条件で**
`comfy.ldm.flux.model.Flux.forward_orig` を差し替えていること。
使っていない FLUX.1 ワークフローにも patch が効いてしまい、
差し替え後の関数の引数に `timestep_zero_index` が無いため呼び出しと合わない。

対処はどちらか:

1. `custom_nodes/comfyui-flux2fun-controlnet` を削除または無効化して ComfyUI を再起動
2. `flux_patch.py` の `patched_forward_orig` の引数に 1 行足す

```python
def patched_forward_orig(
        self, img, img_ids, txt, txt_ids, timesteps, y,
        guidance=None,
        control=None,
        timestep_zero_index=None,   # ← これを追加
        transformer_options={},
        attn_mask=None,
):
```

差し替えは import 時に起きるので、**ComfyUI の完全な再起動が必要**。
起動ログに `[Flux2 Fun] ControlNet patch applied` が出なくなれば解除されている。

---

## 2枚の画風を融合する版

`Flux1_StyleBlend_TwoImages.json`

構図制御は使わず、**読み込んだ 2 枚を混ぜて**出力する。

混ぜる系統が 2 つあり、役割が違う。

| 何を混ぜるか | どのノード | 実体 |
|---|---|---|
| **顔・構図** | 「2枚を重ねる ◀ 顔の混合比」の `blend_factor` | 画素を実際に重ねる |
| **画風・色** | 「画風A の強さ」「画風B の強さ」の `strength` | Redux トークン |

```
顔:   Image1 → 画風A を生成解像度に合わせる ┐
                                            ├ 2枚を重ねる → latent 化 → サンプラー
      Image2 → 画風B を生成解像度に合わせる ┘        └→ 重ねた結果（出発点）

画風: Image1 → 画風として読み取る → 画風A の強さ ┐
      Image2 → 画風として読み取る → 画風B の強さ ┴→ ガイダンス
```

### Redux だけでは顔は保てない

Redux トークンを 2 系統並べれば画風は混ざるが、**顔の同一性は再現されない**。
Redux は画像を 384×384 のトークン列に潰すので、個人を特定する情報が落ちる。
空の latent から始める text-to-image では画素側の手がかりも無いため、
出力の顔は毎回ゼロから生成される。

そこで 2 枚を実際に重ねた画像を出発点に据え、
「denoise ◀ 元の2枚をどれだけ残すか」でどれだけ残すかを決める構成にしてある。

| `denoise` | 結果 |
|---|---|
| `0.30` | ほぼ重ねたまま。ズレだけが整理される |
| `0.40` | 元の 2 枚の面影が強く残る |
| `0.60` | 既定値。顔立ちを引き継ぎつつ絵として整う |
| `0.80` | かなり描き変わる |
| `1.00` | 出発点が消えて完全な text-to-image。顔は別人になる |

`denoise` が `1.00` のとき出発点が消えるのは、flow-matching の `noise_scaling` が
`sigma * noise + (1 - sigma) * latent` で、`denoise=1.0` では `sigma=1.0` となり
latent 項の係数が 0 になるため。空 latent のノードは不要なので削除してある。

**顔が全然違う人になるときは、まず `denoise` を下げる。**

「2枚を重ねる ◀ 顔の混合比」の `blend_factor` は `0.0` で A のみ、`1.0` で B のみ、
`0.5` で等分。重ねた結果は「重ねた結果（出発点）」に出るので、見ながら決められる。

### 出力が硬い・AI っぽいとき

重ねた画像より最終出力のほうが悪く見えるのは、サンプラーが絵を描き直しているから。
重なりの曖昧さ（にじみ・低コントラスト）は真っ先に潰される。

| 変更するノード | 変更内容 |
|---|---|
| 「denoise ◀ 元の2枚をどれだけ残すか」 | `0.60` → `0.35` |
| 「FluxGuidance ◀ 絵の磨き具合」 | `3.5` → `2.0`〜`2.5` |
| 「プロンプト（画材を書く）」 | 人物ではなく画材と質感だけを書く |

プロンプト例:

```
watercolor portrait on rough paper, loose wet-on-wet washes,
visible paper texture, muted palette, unfinished edges, soft focus
```

人物の描写は書かない。顔と構図は「2枚を重ねる ◀ 顔の混合比」が担当しているので、
プロンプトは画材と質感だけを指定する。

### なぜ比が strength で決まるのか

`strength_type` が `multiply` のとき、`nodes.py:1134` が

```python
cond *= strength
```

と Redux トークンそのものを定数倍しているため、2 段直列にすれば比がそのまま効く。
`attn_bias` は `log(strength)` を attention バイアスに足す別系統で、
`strength` が 1.0 だと何も起きない。混合比の調整には `multiply` を使う。

### 画風の混合比の目安

| したいこと | 「画風A の強さ」 | 「画風B の強さ」 |
|---|---|---|
| 等分に混ぜる（既定値） | 0.6 | 0.6 |
| A を主、B を隠し味 | 0.8 | 0.3 |
| B を主、A を隠し味 | 0.3 | 0.8 |
| 両方もっと強く | 0.9 | 0.9 |
| プロンプトを効かせたい | 0.4 | 0.4 |

| 症状 | 対処 |
|---|---|
| 片方の絵がそのまま出てしまう | その側の `strength` を 0.3 前後まで下げる |
| どちらの画風も乗らない | 両方 0.9 に上げる |
| 混ざらず継ぎ接ぎに見える | 2 枚の明度・彩度を近づけてから読み込む |

片方だけの効果を確認したいときは、その強さのノードを選んで
**Ctrl+B** でバイパスすると素通しになる。

### crop を none にしてある

「Image1 を画風として読み取る」「Image2 を画風として読み取る」の `crop` は、
テンプレート既定の `center` ではなく **`none`**。
`center` は中央を正方形に切り取るため画面端の色がトークンに入らない。
色彩を混ぜる用途では `none` のほうが元画像の色を拾う。

### 解像度は参照画像に合わせる

「width（生成幅）」「height（生成高さ）」は `832 × 1216`。
テンプレート既定の `1024 × 1024` のままだと縦長の参照画像が正方形に詰め込まれ、
構図ごと作り直されて顔も変わる。

### 必要なもの

`Flux1_StyleRef_x_ControlNet.json` と同じ。ただし **ControlNet は不要**。
カスタムノードも不要。

構図を指定する経路が無いので、レイアウトはプロンプトと seed 任せになる。

---

## Face Swap 版

`Flux1_FaceSwap_StyleFromImage1.json`

**Image1 の画風・色彩・雰囲気をそのまま残し、顔だけ Image2 の形に差し替える。**

| 入力 | ノード | 役割 |
|---|---|---|
| **Image1** | 「Image1 — 画風の元＆キャンバス（顔をマスクで塗る）」 | 画風の元。かつキャンバス本体 |
| **Image2** | 「Image2 — 顔の形」 | 顔の形 |

### 手順

1. 「Image1 — 画風の元＆キャンバス（顔をマスクで塗る）」に、画風の元にしたい絵を読み込む
2. そのノードの**画像部分を右クリック** → **Open in MaskEditor** を選び、
   差し替えたい**顔の範囲をブラシで塗る**
3. 右下の **Save to node** を押す。**押さないと保存されない**
4. 「Image2 — 顔の形」に、顔の形の元にしたい絵を読み込む
5. 実行。「貼り付け結果（描き直す前）」と「最終出力」に結果が出る

手順 3 に成功すると、ノードのファイル名表示が `clipspace/...` に変わる。
これがマスクが入った証拠。

### マスクは顔だけにする

髪まで塗ると髪ごと描き直しになり、Image1 の絵柄が失われやすい。
**眉から顎まで、輪郭の内側だけ**を塗るほうがきれいに馴染む。
髪や首は Image1 のまま残したほうが結果が良い。

### 位置合わせ（ここが一番大事）

見るのは **「仮置きの確認（マスクを掛ける前）」**。Image1 の上に Image2 が
そのまま重なった状態が出る。**Image2 の顔が Image1 の顔と同じ位置・同じ大きさに
来るまで**、次の 2 つを調整する。

| 調整するもの | ノード | 値 |
|---|---|---|
| 大きさ | 「Image2 の顔の大きさ ◀ 倍率」 | `scale_by`（`1.0` = キャンバスと同じ、`0.6` = 6割） |
| 位置 | 「Image2 の位置を決める（仮置き）」 | `x`（右が正）/ `y`（下が正） |

合ったら「貼り付け結果（描き直す前）」を見る。Image1 の顔の位置に Image2 の顔が
はまっていれば準備完了。縮小すると右下に余白ができるが、マスクの外なので
出力には影響しない。

Image2 は手前の「Image2 をキャンバスに合わせる」で Image1 と同じ解像度に
そろえてある。ここは自動なので触らなくてよい。大きさの調整は倍率のほうで行う。

「Image2 の位置を決める（仮置き）」はマスクを繋いでいないので、Image2 の矩形が
そのまま Image1 の上に置かれる。次の「顔をマスクの形で合成」がマスクを掛けて、
顔の範囲だけを採用する。この 2 段構成にしているのは、`ImageCompositeMasked` が
マスクを **source の大きさに合わせて拡縮する**ため。縮めた Image2 に直接マスクを
渡すと、マスクごと縮んで顔の位置と対応しなくなる。

### 出力が Image2 と似ていないとき

まず位置合わせを疑う。上の 2 つのプレビューで顔が重なっているか確認する。
合っているのに似ないなら「denoise ◀ 顔をどれだけ描き直すか」を下げる。

| `denoise` | 結果 |
|---|---|
| `0.45` | Image2 の顔立ちがよく残る。写真の質感も残りやすい |
| `0.65` | 既定値 |
| `0.85` | Image1 の絵柄になじむが、顔は Image2 に似なくなる |

顔立ちを取るか絵柄を取るかの綱引き。`0.65` から上下に振って探す。
マスクの外は一切変わらないので、どちらに振っても顔以外は劣化しない。

### 出力が Image1 と全く同じになるとき

**マスクが空**。「貼り付け結果（描き直す前）」に Image2 の顔が見えていなければ確定。

アルファチャンネルの無い画像を読み込むと、`nodes.py:1788` で

```python
mask = torch.zeros((64, 64), dtype=torch.float32, device="cpu")
```

つまり全面ゼロのマスクが出力される。あとは連鎖する。

| ノード | 全ゼロマスクでの挙動 |
|---|---|
| 「顔をマスクの形で合成」 | Image2 を 1 ピクセルも採用しない |
| 「マスク内だけ描き直す」 | 描き直す領域がゼロ → サンプラーが何もしない |
| 「マスク外を Image1 に戻す」 | 戻す領域がゼロ → Image1 がそのまま出る |

`denoise` を何に変えても結果は変わらない。手順 2〜3 をやり直す。

### 仕組み

貼り付け → マスク付き img2img → マスク外を元に戻す、の 3 段構成。

```
Image1 ─┬ 解像度を取得
        ├ 画風として読み取る → 画風の適用（Redux）
        ├ 「Image2 の位置を決める（仮置き）」の下地
        ├ 「顔をマスクの形で合成」の下地
        └ 「マスク外を Image1 に戻す」の下地
  マスク ─ 少し広げる → 縁をぼかす → 合成 3 つと「マスク内だけ描き直す」へ

Image2 → キャンバスに合わせる → 顔の大きさ（倍率） → 位置を決める（仮置き）
                                                    ├→ 仮置きの確認
                                                    └→ 顔をマスクの形で合成

顔をマスクの形で合成 → latent 化 → マスク内だけ描き直す → サンプラー
サンプラー → latent → 画像 → マスク外を Image1 に戻す → 最終出力
```

1. LoadImage の `MASK` 出力は `1. - alpha`（`nodes.py:1787`）なので、
   MaskEditor で塗った領域が `1` になる。
2. 「顔をマスクの形で合成」がその領域に Image2 を貼る（雑なコラージュ）。
3. 「マスク内だけ描き直す」でマスクの内側だけをノイズ対象にする。
   `SamplerCustomAdvanced` は `denoise_mask` として受け取る
   （`nodes_custom_sampler.py:1055`）。
4. 最後に「マスク外を Image1 に戻す」でマスクの外側を Image1 の画素に戻す。
   **顔以外は 1 ピクセルも変わらない。** ここが「画風を完全に踏襲」の保証。

解像度は「Image1 の解像度を取得」で Image1 から読む。マスクとキャンバスの大きさが
必ず一致するので、マスクをリサイズする経路が要らない。
Image1 が大きすぎると 8GB では OOM になるため、1024×1024 相当までに収める。

**ControlNet は使わない。** 顔の形は貼り付けた画素そのものが担うので、
8GB に 4GB の ControlNet を積む必要がない。

### 調整箇所

| 症状 | 変更するノード | 変更内容 |
|---|---|---|
| 顔が Image2 に似ない | 「denoise ◀ 顔をどれだけ描き直すか」 | `0.65` → `0.45` |
| 写真の質感が残る・浮いて見える | 同上 | `0.65` → `0.80` |
| 顔だけ画風が違う | 「画風の適用（Redux）」 | `strength` `1.0` → `1.2` |
| 継ぎ目の線が見える | 「マスクの縁をぼかす」 | 4 つの値を `24` → `48` |
| 塗った範囲が足りない | 「マスクを少し広げる」 | `expand` `8` → `24` |

### 必要なもの

`Flux1_StyleBlend_TwoImages.json` と同じ。**カスタムノードも ControlNet も不要。**

### 限界

これは**貼り付けた画素の形をなぞる方式**であって、顔認識による face swap ではない。
Image2 の顔立ちは画素の形として伝わるが、描き直す過程でどうしても崩れる。
人物を特定できるレベルで同一性を移したい場合は
PuLID-Flux / InstantID / ReActor などのノードパックが必要になる。

---

## Image1 の画風で Image2 を描き直す版

`Flux1_Repaint_Image2_in_Image1Style.json`

**Image2 をそのまま下地にして、Image1 の画風で描き直す。**
顔も構図も最初から正しい位置にあるので、**マスクも位置合わせも要らない。**

| 入力 | ノード | 決めるもの |
|---|---|---|
| **Image1** | 「Image1 — 画風の参照」 | 画風・色調・タッチ |
| **Image2** | 「Image2 — 顔と構図」 | 顔・構図・全体の内容 |

```
Image1 → Image1 を画風として読み取る → 画風の強さ（Redux）→ サンプラー
Image2 → 縦横比から解像度を自動決定 → latent（出発点） → サンプラー
```

### Face Swap 版との使い分け

| | このワークフロー | `Flux1_FaceSwap_StyleFromImage1.json` |
|---|---|---|
| 出力の構図 | **Image2** | **Image1** |
| Image1 の背景・服 | 残らない | そのまま残る |
| マスク | 不要 | 必要 |
| 位置合わせ | 不要 | 必要 |
| 手間 | 少ない | 多い |

「Image1 の絵柄で Image2 の人物を描きたい」ならこちら。
「Image1 の絵はそのままで顔だけ差し替えたい」なら Face Swap 版。

### 手順

1. 「Image1 — 画風の参照」に、画風の元にしたい絵を読み込む
2. 「Image2 — 顔と構図」に、顔と構図の元にしたい絵を読み込む
3. 実行。以上

**解像度の設定は要らない。**「Image2 の縦横比から解像度を自動決定」が Image2 の
縦横比を見て、`672×1568` 〜 `1568×672` の 17 通り（いずれも約 1MP）から一番近い
ものを選び、そこへ合わせる。ここで決まった解像度は `GetImageSize` 経由で
`ModelSamplingFlux` にも渡るので、shift 補正も自動で追従する。

Image2 の縦横比が候補とぴったり一致しない場合だけ、中央で少し切り取られる。
切れ方は「出発点の確認（切り取り位置）」で確認できる。

### 一番効くつまみ

「denoise ◀ Image1 の画風にどれだけ寄せるか」。この 1 つで結果がほぼ決まる。

| `denoise` | 結果 |
|---|---|
| `0.35` | Image2 のほぼそのまま。色味が少し寄る程度 |
| `0.55` | 既定値。顔立ちを保ちつつ画風が乗る |
| `0.75` | しっかり描き直される。顔立ちは崩れ始める |
| `0.90` | Image2 は構図のあたり程度 |

**顔を残したいなら下げる。画風を強くしたいなら上げる。**
まず `0.55` で 1 枚出してから振る。

### 調整箇所

| 症状 | 変更するノード | 変更内容 |
|---|---|---|
| 写真のままで絵にならない | 「denoise ◀ Image1 の画風にどれだけ寄せるか」 | `0.55` → `0.70` |
| 顔が別人になる | 同上 | `0.55` → `0.40` |
| 画風が乗らない | 「画風の強さ（Redux）」 | `strength` `1.0` → `1.3` |
| 画風が強すぎて崩れる | 同上 | `strength` `1.0` → `0.7` |
| 仕上がりが硬い・AI っぽい | 「FluxGuidance ◀ 絵の磨き具合」 | `2.5` → `1.8` |
| 端が少し切れる | — | Image2 を候補の縦横比に近づけて用意する |

プロンプトは人物ではなく**画材と質感**を書く。顔と構図は Image2 が
担当しているので、人物の描写を書くとそちらに引っ張られて顔が変わる。

### 必要なもの

`Flux1_StyleBlend_TwoImages.json` と同じ。**カスタムノードも ControlNet も不要。**

---

## Klein Face Swap 版

`Flux2Klein_FaceSwap_StyleFromImage1.json`

FLUX.2 Klein 9B + [Best Face Swap LoRA] による頭部差し替えに、
**画風を Image1 に揃える 2 段目**を足したもの。ベースは利用者提供のワークフロー。

| 入力 | ノード | 決めるもの |
|---|---|---|
| **Image1** | 「Image1 — 画風＆背景（Picture 1）」 | 画風・色調・背景・体・表情 |
| **Image2** | 「Image2 — 顔（Picture 2）」 | 顔立ち |

**マスクも位置合わせも不要。** 2 枚を参照ラテントとしてモデルに渡し、
LoRA とプロンプトで頭部を入れ替える方式。

### 2 段構え

| | やること | 出力 |
|---|---|---|
| **1段目** | Best Face Swap LoRA で頭部を差し替える | 「1段目の出力（顔だけ入れ替えた状態）」 |
| **2段目** | Image1 を参照に画風だけを揃える | 「最終出力（画風を揃えたあと）」 |

元のワークフローは頭部の差し替えには成功するが、**Picture 2 の写真的な質感・
化粧・色まで持ち込んでしまう**。2 段目でそれを直す。

2 段目は 1 段目の出力を `VAEEncode` し直し、**Image1 だけを参照ラテントとして**
低い `denoise` で描き直す。画風は構成上必ず揃う。
`Flux2Scheduler` には `denoise` が無いので、`SplitSigmasDenoise` で sigmas の
後ろ側（`low_sigmas`）だけを取り出して部分デノイズにしている。

### 触るのはここだけ

「denoise ◀ 2段目でどれだけ描き直すか」

| `denoise` | 結果 |
|---|---|
| `0.20` | ほぼ 1 段目のまま。色味が少し寄る程度 |
| `0.35` | 既定値。画風が揃い、顔立ちは保たれる |
| `0.50` | しっかり塗り直される。顔立ちが少し動く |
| `0.70` | 別人になり始める |

**画風が揃わないなら上げる。顔が変わるなら下げる。**

### 1 段目のプロンプト

`head_swap:` は **LoRA のトリガーワード**。この 1 語と「Picture 1 / Picture 2」
という呼び方は学習時の文言なので**変えてはいけない**。言い換えると LoRA が効かない。

その形を保ったまま、末尾に画風の指示を足してある。

```
Render the new head in the exact same medium and painting style as Picture 1:
same brush work, same color palette, same paper texture, same level of detail.
Do not copy the photographic lighting, skin texture, make-up or colors of Picture 2.
```

### 2 段目を止めたいとき

「画風統一（2段目）」グループのタイトルバーを右クリック → **Bypass Group Nodes**。
元のワークフローと同じ挙動に戻る。

### 調整箇所

| 症状 | 対処 |
|---|---|
| 画風が揃わない | `denoise` `0.35` → `0.50` |
| 顔が別人になる | `denoise` `0.35` → `0.25` |
| 顔交換自体が起きない | 1 段目のプロンプトが `head_swap:` で始まっているか確認 |
| 2 段目で写真っぽさが戻る | 「2段目のガイダンス」の `model` を「拡散モデルの読み込み」に直結する |

2 段目のモデルは 1 段目と同じ（LoRA 適用済み）を使っている。モデルの入れ替えが
起きないぶん速いが、LoRA が Picture 2 の見た目を呼び戻す場合は直結に変える。

### 必要なもの

| 種類 | ファイル |
|---|---|
| diffusion model | `flux-2-klein-9b-fp8.safetensors` |
| text encoder | `qwen_3_8b_fp8mixed.safetensors` |
| VAE | `flux2-vae.safetensors` |
| LoRA | `bfs_head_v1_flux-klein_9b_step3500_rank128.safetensors` |

2 段目は 1 段目と同じモデルを使い回すので追加のダウンロードは無い。
生成時間はおよそ 1.35 倍（2 段目は `denoise` `0.35` ぶんの step 数）。

---

## 形だけを渡す版

`Flux1_ShapeOnly_FaceFromImage2.json`

**Image2 の画素をモデルに一切渡さない。** グレースケールの形の情報に変換してから
ControlNet に入れるので、モデルが Image2 から受け取れるのは形だけになる。

| 何を | どこから | 割合 |
|---|---|---|
| 画風・色・雰囲気 | 「Image1 — 画風・色・雰囲気」 | 100% |
| 形 | 「Image2 — 形だけを使う」 | 100% |

```
Image1 → 画風の強さ（Redux）─────────────┐
                                          ↓
Image2 ─┬ 前処理 1段目 ─→ 形の適用 1段目
        │                       ↓
        ├ 前処理 2段目 ─→ 形の適用 2段目
        │                       ↓
        └ 2段目・別案 ─→ 形の適用 2段目・別案 → サンプラー
```

3 系統が直列に繋がっていて、**有効にした段だけが効く**。切り替えは Ctrl+B。

| 使いたい構成 | 有効にする段 |
|---|---|
| 立体だけ | 1段目 |
| 立体 ＋ 線（種類を選ぶ）※既定 | 1段目 ＋ 2段目 |
| 立体 ＋ 線（数値で詰める） | 1段目 ＋ 2段目・別案 |
| 線を 2 系統重ねる | 全部 |

出荷時は「形の適用 2段目・別案（Ctrl+B で無効）」だけが無効になっている。

### なぜプロンプトでは駄目だったのか

参照ラテント（`ReferenceLatent`）や Redux は、**フルカラーの画素をそのまま**
モデルに渡す。色も筆致も写真的な質感もモデルには「見えて」いる。
見えているものを言葉で無かったことにはできない。

`no face paint`, `do not copy the colors of Picture 2` といった否定形を
いくら重ねても、参照画像の見た目は残り続ける。**経路ごと断つしかない。**

深度マップや線画はグレースケールの形の情報だけで、色も筆致も含まない。
Image2 の画風が混ざらないことが**構造的に保証される**。

### 前処理の種類は手で選ぶ

前処理は `AIO_Preprocessor`（画面では **AIO Aux Preprocessor** と表示されます）に
してあるので、1 段目・2 段目それぞれで種類をプルダウンから選べる。
2 段を別々の種類にできる。

| 選ぶもの | 渡る情報 | 得意なこと |
|---|---|---|
| `DepthAnythingV2Preprocessor` | 深度マップ | 鼻の高さ・頬骨・顎の張り。**立体** |
| `LineArtPreprocessor` | 線画 | 目・鼻・口の位置と形。**造作** |
| `AnimeLineArtPreprocessor` | アニメ線画 | イラスト原稿向き。線が太い |
| `CannyEdgePreprocessor` | 輪郭線 | 硬い。写真から輪郭だけ欲しいとき |
| `HEDPreprocessor` | 柔らかい線 | 筆致に近い。絵画向き |
| `DWPreprocessor` | 骨格 | 全身の姿勢。顔には効かない |
| `none` | 元画像そのまま | **画風が混ざるので使わない** |

選んだ種類に合わせて「Union の制御タイプ（1段目）」「Union の制御タイプ（2段目）」も
変える。深度なら `depth`、線なら `canny/lineart/anime_lineart/mlsd`、
骨格なら `openpose`。

| 目的 | 1段目 | 2段目 |
|---|---|---|
| 顔を似せる（既定） | `DepthAnythingV2Preprocessor` | `LineArtPreprocessor` |
| 絵画に寄せる | `DepthAnythingV2Preprocessor` | `HEDPreprocessor` |
| 線画原稿から起こす | `AnimeLineArtPreprocessor` | 2段目は Ctrl+B で無効 |
| 立体だけ欲しい | `DepthAnythingV2Preprocessor` | 2段目は Ctrl+B で無効 |

前処理ごとの細かい数値（Canny のしきい値など）は触れない。`AIO_Preprocessor` は
`image` と `resolution` 以外を既定値で呼ぶため（`__init__.py:97-126`）。

### 数値で詰めたいとき — 2段目・別案

そのために「Image2 の前処理 2段目・別案（Standard Lineart）◀ 数値で調整」を別系統で用意してある。
`LineartStandardPreprocessor`（画面では **Standard Lineart**）の専用ノードなので、
種類は固定される代わりに数値が触れる。

| 数値 | 既定 | 効果 |
|---|---|---|
| `intensity_threshold` | `8` | 下げる（→ `3`）と薄い線まで拾う。上げる（→ `14`）と濃い線だけ |
| `guassian_sigma` | `6.0` | 上げる（→ `12`）とノイズが消えて線が太くまとまる |
| `resolution` | `1024` | 下げると細かいざらつきが消える |

`guassian_sigma` は綴りが誤っているが、これがソース上の正式な名前
（`node_wrappers/lineart_standard.py:9`）。

lineart 系のうち数値を持つのはこれと `AnyLinePreprocessor` だけ。
`LineArtPreprocessor`（Realistic Lineart）と `AnimeLineArtPreprocessor` は
学習済みモデルが線を描くので、しきい値という概念がそもそも無い。

### 手順

1. 「Image1 — 画風・色・雰囲気」に画風の元を読み込む
2. 「Image2 — 形だけを使う」に形の元を読み込む
3. 前処理の種類と制御タイプを選ぶ（既定のままでも動く）
4. 実行

解像度の設定は不要。Image2 の縦横比から自動で決まる。

### 必ず確認すること

- 「1段目に渡る情報」→ 選んだ前処理の結果
- 「2段目に渡る情報」→ 同上
- 「2段目・別案に渡る情報」→ 同上

これらがモデルに渡る Image2 の情報の全て。**灰色か白黒であれば正常。**
色が付いていたら前処理が `none` になっているか、効いていない。

3 つのプレビューはサンプラーを回さなくても更新される。**線の出方はここで
見比べてから決める。**

### 形は 2 段で渡す

深度だけだとのっぺりして似ない。線だけだと立体が出ない。
**2 つ重ねると顔の似方がはっきり上がる。**

「形の適用 1段目」と「形の適用 2段目（Ctrl+B で無効）」
（画面のノード検索では **Apply ControlNet** と表示されます）は直列に繋ぐと
連結される。1 段目の出力を 2 段目の入力に渡すと、`nodes.py:966-971` で
`previous_controlnet` として連結され、両方の制御が同時にかかる。

```python
prev_cnet = d.get('control', None)
...
c_net = control_net.copy().set_cond_hint(control_hint, strength, (start_percent, end_percent), vae=vae)
c_net.set_previous_controlnet(prev_cnet)
```

**ControlNet モデルの読み込みは 1 つで済む。** Apply 側が内部で `copy()` して
重みを共有するため（`nodes.py:970`）、2 段にしても VRAM は 1 個分しか使わない。

### 調整の順番

1. **まず 1 段目だけで出す。**
   「形の適用 2段目（Ctrl+B で無効）」を選んで **Ctrl+B**
2. **似方が足りなければ 2 段目を有効にする。** Ctrl+B をもう一度
3. **線の出方に不満があれば別案に切り替える。**
   「形の適用 2段目（Ctrl+B で無効）」を Ctrl+B して、
   「形の適用 2段目・別案（Ctrl+B で無効）」の Ctrl+B を解除

| 症状 | 変更するノード | 変更内容 |
|---|---|---|
| 顔が似ない | 「形の適用 2段目（Ctrl+B で無効）」 | `strength` `0.45` → `0.70` |
| 線が絵に残る | 同上 | `end_percent` `0.60` → `0.40` |
| 線が拾えていない・多すぎる | 「Image2 の前処理 2段目（AIO Aux Preprocessor）◀ 種類を選ぶ」 | 種類を変える。`LineArtPreprocessor` ⇄ `HEDPreprocessor` |
| 線を数値で詰めたい | 「Image2 の前処理 2段目・別案（Standard Lineart）◀ 数値で調整」 | 上の表を参照。別案の段を有効にする |
| 立体が出ない | 「形の適用 1段目」 | `strength` `0.85` → `1.00` |
| 形が強すぎて画風が乗らない | 1段目・2段目の `strength` を両方下げる | — |
| 画風が乗らない | 「画風の強さ（Redux）」 | `strength` `1.0` → `1.3` |
| 仕上がりが硬い | 「FluxGuidance ◀ 絵の磨き具合」 | `2.5` → `1.8` |
| 前処理が粗い | 前処理ノードの `resolution` | `1024` → `1536` |

**2 段目の `end_percent` を `0.60` と低めにしてあるのが要点。** 線は序盤で
顔の造作を決めるのに使い、後半は画風に任せる。`1.0` にすると線がそのまま絵に残る。

プロンプトには**画材だけ**を書く。人物の描写を書くと、そちらに引っ張られて
ControlNet の形と喧嘩する。

### この方式の位置づけ

**Image2 の画風が混ざらないことは構造的に保証される。**
顔の似方は 2 段構成でかなり上がるが、Best Face Swap LoRA ほどではない。

- 似顔絵としての精度を最優先 → `Flux2Klein_FaceSwap_StyleFromImage1.json`
- 画風の純度を優先 → こちら

### 必要なもの

`Flux1_StyleRef_x_ControlNet.json` と同じ。加えて前処理に
[`comfyui_controlnet_aux`](https://github.com/Fannovel16/comfyui_controlnet_aux)
が要る（Krea2 版で既に使っているものと同じ）。前処理は 3 系統ともここから
来ているので、これが無いと動かない。

### Union の制御タイプについて

「Union の制御タイプ（1段目）」「Union の制御タイプ（2段目）」は画像を変えない。
番号を 1 個添えるだけ（`comfy_extras/nodes_controlnet.py:24-33`）。

**Union Pro 2.0 では受け取る部品（`controlnet_mode_embedder`）が無いので、
何を選んでも結果は同じ。** 1.0 に戻したときだけ意味を持つ。`auto` は自動判別では
なく、**番号を添えない**という意味。
