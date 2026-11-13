# Conceptual model

Business entities and relationships, independent of any technology. Both datasets map onto the same
concepts. Where a dataset does not hold a concept, the mapping says so.

| Concept | Olist (Brazilian e-commerce) | UCI Online Retail | Meaning |
|---|---|---|---|
| Customer | customer (unique id) | CustomerID | A person who buys. Can be unknown in the retail data. |
| Order | order | Invoice | One purchase transaction. |
| Order item | order item | Invoice line | One product within an order, with quantity and price. |
| Product | product | StockCode | What is sold. |
| Seller | seller | not in dataset | The marketplace merchant that ships an item. |
| Payment | order payment | not in dataset | How an order was paid. |
| Review | order review | not in dataset | Customer feedback on an order. |
| Location | zip code prefix, city, state | Country (no zip) | Where a customer or seller is. |

## Relationships

- A **Customer** places zero or more **Orders**.
- An **Order** contains one or more **Order items**.
- Each **Order item** refers to one **Product** and is supplied by one **Seller** (Olist only).
- An **Order** is paid through one or more **Payments** (Olist only).
- An **Order** receives at most one **Review** (Olist only).
- A **Customer** and a **Seller** are each located in one **Location**.
