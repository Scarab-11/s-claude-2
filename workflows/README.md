# Krea2 StyleReference × 構図制御 ワークフロー

元の StyleReference ワークフロー（構図をプロンプトのみで決める text-to-image）を拡張し、
**スタイルと構図を別々の画像で指定**できるようにしたもの。

| ファイル | 内容 |
|---|---|
| `Krea2_StyleRef_x_Structure.json` | **推奨。** depth ControlNet と img2img を切り替えられる統合版 |
| `Krea2_StyleRef_x_DepthControlNet.json` | depth ControlNet のみの初版 |

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
