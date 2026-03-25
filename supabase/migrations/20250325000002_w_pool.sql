-- W pool: the distribution of w, one slot per agent
CREATE TABLE w_pool (
  id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
  task_id TEXT REFERENCES tasks(id) NOT NULL,
  content TEXT DEFAULT '',
  slot_index INT NOT NULL,
  updated_at TIMESTAMPTZ DEFAULT now(),
  UNIQUE (task_id, slot_index)
);

ALTER TABLE w_pool ENABLE ROW LEVEL SECURITY;
CREATE POLICY "allow_all" ON w_pool FOR ALL USING (true) WITH CHECK (true);

-- Track which w_pool slot each proposal was compared against
ALTER TABLE proposals ADD COLUMN IF NOT EXISTS w_pool_slot INT;
