-- Migration 004: User message feedback (positive/negative ratings + comments)
--
-- Enables users to submit 👍 or 👎 on generated assistant responses, creating
-- a quality dataset for prompt tuning and retrieval improvements.

ALTER TABLE public.messages
    ADD COLUMN IF NOT EXISTS feedback TEXT CHECK (feedback IN ('positive', 'negative')),
    ADD COLUMN IF NOT EXISTS feedback_comment TEXT,
    ADD COLUMN IF NOT EXISTS feedback_at TIMESTAMPTZ;

-- Index for analytics and feedback aggregation queries
CREATE INDEX IF NOT EXISTS idx_messages_feedback
    ON public.messages (feedback)
    WHERE feedback IS NOT NULL;
