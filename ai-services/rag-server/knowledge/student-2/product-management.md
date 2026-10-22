#KICKLAB Product Management

The Product Management feature is owned by Student 2. It allows staff to manage the KICKLAB product catalogue.

Staff can create, view, update, and delete products.

Each product contains:
- product_id
- name
- category
- description
- price 
- brand
- status

The Product Management frontend runs on port 3002.
The Product Management backend runs on port 5002.
The Product database API runs on port 6002.

# Product AI Description Generation

Product Management includes an AI description generation feature using Ollama with the llama3.1:8b model.

The AI generates a short product description using the stored product name, category, brand, and price.

The prompt instructs the AI to use only the provided product information and not invent specifications or features.

The generated description is returned to the frontend and is not automatically saved to the product database.

# Shared MCP Integration 

The shared MCP service can retrieve product information using a product ID.

The Product Management backend accesses the shared MCP service rather tahn calling the MCP tool directly from the frontend.