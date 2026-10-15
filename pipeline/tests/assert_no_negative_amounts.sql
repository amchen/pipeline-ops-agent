-- Fails (returns rows) if any order has a negative amount.
select order_id, amount
from {{ ref('stg_orders') }}
where amount < 0
