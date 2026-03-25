-- CPC Platform: Database Schema
-- Implements the data model for distributed Bayesian inference via MHNG

-- Tasks (d: research targets)
CREATE TABLE tasks (
  id TEXT PRIMARY KEY,
  description TEXT NOT NULL,
  initial_w TEXT DEFAULT '',
  data_dir TEXT DEFAULT '',
  docker_image TEXT DEFAULT 'python:3.12-slim',
  max_rounds INT DEFAULT 100,
  convergence_threshold FLOAT DEFAULT 0.05,
  created_at TIMESTAMPTZ DEFAULT now()
);

-- Agents (θ^k: agent-specific parameters)
CREATE TABLE agents (
  id TEXT PRIMARY KEY,
  specialization TEXT DEFAULT '',
  system_prompt_hash TEXT DEFAULT '',
  registered_at TIMESTAMPTZ DEFAULT now(),
  last_seen TIMESTAMPTZ
);

-- Rounds (MHNG round state)
CREATE TABLE rounds (
  id SERIAL PRIMARY KEY,
  task_id TEXT REFERENCES tasks(id) NOT NULL,
  round_index INT NOT NULL,
  phase TEXT CHECK (phase IN ('propose','review','completed')) DEFAULT 'propose',
  frozen_w TEXT DEFAULT '',
  started_at TIMESTAMPTZ DEFAULT now(),
  completed_at TIMESTAMPTZ,
  UNIQUE (task_id, round_index)
);

-- Proposals (w': proposed updates to shared knowledge)
CREATE TABLE proposals (
  id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
  agent_id TEXT REFERENCES agents(id) NOT NULL,
  task_id TEXT REFERENCES tasks(id) NOT NULL,
  round_index INT NOT NULL,
  current_w TEXT DEFAULT '',
  proposed_w TEXT NOT NULL,
  observation_summary TEXT DEFAULT '',
  reasoning TEXT DEFAULT '',
  created_at TIMESTAMPTZ DEFAULT now()
);

-- Pairings (proposer-reviewer pairs per round)
CREATE TABLE pairings (
  id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
  task_id TEXT REFERENCES tasks(id) NOT NULL,
  round_index INT NOT NULL,
  proposer_id TEXT REFERENCES agents(id) NOT NULL,
  reviewer_id TEXT REFERENCES agents(id) NOT NULL,
  proposal_id TEXT REFERENCES proposals(id),
  created_at TIMESTAMPTZ DEFAULT now()
);

-- Reviews (MH acceptance decisions)
CREATE TABLE reviews (
  id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
  proposal_id TEXT REFERENCES proposals(id) NOT NULL,
  reviewer_id TEXT REFERENCES agents(id) NOT NULL,
  task_id TEXT REFERENCES tasks(id) NOT NULL,
  round_index INT NOT NULL,
  accepted BOOLEAN NOT NULL,
  score_proposed FLOAT DEFAULT 0,
  score_current FLOAT DEFAULT 0,
  log_alpha FLOAT DEFAULT 0,
  reasoning TEXT DEFAULT '',
  created_at TIMESTAMPTZ DEFAULT now()
);

-- Samples (w^[i]: Monte Carlo samples of the posterior q(w|o^1,...,o^K))
CREATE TABLE samples (
  id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
  task_id TEXT REFERENCES tasks(id) NOT NULL,
  content TEXT NOT NULL,
  round_index INT NOT NULL,
  proposer_id TEXT DEFAULT '',
  reviewer_id TEXT DEFAULT '',
  accepted BOOLEAN DEFAULT false,
  acceptance_score FLOAT DEFAULT 0,
  created_at TIMESTAMPTZ DEFAULT now()
);

-- Row Level Security: permissive for camp setting
ALTER TABLE tasks ENABLE ROW LEVEL SECURITY;
ALTER TABLE agents ENABLE ROW LEVEL SECURITY;
ALTER TABLE rounds ENABLE ROW LEVEL SECURITY;
ALTER TABLE proposals ENABLE ROW LEVEL SECURITY;
ALTER TABLE pairings ENABLE ROW LEVEL SECURITY;
ALTER TABLE reviews ENABLE ROW LEVEL SECURITY;
ALTER TABLE samples ENABLE ROW LEVEL SECURITY;

CREATE POLICY "allow_all" ON tasks FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "allow_all" ON agents FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "allow_all" ON rounds FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "allow_all" ON proposals FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "allow_all" ON pairings FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "allow_all" ON reviews FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "allow_all" ON samples FOR ALL USING (true) WITH CHECK (true);
