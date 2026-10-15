select
    customer_id,
    name,
    region,
    signup_date
from {{ source('raw', 'customers') }}
