-- =========================================================
-- INTERNSHIELD SUPPORT INBOX + REPLIES UPGRADE
-- Run after the original public.support_requests table exists.
-- =========================================================

ALTER TABLE public.support_requests
ADD COLUMN IF NOT EXISTS user_email TEXT;

ALTER TABLE public.support_requests
ADD COLUMN IF NOT EXISTS user_name TEXT;

ALTER TABLE public.support_requests
ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ
NOT NULL DEFAULT NOW();


CREATE TABLE IF NOT EXISTS public.support_replies (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    request_id UUID NOT NULL
        REFERENCES public.support_requests(id)
        ON DELETE CASCADE,

    sender_type TEXT NOT NULL
        CHECK (
            sender_type IN (
                'user',
                'admin'
            )
        ),

    sender_email TEXT,

    message TEXT NOT NULL
        CHECK (
            char_length(message)
            BETWEEN 5 AND 3000
        ),

    created_at TIMESTAMPTZ NOT NULL
        DEFAULT NOW()
);


CREATE INDEX IF NOT EXISTS
support_replies_request_created_idx
ON public.support_replies (
    request_id,
    created_at
);


ALTER TABLE public.support_replies
ENABLE ROW LEVEL SECURITY;


DROP POLICY IF EXISTS
"Users can view replies for own support requests"
ON public.support_replies;

CREATE POLICY
"Users can view replies for own support requests"
ON public.support_replies
FOR SELECT
USING (
    EXISTS (
        SELECT 1
        FROM public.support_requests request_row
        WHERE
            request_row.id = request_id
            AND request_row.user_id = auth.uid()
    )
);


DROP POLICY IF EXISTS
"Users can add followups to own support requests"
ON public.support_replies;

CREATE POLICY
"Users can add followups to own support requests"
ON public.support_replies
FOR INSERT
WITH CHECK (
    sender_type = 'user'
    AND EXISTS (
        SELECT 1
        FROM public.support_requests request_row
        WHERE
            request_row.id = request_id
            AND request_row.user_id = auth.uid()
    )
);


GRANT USAGE
ON SCHEMA public
TO authenticated;

GRANT SELECT, INSERT
ON TABLE public.support_replies
TO authenticated;


CREATE INDEX IF NOT EXISTS
support_requests_status_updated_idx
ON public.support_requests (
    status,
    updated_at DESC
);

CREATE INDEX IF NOT EXISTS
support_requests_user_updated_idx
ON public.support_requests (
    user_id,
    updated_at DESC
);
