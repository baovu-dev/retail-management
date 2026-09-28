# Review Sentiment Scoring

Every new review comment is scored for sentiment by AI-Mode, which uses Ollama
running llama3.1:8b. The score ranges from -1 (very negative) to 1 (very positive).

A review is automatically flagged for moderation when its sentiment score is
below -0.8. Flagged reviews stay visible to staff on the /moderate page.

If a comment is empty, it is given a neutral score of 0.0. If the AI call fails,
the review is also given 0.0 so that submission never breaks.

The sentiment prompt is stored as a separate text file so it can be tuned
without changing code.