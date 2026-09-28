from ollama_client import ask

TEST_COMMENT = "Great quality, fast shipping!"

PROMPT = (
    "Rate the sentiment of this product review from -1 (very negative) "
    "to 1 (very positive). Reply with only the number.\n\nReview: {comment}"
)

STRICT_PROMPT = (
    "Reply with ONE number between -1 and 1 and nothing else. "
    "No words, no explanation.\n\nReview: {comment}"
)


def _parse_score(reply):
    try:
        score = float(reply)
        return score if -1 <= score <= 1 else None
    except (TypeError, ValueError):
        return None


def run(stage):
    stage("PLAN", f"Test AI-Mode sentiment scoring on: '{TEST_COMMENT}'")

    stage("ACT", "Calling Ollama")
    reply, error = ask(PROMPT.format(comment=TEST_COMMENT))

    stage("OBSERVE", f"Reply: {reply!r}" if not error else f"Error: {error}")
    score = _parse_score(reply)

    if score is None:
        stage("ADAPT", "Reply was not a valid score, retrying with a stricter prompt")
        reply, error = ask(STRICT_PROMPT.format(comment=TEST_COMMENT))
        stage("OBSERVE", f"Retry reply: {reply!r}" if not error else f"Error: {error}")
        score = _parse_score(reply)

    passed = score is not None and score > 0
    result = "PASS" if passed else "FAIL"
    stage("ADAPT", f"{result}: score={score} (expected a positive number between -1 and 1)")
    return passed