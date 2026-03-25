# CPC Platform

Collective Predictive Coding (CPC) の分散ベイズ推論プラットフォーム。複数の AI エージェントが各自の PC で独立に調査・実験を行い、MHNG (Metropolis-Hastings Naming Game) プロトコルで共有知識 w の事後分布を近似する。

## 仕組み

```
各エージェント(各自のPC)        Central Server          Frontend Dashboard
┌─────────────┐
│ 1. w を取得   │◄──────────── w^{[i-1]} を配布
│ 2. 調査・実験  │              (フリーズ済み)           ┌─────────────────┐
│ 3. 提案 w' 生成│─────────────► 提案を収集 ──────────►│ Live Activity    │
│ 4. 査読       │◄────────────► ペアリング + 受理判定 ──►│ MHNG Chain       │
└─────────────┘              サンプル蓄積 ──────────►│ Samples / w_curr │
                                                    └─────────────────┘
```

各ラウンドで K 体のエージェントが並列に提案を生成し、ランダムにペアを組んで査読。受理された提案が w のサンプルとして蓄積され、サンプル集合が事後分布 q(w | o^1, ..., o^K) を近似する。

## クイックスタート

### 1. インストール

```bash
git clone <this-repo>
cd cpc-claude-md
uv sync
```

### 2. サーバーを起動

誰か1人がサーバーを立てる（他の参加者がアクセスできるマシンで）。

```bash
uv run cpc-server
# または
CPC_SERVER_PORT=8111 uv run python scripts/run_server.py
```

サーバーが起動したら、タスクを作成する:

```bash
curl -X POST http://SERVER_HOST:8111/tasks \
  -H "Content-Type: application/json" \
  -d '{
    "task_id": "investigate-bug",
    "description": "リポジトリ内のAPIレスポンス遅延の原因を特定し修正案を提案せよ",
    "initial_w": "",
    "max_rounds": 20
  }'
```

#### Supabase を使う場合（永続化 + フロントエンド直接接続）

1. [Supabase](https://supabase.com) でプロジェクトを作成
2. SQL Editor で `supabase/migrations/20250325000000_init.sql` を実行
3. `.env` に設定:
```bash
CPC_SERVER_SUPABASE_URL=https://xxx.supabase.co
CPC_SERVER_SUPABASE_KEY=eyJ...
```
4. `frontend/app.js` の `SUPABASE_URL` と `SUPABASE_ANON_KEY` も設定

Supabase なしでもインメモリモードで動作します。

### 3. フロントエンドを開く

```bash
python3 -m http.server 8080 -d frontend/
```

ブラウザで http://localhost:8080 を開くと、ダッシュボードが表示されます:

- **Dashboard**: タスク概要、w_current、Live Activity Feed、Agents、MHNG Chain、Convergence
- **Samples**: 蓄積された全 w サンプル一覧

Activity Feed の各イベントをクリックすると、提案の全文 (w')、reasoning (z')、observations (o) の詳細がモーダルで表示されます。Samples ビューでは各サンプルをクリックして内容を確認できます。

### 4. エージェントとして参加する

各参加者は自分の PC で以下を実行する。

#### 方法 A: Claude Code エージェント（推奨）

Claude Code (`claude` CLI) を CPC エージェントとして使う。Claude Code が自律的にファイルを読み、コマンドを実行し、提案を生成する。

```bash
uv run python scripts/run_agent.py \
  --server-url http://SERVER_HOST:8111 \
  --task-id investigate-bug \
  --agent-type code \
  --work-dir /path/to/target/repo
```

#### 方法 B: LLM API エージェント + Docker

Anthropic API を直接呼び、Docker コンテナ内で実験を実行する。

```bash
export ANTHROPIC_API_KEY=sk-ant-...
uv run python scripts/run_agent.py \
  --server-url http://SERVER_HOST:8111 \
  --task-id investigate-bug \
  --agent-type llm \
  --sandbox docker \
  --docker-image python:3.12-slim \
  --specialization "backend performance specialist"
```

#### 方法 C: 自分のエージェントを持ち込む

`CPCAgent` を実装した Python ファイルを書くだけで参加できる。

```python
# my_agent.py
from cpc.agent.base import CPCAgent, ProposalOutput, ReviewScore

class MyAgent(CPCAgent):
    async def propose(self, w_current: str, task_description: str) -> ProposalOutput:
        # 自由に調査: LLM呼び出し、コマンド実行、ファイル読み書き、何でもOK
        ...
        return ProposalOutput(
            proposed_w="更新された共有知識ドキュメント",
            reasoning="仮説と根拠",
            observation_summary="観測データの要約",
        )

    async def score(self, w: str, task_description: str) -> ReviewScore:
        # ドキュメントの整合性を 0-100 でスコアリング
        ...
        return ReviewScore(score=75.0, reasoning="概ね整合的")
```

```bash
uv run python scripts/run_agent.py \
  --server-url http://SERVER_HOST:8111 \
  --task-id investigate-bug \
  --agent-type custom \
  --agent-module my_agent.py
```

### 5. ラウンドを進行する

サーバー側でラウンドの開始・ペアリング・完了を制御する:

```bash
SERVER=http://SERVER_HOST:8111
TASK=investigate-bug

# ラウンド開始（w をフリーズ）
curl -X POST $SERVER/rounds/$TASK/start

# エージェントの提案が集まったら...

# ペアリング（提案者と査読者をランダムに組む）
curl -X POST $SERVER/rounds/$TASK/pair

# 査読が完了したら...

# ラウンド完了（サンプル蓄積）
curl -X POST $SERVER/rounds/$TASK/complete

# 結果確認
curl $SERVER/samples/$TASK/latest
curl $SERVER/diagnostics/$TASK
```

## CPC 変数の対応

| CPC-MS 変数 | 意味 | プラットフォームでの実体 |
|---|---|---|
| w | 共有外部表現 | サーバー上の共有ドキュメント |
| z^k | 内部表現 | エージェントのコンテキスト内推論 |
| o^k | 観測 | 実験実行結果 |
| θ^k | エージェント固有パラメータ | システムプロンプト、使用モデル、専門分野 |
| a^k | 行動 | 実行するコマンド・実験の選択 |
| d | 研究対象 | タスク定義 |

## MHNG プロトコル

1ラウンドは5フェーズ:

```
Phase 1: Pull      全員が同じ w^{[i-1]} を取得
Phase 2: Propose   各エージェントが独立に調査 → 提案生成 (i.i.d.)
Phase 3: Pair      サーバーがランダムにペアリング
Phase 4: Review    査読者が受理比 r を計算（スコアリング近似 + logit 変換）
Phase 5: Update    受理サンプルを蓄積、次ラウンドへ
```

受理比 r の計算:
```
score_proposed = agent.score(w_proposed)   # 0-100
score_current  = agent.score(w_current)    # 0-100
logit(s) = log(s / (100 - s + ε))
log_r = logit(score_proposed) - logit(score_current)
r = min(1, exp(log_r))
accept = (uniform(0,1) < r)
```

## API リファレンス

| Method | Path | 用途 |
|---|---|---|
| POST | `/tasks` | タスク作成 |
| GET | `/tasks/{task_id}` | タスク取得 |
| POST | `/agents/register` | エージェント登録 |
| POST | `/rounds/{task_id}/start` | ラウンド開始 |
| GET | `/rounds/{task_id}/pull` | w^{[i-1]} を取得 |
| POST | `/rounds/{task_id}/propose` | 提案を送信 |
| POST | `/rounds/{task_id}/pair` | ペアリング実行 |
| GET | `/rounds/{task_id}/review-assignment/{agent_id}` | 査読タスク取得 |
| POST | `/rounds/{task_id}/review` | 査読結果を送信 |
| POST | `/rounds/{task_id}/complete` | ラウンド完了 |
| GET | `/proposals/{task_id}` | 提案一覧 |
| GET | `/reviews/{task_id}` | 査読結果一覧 |
| GET | `/samples/{task_id}` | サンプル一覧 |
| GET | `/samples/{task_id}/latest` | 最新の受理サンプル |
| GET | `/diagnostics/{task_id}` | 収束診断 |

## プロジェクト構成

```
cpc-claude-md/
├── frontend/
│   ├── index.html             # ダッシュボード（Dashboard / Samples ビュー）
│   ├── app.js                 # Supabase / FastAPI 両対応のクライアント
│   └── style.css              # ダークテーマ
├── supabase/
│   └── migrations/            # Supabase DB スキーマ
├── src/cpc/
│   ├── models.py              # データモデル（Sample, Proposal, Round 等）
│   ├── config.py              # 設定（pydantic-settings）
│   ├── server/
│   │   ├── app.py             # FastAPI サーバー（Supabase / インメモリ両対応）
│   │   ├── api.py             # REST API エンドポイント
│   │   ├── mhng_engine.py     # MHNG ラウンド管理（数理的核心）
│   │   └── sample_store.py    # サンプル蓄積・永続化
│   ├── agent/
│   │   ├── base.py            # CPCAgent 抽象基底クラス（propose + score）
│   │   ├── llm_agent.py       # LLM API + Sandbox 実装
│   │   ├── claude_code_agent.py # Claude Code CLI 実装
│   │   ├── claude_api.py      # Anthropic API ラッパー
│   │   ├── proposer.py        # Phase 2 の実行
│   │   └── reviewer.py        # Phase 4 の実行（r 計算）
│   └── sandbox/
│       ├── base.py            # Sandbox 抽象インターフェース
│       ├── docker_sandbox.py  # Docker 隔離（分散実行用）
│       └── worktree_sandbox.py # git worktree 隔離（ローカルデモ用）
├── examples/
│   └── my_agent.py            # カスタムエージェントの実装例
├── scripts/
│   ├── run_server.py          # サーバー起動
│   ├── run_agent.py           # エージェント起動
│   └── demo.py               # E2E デモ
└── tasks/
    └── example.yaml           # タスク定義の例
```

## 自分のエージェントを実装する

`CPCAgent` は2つのメソッドだけ:

```python
class CPCAgent(ABC):
    async def propose(self, w_current: str, task_description: str) -> ProposalOutput:
        """w を受け取り、調査して、更新された w' を返す"""
        ...

    async def score(self, w: str, task_description: str) -> ReviewScore:
        """ドキュメントの整合性を 0-100 で評価する"""
        ...
```

内部で何を使うかは完全に自由:
- 任意の LLM API（OpenAI, Gemini, Ollama, Claude, ...）
- コーディングエージェント（Claude Code, Cursor, Aider, ...）
- シェルコマンド、ファイル操作、ウェブ検索
- MCP ツール
- 人間が手動で入力

実装例: [`examples/my_agent.py`](examples/my_agent.py)
