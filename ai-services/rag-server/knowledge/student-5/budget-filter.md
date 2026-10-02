# What happens when a customer sets a budget

When a customer sets a budget, the recommendation engine treats it as a hard filter. Shoes above that budget are excluded. They are not shown in the recommendation carousel.

If the customer says "shoes under 120", or sets a budget of 120 dollars, every recommended sneaker must cost 120 dollars or less. A product that costs more than the budget is removed before the picks are shown.

The chatbot does not ignore a budget. The ranked list is calculated in the backend, and the budget check happens there.
