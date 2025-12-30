# セッション管理リファクタリング

## 概要

`st.session_state`周りの処理をLocalStorageベースのアーキテクチャに整理しました。

## 主な変更点

### 1. **LocalStorageベースの永続化**
- サーバー側のキャッシュ（`_history_store`）を削除
- ブラウザのLocalStorageを使用してデータを永続化
- 画像データはbase64エンコードしてLocalStorageに保存

### 2. **新規モジュール**

#### `app/storage.py` - LocalStorage連携ユーティリティ
- `LocalStorageManager`: LocalStorageとのデータ連携を管理
  - `get(name, default)`: LocalStorageから値を取得
  - `set(name, value)`: LocalStorageに値を保存
  - `remove(name)`: LocalStorageから値を削除
  - `encode_image(bytes)`: 画像データをbase64エンコード
  - `decode_image(str)`: base64データをデコード

#### `app/session.py` - セッション状態管理
- `SessionManager`: セッションのライフサイクルを制御
  - `get_client_id()`: ブラウザ固定のクライアントID取得
  - `initialize()`: セッション状態の初期化
  - `sync_from_local_storage()`: LocalStorageから読み込み
  - `sync_to_local_storage()`: LocalStorageに保存
  - `clear_local_storage()`: LocalStorageをクリア

### 3. **データ管理の変更**

#### ジョブキュー (`jobs`)
- **以前**: `st.session_state`のみに保存（リロードで消失）
- **現在**: LocalStorageに永続化（リロード後も保持）

#### 履歴 (`history`)
- **以前**: サーバー側キャッシュ（TTL: 10分）
- **現在**: LocalStorageに永続化（ブラウザが保持する限り永続）

#### 画像データ
- **以前**: バイトデータのまま保存
- **現在**: base64エンコードしてテキスト形式で保存

### 4. **セッションID（client_id）**
- ブラウザ単位で固定（同じブラウザの複数タブは同じID）
- LocalStorageに保存（ブラウザを閉じても維持）
- ULID形式で生成

### 5. **マルチタブ対応**
- 同じブラウザで複数タブを開いた場合、1ユーザーとしてカウント
- 同時リクエスト制限はブラウザ（client_id）単位で適用

## 使用方法

### アプリケーション起動時
```python
def main():
    # セッション初期化
    session_manager.initialize()
    session_manager.sync_from_local_storage()
    
    # ... アプリケーション処理 ...
```

### 履歴の保存と読み込み
```python
# 履歴を取得
history = _get_history()

# 履歴に追加
_append_history({
    "positive_prompt": "...",
    "negative_prompt": "...",
    "seed": 12345,
    "images": [storage_manager.encode_image(img_bytes)],
    "prompt_id": "...",
    "status": "success",
})

# 履歴を更新
_upsert_history(job_id, {"status": "running"})
```

### ジョブキューの管理
```python
# ジョブを追加
_add_job({
    "id": str(ULID()),
    "status": "queued",
    "positive_prompt": "...",
    "negative_prompt": "...",
    "seed": 12345,
})

# ジョブを更新
_update_job(job_id, status="running")

# ジョブを削除
_remove_job(job_id)
```

### LocalStorageのクリア
```python
# デバッグやテスト用
session_manager.clear_local_storage()
```

## LocalStorageの制限

### 容量制限
- 一般的なブラウザ: 5〜10MB
- 画像サイズと履歴数に注意が必要

### 推奨事項
- 大きな画像を大量に保存する場合は、古い履歴を定期的にクリア
- 必要に応じて履歴の最大件数を制限する機能を追加検討

## トラブルシューティング

### LocalStorageが保存されない
1. ブラウザのプライベートモード/シークレットモードを使用していないか確認
2. ブラウザの設定でCookieやStorageが無効になっていないか確認
3. ブラウザのコンソールでエラーを確認

### 画像が表示されない
1. LocalStorageの容量制限に達していないか確認
2. base64エンコード/デコードが正しく行われているか確認

### 複数タブで同期されない
- 現在の実装では、タブ間でのリアルタイム同期は未対応
- 各タブでページをリロードすることでLocalStorageから最新データを読み込み

## 今後の改善案

1. **履歴の自動クリーンアップ**
   - 古い履歴を自動削除する機能
   - LocalStorageの容量管理

2. **タブ間同期**
   - `storage`イベントを使用したタブ間リアルタイム同期

3. **圧縮**
   - 画像データの圧縮オプション
   - 履歴データの圧縮

4. **エクスポート/インポート**
   - 履歴データのエクスポート/インポート機能
   - バックアップ機能
