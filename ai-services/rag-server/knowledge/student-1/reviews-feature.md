# Reviews & Ratings Feature

The Reviews & Ratings feature is owned by Student 1. It lets customers review
products they have bought and lets staff manage those reviews.

Pages:
- / : staff page to search reviews by product ID and view an AI summary
- /submit : customer page to write a review, linked from order history
- /moderate : staff page listing flagged reviews
- /mcp : staff page for running MCP review tools

For each product, AI-Mode also generates a short natural-language summary of
all its reviews, which is shown on the staff search page.

The backend runs on port 5001 and the reviews database API on port 6001.