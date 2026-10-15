select
    order_id,
    customer_id,
    cast(order_ts as timestamp) as order_ts,
    cast(amount as decimal(12, 2)) as amount,
    lower(status) as status
from {{ source('raw', 'orders') }}
