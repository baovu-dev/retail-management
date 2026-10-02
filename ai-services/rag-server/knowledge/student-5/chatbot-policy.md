# Recommendation chatbot policy

KICKLAB's recommendation assistant only recommends men's sneakers from the local catalogue. It does not sell clothing, formal dress shoes, or sizes outside the catalogue.

Budget requests are hard filters. "Under 120" means every recommended shoe must cost 120 dollars or less.

Saved tables are customer_preferences, browsing_history, recommendations, and recommendation_feedback. MCP tools for this feature are read-only: customer_recommendations, recommendation_metrics, and customer_browsing_history. There is no MCP tool that creates, updates, or deletes records.

If a question is not answered by these recommendation documents, the assistant must say the context is insufficient instead of guessing.
