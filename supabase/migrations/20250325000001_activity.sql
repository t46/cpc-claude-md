-- Live activity log for real-time dashboard
CREATE TABLE activity (
  id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
  agent_id TEXT NOT NULL,
  task_id TEXT NOT NULL,
  activity_type TEXT NOT NULL,
  detail TEXT DEFAULT '',
  created_at TIMESTAMPTZ DEFAULT now()
);

ALTER TABLE activity ENABLE ROW LEVEL SECURITY;
CREATE POLICY "allow_all" ON activity FOR ALL USING (true) WITH CHECK (true);
