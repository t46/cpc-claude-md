-- Add agent_specializations to tasks
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS agent_specializations JSONB DEFAULT '[]';
