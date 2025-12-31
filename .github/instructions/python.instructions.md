---
applyTo: "**/*.py"
---

# Python 固有ルール

## 基本方針
- Python 3.13以上を対象とすること
- PEP8準拠の確認
- 型ヒントの活用（引数、戻り値、変数）
- f-stringの使用推奨 (古いformat方法からの移行)
- リスト内包表記の活用
- 例外処理の適切な実装

## 非同期処理
- httpx[http2] ライブラリを使用して非同期HTTPクエストを行うこと
- Async/Awaitの適切な使用
- asyncio.run()でイベントループを管理

## Streamlit固有
- **Fragment API**: 部分的な自動更新が必要な場合は`@st.fragment(run_every="Xs")`を使用
- **session_state**:
  - 一時的なデータはsession_stateのみで管理
  - 永続化が必要なデータのみLocalStorageを使用
  - リロード時の初期化戦略を明確に
- **キャッシュ**:
  - `@st.cache_data`: データのキャッシュ（関数の戻り値）
  - `@st.cache_resource`: リソースのキャッシュ（DB接続、グローバル状態等）
  - show_spinner=Falseで不要なスピナーを非表示

## データ管理
- **dataclass**: 設定やデータ構造の定義に使用（frozen=Trueで不変性を担保）
- **ULID**: 一意なID生成にはULIDを使用（タイムスタンプ+ランダム性）
- **タイムスタンプ**:
  - UNIXタイムスタンプ（int）で保存・管理
  - `int(time.time())`で現在時刻を取得
  - TTL処理などに活用

## 環境変数・設定管理
- python-dotenvで.envファイルから環境変数を読み込み
- デフォルト値をFinalで定義
- 型変換と検証を確実に行う
- os.getenv()の第2引数でデフォルト値を指定

## LocalStorage連携
- streamlit-js-evalを使用してブラウザのLocalStorageと連携
- JavaScriptの実行結果は初回レンダリング時にNoneを返す可能性があるため、再試行処理を実装
- カウンターを使ってキャッシュバイパスを実現

## セキュリティ
- ユーザー入力は必ずバリデーション
- 許可リスト方式での検証を推奨
- エラーメッセージから機密情報（URL、パス等）を除外
- 型チェックと範囲チェックを確実に実行
