-- Fails if the newest order is more than 1 day older than the load reference time.
select m.max_ts, p.as_of
from (select max(order_ts) as max_ts from {{ ref('stg_orders') }}) as m
cross join (select as_of from {{ source('raw', 'pipeline_meta') }}) as p
where m.max_ts < p.as_of - interval 1 day
