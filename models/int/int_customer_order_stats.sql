with orders as (
    select * from {{ ref('stg_orders') }}
),

completed as (
    select *
    from orders
    where status = 'completed'
),

per_customer as (
    select
        customer_id,
        count(*)                  as completed_order_count,
        sum(amount_cents)         as lifetime_amount_cents,
        min(order_date)           as first_completed_order_date,
        max(order_date)           as last_completed_order_date
    from completed
    group by 1
)

select * from per_customer
