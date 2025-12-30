# Streamlit Based ComfyUI Web Tool

Streamlit で ComfyUI API + WebSocket サーバーを操作する簡易フロントエンドです。プロンプト・ネガティブプロンプト・シードのみユーザーが変更でき、その他のノード設計はワークフローテンプレート JSON で固定します。履歴はセッション間で保持され、リロード後も prompt_id を用いて結果を再取得します。

## セットアップ
1. Python 3.13 で仮想環境を作成し、有効化します。
2. 依存関係をインストールします。
   ```bash
   pip install -r requirements.txt
   ```
3. `.env.example` を `.env` にコピーし、環境変数を設定します。
  - `COMFYUI_BASE_URL` (例: http://localhost:8188)
  - `COMFYUI_WS_URL` (例: ws://localhost:8188/ws)
  - `WORKFLOW_JSON_PATH` (例: workflows/your_workflow.json)
  - `IMAGE_WIDTH` / `IMAGE_HEIGHT` (例: 512)
  - `MAX_ACTIVE_REQUESTS` (1セッション同時リクエスト数、例: 2)
  - `REQUEST_TIMEOUT_SECONDS` (例: 90)
  - `GLOBAL_MAX_ACTIVE_REQUESTS` (全体同時上限、例: 100。0 で無効)
  - `HISTORY_TTL_SECONDS` (履歴の保持期間、例: 86400)
  - `LOG_LEVEL` (TRACE/DEBUG/INFO など)
  - `DEBUG_MODE` (trueでサイドバーにAPI/WS URLを表示)
4. ワークフロー JSON を配置します。`workflows/example.json` はプレースホルダのみのサンプルなので、実運用用の ComfyUI ワークフローに差し替えてください。

## ワークフローテンプレートの書き方
ワークフロー JSON 内に以下のプレースホルダ文字列を含めると、実行時に入力値で置換します。
- `{{positive_prompt}}`
- `{{negative_prompt}}`
- `{{seed}}`
- `{{width}}`
- `{{height}}`

例:
```json
{
  "nodes": {
    "1": {
      "class_type": "KSampler",
      "inputs": {
        "seed": "{{seed}}",
        "width": "{{width}}",
        "height": "{{height}}"
      }
    },
    "2": {
      "class_type": "CLIPTextEncode",
      "inputs": {"text": "{{positive_prompt}}", "clip": ["3", 0]}
    },
    "4": {
      "class_type": "CLIPTextEncode",
      "inputs": {"text": "{{negative_prompt}}", "clip": ["3", 0]}
    }
  }
}
```

プレースホルダが1つも見つからない場合はエラーになります。必ず上記のいずれかを含めてください。

## 実行
```bash
streamlit run app.py
```

## ユーザー体験
- ライト/ダークテーマの切り替え
- プロンプト/ネガティブプロンプト入力、シードは -1 指定で 32bit ランダム、それ以外は指定値をそのまま使用
- 履歴はセッション間で保持され、prompt_id 付き running は自動で再取得（60秒ごとに自動リロード）
- 各出力画像にダウンロードボタンを表示
- 1セッションあたり同時リクエスト数を環境変数で制限 (デフォルト2件)。完了後は追加リクエスト可能
- システム全体の同時実行上限 (`GLOBAL_MAX_ACTIVE_REQUESTS`) を設定可能

## 注意
- ComfyUI 側の認証・公開範囲は別途ご確認ください。本ツールはエンドポイントをそのまま利用します。
- WebSocket/HTTP が長時間応答しない場合は `REQUEST_TIMEOUT_SECONDS` を調整してください。
- 履歴再取得は prompt_id が存在する running エントリを対象に行います。prompt_id を取得する前にリロードしたジョブは復旧されず、自動的に履歴から除去されます。
