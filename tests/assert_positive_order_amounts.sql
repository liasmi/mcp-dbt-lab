-- Fails if any order amount is zero or negative
select order_id, amount_usd
from {{ ref('fct_orders') }}
where amount_usd <= 0
