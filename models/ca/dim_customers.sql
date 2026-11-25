with customers as (
    select * from {{ ref('stg_customers') }}
),

stats as (
    select * from {{ ref('int_customer_order_stats') }}
),

countries as (
    select * from {{ ref('country_codes') }}
),

final as (
    select
        c.customer_id,
        c.customer_name,
        c.signup_date,
        co.country_name,
        coalesce(s.completed_order_count, 0)      as completed_order_count,
        {{ cents_to_dollars('coalesce(s.lifetime_amount_cents, 0)') }}
                                                  as lifetime_amount_usd
    from customers c
    left join stats s on c.customer_id = s.customer_id
    left join countries co on c.country_code = co.country_code
)

select * from final
