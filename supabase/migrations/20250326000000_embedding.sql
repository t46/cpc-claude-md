-- Add embedding columns for W distribution visualization
ALTER TABLE w_pool ADD COLUMN IF NOT EXISTS embedding JSONB;
ALTER TABLE samples ADD COLUMN IF NOT EXISTS embedding JSONB;
