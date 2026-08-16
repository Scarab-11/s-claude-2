# Krea2 StyleReference × ControlNet ワークフロー

`Krea2_StyleRef_x_DepthControlNet.json`

元の StyleReference ワークフロー（構図をプロンプトのみで決める text-to-image）に
Krea2 用 ControlNet を追加し、**スタイルと構図を別々の画像で指定**できるようにしたもの。

| 入力 | ノード | 決めるもの |
|---|---|---|
| **Image1** | `LoadImage` #25 | 画風・色調・タッチ |
| **Image2** | `LoadImage` #46 | 形・構図・レイアウト |

## 経路

```
Image1 ─ FluxKontextImageScale #28 ─ TextEncodeKrea2OstrisEdit #34/#35 (image1)
                                     └ krea2_style_reference LoRA #32 がスタイルとして解釈

Image2 ─ FluxKontextImageScale #47 ┬ DepthAnythingV2Preprocessor #48
                                   │   └ Krea2ControlImageEncode #49 ─ Krea2ControlApply #51
                                   └ GetImageSize #36 ─ EmptyLatentImage #6 （出力解像度）

LoaderGGUF #44 ─ Krea2OstrisEditModelPatch #33 ─ LoraLoaderModelOnly #32 (style)
               ─ Krea2ControlLoRALoader #50 (depth) ─ Krea2ControlApply #51 ─ KSampler #7
```

出力解像度は構図を決める **Image2** に追従する（元は Image1 に追従していた）。

## 必要なもの

カスタムノード:

- [ostris/ComfyUI-Krea2-Ostris-Edit](https://github.com/ostris/ComfyUI-Krea2-Ostris-Edit)
- [facok/comfyui-krea2-controlnet](https://github.com/facok/comfyui-krea2-controlnet)
- [Fannovel16/comfyui_controlnet_aux](https://github.com/Fannovel16/comfyui_controlnet_aux) — 深度推定 #48 用。
  深度マップを自前で用意するなら不要（#48 を Ctrl+B でバイパス）

モデル:

```
models/loras/Krea2/
├── krea2_style_reference.safetensors   # ostris/krea2_turbo_style_reference
└── depth-control-lora.safetensors      # Patil/Krea-2-depth-controlnet (862MB)
```

## pose に差し替える

1. #50 の LoRA を [thedeoxen/Krea-2-pose-controlnet](https://huggingface.co/thedeoxen/Krea-2-pose-controlnet) に変更
2. #48 を `DWPreprocessor` / `OpenposePreprocessor` に差し替え
3. #49 の `channel_mode` を `rgb`、`normalize` を `none` に変更
   （骨格図は色が意味を持つため。深度マップはグレースケール＋正規化）

## 調整の勘所

- 構図が効きすぎてスタイルが乗らない → #50 の `strength` を 0.6〜0.8 に下げる
- 構図が守られない → #50 の `strength` を上げる、または #32（スタイル LoRA）を下げる
- ControlNet 併用時は #7 の `steps` を 8 → 10 前後にすると安定しやすい
- `cfg` は 1.0（turbo 系）のため、ネガティブプロンプト #35 は実質無効
