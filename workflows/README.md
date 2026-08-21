# Krea2 StyleReference × 構図制御 ワークフロー

元の StyleReference ワークフロー（構図をプロンプトのみで決める text-to-image）を拡張し、
**スタイルと構図を別々の画像で指定**できるようにしたもの。

| ファイル | 内容 |
|---|---|
| `Flux1_StyleRef_x_ControlNet.json` | **推奨。** FLUX.1-dev 版。Redux(画風) × ControlNet Union(構図)。8GB VRAM 向け |
| `Flux1_StyleBlend_TwoImages.json` | FLUX.1-dev 版。**2枚の画風を融合**させる（構図制御なし）。8GB VRAM 向け |
| `Flux1_FaceSwap_StyleFromImage1.json` | FLUX.1-dev 版。**Image1 の画風のまま顔だけ Image2 に差し替える**。8GB VRAM 向け |
| `Flux2_StyleRef_x_ControlNet.json` | FLUX.2-dev 版。同じ構成だが **VRAM 16GB 以上が必要** |
| `Krea2_StyleRef_x_Structure.json` | Krea2 版。depth ControlNet と img2img を切り替えられる統合版 |
| `Krea2_StyleRef_x_DepthControlNet.json` | Krea2 版。depth ControlNet のみの初版 |
| `Krea2_StyleRef_x_LineArtReference.json` | Krea2 版。線画を `image2` の参照画像として渡す試作 |

FLUX 版については [FLUX.1 版](#flux1-版) / [FLUX.2 版](#flux2-版) /
[2枚の画風を融合する版](#2枚の画風を融合する版) /
[Face Swap 版](#face-swap-版) を参照。以下は Krea2 版の説明。

| 入力 | ノード | 決めるもの |
|---|---|---|
| **Image1** | `LoadImage` #25 | 画風・色調・タッチ |
| **Image2** | `LoadImage` #46 | 形・構図・レイアウト |

## 統合版の構成

```
Image1 ─ FluxKontextImageScale #28 ─ TextEncodeKrea2OstrisEdit #34/#35 (image1)
                                     └ krea2_style_reference LoRA #32 がスタイルとして解釈

Image2 ─ FluxKontextImageScale #47 ─ VAEEncode #54 ─┬─ KSampler #7 (latent_image)
                                    │               └─ Krea2ControlImageEncode #49 (サイズ合わせ)
                                    └ DepthAnythingV2Preprocessor #48 ─ #49 ─ Krea2ControlApply #51

LoaderGGUF #44 ─ Krea2OstrisEditModelPatch #33 ─ LoraLoaderModelOnly #32 (style)
               ─ Krea2ControlLoRALoader #50 ─ Krea2ControlApply #51 ─ KSampler #7 (model)
```

出力解像度は `FluxKontextImageScale` #47 が決めるため、**Image2 のアスペクト比**に追従する。

## モード切替

`MODE A - depth ControlNet` グループのタイトルバーを右クリック →
**Bypass Group Nodes** で一括バイパスできる。

| | ControlNet グループ | `denoise` (#7) | 用途 |
|---|---|---|---|
| **Mode A** | 有効 | `1.00` | Image2 が写真・3DCG |
| **Mode B** | バイパス | `0.60`〜`0.75` | Image2 が線画・ラフ |
| **Mode C** | 有効 | `0.80`〜`0.90` | 構図を固定しつつ元画像の色味も引き継ぐ |

Mode A で `denoise` が `1.00` のとき、`VAEEncode` #54 の内容は完全にノイズで打ち消される。
flow-matching の `noise_scaling` は `sigma * noise + (1 - sigma) * latent` で、`denoise=1.0`
では `sigma=1.0` となり latent 項の係数が 0 になるため、`EmptyLatentImage` を使った場合と
数学的に等価になる。ゆえに latent 供給元を VAEEncode に一本化しても Mode A の挙動は変わらない。

### Mode B の denoise 目安

- `0.50` — 線画の形をほぼ保持。ただし白背景も残りやすい
- `0.65` — 標準。形は保ちつつ塗りと質感が入る
- `0.80` — 大きく描き変わる。線画は構図のあたり程度

## 必要なもの

カスタムノード:

- [ostris/ComfyUI-Krea2-Ostris-Edit](https://github.com/ostris/ComfyUI-Krea2-Ostris-Edit)
- [facok/comfyui-krea2-controlnet](https://github.com/facok/comfyui-krea2-controlnet) — Mode A のみ
- [Fannovel16/comfyui_controlnet_aux](https://github.com/Fannovel16/comfyui_controlnet_aux) — 深度推定 #48 用。
  深度マップを自前で用意するなら不要（#48 を Ctrl+B でバイパス）

モデル:

```
models/loras/Krea2/
├── krea2_style_reference.safetensors   # ostris/krea2_turbo_style_reference
└── depth-control-lora.safetensors      # Patil/Krea-2-depth-controlnet (862MB, Mode A のみ)
```

Mode B だけを使う場合、ControlNet 側のノードパックと LoRA はどちらも不要。

## Control LoRA の対応状況

| 制御タイプ | 公開重み |
|---|---|
| depth | [Patil/Krea-2-depth-controlnet](https://huggingface.co/Patil/Krea-2-depth-controlnet) |
| pose | [thedeoxen/Krea-2-pose-controlnet](https://huggingface.co/thedeoxen/Krea-2-pose-controlnet) |
| canny / lineart / tile / normal | 未公開（[学習コード](https://github.com/Tanmaypatil123/Krea-2-controlnet)のみ） |

`comfyui-krea2-controlnet` が canny や lineart の前処理出力を受け取れるのは
`Krea2ControlImageEncode` の入力仕様の話であって、対応する Control LoRA が存在するという
意味ではない。depth LoRA に canny 画像を流しても制御は効かない（期待する入力分布が違う）。
線画を構図ソースにする場合は Mode B を使う。

pose に差し替える場合:

1. #50 の LoRA を pose 用に変更
2. #48 を `DWPreprocessor` / `OpenposePreprocessor` に差し替え
3. #49 の `channel_mode` を `rgb`、`normalize` を `none` に変更
   （骨格図は色が意味を持つため。深度マップはグレースケール＋正規化）

## 調整の勘所

- 構図が効きすぎてスタイルが乗らない → #50 の `strength` を 0.6〜0.8 に下げる
- 構図が守られない → #50 の `strength` を上げる、または #32（スタイル LoRA）を下げる
- ControlNet 併用時は #7 の `steps` を 8 → 10 前後にすると安定しやすい
- `cfg` は 1.0（turbo 系）のため、ネガティブプロンプト #35 は実質無効

---

## FLUX.2 版

`Flux2_StyleRef_x_ControlNet.json`

Krea2 では Style Reference と ControlNet を同時に成立させられなかった
（公開 Control LoRA が depth / pose のみで、線画を構図として渡す手段が無い）。
FLUX.2 は両方を素直に併用できる。

| 入力 | ノード | 決めるもの | 経路 |
|---|---|---|---|
| **Image1** | `LoadImage` #93 | 画風・色調・タッチ | `ReferenceLatent` #96 |
| **Image2** | `LoadImage` #70 | 形・構図 | `Flux2FunControlNetApply` #91 |

```
CLIPTextEncode #6 ─ FluxGuidance #26 ─ ReferenceLatent #96 ─ Flux2FunControlNetApply #91 ─ BasicGuider #22
                                          │                       │
Image1 ─ ImageScaleToTotalPixels #94 ─ VAEEncode #95            Image2 ─ ImageScale #81
```

`Flux2FunControlNetApply` は conditioning の dict を複製して `control` を足すだけなので、
`ReferenceLatent` が入れた `reference_latents` はそのまま残る。
ControlNet 側の patch も参照ラテントを認識し、control hint を本画像トークンにのみ適用する。
よって両者は競合しない。

### 必要なもの

| 種類 | ファイル | 置き場所 |
|---|---|---|
| diffusion model | `flux2-dev`（bf16 / fp8 / gguf q4_k_m） | `models/diffusion_models/` |
| text encoder | `mistral_3_small_flux2_*.safetensors` | `models/text_encoders/` |
| VAE | `flux2-vae.safetensors` | `models/vae/` |
| ControlNet | `FLUX.2-dev-Fun-Controlnet-Union.safetensors`（約 8.3GB） | `models/controlnet/` |

カスタムノードは [`bryanmcguire/comfyui-flux2fun-controlnet`](https://github.com/bryanmcguire/comfyui-flux2fun-controlnet) の 1 つだけ。
ControlNet 本体は [`alibaba-pai/FLUX.2-dev-Fun-Controlnet-Union`](https://huggingface.co/alibaba-pai/FLUX.2-dev-Fun-Controlnet-Union)。

### ControlNet Union の対応種別

pose / canny / depth / HED / MLSD / tile を**自動判別**する。
種別の切り替えノードは無く、**線画はそのまま `control_image` に入れてよい**（前処理ノード不要）。

### 調整箇所

| 症状 | 変更 |
|---|---|
| 構図が Image2 に従わない | #91 `strength` 0.75 → 0.90 |
| 線画の線がそのまま出力に残る | #91 `strength` 0.75 → 0.60 |
| 画風が乗らない | プロンプトの style 記述を具体化する / Image1 を差し替える |

解像度は `PrimitiveNode` #50 (width) / #51 (height) の 2 箇所だけ変えれば、
latent・scheduler・Image2 リサイズの 3 つに伝わる。

推奨値: steps 25〜50 (#48)、`FluxGuidance` 3.5〜4.5 (#26)、sampler `euler`。

### VRAM 要件（重要）

**8GB では動作しない。** `Flux2FunControlNetLoader` は

```python
controlnet.to(device=device, dtype=dtype)
```

でチェックポイント全体を VRAM に常駐させる。ComfyUI のモデルマネージャの管理外なので
オフロードされない。8.3GB のこのモデルでは 8GB カードがそれだけで埋まり、
後続の `VAEEncode` が 128MB すら確保できずに OOM になる。

また Fun ControlNet Union は **flux2-dev 専用**で、Klein 4B / 9B では使えない
（[HF discussion](https://huggingface.co/alibaba-pai/FLUX.2-dev-Fun-Controlnet-Union/discussions/3)）。
テキストエンコーダも T5 ではなく Mistral 3 Small が必要。

8GB 環境では `Flux1_StyleRef_x_ControlNet.json` を使うこと。

---

## FLUX.1 版

`Flux1_StyleRef_x_ControlNet.json`

FLUX.2 版と同じ役割分担を、8GB VRAM で動く構成にしたもの。
ベースは ComfyUI 公式テンプレート `flux_redux_model_example.json`。

| 入力 | ノード | 決めるもの | 経路 |
|---|---|---|---|
| **Image1** | `LoadImage` #40 | 画風・色調・タッチ | `CLIPVisionEncode` #39 → `StyleModelApply` #41 (Redux) |
| **Image2** | `LoadImage` #55 | 形・構図 | `ImageScale` #56 → `ControlNetApplyAdvanced` #54 |

```
CLIPTextEncode #6 ─ FluxGuidance #26 ─ StyleModelApply #41 ─ ControlNetApplyAdvanced #54 ─ BasicGuider #22
                                            │                        │
Image1 ─ CLIPVisionEncode #39 ───────────────┘   Image2 ─ ImageScale #56 ─ Canny #59 ─┬─ #54
                                                                                     └─ PreviewImage #58
```

### 前処理 #59 とプレビュー #58

**`SetUnionControlNetType` #53 は画像を加工しない。** どの mode embedding を
使うかを ControlNet に伝えるだけなので、`canny` や `lineart` を選んでも
写真は写真のまま `#54` に渡る。線を取り出すには前処理ノードが必要で、
そのために ComfyUI 標準の `Canny` #59 を `#56` と `#54` の間に入れてある。

`PreviewImage` #58 には `#59` の出力＝`#54` に渡るのと**同じ IMAGE** が出る。

| Image2 の中身 | #59 の扱い |
|---|---|
| 写真・イラスト | そのまま有効。線が抽出される |
| 最初から線画 | #59 を選んで **Ctrl+B** でバイパス（素通し） |

| 症状 | 変更 |
|---|---|
| 線が少なすぎる | #59 `low_threshold` 0.2 → 0.1 |
| 線が多すぎる・ノイズだらけ | #59 `high_threshold` 0.5 → 0.8 |

`depth` / `openpose` に相当する前処理ノードは ComfyUI 標準には無い。
[`comfyui_controlnet_aux`](https://github.com/Fannovel16/comfyui_controlnet_aux)
を入れて #59 を差し替える。

`#54` の `negative` には空の `CLIPTextEncode` #51 を繋いである。
`BasicGuider` は positive しか使わないため negative 出力は捨てている。

`VAELoader` #10 は `#54` の `vae` にも繋いである。Union Pro 2.0 は latent 空間で
hint を作るため VAE が必須で、未接続だとサンプリング開始時に
`This Controlnet needs a VAE but none was provided` で落ちる
（`comfy/controlnet.py:278`）。

### 制御タイプの手動指定（#53）

`SetUnionControlNetType` #53 のドロップダウンで、Image2 をどう解釈させるかを
明示できる。選べる文字列は ComfyUI 本体の `comfy/cldm/control_types.py` に
定義された 8 種類と `auto` のみ。

| 入れる画像 | #53 で選ぶ値 |
|---|---|
| 線画 / canny / MLSD | `canny/lineart/anime_lineart/mlsd` ← 既定値 |
| ラフ線 / scribble / HED / PiDi | `hed/pidi/scribble/ted` |
| 深度マップ | `depth` |
| ポーズ（棒人間） | `openpose` |
| 法線マップ | `normal` |
| セグメンテーション | `segment` |
| タイル（拡大用） | `tile` |
| 部分描き直し | `repaint` |

**ただし Union Pro 2.0 では効かない。** 2.0 は mode embedding
(`controlnet_mode_embedder`) を持たないため、`ControlNetFlux.forward_orig` の

```python
if self.controlnet_mode_embedder is not None and len(control_type) > 0:
```

の分岐に入らず、指定した型は黙って捨てられる（エラーにはならない）。
型指定を実際に効かせたい場合は #52 で **Union Pro 1.0** を読み込む。
2.0 のままなら `auto` でも手動指定でも出力は同じ。

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

### 調整箇所

| 症状 | 変更 |
|---|---|
| 構図が Image2 に従わない | #54 `strength` 0.75 → 0.90、`end_percent` 0.85 → 1.00 |
| 線画の線が出力に残る | #54 `end_percent` 0.85 → 0.60 |
| 画風が乗らない | #41 `strength` 0.6 → 0.9 |
| 画風が強すぎてプロンプトが効かない | #41 `strength` 0.6 → 0.3 |

実際に良い結果が出た組み合わせは #41 `0.9` / #54 `0.90` / `end_percent` `0.85`。
既定値は初期値のままにしてあるので、必要なら手動で上げる。

解像度は `PrimitiveNode` #34 (width) / #35 (height) の 2 箇所だけ変えれば、
latent・`ModelSamplingFlux`・Image2 リサイズの 3 つに伝わる。

### 既知の衝突: comfyui-flux2fun-controlnet

FLUX.2 用の [`comfyui-flux2fun-controlnet`](https://github.com/bryanmcguire/comfyui-flux2fun-controlnet)
を入れていると、この FLUX.1 版がサンプリング開始直後に落ちる。

```
TypeError: patched_forward_orig() got an unexpected keyword argument 'timestep_zero_index'
```

原因は `flux_patch.apply_patch()` が **import 時に無条件で**
`comfy.ldm.flux.model.Flux.forward_orig` を差し替えていること（`nodes.py:26`）。
このノードパックを使っていない FLUX.1 ワークフローにも patch が効いてしまう。
そして `patched_forward_orig` の引数に `timestep_zero_index` が無いため、
ComfyUI 0.26.0 の `comfy/ldm/flux/model.py:406` からの呼び出しと合わない。

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
8GB なら 832×1216 程度が上限。足りなければ #12 を `Unet Loader (GGUF)` に置き換えて
Q4_K_M を使う。

## 2枚の画風を融合する版

`Flux1_StyleBlend_TwoImages.json`

構図制御は使わず、**読み込んだ 2 枚を混ぜて**出力する。
ベースは ComfyUI 公式テンプレート `flux_redux_model_example.json`
（このテンプレートは元から Redux 経路を 2 本持っている）。

混ぜる系統が 2 つあり、役割が違う。

| 何を混ぜるか | どこで | 実体 |
|---|---|---|
| **顔・構図** | `ImageBlend` #54 の `blend_factor` | ピクセルを実際に重ねる |
| **画風・色** | `StyleModelApply` #41 / #45 の `strength` | Redux トークン |

```
顔:   Image1 → ImageScale #52 ┐
                              ├ ImageBlend #54 → VAEEncode #55 → SamplerCustomAdvanced #13
      Image2 → ImageScale #53 ┘                → PreviewImage #56

画風: Image1 → CLIPVisionEncode #39 → StyleModelApply #41 ┐
      Image2 → CLIPVisionEncode #46 → StyleModelApply #45 ┴→ BasicGuider #22
```

### Redux だけでは顔は保てない

`StyleModelApply` を 2 段直列にすると両方の Redux トークンが並ぶので画風は混ざるが、
**顔の同一性は再現されない**。SigLIP が画像を 384×384 のトークン列に潰す時点で
個人を特定する情報が落ちるうえ、空 latent から始める txt2img では画素側の手がかりが
一切ない。結果、出力の顔は毎回ゼロから生成される。

そこで 2 枚を実際に重ねた画像を `VAEEncode` して latent の出発点に据え、
`BasicScheduler` #17 の `denoise` でどれだけ残すかを決める構成にしてある。

| `denoise` (#17) | 結果 |
|---|---|
| `0.40` | 元の 2 枚の面影が強く残る。重ねた跡も残りやすい |
| `0.60` | 既定値。顔立ちを引き継ぎつつ絵として整う |
| `0.80` | かなり描き変わる。構図だけ引き継ぐ |
| `1.00` | アンカーが消えて完全な txt2img。顔は別人になる |

`denoise` が `1.00` のとき `VAEEncode` の内容が消えるのは、flow-matching の
`noise_scaling` が `sigma * noise + (1 - sigma) * latent` で、`denoise=1.0` では
`sigma=1.0` となり latent 項の係数が 0 になるため。`EmptySD3LatentImage` は
不要になったので削除してある。

**「顔が全然違う人になる」ときは、まず `denoise` を下げる。**

`ImageBlend` #54 の `blend_factor` は `0.0` で A のみ、`1.0` で B のみ、`0.5` で等分。
重ねた結果は `PreviewImage` #56 に出るので、見ながら決められる。

### なぜ比が strength で決まるのか

`strength_type` が `multiply` のとき、`nodes.py:1134` が

```python
cond *= strength
```

と Redux トークンそのものを定数倍しているため、2 段直列にすれば比がそのまま効く。
`attn_bias` は `log(strength)` を attention バイアスに足す別系統で、
`strength` が 1.0 だと何も起きない。混合比の調整には `multiply` を使う。

### 画風の混合比の目安

| したいこと | #41 (A) | #45 (B) |
|---|---|---|
| 等分に混ぜる（既定値） | 0.6 | 0.6 |
| A を主、B を隠し味 | 0.8 | 0.3 |
| B を主、A を隠し味 | 0.3 | 0.8 |
| 両方もっと強く | 0.9 | 0.9 |
| プロンプトを効かせたい | 0.4 | 0.4 |

| 症状 | 対処 |
|---|---|
| **顔が全然違う人になる** | **#17 `denoise` を 0.45 前後まで下げる** |
| 片方の絵がそのまま出てしまう | その側の `strength` を 0.3 前後まで下げる |
| どちらの画風も乗らない | 両方 0.9 に上げる |
| プロンプトが完全に無視される | 両方 0.4 に下げる |
| 混ざらず継ぎ接ぎに見える | 2 枚の明度・彩度を近づけてから読み込む |

片方だけの効果を確認したいときは、その `StyleModelApply` を選んで
**Ctrl+B** でバイパスすると素通しになる。

### 解像度は参照画像に合わせる

`PrimitiveNode` #34 / #35 は `832 × 1216`。テンプレート既定の `1024 × 1024` のままだと
縦長の参照画像が正方形に詰め込まれ、構図ごと作り直されて顔も変わる。
参照画像のアスペクト比に合わせるほうが結果が安定する。

プロンプト #6 も参照画像と主題を揃えておく。無関係な文章が入っていると
その分だけ絵が作り直される。

### crop を none にしてある

`CLIPVisionEncode` #39 / #46 の `crop` は、テンプレート既定の `center` ではなく
**`none`** にしてある。`center` は中央を正方形に切り取るため画面端の色が
トークンに入らない。色彩を混ぜる用途では `none` のほうが元画像の色を拾う。

### 必要なもの

`Flux1_StyleRef_x_ControlNet.json` と同じ。ただし **ControlNet は不要**。

| 種類 | ファイル | 置き場所 |
|---|---|---|
| diffusion model | `flux1-dev-fp8.safetensors` | `models/diffusion_models/` |
| text encoder | `t5xxl_fp8_e4m3fn_scaled.safetensors` + `clip_l.safetensors` | `models/text_encoders/` |
| VAE | `ae.safetensors` | `models/vae/` |
| style model | `flux1-redux-dev.safetensors` | `models/style_models/` |
| clip vision | `sigclip_vision_patch14_384.safetensors` | `models/clip_vision/` |

**カスタムノードは不要。** すべて ComfyUI 標準ノード。

顔の同一性そのものを保証したい場合、標準ノードの範囲ではここが限界になる。
PuLID-Flux や InstantID のように顔埋め込みを別経路で注入するノードパックが必要。

---

## Face Swap 版

`Flux1_FaceSwap_StyleFromImage1.json`

**Image1 の画風・色彩・雰囲気をそのまま残し、顔だけ Image2 の形に差し替える。**

| 入力 | ノード | 役割 |
|---|---|---|
| **Image1** | `LoadImage` #40 | 画風の元。かつキャンバス本体。顔をマスクで塗る |
| **Image2** | `LoadImage` #47 | 顔の形 |

### 手順

1. **Image1 #40** に画風の元になる絵を読み込む
2. #40 を右クリック → **Open in MaskEditor** で、差し替えたい**顔の範囲を塗る**
3. **Image2 #47** に顔の形の元になる絵を読み込む
4. 実行。`PreviewImage` #59 に貼り付け結果、`SaveImage` #9 に最終出力

### 仕組み

貼り付け → マスク付き img2img → マスク外を元に戻す、の 3 段構成。

```
Image1 ─┬ GetImageSize #52 → 解像度
        ├ CLIPVisionEncode #39 → StyleModelApply #41   (画風)
        ├ ImageCompositeMasked #54 の destination
        └ ImageCompositeMasked #60 の destination       (最後に戻す)
  MASK ── GrowMask #57 → FeatherMask #58 → #54 / #56 / #60

Image2 ── ImageScale #53 → #54 の source                (顔の形)

#54 → VAEEncode #55 → SetLatentNoiseMask #56 → SamplerCustomAdvanced #13
#13 → VAEDecode #8 → #60 の source → SaveImage #9
```

1. `LoadImage` の `MASK` 出力は `1. - alpha`（`nodes.py:1787`）なので、
   MaskEditor で塗った領域が `1` になる。
2. `ImageCompositeMasked` #54 がその領域に Image2 を貼る（雑なコラージュ）。
3. `SetLatentNoiseMask` #56 でマスク内だけをノイズ対象にする。
   `SamplerCustomAdvanced` は `denoise_mask=noise_mask` として受け取る
   （`nodes_custom_sampler.py:1055`）。`denoise` を下げれば貼った顔の形が残り、
   Redux #41 が Image1 の画風で塗り直す。
4. `VAEDecode` のあと `ImageCompositeMasked` #60 でマスク外を Image1 の画素に戻す。
   **顔以外は 1 ピクセルも変わらない。** ここが「画風を完全に踏襲」の保証。

解像度は `GetImageSize` #52 で Image1 から取る。マスクとキャンバスのサイズが
必ず一致するので、マスクをリサイズする経路が要らない。
Image1 が大きすぎると 8GB では OOM になるため、1024×1024 相当までに収める。

**ControlNet は使わない。** 顔の形は貼り付けた画素そのものが担うので、
8GB に 4GB の ControlNet を積む必要がない。

### 位置合わせ

`ImageCompositeMasked` #54 の `x` / `y` で Image2 をずらせる。
まず #59 のプレビューを見て、Image2 の顔がマスクの位置に来るよう調整する。
Image1 と Image2 で顔の大きさ・向きが大きく違うと破綻するので、
**似た構図の 2 枚**を使うのが前提。

### 調整箇所

| 症状 | 変更 |
|---|---|
| 顔が Image2 に似ない | #17 `denoise` 0.55 → 0.40 |
| 貼り付けた跡が残る・浮いて見える | #17 `denoise` 0.55 → 0.70 |
| 継ぎ目の線が見える | #58 のぼかし 24 → 48 |
| 顔だけ画風が違う | #41 `strength` 0.8 → 1.0 |
| 塗った範囲が足りない | #57 `expand` 8 → 24 |

### 必要なもの

`Flux1_StyleBlend_TwoImages.json` と同じ。**カスタムノードも ControlNet も不要。**

### 限界

これは**構造ベースの差し替え**であって、顔認識による face swap ではない。
Image2 の顔立ちは貼り付けた画素の形として伝わるが、`denoise` で塗り直す過程で
どうしても崩れる。人物を特定できるレベルで同一性を移したい場合は
PuLID-Flux / InstantID / ReActor などのノードパックが必要になる。
