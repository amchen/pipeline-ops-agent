select
    cast(o.order_ts as date) as order_date,
    c.region,
    count(*) as orders,
    sum(o.amount) as revenue
from {{ ref('stg_orders') }} as o
left join {{ ref('stg_customers') }} as c using (customer_id)
where o.status = 'completed'
group by 1, 2
